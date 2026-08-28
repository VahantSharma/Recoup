"""The single documented command that rebuilds data/recoup.db from scratch.

A judge cloning this repo has no DB file yet -- every other script and the live
endpoint (app.main) already call app.db.init_db() themselves and would create it
implicitly on first run, but "it happened to regenerate as a side effect of some other
command" is not a rebuild command a README can point to. This is.

Safe to run repeatedly: Base.metadata.create_all() only creates tables that don't
already exist -- it never drops or truncates data. To truly start over, delete
data/recoup.db (or whatever DATABASE_URL points at -- see app.db._resolve_database_url)
and run this again.

Run: cd backend && python -m scripts.init_db
"""
from __future__ import annotations

from app.db import DATABASE_URL, init_db


def main() -> None:
    init_db()
    print(f"Initialized (or confirmed) all tables at {DATABASE_URL}")


if __name__ == "__main__":
    main()
