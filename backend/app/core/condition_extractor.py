"""
condition_extractor.py
======================
Thin wrapper that combines ast_parser + cfg_builder outputs into
a clean ConditionInfo list with node-level metadata for the API response.
"""
from __future__ import annotations

from app.core.ast_parser import ConditionInfo, ParseResult
from app.core.cfg_builder import CFGGraph


def extract_conditions(parse_result: ParseResult, cfg: CFGGraph) -> list[ConditionInfo]:
    """
    Return the conditions from the parse result, enriched with CFG node
    context (which CFG node each condition belongs to, if determinable).

    Currently a pass-through; future work can cross-reference CFG node ids.
    """
    return parse_result.conditions
