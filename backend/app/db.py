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


_REPO_ROOT = Path(__file__).resolve().parent.parent.parent  # backend/app/db.py -> repo root


def _default_db_url() -> str:
    data_dir = _REPO_ROOT / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{(data_dir / 'recoup.db').as_posix()}"


def _resolve_database_url(raw: str | None) -> str:
    """A relative sqlite:/// DATABASE_URL resolves against the process's cwd, which
    silently landed in two different files once already (Day 1's finding) — and did
    so *again* live during Day 2 verification, from a stale process environment still
    carrying an old .env value after .env itself had been fixed to leave the var
    blank. Leaving DATABASE_URL blank in .env is not sufficient on its own, because
    the harness inherits the launching shell's already-resolved environment for the
    life of a session — this closes the ambiguity at the source instead: any relative
    sqlite path, wherever it came from, resolves against the repo root, never cwd."""
    prefix = "sqlite:///"
    if not raw or not raw.startswith(prefix):
        return _default_db_url()
    path_part = Path(raw[len(prefix):])
    if path_part.is_absolute():
        return raw
    resolved = (_REPO_ROOT / path_part).resolve()
    resolved.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{resolved.as_posix()}"


DATABASE_URL = _resolve_database_url(os.environ.get("DATABASE_URL"))

_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=_connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def init_db() -> None:
    """Create all tables. Safe to call repeatedly (create_all is idempotent)."""
    from . import models  # noqa: F401 — import registers the models on Base.metadata

    Base.metadata.create_all(bind=engine)
