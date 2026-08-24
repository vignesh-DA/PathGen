"""
Pydantic v2 schemas for all API request/response bodies.
"""
from __future__ import annotations

from typing import Any
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# /api/analyze
# ---------------------------------------------------------------------------

class AnalyzeRequest(BaseModel):
    source_code: str = Field(..., description="Raw C source code string")
    function_name: str = Field("main", description="Which function to analyse (default: main)")


class ConditionInfoSchema(BaseModel):
    condition_id: str
    expr_str: str
    variables: list[str]
    inferred_types: dict[str, str]
    source_line: int | None
    source_col: int | None
    ast_node_type: str
    operator: str | None


class CFGNodeSchema(BaseModel):
    id: str
    label: str
    block_type: str
    statements: list[str]
    source_lines: list[int]


class CFGEdgeSchema(BaseModel):
    source: str
    target: str
    label: str
    condition: str | None


class AnalyzeResponse(BaseModel):
    function_name: str
    entry_node: str
    exit_node: str
    cyclomatic_complexity: int
    node_count: int
    edge_count: int
    nodes: list[CFGNodeSchema]
    edges: list[CFGEdgeSchema]
    conditions: list[ConditionInfoSchema]
    parse_errors: list[str]
    unsupported_constructs: list[str]


# ---------------------------------------------------------------------------
# /api/generate-tests
# ---------------------------------------------------------------------------

class GenerateTestsRequest(BaseModel):
    source_code: str = Field(..., description="Original C source code")
    function_name: str = Field("main")
    max_paths: int | None = Field(None, description="Override max paths (default from config)")
    max_loop_iterations: int | None = Field(None)


class PathConditionSchema(BaseModel):
    condition_expr: str
    branch_taken: str
    from_node: str
    to_node: str


class TestCaseSchema(BaseModel):
    test_id: str
    path_id: str
    input_values: dict[str, Any]
    path_conditions: list[dict]
    expected_output: str
    boundary_flag: bool
    derivation_method: str
    explanation: str
    path_steps: list[str]


class SolverResultSchema(BaseModel):
    condition_id: str
    expr_str: str
    variables: list[str]
    true_values: dict[str, Any]
    false_values: dict[str, Any]
    boundary_values: dict[str, Any]
    is_satisfiable: bool
    boundary_flag: bool
    solver_notes: str


class GenerateTestsResponse(BaseModel):
    test_cases: list[TestCaseSchema]
    solver_results: list[SolverResultSchema]
    total_paths_enumerated: int
    total_test_cases: int


# ---------------------------------------------------------------------------
# /api/history
# ---------------------------------------------------------------------------

class HistoryItem(BaseModel):
    id: int
    created_at: str
    function_name: str
    source_code_preview: str   # first 200 chars
    node_count: int
    edge_count: int
    test_case_count: int


class HistoryListResponse(BaseModel):
    items: list[HistoryItem]
    total: int


class HistoryDetailResponse(BaseModel):
    id: int
    created_at: str
    source_code: str
    cfg_json: dict
    test_cases: list[TestCaseSchema]
