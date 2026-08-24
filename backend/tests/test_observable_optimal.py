from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.corpus_builder import build_corpus
from app.harness.observable_optimal import (
    ATTEMPT_PENALTY_GRID,
    DEFER_CUTOFF_GRID,
    SCARCITY_THRESHOLD_GRID,
    STALENESS_PENALTY_PER_DAY_GRID,
    TICKET_SIZE_BONUS_GRID,
    WEIGHT_RATIO_GRID,
    ObservableOptimalParams,
    ObservableOptimalPolicy,
    run_observable_optimal_search,
)
from app.harness.run import run_arm


def _corpus(n=300, seed=42):
    return build_corpus(n=n, seed=seed, batch_simulated_start_at=datetime(2026, 1, 1, tzinfo=timezone.utc))


def test_never_touches_app_simulator():
    """Structural claim from the module docstring, checked directly: this file
    imports nothing from app.simulator, unlike oracle.py."""
    import ast
    from pathlib import Path

    path = Path(__file__).resolve().parent.parent / "app" / "harness" / "observable_optimal.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            assert "simulator" not in module.split("."), f"unexpected simulator import: {module}"
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert "simulator" not in alias.name.split("."), f"unexpected simulator import: {alias.name}"


def test_conforms_to_the_policy_protocol_shape():
    import inspect

    from app.harness.policies import Policy

    policy_params_ = list(inspect.signature(ObservableOptimalPolicy.propose).parameters)
    protocol_params = list(inspect.signature(Policy.propose).parameters)
    assert policy_params_ == protocol_params


def test_runs_through_the_unmodified_harness():
    params = ObservableOptimalParams(1.0, 1, 1.0, 0.0, 0.0, 0.0)
    corpus = _corpus()
    rows = run_arm(corpus, ObservableOptimalPolicy(params), 42, 24, 45)
    assert len(rows) == len(corpus)


def test_search_scores_every_combination_and_is_deterministic():
    corpus = _corpus(n=200)
    winner_a, nv_a = run_observable_optimal_search(corpus=corpus)
    winner_b, nv_b = run_observable_optimal_search(corpus=corpus)
    assert winner_a == winner_b
    assert nv_a == nv_b
    assert winner_a.weight_ratio in WEIGHT_RATIO_GRID
    assert winner_a.scarcity_threshold in SCARCITY_THRESHOLD_GRID
    assert winner_a.defer_cutoff in DEFER_CUTOFF_GRID
    assert winner_a.ticket_size_bonus in TICKET_SIZE_BONUS_GRID
    assert winner_a.attempt_penalty in ATTEMPT_PENALTY_GRID
    assert winner_a.staleness_penalty_per_day in STALENESS_PENALTY_PER_DAY_GRID


def test_never_touches_a_held_out_seed():
    import ast
    from pathlib import Path

    path = Path(__file__).resolve().parent.parent / "app" / "harness" / "observable_optimal.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imported_names = {
        alias.asname or alias.name
        for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
        for alias in node.names
    }
    assert "HELD_OUT_SEEDS" not in imported_names
