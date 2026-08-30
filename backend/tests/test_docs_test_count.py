"""docs/ENGINEERING-DOCTRINE.md's Stack & commands section states a specific test count
-- an adversarial pass (`docs/audit.md`) found it stale (claimed 249, actual was already
266+ at the time) and fixed it, but a hand-fixed number drifts again the next time a
test is added without anyone remembering to update a sentence in a markdown file. This
is the structural guard against a repeat: it re-collects the real suite (a subprocess,
not introspection of the currently-running session, since this session's own count
isn't final until collection for the WHOLE run completes) and asserts the doctrine
file's stated number still matches it exactly.

Reads `docs/ENGINEERING-DOCTRINE.md` directly, not the repo-root `CLAUDE.md` stub --
the stub is now three lines that `@`-import the real content for Claude Code's own
tooling, and no longer contains the sentence this test looks for.

If this test fails, the fix is almost always "update the number in
docs/ENGINEERING-DOCTRINE.md to match what's printed below" -- not to edit this test.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DOCTRINE_MD = REPO_ROOT / "docs" / "ENGINEERING-DOCTRINE.md"
BACKEND_DIR = REPO_ROOT / "backend"

# Matches "289 tests as of Day 5" -- deliberately anchored to this exact phrase rather
# than any number in the file, so this can't accidentally match an unrelated digit
# elsewhere in the doctrine file.
_COUNT_PATTERN = re.compile(r"\((\d+) tests as of Day 5")


def _documented_test_count() -> int:
    text = DOCTRINE_MD.read_text(encoding="utf-8")
    match = _COUNT_PATTERN.search(text)
    assert match, (
        "docs/ENGINEERING-DOCTRINE.md's Stack & commands section no longer contains "
        "the expected '(NNN tests as of Day 5' phrase this test looks for -- update "
        "_COUNT_PATTERN if the sentence was deliberately reworded, don't just delete "
        "this test"
    )
    return int(match.group(1))


def _actual_test_count() -> int:
    # A real subprocess collection, not this session's own sys.modules state -- the
    # only way to get the true total for the whole suite, including this file itself,
    # without depending on pytest-internal hooks that would make the check itself
    # fragile to unrelated pytest version changes.
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q"],
        cwd=BACKEND_DIR, capture_output=True, text=True, timeout=120,
    )
    match = re.search(r"(\d+) tests? collected", result.stdout)
    assert match, f"could not parse a test count from pytest --collect-only output:\n{result.stdout}\n{result.stderr}"
    return int(match.group(1))


def test_doctrine_md_test_count_matches_the_real_suite():
    documented = _documented_test_count()
    actual = _actual_test_count()
    assert documented == actual, (
        f"docs/ENGINEERING-DOCTRINE.md says '{documented} tests as of Day 5', but the "
        f"real suite currently collects {actual} -- update the number in that file's "
        "Stack & commands section to match (this is almost always the fix; the test "
        "count is expected to grow)"
    )
