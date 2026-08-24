"""
AI Layer — Fallback Chain
==========================
Called only when Module 1 hits a C construct it cannot model
(complex pointer arithmetic, unions, function pointers, etc.).

Returns a test case suggestion tagged "AI-SUGGESTED (unverified)".
"""
from __future__ import annotations

import json

from app.ai.langchain_setup import get_llm, FALLBACK_PROMPT


def suggest_fallback_test(
    construct_description: str,
    source_context: str,
) -> dict | None:
    """
    Ask Groq to suggest a test case for an unsupported C construct.

    Returns a dict with keys: input_values, expected_output, rationale
    or None if LLM unavailable.
    """
    llm = get_llm()
    if llm is None:
        return None

    chain = FALLBACK_PROMPT | llm
    try:
        result = chain.invoke({
            "construct_description": construct_description,
            "source_context": source_context,
        })
        text = result.content.strip()
        # Strip markdown code fences if present
        if text.startswith("```"):
            text = "\n".join(text.split("\n")[1:-1])
        return json.loads(text)
    except Exception as exc:
        return {"error": str(exc), "input_values": {}, "expected_output": "unknown",
                "rationale": "AI fallback failed."}
