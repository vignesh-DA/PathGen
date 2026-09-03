"""
Database session and initialisation.
"""
from __future__ import annotations

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session

from app.config import settings
from app.models.db_models import Base

engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False},  # SQLite-specific
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    """Create all tables and perform lightweight migrations if needed."""
    Base.metadata.create_all(bind=engine)
    with engine.connect() as conn:
        try:
            result = conn.execute(text("PRAGMA table_info(analysis_runs)"))
            cols = [row[1] for row in result.fetchall()]
            if cols and "language" not in cols:
                conn.execute(text("ALTER TABLE analysis_runs ADD COLUMN language VARCHAR(32) DEFAULT 'c'"))
                conn.commit()
        except Exception:
            pass


def get_db():
    """FastAPI dependency: yields a DB session."""
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()
