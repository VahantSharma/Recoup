"""Run provenance — the DATABASE_URL bug's real lesson made structural.

That bug was caught because two diverging files are visible if you go looking. The
eval-stage version won't announce itself the same way: a stale corpus, a changed seed,
or an uncommitted policy tweak between a control run and a treatment run produces a
number that looks plausible and is wrong for a reason nobody can reconstruct three
days later. Every batch records exactly what produced it, so every number the
dashboard eventually shows resolves to a manifest.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import asdict, is_dataclass
from pathlib import Path

from .db import DATABASE_URL

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def git_sha() -> str:
    """Never lets provenance-gathering itself crash a run — falls back to 'unknown'
    rather than raising, e.g. if git isn't on PATH in some execution environment."""
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=_REPO_ROOT, text=True, stderr=subprocess.DEVNULL
        ).strip()
    except Exception:
        return "unknown"


def db_path() -> str:
    """The absolute-vs-relative DATABASE_URL bug is exactly why this gets snapshotted
    per batch rather than trusted to stay stable as a global for the life of a
    project."""
    return DATABASE_URL


def _json_default(value):
    if hasattr(value, "isoformat"):
        return value.isoformat()
    raise TypeError(f"not JSON-serializable for corpus_hash: {value!r}")


def corpus_hash(drafts: list) -> str:
    """Deterministic hash of the exact cases a run executed over. Same corpus (same
    seed, same params) -> same hash, always — proven by
    tests/test_manifest.py::test_corpus_hash_is_deterministic, not assumed."""
    rows = [asdict(d) if is_dataclass(d) else d for d in drafts]
    serialized = json.dumps(rows, sort_keys=True, default=_json_default)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def params_json(params: dict) -> str:
    return json.dumps(params, sort_keys=True)
