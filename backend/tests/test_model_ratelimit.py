from __future__ import annotations

import time

from pydantic import BaseModel

from app.model.provider import TokenUsage
from app.model.ratelimit import RateLimitedProvider, TokenBucketRateLimiter, default_limiter_for


class _Tiny(BaseModel):
    value: int


class _FakeProvider:
    name = "fake"
    model_id = "fake-model"

    def __init__(self):
        self.call_count = 0

    def complete(self, prompt, schema, *, temperature=0.0):
        self.call_count += 1
        return schema(value=self.call_count), TokenUsage(provider=self.name, model_id=self.model_id, input_tokens=1, output_tokens=1)


def test_bucket_allows_up_to_the_limit_without_blocking():
    limiter = TokenBucketRateLimiter(requests_per_minute=5)
    start = time.monotonic()
    for _ in range(5):
        limiter.acquire()
    elapsed = time.monotonic() - start
    assert elapsed < 1.0, "should not have blocked for the first 5 calls within the limit"


def test_bucket_sleeps_for_the_6th_call_within_the_window(monkeypatch):
    """Verifies the sleep DECISION and its approximate duration without actually
    waiting ~60s in the test suite -- time.sleep is mocked, not the limiter's logic."""
    slept_for = []
    monkeypatch.setattr("app.model.ratelimit.time.sleep", lambda seconds: slept_for.append(seconds))

    limiter = TokenBucketRateLimiter(requests_per_minute=5)
    now = time.monotonic()
    for _ in range(5):
        limiter._call_times.append(now)
    limiter.acquire()  # 6th call, window still full -- should sleep, not raise or return instantly

    assert len(slept_for) == 1
    assert 55 < slept_for[0] <= 60, f"expected to sleep ~60s for the window to clear, got {slept_for[0]:.1f}s"


def test_rate_limited_provider_calls_acquire_before_every_complete():
    limiter = TokenBucketRateLimiter(requests_per_minute=1000)
    calls = []
    original_acquire = limiter.acquire

    def _tracked_acquire():
        calls.append(True)
        original_acquire()

    limiter.acquire = _tracked_acquire
    fake = _FakeProvider()
    provider = RateLimitedProvider(fake, limiter)
    provider.complete("prompt", _Tiny)
    provider.complete("prompt", _Tiny)
    assert len(calls) == 2
    assert fake.call_count == 2


def test_default_limiter_for_groq_matches_the_confirmed_rpm():
    from app.model.ratelimit import GROQ_CONFIRMED_RPM

    limiter = default_limiter_for("groq")
    assert limiter.requests_per_minute == GROQ_CONFIRMED_RPM == 30


def test_default_limiter_for_unknown_provider_raises():
    import pytest

    with pytest.raises(ValueError):
        default_limiter_for("not-a-real-provider")
