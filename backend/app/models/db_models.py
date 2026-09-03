"""
SQLAlchemy ORM models for run history.
"""
from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy import Column, Integer, String, Text, DateTime
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class AnalysisRun(Base):
    __tablename__ = "analysis_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    function_name = Column(String(128), default="main")
    language = Column(String(32), default="c")
    source_code = Column(Text, nullable=False)
    cfg_json = Column(Text, nullable=False)       # JSON string
    test_cases_json = Column(Text, nullable=False)  # JSON string
    node_count = Column(Integer, default=0)
    edge_count = Column(Integer, default=0)
    test_case_count = Column(Integer, default=0)

    def cfg_dict(self) -> dict:
        return json.loads(self.cfg_json)

    def test_cases_list(self) -> list:
        return json.loads(self.test_cases_json)
