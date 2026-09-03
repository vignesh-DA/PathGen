"""
POST /api/generate-tests
========================
Runs Module 2: takes C source (re-parses internally),
runs symbolic solver + path enumerator + test case builder + AI explanations.
Returns test case list + solver metadata.
"""
from __future__ import annotations

import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.ai.explain_chain import explain_all
from app.core.language_dispatcher import parse_source
from app.core.cfg_builder import build_cfg, cfg_to_json
from app.core.condition_extractor import extract_conditions
from app.core.path_enumerator import enumerate_paths
from app.core.symbolic_solver import solve_all_conditions
from app.core.test_case_builder import build_test_cases
from app.db.session import get_db
from app.models.db_models import AnalysisRun
from app.models.schemas import GenerateTestsRequest, GenerateTestsResponse

router = APIRouter()


@router.post("/generate-tests", response_model=GenerateTestsResponse)
async def generate_tests(
    request: GenerateTestsRequest,
    db: Session = Depends(get_db),
):
    """
    Full pipeline: parse → CFG → symbolic solve → path enumerate → test cases → AI explanations.

    Steps:
    1. Re-parse C source (idempotent)
    2. Build CFG
    3. Solve all conditions with Z3
    4. Enumerate paths (with loop bounds)
    5. Build TestCase objects
    6. Attach AI explanations (LangChain + Groq)
    7. Persist run to SQLite
    8. Return test cases + solver metadata
    """
    if not request.source_code.strip():
        raise HTTPException(status_code=400, detail="source_code must not be empty")

    # Step 1 & 2: Parse + CFG (language-aware)
    parse_result = parse_source(request.source_code, request.language)
    if parse_result.parse_errors and parse_result.ast is None:
        raise HTTPException(
            status_code=422,
            detail={"message": f"Parse error in {request.language}", "errors": parse_result.parse_errors},
        )

    cfg = build_cfg(parse_result, function_name=request.function_name)
    conditions = extract_conditions(parse_result, cfg)

    # Step 3: Symbolic solve
    solver_results_list = solve_all_conditions(conditions)
    solver_by_id = {sr.condition_id: sr for sr in solver_results_list}

    # Step 4: Path enumeration
    paths = enumerate_paths(
        cfg,
        max_paths=request.max_paths,
        max_loop_iters=request.max_loop_iterations,
    )

    # Step 5: Build test cases
    test_cases = build_test_cases(paths, cfg, solver_by_id, conditions)

    # Step 6: AI explanations (post-processing, isolated)
    test_cases = explain_all(test_cases)

    # Step 7: Persist
    cfg_dict = cfg_to_json(cfg)
    tc_dicts = [
        {
            "test_id": tc.test_id,
            "path_id": tc.path_id,
            "input_values": tc.input_values,
            "path_conditions": tc.path_conditions,
            "expected_output": tc.expected_output,
            "boundary_flag": tc.boundary_flag,
            "derivation_method": tc.derivation_method,
            "explanation": tc.explanation,
            "path_steps": tc.path_steps,
        }
        for tc in test_cases
    ]
    run = AnalysisRun(
        function_name=request.function_name,
        language=request.language,
        source_code=request.source_code,
        cfg_json=json.dumps(cfg_dict),
        test_cases_json=json.dumps(tc_dicts),
        node_count=cfg.node_count,
        edge_count=cfg.edge_count,
        test_case_count=len(test_cases),
    )
    db.add(run)
    db.commit()

    # Step 8: Return
    return GenerateTestsResponse(
        test_cases=tc_dicts,
        solver_results=[
            {
                "condition_id": sr.condition_id,
                "expr_str": sr.expr_str,
                "variables": sr.variables,
                "true_values": sr.true_values,
                "false_values": sr.false_values,
                "boundary_values": sr.boundary_values,
                "is_satisfiable": sr.is_satisfiable,
                "boundary_flag": sr.boundary_flag,
                "solver_notes": sr.solver_notes,
            }
            for sr in solver_results_list
        ],
        total_paths_enumerated=len(paths),
        total_test_cases=len(test_cases),
    )
