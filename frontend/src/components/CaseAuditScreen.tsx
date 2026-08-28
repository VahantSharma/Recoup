import { useEffect, useState } from "react";
import "./CaseAuditScreen.css";
import { loadCaseAudit } from "../lib/artifacts/loader";
import { withProvenance } from "../lib/artifacts/provenance";
import { decisiveReason, describeOutcome } from "../lib/outcome";
import type { ArtifactEnvelope, CaseAuditArtifact, CaseAuditRow } from "../lib/artifacts/types";
import { Badge } from "./Badge";
import { CaseList } from "./CaseList";
import { CopyButton } from "./CopyButton";
import { DecisionStep } from "./DecisionStep";
import { Figure } from "./Figure";
import { GuardrailTable } from "./GuardrailTable";
import { InfoTip } from "./InfoTip";

const CASE_AUDIT_URL = "/data/case_audit.json";

type LoadState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; envelope: ArtifactEnvelope<CaseAuditArtifact> };

/** Prefer opening on a case the gate REFUSED -- the strongest, most informative frame
 * -- over the all-passed harvested payment. hard_decline_stop is the strongest
 * refusal per the design review; falls back to the artifact's own default_case_id if
 * no such case exists in this run. The harvested payment stays reachable (and marked
 * "verified live") in the sidebar either way -- it just isn't the opening frame. */
function pickInitialCaseId(artifact: CaseAuditArtifact): string {
  const hardDecline = artifact.cases.find((c) => decisiveReason(c) === "hard_decline_stop");
  if (hardDecline) return hardDecline.case_id;
  const anyRefusal = artifact.cases.find((c) => {
    const r = decisiveReason(c);
    return r != null && r !== "permitted";
  });
  return anyRefusal?.case_id ?? artifact.default_case_id;
}

export function CaseAuditScreen() {
  const [state, setState] = useState<LoadState>({ status: "loading" });
  const [selectedId, setSelectedId] = useState<string | null>(null);

  useEffect(() => {
    loadCaseAudit()
      .then((envelope) => {
        setState({ status: "ready", envelope });
        setSelectedId(pickInitialCaseId(envelope.data));
      })
      .catch((err: unknown) => {
        setState({ status: "error", message: err instanceof Error ? err.message : String(err) });
      });
  }, []);

  if (state.status === "loading") {
    return <main className="screen"><p className="screen-loading">Loading case audit…</p></main>;
  }
  if (state.status === "error") {
    // Loud, visible failure -- never a silent fallback to stale or wrong data.
    return (
      <main className="screen">
        <h1>Case audit — failed to load</h1>
        <pre className="load-error">{state.message}</pre>
      </main>
    );
  }

  const { envelope } = state;
  const { manifest } = envelope;
  const cases = envelope.data.cases;
  const selected = cases.find((c) => c.case_id === selectedId) ?? cases[0];
  const shortSha = manifest.git_sha.slice(0, 7);

  return (
    <main className="screen">
      <div className="masthead">
        <div className="masthead-wordmark">
          <span className="masthead-mark">Recoup</span>
          <span className="masthead-tag">a ledger of every decision, not just the wins</span>
        </div>
        <div className="masthead-right">Case Audit</div>
      </div>
      <p className="screen-subtitle">
        Pick any case on the left. Each one walks the same five questions a payments
        engineer asks: why it failed, how it was classified, what the gate decided and
        why, what happened next, and how it ended.
      </p>

      <div className="provenance-strip">
        Every figure on this page resolves to run manifest{" "}
        <span className="provenance-strip-sha">{shortSha}</span> — click any
        <em> dotted</em> value to see exactly which run produced it.
      </div>

      <div className="screen-layout">
        <CaseList
          cases={cases}
          selectedId={selected.case_id}
          onSelect={setSelectedId}
          liveCaseId={envelope.data.default_case_id}
          unreachable={envelope.data.structurally_unreachable_guardrails}
        />
        <CaseTrace key={selected.case_id} row={selected} manifest={manifest} artifactUrl={CASE_AUDIT_URL} />
      </div>
    </main>
  );
}

function CaseTrace({
  row,
  manifest,
  artifactUrl,
}: {
  row: CaseAuditRow;
  manifest: ArtifactEnvelope<CaseAuditArtifact>["manifest"];
  artifactUrl: string;
}) {
  const decisive = row.gate_calls[row.gate_calls.length - 1] ?? null;
  const p = <T,>(v: T) => withProvenance(v, manifest, artifactUrl);

  const actionText =
    decisive == null
      ? "no action ever proposed"
      : decisive.decision === "approved"
        ? "permitted"
        : decisive.route_to === "NEEDS_REVIEW"
          ? "refused — deferred to human review"
          : decisive.route_to === "NOT_WORKED"
            ? "refused — deliberately not worked (below break-even)"
            : "refused — terminal, no override";

  return (
    <div className="trace">
      {row.case_kind === "crafted" && (
        <div className="crafted-banner">
          CRAFTED EXAMPLE — not drawn from the corpus. {row.crafted_note}
        </div>
      )}

      <DecisionStep number={1} title="Payment failed">
        <div className="kv-row">
          <span className="kv-label">reason</span>
          <Figure value={p(row.error_reason ?? "(none)")} />
        </div>
        <div className="kv-row">
          <span className="kv-label">amount</span>
          <Figure value={p(`₹${(row.amount_paise / 100).toFixed(2)}`)} />
        </div>
        <div className="kv-row">
          <span className="kv-label">
            evidence
            <InfoTip text="harvested = this exact failure was observed on a real Razorpay test-mode API call. documented = a realistic case built from Razorpay's published reason strings, not this specific payment." />
          </span>
          <Figure value={p(row.decline_class_source)} badgeTone={row.decline_class_source === "harvested" ? "ok" : "warn"} />
        </div>
      </DecisionStep>

      <DecisionStep number={2} title="Classified">
        <div className="kv-row">
          <span className="kv-label">
            taxonomy branch
            <InfoTip text="Razorpay publishes the reason string ('debit_instrument_blocked') but not whether it's retryable. Sorting it into hard / soft / technical — and therefore whether a retry is even attempted — is Recoup's own judgment call." />
          </span>
          <Figure value={p(row.decline_class)} />
        </div>
        <p className="step-note">
          This hard/soft/technical classification is Recoup's own work, built on card-network
          convention — Razorpay does not publish this designation alongside its reason strings.
        </p>
      </DecisionStep>

      <DecisionStep number={3} title="Gate evaluated">
        {decisive ? (
          <GuardrailTable call={decisive} />
        ) : (
          <p className="step-note">No gate call was ever made for this case.</p>
        )}
      </DecisionStep>

      <DecisionStep number={4} title="Action">
        <div className="kv-row">
          <span className="kv-label">action</span>
          <Figure value={p(actionText)} />
        </div>
        {decisive?.decision === "approved" ? (
          <div className="kv-row">
            <span className="kv-label">
              idempotency key
              <InfoTip text="A fingerprint of (case, attempt number) checked before every money-touching action. If this exact action were ever replayed — a retry, a crash recovery — the same key catches it and the second attempt becomes a no-op, never a second charge." />
            </span>
            <span className="idempotency-value">
              <Figure value={p(`${decisive.idempotency_key.slice(0, 12)}…`)} mono />
              <CopyButton value={decisive.idempotency_key} />
            </span>
          </div>
        ) : (
          <div className="kv-row">
            <span className="kv-label">
              idempotency key
              <InfoTip text="Only derived once an action actually executes. This case was refused before that point, so there is nothing to replay-protect." />
            </span>
            <span className="step-note-inline">not consumed — no action was taken</span>
          </div>
        )}
      </DecisionStep>

      <DecisionStep number={5} title="Outcome" isLast>
        <div className="kv-row">
          <span className="kv-label">final status</span>
          <Figure value={p(row.final_status)} />
        </div>
        <div className="kv-row">
          <span className="kv-label">outcome</span>
          <Badge label={describeOutcome(row).label} tone={describeOutcome(row).tone} />
        </div>
      </DecisionStep>
    </div>
  );
}
