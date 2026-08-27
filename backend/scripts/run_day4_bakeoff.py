"""Day 4 Phase C: 20 calls per provider, temperature=0, real Playbook schema, real
synthesis prompt (app.model.playbook_synthesis, built from a real PROPOSAL_SEED run --
no invented numbers). Measures provider reliability/determinism (schema-validation
rate, sensibility rate), NOT whose playbook is better -- held-out lift (Amendment 3)
is computed separately once real playbooks are synthesized and swapped into the
ablation (scripts/run_bound_decomposition.py-style, see scripts/run_day4_ablation.py).

Applies the Phase-B pre-registered abstention rule (app/model/abstention.py)
MECHANICALLY: computes the three checks, reports the values, lets the rule decide. No
judgment exercised about whether abstention "should" fire -- if it fires, that's the
result, reported plainly.

Uses the disk cache (app/model/cache.py, call_index=0..19 so the 20 calls are 20
genuinely independent generations, not one cached response 20 times) and the token-
bucket rate limiter (app/model/ratelimit.py) -- a re-run of this exact script is free
after the first real run.

Run: cd backend && python -m scripts.run_day4_bakeoff
"""
from __future__ import annotations

import json
from pathlib import Path

from app import manifest
from app.model.abstention import decide_abstention
from app.model.cache import CachedProvider, cache_key
from app.model.playbook_schema import PlaybookProposal
from app.model.playbook_synthesis import build_synthesis_prompt, compute_synthesis_stats
from app.model.provider import get_provider
from app.model.ratelimit import RateLimitedProvider, default_limiter_for
from app.model.sensibility import is_sensible, to_sensible_candidate
from app.model.seeds import PROPOSAL_SEED
from app.policy_params import NETWORK_ATTEMPT_BUDGET_PER_CARD_30D

N_CALLS = 20
DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def run_bakeoff_for_provider(provider_name: str, prompt: str) -> dict:
    raw_provider = get_provider(provider_name)
    limiter = default_limiter_for(provider_name)
    rate_limited = RateLimitedProvider(raw_provider, limiter)

    per_call = []
    sensible_candidates = []
    total_input_tokens = 0
    total_output_tokens = 0

    for i in range(N_CALLS):
        cached = CachedProvider(rate_limited, call_index=i)
        key = cache_key(raw_provider.name, raw_provider.model_id, prompt, PlaybookProposal, call_index=i)
        try:
            proposal, usage = cached.complete(prompt, PlaybookProposal, temperature=0.0)
        except Exception as e:  # any failure to produce a schema-valid PlaybookProposal
            per_call.append({"index": i, "cache_key": key, "schema_valid": False, "sensible": False, "reason": f"{type(e).__name__}: {e}"})
            continue

        total_input_tokens += usage.input_tokens
        total_output_tokens += usage.output_tokens
        ok, reason = is_sensible(proposal, NETWORK_ATTEMPT_BUDGET_PER_CARD_30D)
        per_call.append({
            "index": i, "cache_key": key, "schema_valid": True, "sensible": ok, "reason": reason,
            "proposal": proposal.model_dump(),
        })
        if ok:
            sensible_candidates.append(to_sensible_candidate(proposal))

    schema_valid_count = sum(1 for c in per_call if c["schema_valid"])
    sensible_count = sum(1 for c in per_call if c["sensible"])
    verdict = decide_abstention(N_CALLS, sensible_candidates)

    return {
        "provider": provider_name,
        "model_id": raw_provider.model_id,
        "schema_valid_count": schema_valid_count,
        "sensible_count": sensible_count,
        "per_call": per_call,
        "abstained": verdict.abstained,
        "abstain_reason": verdict.reason,
        "total_input_tokens": total_input_tokens,
        "total_output_tokens": total_output_tokens,
    }


def main() -> None:
    stats = compute_synthesis_stats()
    prompt = build_synthesis_prompt(stats)

    print("=== MANIFEST -- Day 4 bake-off ===")
    print(f"git_sha = {manifest.git_sha()}")
    print(f"proposal_seed = {PROPOSAL_SEED}")
    print(f"n_calls_per_provider = {N_CALLS}")
    print(f"prompt_sha256 = {__import__('hashlib').sha256(prompt.encode()).hexdigest()[:16]}")
    print()

    results = {}
    for provider_name in ("gemini", "groq"):
        print(f"--- {provider_name} ---")
        result = run_bakeoff_for_provider(provider_name, prompt)
        results[provider_name] = result
        print(f"model_id: {result['model_id']}")
        print(f"schema_valid: {result['schema_valid_count']}/{N_CALLS}")
        print(f"sensible:     {result['sensible_count']}/{N_CALLS}")
        print(f"abstained (Phase-B rule, applied mechanically): {result['abstained']}")
        if result["abstained"]:
            print(f"  reason: {result['abstain_reason']}")
        print(f"tokens: input={result['total_input_tokens']}  output={result['total_output_tokens']}")
        for c in result["per_call"]:
            if not c["schema_valid"]:
                print(f"  [{c['index']:2}] SCHEMA-INVALID: {c['reason']}")
            elif not c["sensible"]:
                print(f"  [{c['index']:2}] not sensible: {c['reason']}")
        print()

    out_path = DATA_DIR / "day4_bakeoff_results.json"
    out_path.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    print(f"wrote full per-call results to {out_path}")


if __name__ == "__main__":
    main()
