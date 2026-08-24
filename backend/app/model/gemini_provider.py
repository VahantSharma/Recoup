"""Gemini implementation of ModelProvider. Written against fields confirmed by
introspecting the actually-installed SDK (google-genai==1.2.0) and real calls, not a
fetched doc summary -- prior research this session found the Gemini structured-output
API surface disagreeing across sources (response_schema+.parsed vs.
response_json_schema+.text+manual validation).

Model id: gemini-2.5-flash-lite (the plan's original pick) returned a live 404 --
"no longer available to new users... use models/gemini-3.5-flash-lite" -- confirmed
via the real API at call time, not assumed from any doc.

Schema handling, confirmed live (not assumed): passing our pydantic classes directly
as response_schema fails -- Gemini's internal types.Schema supports only a SUBSET of
JSON Schema (no additionalProperties, no exclusiveMinimum/Maximum; confirmed by
listing types.Schema.model_fields), and app.model.playbook_schema's classes use both
(extra="forbid" for Groq's strict mode, Field(gt=0) for positivity) -- a real,
live-discovered cross-provider incompatibility, not a hypothetical one. Fixed by
sanitizing a copy of the schema for the REQUEST only (strip additionalProperties,
exclusiveMinimum/Maximum -> minimum/maximum) -- Gemini's own process_schema still
inlines $defs from that dict, confirmed working end-to-end. Because response_schema
is then a dict (not the original class), response.parsed comes back as a plain dict,
confirmed live, not the pydantic instance -- so this provider validates response.text
through the ORIGINAL (unsanitized) pydantic class itself, which still enforces the
true gt=0/extra=forbid constraints on the parsed result even though Gemini itself
was never told about them.
"""
from __future__ import annotations

import os
import time

from google import genai
from google.genai import errors, types
from pydantic import BaseModel

from .provider import TokenUsage

MODEL_ID = "gemini-3.5-flash-lite"
MAX_RETRIES = 5


def _gemini_safe_schema(node):
    """Recursively strips JSON-Schema keywords Gemini's types.Schema can't represent.
    minimum/maximum become inclusive approximations of exclusiveMinimum/Maximum --
    slightly looser at the request level, but the true bound is still enforced when
    the response is validated through the original pydantic class afterward."""
    if isinstance(node, dict):
        node = dict(node)
        node.pop("additionalProperties", None)
        if "exclusiveMinimum" in node:
            node["minimum"] = node.pop("exclusiveMinimum")
        if "exclusiveMaximum" in node:
            node["maximum"] = node.pop("exclusiveMaximum")
        return {k: _gemini_safe_schema(v) for k, v in node.items()}
    if isinstance(node, list):
        return [_gemini_safe_schema(v) for v in node]
    return node


class GeminiProvider:
    name = "gemini"
    model_id = MODEL_ID

    def __init__(self):
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise RuntimeError(
                "GEMINI_API_KEY not set -- see .env.example (aistudio.google.com/apikey, free, no card)"
            )
        self._client = genai.Client(api_key=api_key)

    def complete(
        self, prompt: str, schema: type[BaseModel], *, temperature: float = 0.0,
    ) -> tuple[BaseModel, TokenUsage]:
        config = types.GenerateContentConfig(
            temperature=temperature,
            response_mime_type="application/json",
            response_schema=_gemini_safe_schema(schema.model_json_schema()),
        )
        delay = 1.0
        last_error: Exception | None = None
        for attempt in range(MAX_RETRIES):
            try:
                response = self._client.models.generate_content(
                    model=self.model_id, contents=prompt, config=config,
                )
                break
            except errors.APIError as e:
                last_error = e
                if e.code == 429 and attempt < MAX_RETRIES - 1:
                    time.sleep(delay)
                    delay *= 2
                    continue
                raise
        else:
            raise last_error  # pragma: no cover -- loop always breaks or raises above

        # response.parsed is a plain dict here (response_schema was a sanitized dict,
        # not the original class -- confirmed live, see module docstring), so the
        # ORIGINAL pydantic class validates response.text directly -- this is what
        # actually enforces gt=0/extra=forbid, which Gemini itself was never told about.
        try:
            parsed = schema.model_validate_json(response.text)
        except Exception as e:
            raise ValueError(f"Gemini response did not validate as {schema.__name__}: {response.text!r}") from e

        usage = TokenUsage(
            provider=self.name,
            model_id=self.model_id,
            input_tokens=response.usage_metadata.prompt_token_count or 0,
            output_tokens=response.usage_metadata.candidates_token_count or 0,
        )
        return parsed, usage
