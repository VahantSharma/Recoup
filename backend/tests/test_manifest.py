from datetime import datetime, timezone

from app.corpus_builder import build_corpus
from app.manifest import corpus_hash, db_path, git_sha, params_json


def _start() -> datetime:
    return datetime(2026, 1, 1, tzinfo=timezone.utc)


def test_corpus_hash_is_deterministic_for_identical_inputs():
    a = build_corpus(n=30, seed=42, batch_simulated_start_at=_start())
    b = build_corpus(n=30, seed=42, batch_simulated_start_at=_start())
    assert corpus_hash(a) == corpus_hash(b)


def test_corpus_hash_differs_for_different_seeds():
    a = build_corpus(n=30, seed=1, batch_simulated_start_at=_start())
    b = build_corpus(n=30, seed=2, batch_simulated_start_at=_start())
    assert corpus_hash(a) != corpus_hash(b)


def test_corpus_hash_differs_for_different_n():
    a = build_corpus(n=30, seed=42, batch_simulated_start_at=_start())
    b = build_corpus(n=31, seed=42, batch_simulated_start_at=_start())
    assert corpus_hash(a) != corpus_hash(b)


def test_git_sha_never_raises_and_returns_a_string():
    sha = git_sha()
    assert isinstance(sha, str)
    assert sha  # non-empty — either a real sha or the 'unknown' fallback


def test_db_path_is_a_nonempty_string():
    assert isinstance(db_path(), str)
    assert db_path()


def test_params_json_is_stable_regardless_of_input_dict_order():
    a = params_json({"soft_share": 0.8, "seed": 42})
    b = params_json({"seed": 42, "soft_share": 0.8})
    assert a == b
