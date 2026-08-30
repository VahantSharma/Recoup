"""Database session/engine setup — SQLAlchemy 2.0.

Plain SQLAlchemy models + hand-written Pydantic schemas (schemas.py), not SQLModel —
see the plan's "Decisions worth flagging" note. The persisted row and what's ever
allowed to leave the process (an API response) are meant to be different things on
purpose: `error_description` and internal gate reasoning stay server-side; only vetted
fields reach a response. Two separate classes make that boundary a file you can point
to instead of a discipline you have to remember.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

logger = logging.getLogger(__name__)


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

# timeout=15: how long a write waits for another connection's lock to clear before
# raising "database is locked" -- Python's sqlite3 default is 5s, confirmed live
# (adversarial pass) to actually raise sqlite3.OperationalError under real contention
# at that default (one connection holding a write transaction, a second one blocked
# behind it). 15s matches the live endpoint's own httpx timeout on the Razorpay calls
# it brackets, so a demo request's slowest-plausible path is bounded by one number,
# not two different ones. Does not eliminate the possibility of a locked-database
# error under sustained contention (that would need WAL mode and/or an explicit
# retry), only makes the realistic single-extra-request case (e.g. a judge
# double-clicking "verify") survive instead of failing on the default timeout.
_connect_args = {"check_same_thread": False, "timeout": 15} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=_connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def _sql_default_literal(value: object) -> str | None:
    """A model-side `mapped_column(default=...)` is a Python-only default -- it fills
    in a value when the ORM builds a new row, but never reaches the table's real DDL,
    so it can't backfill a column added to an existing table (see `_add_missing_columns`
    below). Where the default is one of these simple, unambiguous scalar kinds, reuse
    it as the ALTER TABLE's own DEFAULT so existing rows land on the same value a
    freshly-created row would have gotten, instead of NULL. Anything else (a callable
    like `_new_id`, or no default at all) is left for `_add_missing_columns` to add
    without one -- correct for existing rows only if the app never assumes non-NULL
    there, which is true for every case this has actually hit so far."""
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return "'" + value.replace("'", "''") + "'"
    return None


def _add_missing_columns() -> None:
    """No Alembic migration tooling exists yet (a disclosed, standing gap — see
    docs/ENGINEERING-DOCTRINE.md / docs/buildathon-plan.md's open items). `Base.metadata.create_all()`
    only ever creates whole tables that don't exist yet; it silently does nothing for
    a column added to a model whose table already exists on disk -- confirmed live the
    hard way when `opt_out` was added to PaymentCase (do-not-disturb): every test
    passed (they build a fresh DB), but the one code path that hits the real, persistent
    `data/recoup.db` -- the live endpoint -- started throwing `sqlite3.OperationalError:
    no such column: payment_cases.opt_out` on every call, invisibly, because nothing
    ever restarts that file's schema.

    This closes that whole bug class at the source rather than the one instance: for
    every table this app defines, add whatever columns the model declares that the
    real table on disk is still missing. Safe to run every time `init_db()` runs --
    an already-current table has nothing to add and this is a no-op for it."""
    inspector = inspect(engine)
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if not inspector.has_table(table.name):
                continue  # a brand-new table -- create_all() just handled it in full
            existing_columns = {c["name"] for c in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name in existing_columns:
                    continue
                col_type = column.type.compile(dialect=engine.dialect)
                default_literal = None
                if column.default is not None and getattr(column.default, "is_scalar", False):
                    default_literal = _sql_default_literal(column.default.arg)
                ddl = f"ALTER TABLE {table.name} ADD COLUMN {column.name} {col_type}"
                if default_literal is not None:
                    ddl += f" DEFAULT {default_literal}"
                logger.warning(
                    "db schema drift: table %r existed on disk without column %r -- "
                    "adding it now (%s)", table.name, column.name, ddl,
                )
                conn.execute(text(ddl))


def init_db() -> None:
    """Create all tables, then heal any existing table that predates a column its
    model has since grown. Safe to call repeatedly -- create_all is idempotent, and
    _add_missing_columns is a no-op once a table is current."""
    from . import models  # noqa: F401 — import registers the models on Base.metadata

    Base.metadata.create_all(bind=engine)
    _add_missing_columns()
