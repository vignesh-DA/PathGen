"""
Module 2 — Test Case Builder
============================
Assembles final TestCase objects by combining:
    - A CFGPath (which conditions are taken, in which order)
    - SolverResults (concrete values for each condition)
    - Simple output simulation (scans printf/return statements for expected output)

Derivation method:
    "DERIVED (verified)"   — all conditions solved deterministically by Z3
    "AI-SUGGESTED (unverified)" — one or more conditions required AI fallback

Expected output simulation:
    We do a lightweight string-substitution simulation of the execution path.
    For each node in the path, if its statements contain a printf("%s\\n", "Adult")
    or return X pattern, we extract the literal output and record it.
    This is deliberately simple — it handles the canonical capstone examples.
    Complex arithmetic evaluation is out of scope for path simulation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.core.ast_parser import ConditionInfo
from app.core.cfg_builder import CFGGraph
from app.core.path_enumerator import CFGPath
from app.core.symbolic_solver import SolverResult


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class TestCase:
    test_id: str                              # "TC01", "TC02", ...
    path_id: str                              # which CFGPath this covers
    input_values: dict[str, int | float | str]  # variable → concrete value
    path_conditions: list[dict]               # conditions taken along path
    expected_output: str                      # simulated output from printf/return
    boundary_flag: bool                       # True if any value is a boundary value
    derivation_method: str                    # "DERIVED (verified)" or "AI-SUGGESTED (unverified)"
    explanation: str                          # filled later by LangChain AI layer
    path_steps: list[str]                     # node labels along the path


# ---------------------------------------------------------------------------
# Output simulation
# ---------------------------------------------------------------------------

# Matches: printf("some string\n") or printf("%s\n", "some string")
_PRINTF_LITERAL = re.compile(
    r'printf\s*\(\s*"([^"\\]*(\\.[^"\\]*)*)"\s*\)',  # printf("literal")
)
_PRINTF_STRING_FMT = re.compile(
    r'printf\s*\(\s*"%s[^"]*"\s*,\s*"([^"]*)"\s*\)',  # printf("%s", "str")
)
_PRINTF_INT_FMT = re.compile(
    r'printf\s*\(\s*"%d[^"]*"\s*,\s*(\w+)\s*\)',      # printf("%d", var)
)
# C: return 1; / return "literal";  (semicolon required)
_RETURN_C = re.compile(r'return\s+(\d+(?:\.\d+)?|"[^"]*"|\w+)\s*;')
# JS/Python: return "literal" or return 1 (semicolon optional)
_RETURN_JS_PY = re.compile(r"return\s+(\d+(?:\.\d+)?|\"[^\"]*\"|'[^']*'|[\w]+)\s*;?$")
# Python: print("literal") / console.log("literal")
_PRINT_FN = re.compile(r'(?:print|console\.log)\s*\(\s*(["\'])(.*?)\1\s*\)')


def _simulate_output(path_steps_nodes: list[dict],
                     input_values: dict[str, int | float | str]) -> str:
    """
    Walk the node list and extract any printf/print/console.log/return outputs.
    Substitutes known variable values where possible.
    Handles C (printf, return x;), Python (print(), return x), and JS
    (console.log(), return x / return 'string').
    """
    outputs: list[str] = []

    for node in path_steps_nodes:
        for stmt in node.get("statements", []):
            # printf("literal\n")  — C
            m = _PRINTF_LITERAL.search(stmt)
            if m:
                raw = m.group(1).replace("\\n", "").replace("\\t", "\t")
                outputs.append(raw)
                continue

            # printf("%s\n", "literal")  — C
            m = _PRINTF_STRING_FMT.search(stmt)
            if m:
                outputs.append(m.group(1))
                continue

            # printf("%d\n", var)  — C
            m = _PRINTF_INT_FMT.search(stmt)
            if m:
                var_name = m.group(1)
                if var_name in input_values:
                    outputs.append(str(input_values[var_name]))
                else:
                    outputs.append(f"<{var_name}>")
                continue

            # print("...") / console.log("...")  — Python / JS
            m = _PRINT_FN.search(stmt)
            if m:
                outputs.append(m.group(2))
                continue

            # return statement — try C pattern first (requires ;), then JS/Python
            m = _RETURN_C.search(stmt) or _RETURN_JS_PY.search(stmt)
            if m:
                val = m.group(1).strip('"\'')
                if val in input_values:
                    val = str(input_values[val])
                outputs.append(f"return {val}")

    return "; ".join(outputs) if outputs else "<no output>"



# ---------------------------------------------------------------------------
# Input value picker
# ---------------------------------------------------------------------------

def _pick_input_values(
    path: CFGPath,
    solver_results: dict[str, SolverResult],
    conditions: list[ConditionInfo],
) -> tuple[dict[str, int | float | str], bool, str]:
    """
    Given a path's condition sequence, pick concrete input values.

    For each condition along the path:
    - If branch_taken == "true"  → use solver true_values
    - If branch_taken == "false" → use solver false_values
    - Check if this is a boundary case

    Returns: (input_values, boundary_flag, derivation_method)
    """
    # Build a lookup: condition_expr → SolverResult
    # We match by expr substring since path conditions store the condition expr
    solver_by_expr: dict[str, SolverResult] = {
        sr.expr_str: sr for sr in solver_results.values()
    }
    # Also index by condition_id
    solver_by_id: dict[str, SolverResult] = solver_results

    combined_inputs: dict[str, int | float | str] = {}
    is_boundary = False
    all_derived = True

    for cond_decision in path.conditions_taken:
        cond_expr = cond_decision.get("condition_expr", "")
        branch = cond_decision.get("branch_taken", "true")

        # Strip negation prefix if any
        clean_expr = cond_expr.lstrip("!(").rstrip(")")

        sr = solver_by_expr.get(cond_expr) or solver_by_expr.get(clean_expr)

        if sr is None:
            all_derived = False
            continue

        if not sr.is_satisfiable:
            all_derived = False
            continue

        if branch == "true":
            vals = sr.true_values
            # Check if this is the boundary value
            for vname, vval in vals.items():
                bval = sr.boundary_values.get(vname)
                if bval is not None and bval == vval:
                    is_boundary = True
        elif branch == "false":
            vals = sr.false_values
        else:
            vals = sr.true_values

        # Merge values (later conditions override earlier ones for same variable — last wins)
        combined_inputs.update(vals)

    # If path uses boundary values (indicated by boundary solver results),
    # check if the boundary path is this path
    # For the canonical TC03 (boundary): prefer boundary values for conditions
    # that have boundary_flag=True and the branch taken is "true"
    # We do a second pass to override with boundary values where applicable
    for cond_decision in path.conditions_taken:
        cond_expr = cond_decision.get("condition_expr", "")
        branch = cond_decision.get("branch_taken", "true")
        clean_expr = cond_expr.lstrip("!(").rstrip(")")
        sr = solver_by_expr.get(cond_expr) or solver_by_expr.get(clean_expr)

        if sr and sr.boundary_flag and branch == "true":
            bvals = sr.boundary_values
            # Check if using boundary values changes anything
            if bvals and bvals != sr.true_values:
                # This is a boundary-specific path variant
                # We'll return boundary values for this case
                # Only override if not already overridden
                for vname, bval in bvals.items():
                    if combined_inputs.get(vname) != bval:
                        is_boundary = True

    derivation = "DERIVED (verified)" if all_derived else "AI-SUGGESTED (unverified)"
    return combined_inputs, is_boundary, derivation


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_test_cases(
    paths: list[CFGPath],
    cfg: CFGGraph,
    solver_results: dict[str, SolverResult],
    conditions: list[ConditionInfo],
) -> list[TestCase]:
    """
    Build one TestCase per unique path × input-set combination.

    For paths with boundary conditions, we emit TWO test cases:
    - One with the non-boundary (regular) true_values
    - One with the boundary values
    This gives TC01 (regular TRUE), TC02 (FALSE), TC03 (boundary) for the
    canonical age >= 18 example.
    """
    solver_by_expr: dict[str, SolverResult] = {}
    for sr in solver_results.values():
        solver_by_expr[sr.expr_str] = sr

    test_cases: list[TestCase] = []
    tc_counter = 0

    # Get CFG node data for output simulation
    node_data_map = {nid: data for nid, data in cfg.graph.nodes(data=True)}

    for path in paths:
        variants: list[tuple[dict, bool, str]] = []

        # Normal input values
        inputs, is_bnd, derivation = _pick_input_values(path, solver_results, conditions)
        variants.append((inputs, False, derivation))

        # Boundary variant — check if any condition on this path has boundary values
        # different from its true values
        boundary_inputs: dict[str, int | float | str] = dict(inputs)
        has_boundary_variant = False

        for cond_decision in path.conditions_taken:
            cond_expr = cond_decision.get("condition_expr", "")
            branch = cond_decision.get("branch_taken", "true")
            clean_expr = cond_expr.lstrip("!(").rstrip(")")
            sr = solver_by_expr.get(cond_expr) or solver_by_expr.get(clean_expr)

            if sr and sr.boundary_flag and branch == "true" and sr.boundary_values:
                # Check if boundary ≠ regular true values
                for vname, bval in sr.boundary_values.items():
                    if inputs.get(vname) != bval:
                        boundary_inputs[vname] = bval
                        has_boundary_variant = True

        if has_boundary_variant:
            variants.append((boundary_inputs, True, derivation))

        for input_vals, boundary_flag, deriv in variants:
            tc_counter += 1
            tc_id = f"TC{tc_counter:02d}"

            # Collect path node data for output simulation
            path_nodes = [node_data_map.get(step.node_id, {}) for step in path.steps]
            expected_out = _simulate_output(path_nodes, input_vals)

            test_cases.append(TestCase(
                test_id=tc_id,
                path_id=path.path_id,
                input_values=input_vals,
                path_conditions=path.conditions_taken,
                expected_output=expected_out,
                boundary_flag=boundary_flag,
                derivation_method=deriv,
                explanation="",  # filled by AI layer
                path_steps=[step.node_label for step in path.steps],
            ))

    return test_cases
