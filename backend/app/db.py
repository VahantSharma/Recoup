"""Database session/engine setup — SQLAlchemy 2.0.

Plain SQLAlchemy models + hand-written Pydantic schemas (schemas.py), not SQLModel —
see the plan's "Decisions worth flagging" note. The persisted row and what's ever
allowed to leave the process (an API response) are meant to be different things on
purpose: `error_description` and internal gate reasoning stay server-side; only vetted
fields reach a response. Two separate classes make that boundary a file you can point
to instead of a discipline you have to remember.
"""
from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker


class Base(DeclarativeBase):
    pass


def _default_db_url() -> str:
    # backend/app/db.py -> backend/ -> repo root -> data/recoup.db
    backend_dir = Path(__file__).resolve().parent.parent
    data_dir = backend_dir.parent / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{(data_dir / 'recoup.db').as_posix()}"


DATABASE_URL = os.environ.get("DATABASE_URL") or _default_db_url()

_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=_connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def init_db() -> None:
    """Create all tables. Safe to call repeatedly (create_all is idempotent)."""
    from . import models  # noqa: F401 — import registers the models on Base.metadata

    Base.metadata.create_all(bind=engine)
