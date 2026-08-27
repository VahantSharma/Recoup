"""A simple token-bucket rate limiter, wrapping the cache-miss path only -- a cache
hit (app.model.cache.CachedProvider) never touches the network, so it's never
rate-limited; composition order is CachedProvider(RateLimitedProvider(real_provider)).

Groq's free-tier limit (30 RPM on openai/gpt-oss-120b) is confirmed against the real
docs (console.groq.com/docs/rate-limits, cited in docs/assumptions.md). Gemini's is
not published for this model/tier as of this session -- GEMINI_DEFAULT_RPM below is a
conservative safety default, not a cited limit; each provider's own exponential
backoff on a real 429 (gemini_provider.py / groq_provider.py, both already built) is
what actually enforces correctness regardless of whether this default is exactly
right.
"""
from __future__ import annotations

import time
from collections import deque

from pydantic import BaseModel

from .provider import ModelProvider, TokenUsage

GROQ_CONFIRMED_RPM = 30
GEMINI_DEFAULT_RPM = 10  # conservative, not cited -- see module docstring


class TokenBucketRateLimiter:
    """Sliding-window request limiter: at most `requests_per_minute` calls to
    acquire() are allowed to return within any trailing 60-second window. Blocks
    (sleeps) rather than raising -- correct for a sequential bake-off/synthesis
    script, not meant for concurrent use."""

    def __init__(self, requests_per_minute: int):
        self.requests_per_minute = requests_per_minute
        self._call_times: deque[float] = deque()

    def acquire(self) -> None:
        now = time.monotonic()
        while self._call_times and now - self._call_times[0] >= 60:
            self._call_times.popleft()
        if len(self._call_times) >= self.requests_per_minute:
            sleep_for = 60 - (now - self._call_times[0])
            if sleep_for > 0:
                time.sleep(sleep_for)
            now = time.monotonic()
            while self._call_times and now - self._call_times[0] >= 60:
                self._call_times.popleft()
        self._call_times.append(time.monotonic())


class RateLimitedProvider:
    """Wraps a real ModelProvider, calling limiter.acquire() before every complete()
    call. Only ever wraps the inner (network-capable) provider -- CachedProvider
    should wrap THIS, not the other way around, so a cache hit skips both the network
    call and the rate limit wait entirely."""

    def __init__(self, inner: ModelProvider, limiter: TokenBucketRateLimiter):
        self.inner = inner
        self.limiter = limiter
        self.name = inner.name
        self.model_id = inner.model_id

    def complete(
        self, prompt: str, schema: type[BaseModel], *, temperature: float = 0.0,
    ) -> tuple[BaseModel, TokenUsage]:
        self.limiter.acquire()
        return self.inner.complete(prompt, schema, temperature=temperature)


def default_limiter_for(provider_name: str) -> TokenBucketRateLimiter:
    if provider_name == "groq":
        return TokenBucketRateLimiter(GROQ_CONFIRMED_RPM)
    if provider_name == "gemini":
        return TokenBucketRateLimiter(GEMINI_DEFAULT_RPM)
    raise ValueError(f"no default rate limit known for provider {provider_name!r}")
