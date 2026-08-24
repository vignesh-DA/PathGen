"""
AI Layer — Explanation Chain
=============================
Post-processing step: given a TestCase, call Groq LLM to generate
a one-sentence plain-English explanation.

Called AFTER all deterministic test case generation is complete.
The AI only adds the .explanation field — it never changes input_values,
expected_output, or derivation_method.
"""
from __future__ import annotations

from app.ai.langchain_setup import get_llm, EXPLAIN_PROMPT
from app.core.test_case_builder import TestCase


def explain_test_case(tc: TestCase) -> str:
    """
    Generate a plain-English explanation for a single TestCase.
    Returns the explanation string (or a fallback message if LLM unavailable).
    """
    llm = get_llm()
    if llm is None:
        # Graceful fallback — no API key configured
        conds = tc.path_conditions
        if conds:
            last = conds[-1]
            expr = last.get("condition_expr", "unknown condition")
            branch = last.get("branch_taken", "taken")
            return (
                f"This test case exercises the {branch.upper()} branch of '{expr}' "
                f"with input {tc.input_values}, producing: {tc.expected_output}."
            )
        return f"Test case {tc.test_id} exercises path {tc.path_id}."

    chain = EXPLAIN_PROMPT | llm

    # Build a summary of conditions along the path
    if tc.path_conditions:
        last_cond = tc.path_conditions[-1]
        condition_expr = last_cond.get("condition_expr", "N/A")
        branch_taken = last_cond.get("branch_taken", "N/A")
    else:
        condition_expr = "N/A"
        branch_taken = "N/A"

    try:
        result = chain.invoke({
            "condition_expr": condition_expr,
            "branch_taken": branch_taken,
            "input_values": str(tc.input_values),
            "expected_output": tc.expected_output,
            "boundary_flag": tc.boundary_flag,
        })
        return result.content.strip()
    except Exception as exc:
        return f"Explanation unavailable ({exc})."


def explain_all(test_cases: list[TestCase]) -> list[TestCase]:
    """Attach explanations to all test cases in-place and return the list."""
    for tc in test_cases:
        tc.explanation = explain_test_case(tc)
    return test_cases
