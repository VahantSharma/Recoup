"""Provider-agnostic interface to whatever LLM synthesizes a playbook (Day 4). Nothing
under app/harness/ may import this module or its concrete implementations — see
tests/test_no_model_calls_in_reproducible_paths.py. Only app/model/playbook_synthesis.py
and the scripts under scripts/ that do real synthesis/bake-off work are meant to call
get_provider() for real.

Kept deliberately thin: one method, one usage-accounting shape. Concrete providers
(gemini_provider.py, groq_provider.py) are written against fields confirmed by
introspecting the actually-installed SDK, not against a fetched doc summary — see
docs/assumptions.md's Day 4 section for why that discipline mattered here.
"""
from __future__ import annotations

import os
from typing import Protocol

from dotenv import load_dotenv
from pydantic import BaseModel

# Loads the repo-root .env (python-dotenv walks up from cwd to find it, same as
# every other entry point in this project expects -- see SETUP.md) so
# GEMINI_API_KEY/GROQ_API_KEY/MODEL_PROVIDER are available without requiring the
# caller to have sourced .env into the shell first. Harmless if called more than
# once or if .env doesn't exist (e.g. in CI with real env vars set another way).
load_dotenv()


class TokenUsage(BaseModel):
    provider: str
    model_id: str
    input_tokens: int
    output_tokens: int


class ModelProvider(Protocol):
    name: str
    model_id: str

    def complete(
        self, prompt: str, schema: type[BaseModel], *, temperature: float = 0.0,
    ) -> tuple[BaseModel, TokenUsage]:
        """Sends prompt, asks for structured output conforming to schema, returns the
        parsed object plus real token usage. Never called from anywhere under
        app/harness/."""
        ...


def get_provider(name: str | None = None) -> ModelProvider:
    """Selected by config (MODEL_PROVIDER env var or an explicit arg), never by a
    hardcoded import at a call site -- this is what makes the provider-agnostic claim
    actually true rather than aspirational. Import of the concrete provider modules
    happens inside this function, not at module load time, so importing
    app.model.provider alone (e.g. for the Protocol/TokenUsage types) never pulls in
    a network-capable SDK."""
    selected = name or os.environ.get("MODEL_PROVIDER") or "gemini"
    if selected == "gemini":
        from .gemini_provider import GeminiProvider
        return GeminiProvider()
    if selected == "groq":
        from .groq_provider import GroqProvider
        return GroqProvider()
    raise ValueError(f"unknown MODEL_PROVIDER: {selected!r} (expected 'gemini' or 'groq')")
