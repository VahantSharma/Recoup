"""scripts/init_db.py -- the single documented command that rebuilds data/recoup.db
from scratch (CLAUDE.md, README.md's "Running it" -> CLAUDE.md). A judge cloning the
repo needs this to actually create every table, and needs it to be safe to run more
than once."""
from __future__ import annotations

from sqlalchemy import inspect

from app.db import engine
from scripts.init_db import main


def test_init_db_creates_every_table():
    main()
    tables = set(inspect(engine).get_table_names())
    assert {"batches", "payment_cases", "case_attempts"} <= tables


def test_init_db_is_safe_to_run_twice():
    main()
    main()  # must not raise, must not drop/truncate anything
    tables = set(inspect(engine).get_table_names())
    assert {"batches", "payment_cases", "case_attempts"} <= tables
