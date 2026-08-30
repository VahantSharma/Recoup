"""Proves the DATABASE_URL resolution fix, not just documents it — this bug recurred
live during Day 2 verification (a stale process environment still carried a relative
DATABASE_URL from before .env was fixed to leave it blank), even after Day 1's fix.
_resolve_database_url() closes the ambiguity at the source: any relative sqlite path
resolves against the repo root, regardless of where the raw string came from or what
the process's cwd happens to be."""
from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, inspect, text

from app.db import _REPO_ROOT, _resolve_database_url


def test_blank_or_none_falls_back_to_the_repo_root_default():
    expected = f"sqlite:///{(_REPO_ROOT / 'data' / 'recoup.db').as_posix()}"
    assert _resolve_database_url(None) == expected
    assert _resolve_database_url("") == expected


def test_relative_sqlite_url_resolves_against_repo_root_not_cwd():
    resolved = _resolve_database_url("sqlite:///./data/recoup.db")
    assert resolved == f"sqlite:///{(_REPO_ROOT / 'data' / 'recoup.db').as_posix()}"


def test_relative_sqlite_url_without_leading_dot_also_resolves_against_repo_root():
    resolved = _resolve_database_url("sqlite:///data/recoup.db")
    assert resolved == f"sqlite:///{(_REPO_ROOT / 'data' / 'recoup.db').as_posix()}"


def test_absolute_sqlite_url_is_left_untouched():
    abs_path = (_REPO_ROOT / "somewhere_else" / "custom.db").as_posix()
    raw = f"sqlite:///{abs_path}"
    assert _resolve_database_url(raw) == raw


def test_a_different_relative_path_resolves_to_a_different_absolute_location():
    a = _resolve_database_url("sqlite:///./data/recoup.db")
    b = _resolve_database_url("sqlite:///./data/other.db")
    assert a != b
    assert Path(a[len("sqlite:///"):]).name == "recoup.db"
    assert Path(b[len("sqlite:///"):]).name == "other.db"


# --- init_db() heals a table that predates a new model column -----------------------
#
# Real incident, not a hypothetical: `opt_out` (do-not-disturb) was added to
# PaymentCase, but the actual `data/recoup.db` on disk already had a `payment_cases`
# table from before that change. `Base.metadata.create_all()` only ever creates whole
# tables that don't exist yet -- it silently does nothing for a column added to a
# model whose table is already there. Every test in this suite builds a fresh DB, so
# none of them ever saw it. The one code path that hits the real, persistent file --
# the live endpoint -- started throwing `sqlite3.OperationalError: no such column:
# payment_cases.opt_out` on every single call, invisibly, until it was caught live.
# These tests prove `init_db()`'s healing step against the real db module, not a
# description of it.

def _stale_engine(tmp_path):
    """A real payment_cases table built from the current model, then deliberately
    stripped of `opt_out` -- reproducing exactly what a pre-Day-5-audit database file
    looks like against the post-audit model."""
    from app import db
    from app import models  # noqa: F401 — registers every table on Base.metadata

    engine = create_engine(f"sqlite:///{tmp_path / 'stale.db'}")
    db.Base.metadata.create_all(bind=engine)
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE payment_cases DROP COLUMN opt_out"))
    return engine


def test_init_db_adds_a_column_missing_from_a_pre_existing_table(tmp_path, monkeypatch):
    from app import db

    engine = _stale_engine(tmp_path)
    monkeypatch.setattr(db, "engine", engine)
    assert "opt_out" not in {c["name"] for c in inspect(engine).get_columns("payment_cases")}

    db.init_db()  # the real healing path, unmocked

    columns = {c["name"]: c for c in inspect(engine).get_columns("payment_cases")}
    assert "opt_out" in columns
    # Backfilled to the model's own Python-side default (False -> SQLite's 0), not
    # left to default to NULL -- proves the ALTER TABLE carried a real DEFAULT clause,
    # matching what a freshly-created row would have gotten via the ORM.
    assert str(columns["opt_out"].get("default")).strip("'\" ()") == "0"


def test_init_db_is_idempotent_once_the_table_is_already_current(tmp_path, monkeypatch):
    """Calling init_db() a second time against an already-healed table must not raise
    ('duplicate column name' or similar) and must not touch the schema further."""
    from app import db

    engine = _stale_engine(tmp_path)
    monkeypatch.setattr(db, "engine", engine)

    def _fingerprint(cols):
        # Compare name/nullable/default only -- each get_columns() call returns fresh
        # SQLAlchemy type instances (e.g. two separate VARCHAR() objects) that render
        # identically but aren't `==`, which would make this assert on object identity
        # rather than on whether the schema actually changed.
        return [(c["name"], c["nullable"], c["default"]) for c in cols]

    db.init_db()
    before = _fingerprint(inspect(engine).get_columns("payment_cases"))
    db.init_db()  # second call: must be a real no-op, not just "doesn't crash"
    after = _fingerprint(inspect(engine).get_columns("payment_cases"))
    assert before == after
