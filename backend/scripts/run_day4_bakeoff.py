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
import statistics
from collections import Counter
from pathlib import Path

from app import manifest
from app.export import build_manifest, write_artifact
from app.export_schemas import AbstentionCheckRow, Day4BakeoffArtifact, ProviderBakeoffResult
from app.model.abstention import (
    MAX_CUTOFF_CV,
    MAX_WEIGHT_RATIO_CV,
    MIN_GENERATIONS_FOR_CV,
    MIN_MODAL_AGREEMENT,
    MIN_SENSIBLE_COUNT,
    decide_abstention,
)
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

# The two commits that establish "the abstention rule was written before any bake-off
# result existed" as a checkable fact, not just an assertion -- verified directly via
# `git show --no-patch` this session, not recalled. See docs/results.md's Day 4
# section and interview/18-what-broke-and-how-i-found-it.md for the full account.
ABSTENTION_RULE_COMMIT_SHA = "f4a846362b7c914a04a0614b691a9f02b843ed53"
ABSTENTION_RULE_COMMIT_DATE = "2026-08-24"
BAKEOFF_COMMIT_SHA = "43de681c5509ae9cb020c4c3a4971fb351ddb0f1"
BAKEOFF_COMMIT_DATE = "2026-08-27"


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
        "sensible_candidates": sensible_candidates,  # kept for the Stage 3 export step
                                                        # below -- not part of the raw
                                                        # per-call cache file's own shape
    }


def _coefficient_of_variation(values: list[float]) -> float:
    """Same formula as app.model.abstention's own (private) helper -- recomputed here,
    not imported, since the point of exporting these is showing the actual number Rule
    B compared against its threshold, not just the pass/fail bit."""
    mean = statistics.mean(values)
    return float("inf") if mean == 0 else statistics.pstdev(values) / abs(mean)


def _check_rows(sensible_candidates: list, total_generations: int) -> list[AbstentionCheckRow]:
    """The three pre-registered rules (app.model.abstention.decide_abstention), each
    with the actual computed value against its actual threshold -- Rule B counts as two
    rows here (weight_ratio and defer_priority_cutoff are checked independently, per
    the rule's own docstring: a provider stable on one and scattered on the other must
    not pass silently)."""
    rows = [AbstentionCheckRow(
        rule="A", description="reliability floor -- generations that were schema-valid AND sensible",
        computed_value=f"{len(sensible_candidates)}/{total_generations}",
        threshold=f">= {MIN_SENSIBLE_COUNT}/{total_generations}",
        fired=len(sensible_candidates) < MIN_SENSIBLE_COUNT,
    )]
    if len(sensible_candidates) < MIN_GENERATIONS_FOR_CV:
        rows.append(AbstentionCheckRow(
            rule="B_weight_ratio", description="dispersion of soft/technical priority_weight ratio (CV)",
            computed_value=f"only {len(sensible_candidates)} sensible generations",
            threshold=f">= {MIN_GENERATIONS_FOR_CV} generations needed to measure dispersion", fired=True,
        ))
        rows.append(AbstentionCheckRow(
            rule="B_defer_priority_cutoff", description="dispersion of defer_priority_cutoff (CV)",
            computed_value=f"only {len(sensible_candidates)} sensible generations",
            threshold=f">= {MIN_GENERATIONS_FOR_CV} generations needed to measure dispersion", fired=True,
        ))
    else:
        ratio_cv = _coefficient_of_variation([c.weight_ratio for c in sensible_candidates])
        cutoff_cv = _coefficient_of_variation([c.defer_priority_cutoff for c in sensible_candidates])
        rows.append(AbstentionCheckRow(
            rule="B_weight_ratio", description="dispersion of soft/technical priority_weight ratio (CV)",
            computed_value=f"CV={ratio_cv:.3f}", threshold=f"<= {MAX_WEIGHT_RATIO_CV:.2f}",
            fired=ratio_cv > MAX_WEIGHT_RATIO_CV,
        ))
        rows.append(AbstentionCheckRow(
            rule="B_defer_priority_cutoff", description="dispersion of defer_priority_cutoff (CV)",
            computed_value=f"CV={cutoff_cv:.3f}", threshold=f"<= {MAX_CUTOFF_CV:.2f}",
            fired=cutoff_cv > MAX_CUTOFF_CV,
        ))
    threshold_counts = Counter(c.scarcity_remaining_budget_threshold for c in sensible_candidates)
    if threshold_counts:
        modal_value, modal_count = threshold_counts.most_common(1)[0]
        modal_agreement = modal_count / len(sensible_candidates)
        rows.append(AbstentionCheckRow(
            rule="C", description=f"agreement on scarcity_remaining_budget_threshold (modal value={modal_value})",
            computed_value=f"{modal_agreement:.1%} of {len(sensible_candidates)} sensible generations",
            threshold=f">= {MIN_MODAL_AGREEMENT:.0%}", fired=modal_agreement < MIN_MODAL_AGREEMENT,
        ))
    return rows


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
    raw_dump = {
        name: {k: v for k, v in r.items() if k != "sensible_candidates"}
        for name, r in results.items()
    }
    out_path.write_text(json.dumps(raw_dump, indent=2, default=str), encoding="utf-8")
    print(f"wrote full per-call results to {out_path}")

    # --- Stage 3 export: the bake-off as it happened, plus the three pre-registered
    # abstention checks with their actual computed values -- this is why there's no
    # LLM in the shipped path, and it has to be on screen, not left to a README. ---
    provider_rows = [
        ProviderBakeoffResult(
            provider=name, model_id=r["model_id"], n_calls=N_CALLS,
            schema_valid_count=r["schema_valid_count"], sensible_count=r["sensible_count"],
            abstained=r["abstained"], abstain_reason=r["abstain_reason"],
            checks=_check_rows(r["sensible_candidates"], N_CALLS),
            total_input_tokens=r["total_input_tokens"], total_output_tokens=r["total_output_tokens"],
        )
        for name, r in results.items()
    ]
    artifact = Day4BakeoffArtifact(
        proposal_seed=PROPOSAL_SEED, n_calls_per_provider=N_CALLS,
        abstention_rule_commit_sha=ABSTENTION_RULE_COMMIT_SHA,
        abstention_rule_commit_date=ABSTENTION_RULE_COMMIT_DATE,
        bakeoff_commit_sha=BAKEOFF_COMMIT_SHA, bakeoff_commit_date=BAKEOFF_COMMIT_DATE,
        providers=provider_rows,
    )
    export_manifest = build_manifest(
        script="scripts/run_day4_bakeoff.py", schema_name=Day4BakeoffArtifact.SCHEMA_NAME,
        schema_version=Day4BakeoffArtifact.SCHEMA_VERSION, seed=PROPOSAL_SEED, corpus_hash=None,
        policy_params={}, simulator_params={}, use_common_random_numbers=True,
    )
    artifact_path = write_artifact(
        Day4BakeoffArtifact.SCHEMA_NAME, Day4BakeoffArtifact.SCHEMA_VERSION, export_manifest, artifact,
    )
    print(f"wrote {artifact_path}")


if __name__ == "__main__":
    main()
