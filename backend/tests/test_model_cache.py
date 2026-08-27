from __future__ import annotations

import shutil

import pytest
from pydantic import BaseModel

from app.model.cache import CACHE_DIR, CachedProvider, cache_key
from app.model.provider import TokenUsage


class _Tiny(BaseModel):
    value: int


class _CountingFakeProvider:
    name = "fake"
    model_id = "fake-model"

    def __init__(self):
        self.call_count = 0

    def complete(self, prompt, schema, *, temperature=0.0):
        self.call_count += 1
        return schema(value=self.call_count), TokenUsage(provider=self.name, model_id=self.model_id, input_tokens=1, output_tokens=1)


@pytest.fixture(autouse=True)
def _isolated_cache_dir(tmp_path, monkeypatch):
    fake_dir = tmp_path / "model_cache"
    monkeypatch.setattr("app.model.cache.CACHE_DIR", fake_dir)
    yield
    if fake_dir.exists():
        shutil.rmtree(fake_dir)


def test_cache_key_is_deterministic():
    a = cache_key("gemini", "m1", "hello", _Tiny, call_index=0)
    b = cache_key("gemini", "m1", "hello", _Tiny, call_index=0)
    assert a == b


def test_cache_key_differs_by_call_index():
    """The whole point: 20 bake-off calls at the same prompt/schema must NOT collide
    on one cache entry, or the dispersion measurement is fake."""
    keys = {cache_key("gemini", "m1", "hello", _Tiny, call_index=i) for i in range(20)}
    assert len(keys) == 20


def test_cache_key_differs_by_prompt_provider_model_schema():
    base = cache_key("gemini", "m1", "hello", _Tiny, call_index=0)
    assert cache_key("groq", "m1", "hello", _Tiny, call_index=0) != base
    assert cache_key("gemini", "m2", "hello", _Tiny, call_index=0) != base
    assert cache_key("gemini", "m1", "goodbye", _Tiny, call_index=0) != base


def test_second_call_at_the_same_index_is_a_cache_hit_never_touches_inner():
    fake = _CountingFakeProvider()
    provider = CachedProvider(fake, call_index=0)
    result_a, usage_a = provider.complete("prompt", _Tiny)
    result_b, usage_b = provider.complete("prompt", _Tiny)
    assert fake.call_count == 1, "second call should have been served from cache, not the inner provider"
    assert result_a == result_b
    assert usage_a == usage_b


def test_different_call_indices_are_independent_real_calls():
    fake = _CountingFakeProvider()
    results = []
    for i in range(5):
        provider = CachedProvider(fake, call_index=i)
        result, _ = provider.complete("prompt", _Tiny)
        results.append(result.value)
    assert fake.call_count == 5, "each distinct call_index should be a real, independent call"
    assert results == [1, 2, 3, 4, 5]


def test_cache_persists_to_disk_as_json():
    fake = _CountingFakeProvider()
    provider = CachedProvider(fake, call_index=0)
    provider.complete("prompt", _Tiny)
    key = cache_key(fake.name, fake.model_id, "prompt", _Tiny, call_index=0)
    from app.model import cache as cache_module
    assert (cache_module.CACHE_DIR / f"{key}.json").exists()
