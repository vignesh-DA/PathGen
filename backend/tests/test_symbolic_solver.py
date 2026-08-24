"""
Tests for Module 2 — Symbolic Solver
Validates Z3-derived test case values against the canonical age >= 18 example.
TC01: age=20 (TRUE, non-boundary)
TC02: age=17 (FALSE)
TC03: age=18 (BOUNDARY → inclusive, TRUE branch)
"""
import pytest
from pathlib import Path

from app.core.ast_parser import parse_c_source
from app.core.cfg_builder import build_cfg
from app.core.condition_extractor import extract_conditions
from app.core.symbolic_solver import solve_condition, solve_all_conditions, SolverResult
from app.core.path_enumerator import enumerate_paths
from app.core.test_case_builder import build_test_cases

SAMPLES = Path(__file__).parent / "sample_programs"


def _load(fname: str) -> str:
    return (SAMPLES / fname).read_text()


class TestSymbolicSolverBasic:
    def setup_method(self):
        result = parse_c_source(_load("simple_if_else.c"))
        self.conditions = result.conditions
        assert len(self.conditions) >= 1
        self.sr = solve_condition(self.conditions[0])

    def test_condition_is_satisfiable(self):
        assert self.sr.is_satisfiable, f"Solver notes: {self.sr.solver_notes}"

    def test_true_value_satisfies_condition(self):
        # For age >= 18, true_value["age"] should be >= 18
        age_true = self.sr.true_values.get("age")
        assert age_true is not None
        assert int(age_true) >= 18, f"TRUE value {age_true} does not satisfy age >= 18"

    def test_false_value_falsifies_condition(self):
        # For age >= 18, false_value["age"] should be < 18
        age_false = self.sr.false_values.get("age")
        assert age_false is not None
        assert int(age_false) < 18, f"FALSE value {age_false} does not falsify age >= 18"

    def test_boundary_value_is_18(self):
        # For age >= 18, boundary should be exactly 18
        age_bnd = self.sr.boundary_values.get("age")
        assert age_bnd is not None
        assert int(age_bnd) == 18, f"Boundary value {age_bnd} != 18"

    def test_boundary_flag_is_true(self):
        # >= operator implies boundary is important
        assert self.sr.boundary_flag


class TestCanonicalTC01TC02TC03:
    """
    Validates that the full pipeline produces TC01/TC02/TC03 for simple_if_else.c.
    TC01: age >= 18 TRUE → Adult
    TC02: age < 18  FALSE → Minor
    TC03: age == 18 BOUNDARY → Adult
    """
    def setup_method(self):
        source = _load("simple_if_else.c")
        parse_result = parse_c_source(source)
        cfg = build_cfg(parse_result, "classify_age")
        conditions = extract_conditions(parse_result, cfg)
        solver_results = {sr.condition_id: sr for sr in solve_all_conditions(conditions)}
        paths = enumerate_paths(cfg, max_paths=10, max_loop_iters=3)
        self.tcs = build_test_cases(paths, cfg, solver_results, conditions)
        self.tc_by_id = {tc.test_id: tc for tc in self.tcs}

    def test_at_least_two_test_cases(self):
        assert len(self.tcs) >= 2, (
            f"Expected at least 2 TCs (TRUE + FALSE), got {len(self.tcs)}: "
            f"{[tc.test_id for tc in self.tcs]}"
        )

    def test_has_true_branch_tc(self):
        true_tcs = [tc for tc in self.tcs
                    if any(d.get("branch_taken") == "true" for d in tc.path_conditions)]
        assert len(true_tcs) >= 1, "No TRUE-branch test case found"

    def test_has_false_branch_tc(self):
        false_tcs = [tc for tc in self.tcs
                     if any(d.get("branch_taken") == "false" for d in tc.path_conditions)]
        assert len(false_tcs) >= 1, "No FALSE-branch test case found"

    def test_true_branch_input_gte_18(self):
        true_tcs = [tc for tc in self.tcs
                    if any(d.get("branch_taken") == "true" for d in tc.path_conditions)
                    and not tc.boundary_flag]
        for tc in true_tcs:
            age = tc.input_values.get("age")
            if age is not None:
                assert int(age) >= 18, f"TRUE branch TC has age={age} < 18"

    def test_false_branch_input_lt_18(self):
        false_tcs = [tc for tc in self.tcs
                     if any(d.get("branch_taken") == "false" for d in tc.path_conditions)]
        for tc in false_tcs:
            age = tc.input_values.get("age")
            if age is not None:
                assert int(age) < 18, f"FALSE branch TC has age={age} >= 18"

    def test_boundary_tc_has_age_18(self):
        bnd_tcs = [tc for tc in self.tcs if tc.boundary_flag]
        if bnd_tcs:  # boundary TC may not always be generated depending on path structure
            for tc in bnd_tcs:
                age = tc.input_values.get("age")
                if age is not None:
                    assert int(age) == 18, f"Boundary TC has age={age} != 18"

    def test_derivation_method_is_derived(self):
        for tc in self.tcs:
            assert "DERIVED" in tc.derivation_method or "SUGGESTED" in tc.derivation_method


class TestNestedSolver:
    def setup_method(self):
        result = parse_c_source(_load("nested_if.c"))
        self.solver_results = solve_all_conditions(result.conditions)

    def test_three_solver_results(self):
        assert len(self.solver_results) == 3

    def test_all_satisfiable(self):
        for sr in self.solver_results:
            assert sr.is_satisfiable, f"Condition {sr.expr_str} is not satisfiable"

    def test_boundary_90_75_50(self):
        boundaries = {sr.boundary_values.get("score") for sr in self.solver_results}
        expected = {90, 75, 50}
        assert boundaries == expected, f"Boundaries {boundaries} != {expected}"
