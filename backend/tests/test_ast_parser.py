"""
Tests for Module 1 — AST Parser
Validates pycparser-based parsing against 3 known C programs.
"""
import pytest
from pathlib import Path

from app.core.ast_parser import parse_c_source, ConditionInfo

SAMPLES = Path(__file__).parent / "sample_programs"


def _load(fname: str) -> str:
    return (SAMPLES / fname).read_text()


class TestSimpleIfElse:
    def setup_method(self):
        self.result = parse_c_source(_load("simple_if_else.c"))

    def test_no_parse_errors(self):
        assert self.result.parse_errors == [], f"Parse errors: {self.result.parse_errors}"

    def test_ast_is_not_none(self):
        assert self.result.ast is not None

    def test_exactly_one_condition(self):
        # simple_if_else.c has one if-condition: age >= 18
        assert len(self.result.conditions) == 1, (
            f"Expected 1 condition, got {len(self.result.conditions)}: "
            f"{[c.expr_str for c in self.result.conditions]}"
        )

    def test_condition_expr(self):
        cond = self.result.conditions[0]
        assert "age" in cond.expr_str
        assert ">=" in cond.expr_str

    def test_condition_variables(self):
        cond = self.result.conditions[0]
        assert "age" in cond.variables

    def test_condition_operator(self):
        cond = self.result.conditions[0]
        assert cond.operator == ">="

    def test_condition_ast_node_type(self):
        cond = self.result.conditions[0]
        assert cond.ast_node_type == "If"

    def test_inferred_type_int(self):
        cond = self.result.conditions[0]
        assert cond.inferred_types.get("age") == "int"


class TestNestedIf:
    def setup_method(self):
        self.result = parse_c_source(_load("nested_if.c"))

    def test_no_parse_errors(self):
        assert self.result.parse_errors == []

    def test_three_conditions(self):
        # nested_if.c has 3 if conditions: >=90, >=75, >=50
        assert len(self.result.conditions) == 3, (
            f"Expected 3 conditions, got {len(self.result.conditions)}: "
            f"{[c.expr_str for c in self.result.conditions]}"
        )

    def test_condition_exprs_contain_score(self):
        for c in self.result.conditions:
            assert "score" in c.expr_str

    def test_all_conditions_are_if(self):
        for c in self.result.conditions:
            assert c.ast_node_type == "If"

    def test_operators_are_gte(self):
        for c in self.result.conditions:
            assert c.operator == ">="


class TestLoopWithCondition:
    def setup_method(self):
        self.result = parse_c_source(_load("loop_with_condition.c"))

    def test_no_parse_errors(self):
        assert self.result.parse_errors == []

    def test_while_condition_extracted(self):
        while_conds = [c for c in self.result.conditions if c.ast_node_type == "While"]
        assert len(while_conds) == 1, f"Expected 1 While condition, got {while_conds}"

    def test_while_condition_expr(self):
        cond = next(c for c in self.result.conditions if c.ast_node_type == "While")
        assert "i" in cond.expr_str or "n" in cond.expr_str


class TestMalformedCode:
    def test_syntax_error_returns_error(self):
        result = parse_c_source("int main() { if (x { return 1; } }")
        assert len(result.parse_errors) > 0

    def test_empty_function_no_conditions(self):
        result = parse_c_source("int main() { return 0; }")
        assert result.parse_errors == []
        assert len(result.conditions) == 0
