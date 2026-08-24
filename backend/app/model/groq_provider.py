"""Groq implementation of ModelProvider. Written against fields confirmed by
introspecting the actually-installed SDK (groq==0.37.1) and one real call.

Confirmed live during Day 4 SDK introspection: strict json_schema mode 400s unless
additionalProperties:false is set on EVERY object in the schema -- fixed at the
schema level (app.model.playbook_schema's model_config = ConfigDict(extra="forbid")),
not here. resp.choices[0].message.content is the raw JSON string (no .parsed
convenience on this SDK -- validated manually via schema.model_validate_json()).
resp.usage.prompt_tokens/.completion_tokens are real ints. Rate-limit exception is
groq.RateLimitError, a real typed exception confirmed against the SDK's own module
listing, not guessed.

Model id: openai/gpt-oss-120b -- confirmed active via client.models.list(), matches
the free-tier rate limits already cited in docs/assumptions.md (30 RPM / 1K RPD / 8K
TPM / 200K TPD, console.groq.com/docs/rate-limits).
"""
from __future__ import annotations

import os
import time

import groq
from pydantic import BaseModel

from .provider import TokenUsage

MODEL_ID = "openai/gpt-oss-120b"
MAX_RETRIES = 5


class GroqProvider:
    name = "groq"
    model_id = MODEL_ID

    def __init__(self):
        api_key = os.environ.get("GROQ_API_KEY")
        if not api_key:
            raise RuntimeError(
                "GROQ_API_KEY not set -- see .env.example (console.groq.com/keys, free, no card)"
            )
        self._client = groq.Groq(api_key=api_key)

    def complete(
        self, prompt: str, schema: type[BaseModel], *, temperature: float = 0.0,
    ) -> tuple[BaseModel, TokenUsage]:
        response_format = {
            "type": "json_schema",
            "json_schema": {
                "name": schema.__name__,
                "schema": schema.model_json_schema(),
                "strict": True,
            },
        }
        delay = 1.0
        last_error: Exception | None = None
        for attempt in range(MAX_RETRIES):
            try:
                response = self._client.chat.completions.create(
                    model=self.model_id,
                    temperature=temperature,
                    messages=[{"role": "user", "content": prompt}],
                    response_format=response_format,
                )
                break
            except groq.RateLimitError as e:
                last_error = e
                if attempt < MAX_RETRIES - 1:
                    time.sleep(delay)
                    delay *= 2
                    continue
                raise
        else:
            raise last_error  # pragma: no cover -- loop always breaks or raises above

        content = response.choices[0].message.content
        parsed = schema.model_validate_json(content)

        usage = TokenUsage(
            provider=self.name,
            model_id=self.model_id,
            input_tokens=response.usage.prompt_tokens or 0,
            output_tokens=response.usage.completion_tokens or 0,
        )
        return parsed, usage
