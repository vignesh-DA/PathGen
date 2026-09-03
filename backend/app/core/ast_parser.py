"""
Module 1 — AST Parser
=====================
Wraps pycparser to parse C source code into an AST and extract
structural information about conditional/branching constructs.

Key decisions:
- We use pycparser's CParser directly (no temp files) via a "fake_libc" header trick
  so stdlib types like int, void are recognized without a real compiler.
- We inject a minimal fake_libc preamble inline so the user doesn't need gcc installed.
- Supported constructs: if/if-else, while, for, do-while, switch/case.
"""

from __future__ import annotations

import re
import textwrap
from dataclasses import dataclass, field
from typing import Any

import pycparser
from pycparser import c_ast, c_generator
from pycparser.c_parser import ParseError as CParsError


# ---------------------------------------------------------------------------
# Fake libc preamble — makes pycparser accept common C idioms without gcc
# ---------------------------------------------------------------------------
_FAKE_LIBC_PREAMBLE = textwrap.dedent("""
    typedef int size_t;
    typedef int ssize_t;
    typedef unsigned int uint32_t;
    typedef long long int64_t;
    typedef unsigned long long uint64_t;
    typedef int bool;
    typedef void *_void_ptr;
    enum { false = 0, true = 1 };
    int printf(const char *fmt, ...);
    int scanf(const char *fmt, ...);
    int strlen(const char *s);
    void *malloc(size_t size);
    void free(void *ptr);
""")


@dataclass
class ConditionInfo:
    """Represents a single branching condition extracted from the AST."""
    condition_id: str          # e.g. "C1", "C2"
    expr_str: str              # verbatim condition string, e.g. "age >= 18"
    variables: list[str]       # variable names involved, e.g. ["age"]
    inferred_types: dict[str, str]  # var -> "int"/"float"/"char" where known
    source_line: int | None
    source_col: int | None
    ast_node_type: str         # "If", "While", "For", "Switch"
    operator: str | None       # "<", "<=", ">", ">=", "==", "!=" or None for complex


@dataclass
class ParseResult:
    """Result of parsing a source string (language-agnostic structure)."""
    ast: c_ast.FileAST
    conditions: list[ConditionInfo]
    source_code: str
    parse_errors: list[str] = field(default_factory=list)
    unsupported_constructs: list[str] = field(default_factory=list)
    language: str = "c"  # "c" | "python" | "javascript" | "typescript"


# ---------------------------------------------------------------------------
# Condition expression → string helper
# ---------------------------------------------------------------------------
_generator = c_generator.CGenerator()


def _expr_to_str(node: c_ast.Node) -> str:
    """Convert any AST expression node to its C source representation."""
    try:
        return _generator.visit(node)
    except Exception:
        return "<complex-expr>"


def _extract_variables(node: c_ast.Node) -> list[str]:
    """Recursively collect all ID (variable) names from an expression node."""
    names: list[str] = []

    class _IDCollector(c_ast.NodeVisitor):
        def visit_ID(self, node):  # noqa: N802
            names.append(node.name)

    _IDCollector().visit(node)
    return list(dict.fromkeys(names))  # deduplicate, preserve order


def _extract_operator(node: c_ast.Node) -> str | None:
    """If the top-level expression is a BinaryOp, return its operator."""
    if isinstance(node, c_ast.BinaryOp):
        return node.op
    return None


def _get_line(node: c_ast.Node) -> int | None:
    try:
        return node.coord.line if node.coord else None
    except AttributeError:
        return None


def _get_col(node: c_ast.Node) -> int | None:
    try:
        return node.coord.column if node.coord else None
    except AttributeError:
        return None


# ---------------------------------------------------------------------------
# Variable type inference from declarations
# ---------------------------------------------------------------------------

def _infer_type_str(decl_type: c_ast.Node) -> str:
    """Walk a declaration's type subtree and return a simplified type string."""
    if isinstance(decl_type, c_ast.TypeDecl):
        return _infer_type_str(decl_type.type)
    if isinstance(decl_type, c_ast.IdentifierType):
        names = decl_type.names
        if "float" in names or "double" in names:
            return "float"
        if "char" in names:
            return "char"
        return "int"
    if isinstance(decl_type, c_ast.PtrDecl):
        return "pointer"
    if isinstance(decl_type, c_ast.ArrayDecl):
        return "array"
    return "unknown"


class _TypeInferenceVisitor(c_ast.NodeVisitor):
    """Collects variable → type mappings from declarations in the AST."""

    def __init__(self):
        self.var_types: dict[str, str] = {}

    def visit_Decl(self, node):  # noqa: N802
        if node.name and node.type:
            self.var_types[node.name] = _infer_type_str(node.type)
        self.generic_visit(node)


# ---------------------------------------------------------------------------
# Condition extractor visitor
# ---------------------------------------------------------------------------

class _ConditionExtractor(c_ast.NodeVisitor):
    """Walks the AST and extracts all branching conditions."""

    def __init__(self, var_types: dict[str, str]):
        self._var_types = var_types
        self._conditions: list[ConditionInfo] = []
        self._counter = 0
        self._unsupported: list[str] = []

    def _next_id(self) -> str:
        self._counter += 1
        return f"C{self._counter}"

    def _make_condition(self, cond_node: c_ast.Node, node_type: str) -> ConditionInfo:
        expr_str = _expr_to_str(cond_node)
        variables = _extract_variables(cond_node)
        operator = _extract_operator(cond_node)
        inferred = {v: self._var_types.get(v, "int") for v in variables}
        return ConditionInfo(
            condition_id=self._next_id(),
            expr_str=expr_str,
            variables=variables,
            inferred_types=inferred,
            source_line=_get_line(cond_node),
            source_col=_get_col(cond_node),
            ast_node_type=node_type,
            operator=operator,
        )

    def visit_If(self, node):  # noqa: N802
        if node.cond:
            self._conditions.append(self._make_condition(node.cond, "If"))
        self.generic_visit(node)

    def visit_While(self, node):  # noqa: N802
        if node.cond:
            self._conditions.append(self._make_condition(node.cond, "While"))
        self.generic_visit(node)

    def visit_For(self, node):  # noqa: N802
        if node.cond:
            self._conditions.append(self._make_condition(node.cond, "For"))
        self.generic_visit(node)

    def visit_DoWhile(self, node):  # noqa: N802
        if node.cond:
            self._conditions.append(self._make_condition(node.cond, "DoWhile"))
        self.generic_visit(node)

    def visit_Switch(self, node):  # noqa: N802
        if node.cond:
            # Switch conditions are the switch expression itself
            self._conditions.append(self._make_condition(node.cond, "Switch"))
        self.generic_visit(node)

    @property
    def conditions(self) -> list[ConditionInfo]:
        return self._conditions

    @property
    def unsupported(self) -> list[str]:
        return self._unsupported


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_c_source(source_code: str) -> ParseResult:
    """
    Parse a C source string and extract AST + conditions.

    Args:
        source_code: Raw C source (string). May or may not have #includes.

    Returns:
        ParseResult with .ast, .conditions, .parse_errors, .unsupported_constructs
    """
    # pycparser does NOT support:
    #   1. Preprocessor directives (#include, #define, #pragma, ...)
    #   2. C comments (/* */ or //)
    # Strip both before parsing.
    import re as _re

    # Remove block comments  /* ... */  (non-greedy, DOTALL so it spans lines)
    stripped = _re.sub(r'/\*.*?\*/', '', source_code, flags=_re.DOTALL)
    # Remove line comments  // ...
    stripped = _re.sub(r'//[^\n]*', '', stripped)
    # Remove preprocessor directives (lines starting with optional whitespace + #)
    stripped = _re.sub(r'^\s*#[^\n]*', '', stripped, flags=_re.MULTILINE)

    # Prepend fake libc so pycparser can handle common types/functions
    augmented_source = _FAKE_LIBC_PREAMBLE + "\n" + stripped

    parser = pycparser.CParser()
    parse_errors: list[str] = []
    ast: c_ast.FileAST | None = None

    try:
        ast = parser.parse(augmented_source, filename="<input>")
    except CParsError as exc:
        # Try to give a meaningful error message
        parse_errors.append(str(exc))
        # Return a minimal result so the caller can surface the error
        return ParseResult(
            ast=None,  # type: ignore[arg-type]
            conditions=[],
            source_code=source_code,
            parse_errors=parse_errors,
        )

    # Infer variable types from declarations
    type_visitor = _TypeInferenceVisitor()
    type_visitor.visit(ast)

    # Extract conditions
    extractor = _ConditionExtractor(type_visitor.var_types)
    extractor.visit(ast)

    return ParseResult(
        ast=ast,
        conditions=extractor.conditions,
        source_code=source_code,
        parse_errors=parse_errors,
        unsupported_constructs=extractor.unsupported,
    )
