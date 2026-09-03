"""
Module — Python AST Parser
==========================
Parses Python source code into a unified intermediate representation
that the CFG builder can consume. Uses Python's built-in `ast` module.

Supported constructs:
- if/elif/else
- for, while, break, continue
- try/except/finally
- with statements
- function definitions
- assignments and expressions

Output: Same ConditionInfo + ParseResult structure as the C parser,
enabling the rest of the pipeline (CFG, solver, test cases) to work
identically regardless of source language.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from typing import Any

from app.core.ast_parser import ConditionInfo, ParseResult


# ---------------------------------------------------------------------------
# Type inference from annotations and usage patterns
# ---------------------------------------------------------------------------

class _TypeInferenceVisitor(ast.NodeVisitor):
    """Walk the AST to infer variable types from annotations and assignments."""

    def __init__(self):
        self.var_types: dict[str, str] = {}

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if isinstance(node.target, ast.Name):
            type_name = self._annotation_to_type(node.annotation)
            if type_name:
                self.var_types[node.target.id] = type_name
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        if node.value:
            inferred = self._infer_from_value(node.value)
            for target in node.targets:
                if isinstance(target, ast.Name) and inferred:
                    self.var_types[target.id] = inferred
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        for arg in node.args.args:
            if arg.annotation:
                type_name = self._annotation_to_type(arg.annotation)
                if type_name and isinstance(arg.arg, str):
                    self.var_types[arg.arg] = type_name
        self.generic_visit(node)

    @staticmethod
    def _annotation_to_type(node: ast.AST) -> str | None:
        if isinstance(node, ast.Name):
            mapping = {
                "int": "int", "float": "float", "str": "str",
                "bool": "bool", "list": "list", "dict": "dict",
            }
            return mapping.get(node.id, "int")
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        return None

    @staticmethod
    def _infer_from_value(node: ast.AST) -> str | None:
        if isinstance(node, ast.Constant):
            if isinstance(node.value, bool):
                return "bool"
            if isinstance(node.value, int):
                return "int"
            if isinstance(node.value, float):
                return "float"
            if isinstance(node.value, str):
                return "str"
        elif isinstance(node, ast.List):
            return "list"
        elif isinstance(node, ast.Dict):
            return "dict"
        elif isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                if node.func.id in ("int", "float", "str", "bool"):
                    return node.func.id
        return None


# ---------------------------------------------------------------------------
# Condition extraction
# ---------------------------------------------------------------------------

class _ConditionExtractor(ast.NodeVisitor):
    """Extract branching conditions from Python AST."""

    def __init__(self, var_types: dict[str, str]):
        self.var_types = var_types
        self._conditions: list[ConditionInfo] = []
        self._unsupported: list[str] = []
        self._cond_counter = 0

    def _next_id(self) -> str:
        self._cond_counter += 1
        return f"C{self._cond_counter}"

    def _make_condition(self, node: ast.expr, ast_type: str) -> None:
        expr_str = ast.unparse(node) if hasattr(ast, "unparse") else self._fallback_unparse(node)
        variables = self._extract_variables(node)
        inferred = {v: self.var_types.get(v, "int") for v in variables}
        operator = self._extract_operator(node)

        self._conditions.append(ConditionInfo(
            condition_id=self._next_id(),
            expr_str=expr_str,
            variables=variables,
            inferred_types=inferred,
            source_line=getattr(node, "lineno", None),
            source_col=getattr(node, "col_offset", None),
            ast_node_type=ast_type,
            operator=operator,
        ))

    def visit_If(self, node: ast.If) -> None:
        self._make_condition(node.test, "If")
        self.generic_visit(node)

    def visit_While(self, node: ast.While) -> None:
        self._make_condition(node.test, "While")
        self.generic_visit(node)

    def visit_For(self, node: ast.For) -> None:
        expr_str = f"for loop iteration"
        self._conditions.append(ConditionInfo(
            condition_id=self._next_id(),
            expr_str=expr_str,
            variables=[],
            inferred_types={},
            source_line=getattr(node, "lineno", None),
            source_col=getattr(node, "col_offset", None),
            ast_node_type="For",
            operator=None,
        ))
        self.generic_visit(node)

    @staticmethod
    def _extract_variables(node: ast.expr) -> list[str]:
        names: list[str] = []
        for child in ast.walk(node):
            if isinstance(child, ast.Name):
                names.append(child.id)
        seen: set[str] = set()
        result: list[str] = []
        for n in names:
            if n not in seen:
                seen.add(n)
                result.append(n)
        return result

    @staticmethod
    def _extract_operator(node: ast.expr) -> str | None:
        if isinstance(node, ast.Compare):
            ops_map = {
                ast.Lt: "<", ast.LtE: "<=", ast.Gt: ">", ast.GtE: ">=",
                ast.Eq: "==", ast.NotEq: "!=",
            }
            for op in node.ops:
                if type(op) in ops_map:
                    return ops_map[type(op)]
        return None

    @staticmethod
    def _fallback_unparse(node: ast.AST) -> str:
        """Simple fallback for Python < 3.9 without ast.unparse."""
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Constant):
            return repr(node.value)
        if isinstance(node, ast.Compare):
            ops = {
                ast.Lt: "<", ast.LtE: "<=", ast.Gt: ">", ast.GtE: ">=",
                ast.Eq: "==", ast.NotEq: "!=",
            }
            left = _ConditionExtractor._fallback_unparse(node.left)
            parts = []
            for op, comparator in zip(node.ops, node.comparators):
                op_str = ops.get(type(op), "?")
                right = _ConditionExtractor._fallback_unparse(comparator)
                parts.append(f"{left} {op_str} {right}")
                left = comparator
            return " and ".join(parts)
        return "<expr>"

    @property
    def conditions(self) -> list[ConditionInfo]:
        return self._conditions

    @property
    def unsupported(self) -> list[str]:
        return self._unsupported


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_python_source(source_code: str) -> ParseResult:
    """
    Parse Python source code and extract conditions for CFG construction.

    Args:
        source_code: Raw Python source code string.

    Returns:
        ParseResult with .conditions, .parse_errors, .unsupported_constructs
        (same structure as parse_c_source for pipeline compatibility).
    """
    parse_errors: list[str] = []
    tree: ast.AST | None = None

    try:
        tree = ast.parse(source_code)
    except SyntaxError as exc:
        parse_errors.append(f"Python syntax error: {exc}")
        return ParseResult(
            ast=None,
            conditions=[],
            source_code=source_code,
            parse_errors=parse_errors,
        )

    # Infer variable types
    type_visitor = _TypeInferenceVisitor()
    type_visitor.visit(tree)

    # Extract conditions
    extractor = _ConditionExtractor(type_visitor.var_types)
    extractor.visit(tree)

    return ParseResult(
        ast=tree,
        conditions=extractor.conditions,
        source_code=source_code,
        parse_errors=parse_errors,
        unsupported_constructs=extractor.unsupported,
    )
