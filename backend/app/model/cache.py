"""Disk cache for provider calls, keyed on (provider, model_id, prompt, schema,
call_index) -- built FIRST, before any bake-off run, per the explicit instruction: a
cache miss on call 19 of 20 is expensive to redo, and the cache key belongs in the run
manifest so a result still traces to the exact prompt.

call_index matters and is not decorative: the 20-call bake-off's entire point is
measuring DISPERSION across repeated generations at temperature=0 (real providers are
not perfectly deterministic even at temp=0 -- that's the empirical question being
asked). If the cache key were (provider, model_id, prompt, schema) alone, all 20 calls
in one bake-off run would collide on the same key and the 2nd-20th would silently
return the 1st's cached response -- an artificially perfect (and fake) zero-dispersion
result. call_index=0..19 for the bake-off, left at its default (0) for synthesis
(exactly one official call), keeps each of the 20 generations a genuinely independent
API call the first time, while still making a full RE-RUN of either script free.

CACHE_DIR = backend/data/model_cache/ -- its own gitignore entry (not a wildcard on
data/*.json, since backend/data/harvested_corpus.json is real committed data and must
stay tracked).
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from pydantic import BaseModel

from .provider import ModelProvider, TokenUsage

CACHE_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "model_cache"


def cache_key(provider: str, model_id: str, prompt: str, schema: type[BaseModel], call_index: int = 0) -> str:
    payload = {
        "provider": provider, "model_id": model_id, "prompt": prompt,
        "schema": schema.model_json_schema(), "call_index": call_index,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()


class CachedProvider:
    """Wraps a real ModelProvider. A cache hit never touches the network -- this is
    what app.model.ratelimit's token bucket is built to wrap only the miss path of
    (see that module's own docstring)."""

    def __init__(self, inner: ModelProvider, call_index: int = 0):
        self.inner = inner
        self.name = inner.name
        self.model_id = inner.model_id
        self.call_index = call_index
        CACHE_DIR.mkdir(parents=True, exist_ok=True)

    def complete(
        self, prompt: str, schema: type[BaseModel], *, temperature: float = 0.0,
    ) -> tuple[BaseModel, TokenUsage]:
        key = cache_key(self.inner.name, self.inner.model_id, prompt, schema, self.call_index)
        path = CACHE_DIR / f"{key}.json"
        if path.exists():
            cached = json.loads(path.read_text(encoding="utf-8"))
            return schema.model_validate(cached["result"]), TokenUsage(**cached["usage"])

        result, usage = self.inner.complete(prompt, schema, temperature=temperature)
        path.write_text(
            json.dumps({"result": result.model_dump(mode="json"), "usage": usage.model_dump()}, indent=2),
            encoding="utf-8",
        )
        return result, usage
