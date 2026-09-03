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


# ---------------------------------------------------------------------------
# Expression normalization + compound constraint building
# ---------------------------------------------------------------------------

_TYPE_ALIASES = {
    "int": "int", "float": "float", "double": "float", "real": "float",
    "bool": "bool", "boolean": "bool",
    "str": "str", "string": "str", "char": "str", "String": "str",
}


def _canon_type(t: str | None) -> str:
    return _TYPE_ALIASES.get(t or "int", "int")


def _make_typed_var(name: str, typ: str | None) -> z3.ExprRef:
    t = _canon_type(typ)
    if t == "float":
        return z3.Real(name)
    if t == "bool":
        return z3.Bool(name)
    if t == "str":
        return z3.String(name)
    return z3.Int(name)


def _normalize_expr(expr: str) -> str:
    """Map JS/TS operators to the canonical forms used by the solver."""
    expr = expr.replace("===", "==").replace("!==", "!=")
    expr = re.sub(r"\s*&&\s*", " and ", expr)
    expr = re.sub(r"\s*\|\|\s*", " or ", expr)
    expr = re.sub(r"^\s*!\s*(?=[A-Za-z_(])", "not ", expr)
    return expr.strip()


def _split_top_level(expr: str, sep: str) -> list[str] | None:
    """Split expr on top-level 'sep' (a word), respecting parentheses/brackets."""
    depth = 0
    parts: list[str] = []
    cur: list[str] = []
    i, n = 0, len(expr)
    while i < n:
        ch = expr[i]
        if ch in "([{":
            depth += 1
            cur.append(ch)
        elif ch in ")]}":
            depth -= 1
            cur.append(ch)
        elif depth == 0 and expr[i:i + len(sep)] == sep:
            # sep includes surrounding spaces, so it is already word-delimited
            parts.append("".join(cur).strip())
            cur = []
            i += len(sep)
            continue
        else:
            cur.append(ch)
        i += 1
    parts.append("".join(cur).strip())
    return parts if len(parts) > 1 else None


_CMP_RE = re.compile(r"^\s*(.+?)\s*(===|!==|==|!=|<=|>=|<|>)\s*(.+?)\s*$")


def _atom_to_z3(text: str, var_types: dict[str, str]) -> z3.ExprRef | None:
    """Convert an atomic expression (var, literal, parenthesized) to a z3 expr."""
    text = text.strip()
    if text.startswith("(") and text.endswith(")"):
        inner = _build_constraint(text[1:-1], var_types)
        return inner  # may be BoolRef
    if text in ("true", "True"):
        return z3.BoolVal(True)
    if text in ("false", "False"):
        return z3.BoolVal(False)
    if re.match(r"^['\"].*['\"]$", text):
        return z3.StringVal(text[1:-1])
    try:
        return z3.IntVal(int(text))
    except ValueError:
        pass
    try:
        return z3.RealVal(float(text))
    except ValueError:
        pass
    if re.match(r"^[A-Za-z_][A-Za-z0-9_.]*$", text):
        base = text.split(".")[0]
        return _make_typed_var(base, var_types.get(base))
    return None


def _build_constraint(expr: str, var_types: dict[str, str]) -> z3.BoolRef | None:
    """
    Recursively build a z3 constraint from a (possibly compound) condition.
    Supports and/or/not and single comparisons with typed variables and
    int/float/string/bool literals. Returns None if unsupported.
    """
    expr = _normalize_expr(expr)
    if not expr:
        return None

    for sep, comb in ((" or ", z3.Or), (" and ", z3.And)):
        parts = _split_top_level(expr, sep)
        if parts:
            subs = [_build_constraint(p, var_types) for p in parts]
            if any(s is None for s in subs):
                return None
            return comb(subs)

    # not <expr>
    if expr.startswith("not "):
        inner = _build_constraint(expr[4:], var_types)
        return z3.Not(inner) if inner is not None else None

    m = _CMP_RE.match(expr)
    if not m:
        # Bare truthy expression, e.g. `if flag:` — treat var != 0
        atom = _atom_to_z3(expr, var_types)
        if atom is None:
            return None
        if z3.is_bool(atom):
            return atom
        return atom != z3.IntVal(0)

    lhs_s, op, rhs_s = m.group(1), m.group(2), m.group(3)
    lhs = _atom_to_z3(lhs_s, var_types)
    rhs = _atom_to_z3(rhs_s, var_types)
    if lhs is None or rhs is None:
        return None
    if z3.is_bool(lhs) or z3.is_bool(rhs):
        if op not in ("==", "!="):
            return None
        return (lhs == rhs) if op == "==" else (lhs != rhs)
    if z3.is_string(lhs) or z3.is_string(rhs):
        if op not in ("==", "!="):
            return None
        return (lhs == rhs) if op == "==" else (lhs != rhs)

    ops = {
        "<": lambda: lhs < rhs, "<=": lambda: lhs <= rhs,
        ">": lambda: lhs > rhs, ">=": lambda: lhs >= rhs,
        "==": lambda: lhs == rhs, "!=": lambda: lhs != rhs,
    }
    return ops.get(op, lambda: None)()


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
        elif z3.is_string_value(val):
            result[vname] = val.as_string()
        elif z3.is_true(val):
            result[vname] = True
        elif z3.is_false(val):
            result[vname] = False
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

def _fallback_result(cond: ConditionInfo, notes: str) -> SolverResult:
    """Deterministic solving not possible — deterministic placeholder values."""
    return SolverResult(
        condition_id=cond.condition_id,
        expr_str=cond.expr_str,
        variables=cond.variables,
        true_values={v: 1 for v in cond.variables},
        false_values={v: 0 for v in cond.variables},
        boundary_values={},
        is_satisfiable=False,
        boundary_flag=False,
        solver_notes=notes,
    )


def solve_condition(cond: ConditionInfo) -> SolverResult:
    """
    Given a ConditionInfo, produce a SolverResult with concrete
    true/false/boundary values.

    Handles:
    - Simple comparisons:        x >= 18
    - Compound conditions:       x > 0 && y < 5,  a == 1 or b != 2
    - JS/TS operators:           ===  !==
    - Typed variables:           int, float, bool, string
    - Variable-vs-variable:      x < y
    """
    normalized = _normalize_expr(cond.expr_str)

    if not cond.variables:
        return _fallback_result(cond, "No variables found in condition — AI fallback suggested.")

    # --- For-loop conditions: solved structurally, not via z3 ---
    # `i in range(N)` → true branch: first iteration (i=0), boundary: loop exit
    if cond.ast_node_type == "For" and len(cond.variables) == 1:
        var = cond.variables[0]
        true_values = {var: 0}
        boundary_values = {var: 0}
        m_range = re.match(rf"^{re.escape(var)}\s+in\s+range\((\d+)\)$", normalized)
        if m_range:
            boundary_values = {var: int(m_range.group(1))}
        return SolverResult(
            condition_id=cond.condition_id,
            expr_str=cond.expr_str,
            variables=cond.variables,
            true_values=true_values,
            false_values=boundary_values,
            boundary_values=boundary_values,
            is_satisfiable=True,
            boundary_flag=True,
            solver_notes=(
                f"For loop solved structurally: iteration entry {true_values}, "
                f"loop-exit boundary {boundary_values}"
            ),
        )

    # Typed z3 variables (used for model extraction)
    z3_vars: dict[str, z3.ExprRef] = {
        v: _make_typed_var(v, cond.inferred_types.get(v))
        for v in cond.variables
    }

    constraint = _build_constraint(normalized, cond.inferred_types)
    if constraint is None:
        # Legacy simple path: handle e.g. `x >= 18` even when the compound
        # builder rejects an unusual atom.
        parts = _extract_simple_parts(normalized)
        if parts is not None:
            lhs_name, op, rhs_str = parts
            lhs_z3 = z3_vars.get(lhs_name, z3_vars[cond.variables[0]])
            if rhs_str in z3_vars:
                rhs_z3 = z3_vars[rhs_str]
            elif _try_as_int(rhs_str) is not None:
                rhs_z3 = z3.IntVal(_try_as_int(rhs_str))
            elif _try_as_float(rhs_str) is not None:
                rhs_z3 = z3.RealVal(_try_as_float(rhs_str))
            else:
                rhs_z3 = z3.IntVal(0)
            try:
                constraint = _build_z3_constraint(lhs_z3, op, rhs_z3)
            except KeyError:
                constraint = None
        if constraint is None:
            return _fallback_result(
                cond,
                "Complex expression — deterministic solving not supported; AI fallback suggested.",
            )

    # --- Solve TRUE branch ---
    s_true = z3.Solver()
    s_true.add(constraint)
    if s_true.check() == z3.sat:
        true_values: dict = _model_to_values(s_true.model(), z3_vars, cond.inferred_types)
    else:
        true_values = {v: "UNSAT" for v in cond.variables}
    is_satisfiable = all(true_values.get(v) != "UNSAT" for v in cond.variables)

    # --- Solve FALSE branch ---
    s_false = z3.Solver()
    s_false.add(z3.Not(constraint))
    if s_false.check() == z3.sat:
        false_values: dict = _model_to_values(s_false.model(), z3_vars, cond.inferred_types)
    else:
        false_values = {v: "UNSAT" for v in cond.variables}

    # --- Boundary (only meaningful for simple var-vs-number comparisons) ---
    parts = _extract_simple_parts(normalized)
    lhs_name = parts[0] if parts else cond.variables[0]
    boundary_values: dict = {}
    if is_satisfiable and parts and parts[0] in cond.variables \
            and parts[1] in ("<", "<=", ">", ">=", "==", "!=") \
            and parts[2] not in cond.variables:
        num = _try_as_int(parts[2])
        if num is None:
            num = _try_as_float(parts[2])
        var_type = _canon_type(cond.inferred_types.get(parts[0]))
        if num is not None and var_type in ("int", "float"):
            boundary_values = _derive_boundary(parts[0], parts[1], num,
                                               cond.inferred_types.get(parts[0], "int"))
    elif is_satisfiable:
        # Compound condition: best-effort boundary = true values
        boundary_values = dict(true_values)

    bv = boundary_values.get(lhs_name)
    tv = true_values.get(lhs_name)
    boundary_flag = (bv != tv) or (parts is not None and parts[1] in (">=", "<=", "=="))

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
