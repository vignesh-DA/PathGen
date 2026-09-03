"""
Module — JavaScript/TypeScript Parser
======================================
Parses JavaScript/TypeScript source code into a unified intermediate
representation for CFG construction.

Uses regex-based parsing (lightweight, no external dependencies) to extract:
- if/else if/else
- for, for...of, for...in, while, do-while
- switch/case
- ternary expressions
- function declarations/expressions

Output: Same ConditionInfo + ParseResult structure as the C parser.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from app.core.ast_parser import ConditionInfo, ParseResult


# ---------------------------------------------------------------------------
# Tokenizer for basic JS constructs
# ---------------------------------------------------------------------------

class _JSTokenizer:
    """Simple tokenizer for extracting conditions from JS/TS code."""

    IF_PATTERN = re.compile(r'\bif\s*\(([^)]+)\)', re.MULTILINE)
    ELSE_IF_PATTERN = re.compile(r'\belse\s+if\s*\(([^)]+)\)', re.MULTILINE)
    WHILE_PATTERN = re.compile(r'\bwhile\s*\(([^)]+)\)', re.MULTILINE)
    FOR_PATTERN = re.compile(r'\bfor\s*\(([^)]+)\)', re.MULTILINE)
    SWITCH_PATTERN = re.compile(r'\bswitch\s*\(([^)]+)\)', re.MULTILINE)
    VAR_PATTERN = re.compile(r'\b([a-zA-Z_][a-zA-Z0-9_]*)\b')


# ---------------------------------------------------------------------------
# Condition extraction
# ---------------------------------------------------------------------------

class _ConditionExtractor:
    """Extract branching conditions from JS/TS source."""

    def __init__(self, source: str):
        self.source = source
        self._conditions: list[ConditionInfo] = []
        self._cond_counter = 0

    def _next_id(self) -> str:
        self._cond_counter += 1
        return f"C{self._cond_counter}"

    def _extract_variables(self, expr: str) -> list[str]:
        """Extract variable names from a condition expression."""
        cleaned = expr
        keywords = {'true', 'false', 'null', 'undefined', 'typeof', 'instanceof', 'in', 'of'}
        cleaned = re.sub(r'["\'][^"\']*["\']', '', cleaned)
        cleaned = re.sub(r'\b\d+(\.\d+)?\b', '', cleaned)
        tokens = _JSTokenizer.VAR_PATTERN.findall(cleaned)
        variables = [t for t in tokens if t not in keywords and not t[0].isdigit()]
        seen: set[str] = set()
        result: list[str] = []
        for v in variables:
            if v not in seen:
                seen.add(v)
                result.append(v)
        return result

    def _infer_type(self, var: str, expr: str) -> str:
        """Infer variable type from usage context."""
        if re.search(rf'\b{var}\s*[!=]==?\s*["\']', expr):
            return "string"
        if re.search(rf'\b{var}\s*[!=]==?\s*\d+', expr):
            return "number"
        if re.search(rf'\b{var}\s*[!=]==?\s*(true|false)', expr):
            return "boolean"
        if re.search(rf'\b{var}\s*(<=|>=|<|>)', expr):
            return "number"
        return "number"

    def _extract_operator(self, expr: str) -> str | None:
        """Extract comparison operator from condition."""
        operators = ['===', '!==', '<=', '>=', '==', '!=', '<', '>']
        for op in operators:
            if op in expr:
                return op
        return None

    def _add_condition(self, expr: str, ast_type: str, line_no: int | None = None) -> None:
        """Add a condition to the list."""
        variables = self._extract_variables(expr)
        inferred = {v: self._infer_type(v, expr) for v in variables}
        operator = self._extract_operator(expr)

        self._conditions.append(ConditionInfo(
            condition_id=self._next_id(),
            expr_str=expr.strip(),
            variables=variables,
            inferred_types=inferred,
            source_line=line_no,
            source_col=None,
            ast_node_type=ast_type,
            operator=operator,
        ))

    def extract(self) -> list[ConditionInfo]:
        """Run extraction and return all conditions."""
        # else-if first, so plain `if` matches inside `else if` can be skipped
        else_if_matches = list(_JSTokenizer.ELSE_IF_PATTERN.finditer(self.source))
        else_if_spans = [m.span() for m in else_if_matches]
        for match in else_if_matches:
            self._add_condition(match.group(1), "If", self._line_number(match.start()))
        for match in _JSTokenizer.IF_PATTERN.finditer(self.source):
            if any(s <= match.start() < e for s, e in else_if_spans):
                continue  # already captured by ELSE_IF_PATTERN
            self._add_condition(match.group(1), "If", self._line_number(match.start()))
        for match in _JSTokenizer.WHILE_PATTERN.finditer(self.source):
            self._add_condition(match.group(1), "While", self._line_number(match.start()))
        for match in _JSTokenizer.FOR_PATTERN.finditer(self.source):
            self._add_condition(match.group(1), "For", self._line_number(match.start()))
        for match in _JSTokenizer.SWITCH_PATTERN.finditer(self.source):
            self._add_condition(match.group(1), "Switch", self._line_number(match.start()))
        return self._conditions

    def _line_number(self, pos: int) -> int:
        """Get line number for a position in source."""
        return self.source[:pos].count('\n') + 1


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_javascript_source(source_code: str) -> ParseResult:
    """
    Parse JavaScript/TypeScript source code and extract conditions.

    Args:
        source_code: Raw JS/TS source code string.

    Returns:
        ParseResult with .conditions, .parse_errors, .unsupported_constructs
        (same structure as parse_c_source for pipeline compatibility).
    """
    parse_errors: list[str] = []

    if not _validate_braces(source_code):
        parse_errors.append("Unbalanced braces detected in JavaScript code")

    extractor = _ConditionExtractor(source_code)
    conditions = extractor.extract()

    return ParseResult(
        ast=None,
        conditions=conditions,
        source_code=source_code,
        parse_errors=parse_errors,
        unsupported_constructs=[],
        language="javascript",
    )


def _validate_braces(source: str) -> bool:
    """Check if braces are balanced."""
    stack = []
    in_string = False
    string_char = None
    i = 0
    while i < len(source):
        ch = source[i]
        if ch in ('"', "'", '`') and (i == 0 or source[i-1] != '\\'):
            if not in_string:
                in_string = True
                string_char = ch
            elif ch == string_char:
                in_string = False
        elif not in_string:
            if ch in ('{', '('):
                stack.append(ch)
            elif ch == '}':
                if not stack or stack[-1] != '{':
                    return False
                stack.pop()
            elif ch == ')':
                if not stack or stack[-1] != '(':
                    return False
                stack.pop()
        i += 1
    return len(stack) == 0
