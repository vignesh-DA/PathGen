"""
POST /api/analyze
=================
Runs Module 1: parse C source → build CFG → extract conditions.
Returns CFG JSON + condition list.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.core.ast_parser import parse_c_source
from app.core.cfg_builder import build_cfg, cfg_to_json
from app.core.condition_extractor import extract_conditions
from app.models.schemas import AnalyzeRequest, AnalyzeResponse

router = APIRouter()


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze(request: AnalyzeRequest):
    """
    Parse C source code and build a Control Flow Graph.

    - Parses the C code using pycparser
    - Walks the AST to build a CFG with networkx
    - Extracts all conditional/branching constructs
    - Returns CFG nodes, edges, and conditions as JSON
    """
    if not request.source_code.strip():
        raise HTTPException(status_code=400, detail="source_code must not be empty")

    # Module 1a: Parse
    parse_result = parse_c_source(request.source_code)

    if parse_result.parse_errors and parse_result.ast is None:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "C source code could not be parsed",
                "errors": parse_result.parse_errors,
            },
        )

    # Module 1b: Build CFG
    cfg = build_cfg(parse_result, function_name=request.function_name)

    # Module 1c: Extract conditions
    conditions = extract_conditions(parse_result, cfg)

    # Serialise CFG to dict
    cfg_dict = cfg_to_json(cfg)

    return AnalyzeResponse(
        function_name=cfg_dict["function_name"],
        entry_node=cfg_dict["entry_node"],
        exit_node=cfg_dict["exit_node"],
        cyclomatic_complexity=cfg_dict["cyclomatic_complexity"],
        node_count=cfg_dict["node_count"],
        edge_count=cfg_dict["edge_count"],
        nodes=cfg_dict["nodes"],
        edges=cfg_dict["edges"],
        conditions=[
            {
                "condition_id": c.condition_id,
                "expr_str": c.expr_str,
                "variables": c.variables,
                "inferred_types": c.inferred_types,
                "source_line": c.source_line,
                "source_col": c.source_col,
                "ast_node_type": c.ast_node_type,
                "operator": c.operator,
            }
            for c in conditions
        ],
        parse_errors=parse_result.parse_errors,
        unsupported_constructs=parse_result.unsupported_constructs,
    )
