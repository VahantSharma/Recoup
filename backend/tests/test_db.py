"""Proves the DATABASE_URL resolution fix, not just documents it — this bug recurred
live during Day 2 verification (a stale process environment still carried a relative
DATABASE_URL from before .env was fixed to leave it blank), even after Day 1's fix.
_resolve_database_url() closes the ambiguity at the source: any relative sqlite path
resolves against the repo root, regardless of where the raw string came from or what
the process's cwd happens to be."""
from __future__ import annotations

from pathlib import Path

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
