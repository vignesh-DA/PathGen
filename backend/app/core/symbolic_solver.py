"""
Module 2 — Symbolic Solver
==========================
Uses z3-solver to derive concrete test values for each condition.

For each ConditionInfo, we produce:
    SolverResult:
        condition_id: str
        true_value:   dict[var, concrete_value]   (satisfies TRUE branch)
        false_value:  dict[var, concrete_value]   (satisfies FALSE branch)
        boundary_values: list[dict[var, value]]   (flip point(s))
        is_satisfiable: bool
        solver_notes: str

Supported operators: <  <=  >  >=  ==  !=
Supported types: int, float (mapped to z3.Int / z3.Real)

Design: We create ONE z3 variable per condition variable (fresh per solve call)
and solve three times: once with the constraint as-is (true branch),
once with its negation (false branch), once for the boundary.

Boundary derivation strategy (int variables):
  - For  x >= K  : boundary = K         (minimum TRUE value)
  - For  x >  K  : boundary = K+1       (minimum TRUE value)
  - For  x <= K  : boundary = K         (maximum TRUE value)
  - For  x <  K  : boundary = K-1       (maximum TRUE value)
  - For  x == K  : boundary = K
  - For  x != K  : boundary = K         (the value where cond flips to false)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import z3

from app.core.ast_parser import ConditionInfo


@dataclass
class SolverResult:
    condition_id: str
    expr_str: str
    variables: list[str]
    true_values: dict[str, int | float | str]      # satisfies condition
    false_values: dict[str, int | float | str]     # falsifies condition
    boundary_values: dict[str, int | float | str]  # flip-point value(s)
    is_satisfiable: bool
    boundary_flag: bool    # True if boundary_values differ from true_values
    solver_notes: str


# ---------------------------------------------------------------------------
# Expression → Z3 constraint builder
# ---------------------------------------------------------------------------

def _make_z3_var(name: str, typ: str) -> z3.ExprRef:
    if typ == "float":
        return z3.Real(name)
    return z3.Int(name)


def _extract_simple_parts(expr_str: str) -> tuple[str, str, str] | None:
    """
    Try to parse a simple binary condition like  'age >= 18'  or  'x < y'.
    Returns (lhs, op, rhs) or None for complex expressions.
    """
    pattern = r"^\s*(.+?)\s*(<=|>=|==|!=|<|>)\s*(.+?)\s*$"
    m = re.match(pattern, expr_str.strip())
    if m:
        return m.group(1).strip(), m.group(2).strip(), m.group(3).strip()
    return None


def _try_as_int(s: str) -> int | None:
    try:
        return int(s)
    except ValueError:
        return None


def _try_as_float(s: str) -> float | None:
    try:
        return float(s)
    except ValueError:
        return None


def _build_z3_constraint(lhs_var: z3.ExprRef, op: str,
                          rhs: z3.ExprRef | int | float) -> z3.BoolRef:
    ops = {
        "<":  lhs_var < rhs,
        "<=": lhs_var <= rhs,
        ">":  lhs_var > rhs,
        ">=": lhs_var >= rhs,
        "==": lhs_var == rhs,
        "!=": lhs_var != rhs,
    }
    return ops[op]


def _model_to_values(model: z3.ModelRef, z3_vars: dict[str, z3.ExprRef],
                     var_types: dict[str, str]) -> dict[str, int | float | str]:
    result = {}
    for vname, z3var in z3_vars.items():
        val = model[z3var]
        if val is None:
            result[vname] = 0
        elif z3.is_int_value(val):
            result[vname] = val.as_long()
        elif z3.is_rational_value(val):
            num = val.numerator_as_long()
            den = val.denominator_as_long()
            result[vname] = num / den if den != 0 else num
        else:
            result[vname] = str(val)
    return result


# ---------------------------------------------------------------------------
# Boundary derivation (integer arithmetic, O(1) — no additional z3 solve)
# ---------------------------------------------------------------------------

def _derive_boundary(lhs_name: str, op: str, rhs_val: int | float,
                     var_type: str) -> dict[str, int | float]:
    """Compute the boundary value where the condition flips."""
    if op == ">=":
        return {lhs_name: rhs_val}           # x >= K → boundary is K itself
    if op == ">":
        return {lhs_name: rhs_val + 1}       # x > K  → min TRUE is K+1
    if op == "<=":
        return {lhs_name: rhs_val}           # x <= K → boundary is K itself
    if op == "<":
        return {lhs_name: rhs_val - 1}       # x < K  → max TRUE is K-1
    if op == "==":
        return {lhs_name: rhs_val}           # only one value
    if op == "!=":
        return {lhs_name: rhs_val}           # K is where cond turns FALSE
    return {lhs_name: rhs_val}


# ---------------------------------------------------------------------------
# Main solver
# ---------------------------------------------------------------------------

def solve_condition(cond: ConditionInfo) -> SolverResult:
    """
    Given a ConditionInfo, produce a SolverResult with concrete true/false/boundary values.
    """
    parts = _extract_simple_parts(cond.expr_str)

    if parts is None or len(cond.variables) == 0:
        # Complex expression — cannot solve deterministically
        return SolverResult(
            condition_id=cond.condition_id,
            expr_str=cond.expr_str,
            variables=cond.variables,
            true_values={v: 1 for v in cond.variables},
            false_values={v: 0 for v in cond.variables},
            boundary_values={},
            is_satisfiable=False,
            boundary_flag=False,
            solver_notes="Complex expression — deterministic solving not supported; AI fallback suggested.",
        )

    lhs_name, op, rhs_str = parts

    # Identify variable(s) and constant
    lhs_is_var = lhs_name in cond.variables
    rhs_is_var = rhs_str in cond.variables

    # Build z3 variables
    z3_vars: dict[str, z3.ExprRef] = {}
    for vname in cond.variables:
        z3_vars[vname] = _make_z3_var(vname, cond.inferred_types.get(vname, "int"))

    # Determine RHS z3 expression
    rhs_int = _try_as_int(rhs_str)
    rhs_float = _try_as_float(rhs_str)

    if rhs_is_var and rhs_str in z3_vars:
        rhs_z3 = z3_vars[rhs_str]
    elif rhs_int is not None:
        rhs_z3 = z3.IntVal(rhs_int)
        rhs_numeric = rhs_int
    elif rhs_float is not None:
        rhs_z3 = z3.RealVal(rhs_float)
        rhs_numeric = rhs_float
    else:
        rhs_z3 = z3.IntVal(0)
        rhs_numeric = 0

    if lhs_is_var and lhs_name in z3_vars:
        lhs_z3 = z3_vars[lhs_name]
    else:
        lhs_z3 = z3_vars[cond.variables[0]]

    constraint = _build_z3_constraint(lhs_z3, op, rhs_z3)

    # --- Solve TRUE branch ---
    s_true = z3.Solver()
    s_true.add(constraint)
    true_values: dict = {}
    if s_true.check() == z3.sat:
        true_values = _model_to_values(s_true.model(), z3_vars, cond.inferred_types)
    else:
        true_values = {v: "UNSAT" for v in cond.variables}

    # --- Solve FALSE branch ---
    s_false = z3.Solver()
    s_false.add(z3.Not(constraint))
    false_values: dict = {}
    if s_false.check() == z3.sat:
        false_values = _model_to_values(s_false.model(), z3_vars, cond.inferred_types)
    else:
        false_values = {v: "UNSAT" for v in cond.variables}

    # --- Boundary ---
    boundary_values: dict = {}
    is_satisfiable = true_values.get(lhs_name if lhs_is_var else cond.variables[0]) != "UNSAT"

    if is_satisfiable and lhs_is_var and not rhs_is_var and rhs_numeric is not None:
        boundary_values = _derive_boundary(lhs_name, op, rhs_numeric,
                                           cond.inferred_types.get(lhs_name, "int"))
    elif is_satisfiable:
        # Fallback: boundary = true_value (best-effort)
        boundary_values = dict(true_values)

    # Is boundary value different from plain true value?
    bv = boundary_values.get(lhs_name if lhs_is_var else cond.variables[0] if cond.variables else "")
    tv = true_values.get(lhs_name if lhs_is_var else cond.variables[0] if cond.variables else "")
    boundary_flag = (bv != tv) or op in (">=", "<=", "==")

    notes = f"Solved: {cond.expr_str} → TRUE={true_values}, FALSE={false_values}, boundary={boundary_values}"

    return SolverResult(
        condition_id=cond.condition_id,
        expr_str=cond.expr_str,
        variables=cond.variables,
        true_values=true_values,
        false_values=false_values,
        boundary_values=boundary_values,
        is_satisfiable=is_satisfiable,
        boundary_flag=boundary_flag,
        solver_notes=notes,
    )


def solve_all_conditions(conditions: list[ConditionInfo]) -> list[SolverResult]:
    """Solve all conditions from a ParseResult."""
    return [solve_condition(c) for c in conditions]
