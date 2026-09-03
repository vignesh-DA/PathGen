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
# Expression resolver — the core engine for output simulation
# ---------------------------------------------------------------------------

def _safe_eval(expr: str, env: dict) -> tuple[bool, object]:
    """Evaluate expr with env bindings. Returns (success, value)."""
    try:
        result = eval(expr, {"__builtins__": {}}, dict(env))  # noqa: S307
        return True, result
    except Exception:
        return False, None


def _resolve_expr(expr: str, input_values: dict) -> str:
    """
    Resolve any single expression to a display string.

    Handles:
      • Variable names            → looked up in input_values
      • String literals           → "hello" / 'hi'
      • f-strings                 → f"age is {age}"
      • JS template literals      → `n = ${n}`
      • Numeric literals          → 42, 3.14
      • Arithmetic / comparisons  → a + b, x >= 18
      • Ternary (JS)              → x > 0 ? "pos" : "neg"
      • Boolean                   → true/false → True/False
      • Any safe Python eval-able expression
    """
    expr = expr.strip().rstrip(";")
    if not expr:
        return ""

    # ── Direct variable ──────────────────────────────────────────────────────
    if expr in input_values:
        return str(input_values[expr])

    # ── Python f-string: f"..." or f'...' ────────────────────────────────────
    if len(expr) > 2 and expr[0] == 'f' and expr[1] in ('"', "'"):
        quote = expr[1]
        if expr.endswith(quote):
            template = expr[2:-1]
        else:
            template = expr[2:]
        return re.sub(r'\{([^}]+)\}',
                      lambda m: _resolve_expr(m.group(1), input_values),
                      template)

    # ── JS template literal: `text ${expr} text` ─────────────────────────────
    if expr.startswith('`') and expr.endswith('`'):
        template = expr[1:-1]
        return re.sub(r'\$\{([^}]+)\}',
                      lambda m: _resolve_expr(m.group(1), input_values),
                      template)

    # ── String literals ───────────────────────────────────────────────────────
    for q in ('"', "'"):
        if expr.startswith(q) and expr.endswith(q) and len(expr) >= 2:
            return expr[1:-1]

    # ── Numeric literals ──────────────────────────────────────────────────────
    try:
        return str(int(expr))
    except ValueError:
        pass
    try:
        return str(float(expr))
    except ValueError:
        pass

    # ── JS ternary: cond ? a : b  →  Python: a if cond else b ────────────────
    ternary = re.match(r'^(.+?)\s*\?\s*(.+?)\s*:\s*(.+)$', expr, re.DOTALL)
    if ternary:
        cond_s, if_s, else_s = ternary.group(1, 2, 3)
        # Normalise JS booleans / null / undefined
        js_norm = {"true": "True", "false": "False", "null": "None",
                   "undefined": "None", "===": "==", "!==": "!="}
        cond_py = cond_s
        for js, py in js_norm.items():
            cond_py = re.sub(rf'\b{js}\b', py, cond_py)
        ok, result = _safe_eval(cond_py, input_values)
        if ok:
            chosen = if_s if result else else_s
            return _resolve_expr(chosen.strip(), input_values)

    # ── Try eval with input values directly ──────────────────────────────────
    # Normalise JS keywords to Python so eval works
    normalised = expr
    for js_kw, py_kw in [("true", "True"), ("false", "False"),
                          ("null", "None"), ("undefined", "None"),
                          ("===", "=="), ("!==", "!=")]:
        normalised = re.sub(rf'\b{js_kw}\b', py_kw, normalised)

    ok, val = _safe_eval(normalised, input_values)
    if ok and val is not None:
        return str(val)

    # ── Substitute variable names, then try eval ─────────────────────────────
    substituted = normalised
    for var, v in sorted(input_values.items(), key=lambda x: -len(x[0])):
        substituted = re.sub(rf'\b{re.escape(str(var))}\b', repr(v), substituted)
    ok, val = _safe_eval(substituted, {})
    if ok and val is not None:
        return str(val)

    return f"<{expr}>"


def _split_args(args_str: str) -> list[str]:
    """Split call arguments by comma, respecting nested parens / string literals."""
    args: list[str] = []
    current: list[str] = []
    depth = 0
    in_str = False
    str_char = ''
    i = 0
    while i < len(args_str):
        c = args_str[i]
        if in_str:
            current.append(c)
            if c == '\\' and i + 1 < len(args_str):
                i += 1
                current.append(args_str[i])
            elif c == str_char:
                in_str = False
        elif c in ('"', "'", '`'):
            in_str, str_char = True, c
            current.append(c)
        elif c in ('(', '[', '{'):
            depth += 1
            current.append(c)
        elif c in (')', ']', '}'):
            depth -= 1
            current.append(c)
        elif c == ',' and depth == 0:
            args.append(''.join(current).strip())
            current = []
        else:
            current.append(c)
        i += 1
    if current:
        args.append(''.join(current).strip())
    return [a for a in args if a]


def _extract_fn_args(stmt: str, fn_names: list[str]) -> list[str] | None:
    """
    Find the first matching function call and return its argument strings,
    using balanced-parenthesis matching (so nested calls work correctly).
    """
    for fn in fn_names:
        # Escape dots (console.log) then search
        pattern = rf'(?<!\w){re.escape(fn)}\s*\('
        m = re.search(pattern, stmt)
        if not m:
            continue
        start = m.end() - 1   # index of '('
        depth = 0
        for i in range(start, len(stmt)):
            if stmt[i] == '(':
                depth += 1
            elif stmt[i] == ')':
                depth -= 1
                if depth == 0:
                    return _split_args(stmt[start + 1: i])
    return None


# ---------------------------------------------------------------------------
# Output simulation — public function
# ---------------------------------------------------------------------------

def _simulate_output(path_steps_nodes: list[dict],
                     input_values: dict[str, int | float | str]) -> str:
    """
    Walk the CFG path nodes and extract any output/return statements.

    Covers virtually all common patterns across C, Python, and JavaScript/TypeScript:
      C       – printf(fmt, ...), return expr;
      Python  – print(*args), print(f"..."), return expr
      JS/TS   – console.log(...), return expr, template literals, ternary
    Uses a safe eval engine to resolve variables, arithmetic, f-strings,
    template literals, and JS ternaries automatically.
    """
    outputs: list[str] = []

    for node in path_steps_nodes:
        for stmt in node.get("statements", []):
            s = stmt.strip()

            # ── C printf ─────────────────────────────────────────────────────

            # printf("literal\n")  — no format specifiers at all
            m = re.search(r'printf\s*\(\s*"([^"\\%]*(\\.[^"\\%]*)*)"\s*\)', s)
            if m:
                raw = m.group(1).replace("\\n", "").replace("\\t", "\t")
                outputs.append(raw)
                continue

            # printf("%s...", "literal")
            m = re.search(r'printf\s*\(\s*"%s[^"]*"\s*,\s*"([^"]*)"\s*\)', s)
            if m:
                outputs.append(m.group(1))
                continue

            # printf("...%d...", var_or_expr)  — any numeric format specifier
            m = re.search(r'printf\s*\(\s*"[^"]*%[diouxXeEfgG][^"]*"\s*,\s*(.+?)\s*\)\s*;?$', s)
            if m:
                outputs.append(_resolve_expr(m.group(1), input_values))
                continue

            # printf("...%s...", var_or_expr)
            m = re.search(r'printf\s*\(\s*"[^"]*%s[^"]*"\s*,\s*(.+?)\s*\)\s*;?$', s)
            if m:
                outputs.append(_resolve_expr(m.group(1), input_values))
                continue

            # ── print() / console.log() ──────────────────────────────────────
            args = _extract_fn_args(s, ["print", "console.log"])
            if args is not None:
                parts = [_resolve_expr(a, input_values) for a in args]
                result = " ".join(p for p in parts if p)
                if result:
                    outputs.append(result)
                continue

            # ── return <expr> ────────────────────────────────────────────────
            m = re.match(r'\breturn\b\s+(.+)', s)
            if m:
                ret_expr = m.group(1).strip().rstrip(';').strip()
                if ret_expr:
                    val = _resolve_expr(ret_expr, input_values)
                    outputs.append(f"return {val}")

    return "; ".join(outputs) if outputs else "<no output>"


# ---------------------------------------------------------------------------
# Path-level Z3 solver  (the real fix — solves the whole path at once)
# ---------------------------------------------------------------------------

import z3 as _z3

from app.core.symbolic_solver import (
    _build_constraint,      # build z3 constraint from a condition string
    _make_typed_var,        # create correctly-typed z3 variable
    _model_to_values,       # extract concrete values from a z3 model
    _normalize_expr,        # JS/TS operator normalisation
    _derive_boundary,       # boundary value derivation
    _extract_simple_parts,  # split "lhs op rhs"
    _try_as_int,
    _try_as_float,
    _canon_type,
)


def _collect_var_types(
    conditions_taken: list[dict],
    solver_results: dict[str, "SolverResult"],
) -> dict[str, str]:
    """Aggregate inferred variable types from all SolverResults on this path."""
    var_types: dict[str, str] = {}
    solver_by_expr = {sr.expr_str: sr for sr in solver_results.values()}
    for cd in conditions_taken:
        expr = cd.get("condition_expr", "")
        sr = solver_by_expr.get(expr)
        if sr:
            # SolverResult doesn't store inferred_types directly, but we can
            # reconstruct from the condition objects via the caller.
            pass
    return var_types


def _unwrap_expr(raw_expr: str) -> str:
    """
    Strip the !(…) wrapper the CFG builder adds to false-branch edges.
    '!(amount <= 0)'  →  'amount <= 0'
    'amount <= 0'     →  'amount <= 0'   (unchanged)
    """
    s = raw_expr.strip()
    if s.startswith("!(") and s.endswith(")"):
        return s[2:-1]
    if s.startswith("!") and not s.startswith("!("):
        return s[1:]
    return s


def _solve_path(
    conditions_taken: list[dict],
    solver_results: dict[str, "SolverResult"],
    conditions: list["ConditionInfo"],
) -> tuple[dict[str, int | float | str], bool, bool, str, dict]:
    """
    Solve the FULL path constraint system with Z3.

    For each condition decision on the path:
      - branch_taken == "true"  → add the condition as-is
      - branch_taken == "false" → add its negation  (stripping !(…) wrapper first)

    All constraints are solved jointly in one z3.Solver call, guaranteeing
    the returned values actually reach this path (no more conflicting merges).

    Returns: (input_values, is_boundary, has_boundary_variant, derivation, boundary_inputs)
    """
    # Build lookup maps — keyed by BARE expression (no !(...) wrapper)
    solver_by_expr: dict[str, SolverResult] = {sr.expr_str: sr for sr in solver_results.values()}
    cond_by_expr:   dict[str, ConditionInfo] = {c.expr_str: c for c in conditions}

    # ── Step 1: collect ALL variable types from ALL conditions in the program ──
    # This ensures unconstrained variables (not in this path) still get a
    # default value of 0 instead of appearing as '?' in the output.
    var_types: dict[str, str] = {}
    for ci in conditions:                              # ← ALL conditions, not just path
        var_types.update(ci.inferred_types or {})

    # Pre-build z3 vars for every known variable (all get a default)
    z3_vars: dict[str, _z3.ExprRef] = {
        v: _make_typed_var(v, var_types.get(v))
        for v in var_types
    }

    # ── Step 2: assemble joint constraints ────────────────────────────────────
    joint_constraints: list[_z3.BoolRef] = []
    all_derived = True
    boundary_exprs: list[tuple[str, str, int | float]] = []   # (var, op, rhs_num)

    for cd in conditions_taken:
        raw_expr = cd.get("condition_expr", "")
        branch   = cd.get("branch_taken", "true")

        if not raw_expr:
            continue

        # Strip !(…) wrapper — the polarity is conveyed by branch, not by !
        bare_expr = _unwrap_expr(raw_expr)
        ci        = cond_by_expr.get(bare_expr)

        # Ensure any variables that appear only in this condition are in z3_vars
        if ci:
            for v in ci.variables:
                if v not in z3_vars:
                    z3_vars[v]    = _make_typed_var(v, (ci.inferred_types or {}).get(v))
                    var_types[v]  = _canon_type((ci.inferred_types or {}).get(v))

        local_types = (ci.inferred_types or {}) if ci else {}
        all_types   = {**var_types, **local_types}

        normalised = _normalize_expr(bare_expr)
        c = _build_constraint(normalised, all_types)
        if c is None:
            all_derived = False
            continue

        # Negate for false branches
        if branch == "false":
            c = _z3.Not(c)

        joint_constraints.append(c)

        # Track simple true-branch conditions for boundary derivation
        if branch == "true":
            parts = _extract_simple_parts(normalised)
            if parts and parts[0] in z3_vars and parts[2] not in z3_vars:
                num = _try_as_int(parts[2])
                if num is None:
                    num = _try_as_float(parts[2])
                if num is not None:
                    boundary_exprs.append((parts[0], parts[1], num))

    # ── Step 3: solve the joint system ───────────────────────────────────────
    if not joint_constraints:
        return _pick_input_values_legacy(conditions_taken, solver_results, conditions)

    solver = _z3.Solver()
    solver.add(*joint_constraints)

    if solver.check() != _z3.sat:
        all_derived = False
        return _pick_input_values_legacy(conditions_taken, solver_results, conditions)

    model = solver.model()
    input_values = _model_to_values(model, z3_vars, var_types)

    # ── Step 4: fill in any unconstrained variables with sane defaults ────────
    # Z3 leaves unconstrained vars out of the model; give them a safe default (0).
    for v in z3_vars:
        if v not in input_values:
            input_values[v] = 0
    # ── Step 5: boundary variant ──────────────────────────────────────────────
    # For each simple true-branch condition with a numeric RHS, try pinning the
    # variable to its boundary value while keeping the rest of the constraints.
    is_boundary = False
    boundary_inputs: dict[str, int | float | str] = {}

    if boundary_exprs and all_derived:
        for var, op, rhs_num in reversed(boundary_exprs):
            bv   = _derive_boundary(var, op, rhs_num, var_types.get(var, "int"))
            bval = bv.get(var)
            if bval is None or bval == input_values.get(var):
                continue
            s2 = _z3.Solver()
            s2.add(*joint_constraints)
            s2.add(z3_vars[var] == (
                _z3.IntVal(int(bval)) if isinstance(bval, int) else _z3.RealVal(float(bval))
            ))
            if s2.check() == _z3.sat:
                boundary_inputs = _model_to_values(s2.model(), z3_vars, var_types)
                # Fill unconstrained vars
                for v in z3_vars:
                    if v not in boundary_inputs:
                        boundary_inputs[v] = input_values.get(v, 0)
                is_boundary = True
            break   # one boundary variant per path

    derivation = "DERIVED (verified)" if all_derived else "AI-SUGGESTED (unverified)"
    return input_values, is_boundary, bool(boundary_inputs), derivation, boundary_inputs


def _pick_input_values_legacy(
    conditions_taken: list[dict],
    solver_results: dict[str, "SolverResult"],
    conditions: list["ConditionInfo"],
) -> tuple[dict[str, int | float | str], bool, bool, str, dict]:
    """
    Legacy per-condition value merging (fallback when Z3 path solve fails).
    Less accurate for multi-variable else-if chains but used as safety net.
    """
    solver_by_expr: dict[str, SolverResult] = {sr.expr_str: sr for sr in solver_results.values()}
    combined: dict[str, int | float | str] = {}
    all_derived = True

    for cd in conditions_taken:
        expr   = cd.get("condition_expr", "")
        branch = cd.get("branch_taken", "true")
        clean  = expr.lstrip("!(").rstrip(")")
        sr     = solver_by_expr.get(expr) or solver_by_expr.get(clean)
        if not sr or not sr.is_satisfiable:
            all_derived = False
            continue
        combined.update(sr.true_values if branch != "false" else sr.false_values)

    derivation = "DERIVED (verified)" if all_derived else "AI-SUGGESTED (unverified)"
    return combined, False, False, derivation, {}


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
    Build one TestCase per unique path, with an optional boundary variant.

    Uses path-level Z3 solving: all conditions along the path are solved
    jointly so the returned input values are guaranteed to actually reach
    that path (fixes the else-if chain constraint propagation bug).

    For paths with a boundary value, two test cases are emitted:
      1. Regular values that traverse the path
      2. Boundary values (e.g. age == 18 for age >= 18)
    """
    test_cases: list[TestCase] = []
    tc_counter = 0

    # Get CFG node data for output simulation
    node_data_map = {nid: data for nid, data in cfg.graph.nodes(data=True)}

    for path in paths:
        # ── Joint Z3 solve for this path ──────────────────────────────────────
        result = _solve_path(path.conditions_taken, solver_results, conditions)
        input_values, _is_bnd, has_boundary, derivation, boundary_inputs = result

        variants: list[tuple[dict, bool, str]] = [
            (input_values, False, derivation),
        ]
        if has_boundary and boundary_inputs:
            variants.append((boundary_inputs, True, derivation))

        for input_vals, boundary_flag, deriv in variants:
            tc_counter += 1
            tc_id = f"TC{tc_counter:02d}"

            path_nodes  = [node_data_map.get(step.node_id, {}) for step in path.steps]
            expected_out = _simulate_output(path_nodes, input_vals)

            test_cases.append(TestCase(
                test_id=tc_id,
                path_id=path.path_id,
                input_values=input_vals,
                path_conditions=path.conditions_taken,
                expected_output=expected_out,
                boundary_flag=boundary_flag,
                derivation_method=deriv,
                explanation="",   # filled by AI layer
                path_steps=[step.node_label for step in path.steps],
            ))

    return test_cases
