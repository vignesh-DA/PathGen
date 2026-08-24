"""
GET /api/history
GET /api/history/{run_id}
=========================
Retrieve stored analysis runs from SQLite.
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.db_models import AnalysisRun
from app.models.schemas import HistoryListResponse, HistoryDetailResponse, HistoryItem

router = APIRouter()


@router.get("/history", response_model=HistoryListResponse)
async def list_history(
    limit: int = 20,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    """Return a paginated list of past analysis runs."""
    total = db.query(AnalysisRun).count()
    runs = (
        db.query(AnalysisRun)
        .order_by(AnalysisRun.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    items = [
        HistoryItem(
            id=r.id,
            created_at=r.created_at.isoformat(),
            function_name=r.function_name or "main",
            source_code_preview=r.source_code[:200],
            node_count=r.node_count,
            edge_count=r.edge_count,
            test_case_count=r.test_case_count,
        )
        for r in runs
    ]
    return HistoryListResponse(items=items, total=total)


@router.get("/history/{run_id}", response_model=HistoryDetailResponse)
async def get_history_run(run_id: int, db: Session = Depends(get_db)):
    """Return full detail for a single stored run."""
    run = db.query(AnalysisRun).filter(AnalysisRun.id == run_id).first()
    if run is None:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
    return HistoryDetailResponse(
        id=run.id,
        created_at=run.created_at.isoformat(),
        source_code=run.source_code,
        cfg_json=run.cfg_dict(),
        test_cases=run.test_cases_list(),
    )
