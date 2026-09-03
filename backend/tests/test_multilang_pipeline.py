"""
End-to-end multi-language pipeline tests
========================================
parse → CFG → Z3 solve, for complex programs in C, Python, JS, TS.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import ast as py_ast

from app.core.ast_parser import parse_c_source
from app.core.python_parser import parse_python_source
from app.core.javascript_parser import parse_javascript_source
from app.core.cfg_builder import build_cfg, cfg_to_json
from app.core.symbolic_solver import solve_all_conditions


# ---------------------------------------------------------------------------
# C — nested if/else + loop + compound condition
# ---------------------------------------------------------------------------

C_COMPLEX = """
int grade(int score, int attendance) {
    if (score >= 90 && attendance > 80) {
        return 4;
    } else if (score >= 75) {
        return 3;
    } else {
        return 0;
    }
}
"""


def test_c_complex_pipeline():
    result = parse_c_source(C_COMPLEX)
    assert not result.parse_errors, result.parse_errors
    assert len(result.conditions) >= 2, "if + else-if conditions expected"

    cfg = build_cfg(result, "grade")
    assert cfg.node_count > 2, "CFG should be non-trivial"
    assert cfg.cyclomatic_complexity > 1
    j = cfg_to_json(cfg)
    conds = [n for n in j["nodes"] if n["block_type"] == "condition"]
    assert len(conds) >= 2, conds

    results = solve_all_conditions(result.conditions)
    assert all(r.is_satisfiable for r in results), \
        [r.solver_notes for r in results]
    first = results[0]
    assert first.is_satisfiable
    assert first.true_values.get("score") is not None


# ---------------------------------------------------------------------------
# Python — nested if/elif/else, for loop, while loop
# ---------------------------------------------------------------------------

PY_COMPLEX = """
def classify(score, attendance):
    if score >= 90 and attendance > 80:
        grade = "A"
    elif score >= 75:
        grade = "B"
    else:
        grade = "F"
    total = 0
    for i in range(10):
        total += i
    while total > 100:
        total -= 10
    return grade
"""


def test_python_pipeline_parses():
    result = parse_python_source(PY_COMPLEX)
    assert not result.parse_errors, result.parse_errors
    assert result.language == "python"
    exprs = [c.expr_str for c in result.conditions]
    assert any("score >= 90" in e for e in exprs), exprs
    assert any("total > 100" in e for e in exprs), exprs


def test_python_pipeline_cfg():
    result = parse_python_source(PY_COMPLEX)
    cfg = build_cfg(result, "classify")
    assert cfg.node_count > 4, f"CFG too trivial: {cfg.node_count} nodes"
    j = cfg_to_json(cfg)
    types = [n["block_type"] for n in j["nodes"]]
    assert types.count("condition") >= 4, types  # if, elif, for, while
    labels = [n["label"] for n in j["nodes"]]
    assert any("while" in l for l in labels), labels
    assert any("for" in l for l in labels), labels


def test_python_pipeline_solver():
    result = parse_python_source(PY_COMPLEX)
    results = solve_all_conditions(result.conditions)
    assert len(results) == len(result.conditions)
    assert all(r.is_satisfiable for r in results), [r.solver_notes for r in results]


def test_python_cfg_direct():
    from app.core.python_cfg_builder import build_cfg_python
    tree = py_ast.parse(PY_COMPLEX)
    cfg = build_cfg_python(tree, "classify")
    assert cfg.function_name == "classify"
    assert cfg.cyclomatic_complexity >= 5
    assert cfg.edge_count > cfg.node_count - 2


# ---------------------------------------------------------------------------
# JavaScript — nested if/else if/else + loop + === and && conditions
# ---------------------------------------------------------------------------

JS_COMPLEX = """
function classify(score, attendance) {
    if (score === 100) {
        return "perfect";
    } else if (score >= 90 && attendance > 80) {
        return "A";
    } else {
        return "F";
    }
    let total = 0;
    while (total < 50) {
        total = total + 10;
    }
    return total;
}
"""


def test_js_pipeline_parses():
    result = parse_javascript_source(JS_COMPLEX)
    assert not result.parse_errors, result.parse_errors
    assert result.language == "javascript"
    assert len(result.conditions) >= 3


def test_js_pipeline_cfg():
    result = parse_javascript_source(JS_COMPLEX)
    cfg = build_cfg(result, "classify")
    assert cfg.node_count > 3, f"CFG too trivial: {cfg.node_count} nodes"
    j = cfg_to_json(cfg)
    cond_labels = [n["label"] for n in j["nodes"] if n["block_type"] == "condition"]
    assert len(cond_labels) >= 3, cond_labels
    assert any("score === 100" in l for l in cond_labels), cond_labels
    assert any(e["label"] == "back_edge" for e in j["edges"]), j["edges"]


def test_js_pipeline_solver():
    result = parse_javascript_source(JS_COMPLEX)
    results = solve_all_conditions(result.conditions)
    assert len(results) >= 3
    for r in results:
        assert r.is_satisfiable, r.solver_notes


# ---------------------------------------------------------------------------
# TypeScript — nested if + or-condition + !==
# ---------------------------------------------------------------------------

TS_COMPLEX = """
function grade(x, y) {
    if (x !== 0) {
        if (y > 10 || x < -5) {
            return "high";
        }
        return "mid";
    }
    return "low";
}
"""


def test_ts_pipeline_end_to_end():
    result = parse_javascript_source(TS_COMPLEX)
    assert len(result.conditions) >= 2

    cfg = build_cfg(result, "grade")
    assert cfg.node_count > 3
    j = cfg_to_json(cfg)
    cond_labels = [n["label"] for n in j["nodes"] if n["block_type"] == "condition"]
    assert any("y > 10" in l for l in cond_labels), cond_labels

    results = solve_all_conditions(result.conditions)
    assert all(r.is_satisfiable for r in results), [r.solver_notes for r in results]
    compound = [r for r in results if "y > 10" in r.expr_str]
    assert compound, [r.expr_str for r in results]
