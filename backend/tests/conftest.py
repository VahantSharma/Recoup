"""Point the app at a throwaway temp-file SQLite DB before any `app.*` module is
imported, so running the test suite never touches the real data/recoup.db."""
import os
import tempfile
from pathlib import Path

_tmp_dir = tempfile.mkdtemp(prefix="recoup_test_")
os.environ["DATABASE_URL"] = f"sqlite:///{Path(_tmp_dir, 'test_recoup.db').as_posix()}"
