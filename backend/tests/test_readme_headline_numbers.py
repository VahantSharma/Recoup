"""README.md's three landing-page headline numbers, cross-checked against the real
committed artifact they're computed from -- the same drift class this project has
already been bitten by more than once (the stale test count, the stale "16 documented
reason strings" claim, the stale "four-arm" evaluation section, all found and fixed in
the same pass this test was added in). A number typed by hand into a markdown file
drifts the moment the underlying data changes and nobody remembers to update the
sentence; this makes that drift a test failure instead of a silent contradiction an
outside reviewer finds first.

If this test fails, the fix is almost always "update the number in README.md to match
what this test just computed from the real artifact" -- not to edit this test, and
not to touch the artifact.
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
README_MD = REPO_ROOT / "README.md"
DOCTRINE_MD = REPO_ROOT / "docs" / "ENGINEERING-DOCTRINE.md"
DAY3_ABLATION_JSON = REPO_ROOT / "frontend" / "public" / "data" / "day3_ablation.json"
DAY4_BOUND_DECOMPOSITION_JSON = REPO_ROOT / "frontend" / "public" / "data" / "day4_bound_decomposition.json"


def _readme_text() -> str:
    return README_MD.read_text(encoding="utf-8")


def _day3_ablation() -> dict:
    return json.loads(DAY3_ABLATION_JSON.read_text(encoding="utf-8"))["data"]


def _day4_bound_decomposition() -> dict:
    return json.loads(DAY4_BOUND_DECOMPOSITION_JSON.read_text(encoding="utf-8"))["data"]


def test_readme_rules_only_lift_matches_the_real_artifact():
    data = _day3_ablation()
    row = next(l for l in data["lifts"] if l["arm_a"] == "rules_only" and l["arm_b"] == "control")
    expected = f"+{row['rate_lift'] * 100:.1f}pp"
    assert expected in _readme_text(), (
        f"README.md's headline lift number is stale -- the real artifact "
        f"(day3_ablation.json) currently computes {expected!r}, but that string isn't "
        "in README.md. Update the '## Three numbers, checkable in one command each' "
        "section."
    )


def test_readme_blind_retry_violations_matches_the_real_artifact():
    data = _day3_ablation()
    violations = data["compliance"]["violations_blind_retry"]
    expected = f"{violations:,}"
    assert expected in _readme_text(), (
        f"README.md's headline violations number is stale -- the real artifact "
        f"currently reports {expected!r} violations for blind_retry, but that string "
        "isn't in README.md."
    )


def test_readme_guardrail_reachability_matches_the_real_artifact():
    data = _day3_ablation()
    real_guardrails = [g for g in data["guardrail_reachability"] if g["name"] != "permitted"]
    reachable = sum(1 for g in real_guardrails if g["reachable"])
    expected = f"{reachable} of {len(real_guardrails)}"
    assert expected in _readme_text(), (
        f"README.md's headline guardrail-reachability number is stale -- the real "
        f"artifact currently shows {expected!r} guardrails reachable in this batch, "
        "but that string isn't in README.md."
    )


def test_readme_bound_decomposition_gaps_match_the_real_artifact():
    """The two gaps in the 'three bounds' diagram -- achieved to observable-optimal,
    observable-optimal to oracle. Both are Day 4 numbers, currently pending
    verification (see docs/results.md's Correction section) -- this test only checks
    that whatever value README.md prints for them is the real, current one; it doesn't
    (and can't) check that the underlying pipeline has been re-verified."""
    data = _day4_bound_decomposition()
    gap1 = data["rate_gap1"]["in_sample"] * 100
    gap2 = data["rate_gap2"]["in_sample"] * 100
    expected_gap1 = f"{gap1:+.1f}pp"
    expected_gap2 = f"{gap2:+.1f}pp"
    text = _readme_text()
    assert expected_gap1 in text, (
        f"README.md's achieved->observable-optimal gap is stale -- the real artifact "
        f"(day4_bound_decomposition.json) currently computes {expected_gap1!r}."
    )
    assert expected_gap2 in text, (
        f"README.md's observable-optimal->oracle gap is stale -- the real artifact "
        f"currently computes {expected_gap2!r}."
    )


def test_readme_test_count_badge_matches_the_real_suite():
    """The test-count badge in README.md's title block is a number embedded in a
    shields.io URL -- exactly as prone to silent drift as any other hand-typed figure,
    just easier to overlook since it's inside a Markdown image, not prose. Reuses
    docs/ENGINEERING-DOCTRINE.md's own already-verified count (test_docs_test_count.py
    keeps THAT number honest against the real suite) rather than re-collecting the
    suite a second time in this file."""
    doctrine_text = DOCTRINE_MD.read_text(encoding="utf-8")
    match = re.search(r"\((\d+) tests as of Day 5", doctrine_text)
    assert match, "docs/ENGINEERING-DOCTRINE.md's test-count sentence wasn't found"
    documented = match.group(1)
    text = _readme_text()
    assert f"tests-{documented}" in text or f"tests_{documented}" in text, (
        f"README.md's test-count badge doesn't mention {documented!r} -- the number "
        "in docs/ENGINEERING-DOCTRINE.md's own count, which test_docs_test_count.py "
        "already keeps honest against the real suite."
    )


def test_verify_md_and_architecture_md_exist_and_are_linked_from_readme():
    """README.md's own top section promises VERIFY.md and architecture.md exist --
    prove the links aren't dead, not just that the sentence reads well."""
    assert (REPO_ROOT / "VERIFY.md").is_file()
    assert (REPO_ROOT / "architecture.md").is_file()
    text = _readme_text()
    assert "VERIFY.md" in text
    assert "architecture.md" in text


def test_readme_links_to_reviewing_and_docs_index_and_repo_map_covers_top_level():
    """REVIEWING.md and docs/README.md both exist and are linked; the repo-map table
    doesn't have to be exhaustive but must at least name every top-level directory a
    reviewer would actually clone and see."""
    assert (REPO_ROOT / "REVIEWING.md").is_file()
    assert (REPO_ROOT / "docs" / "README.md").is_file()
    text = _readme_text()
    assert "REVIEWING.md" in text
    # Tracked directories only, via `git ls-files` -- not a raw filesystem walk. A
    # gitignored local-only directory (e.g. interview/, kept on disk but untracked)
    # is real on THIS machine but doesn't exist in a fresh clone; requiring README.md
    # to mention it would make this test's outcome depend on whose machine runs it.
    result = subprocess.run(
        ["git", "ls-tree", "-d", "--name-only", "HEAD"],
        cwd=REPO_ROOT, capture_output=True, text=True, check=True,
    )
    top_level_dirs = {line for line in result.stdout.splitlines() if line}
    for name in top_level_dirs:
        assert name in text, f"'{name}/' is a real top-level directory but isn't mentioned anywhere in README.md"
