import { useEffect, useState } from "react";
import { loadCaseAudit } from "../lib/artifacts/loader";
import { withProvenance } from "../lib/artifacts/provenance";
import type { ArtifactEnvelope, CaseAuditArtifact, CaseAuditRow } from "../lib/artifacts/types";
import { Figure } from "./Figure";
import { GuardrailTable } from "./GuardrailTable";

const CASE_AUDIT_URL = "/data/case_audit.json";

type LoadState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; envelope: ArtifactEnvelope<CaseAuditArtifact> };

export function CaseAuditScreen() {
  const [state, setState] = useState<LoadState>({ status: "loading" });
  const [selectedId, setSelectedId] = useState<string | null>(null);

  useEffect(() => {
    loadCaseAudit()
      .then((envelope) => {
        setState({ status: "ready", envelope });
        setSelectedId(envelope.data.default_case_id);
      })
      .catch((err: unknown) => {
        setState({ status: "error", message: err instanceof Error ? err.message : String(err) });
      });
  }, []);

  if (state.status === "loading") {
    return <main className="screen"><p>Loading case audit…</p></main>;
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

  return (
    <main className="screen">
      <header className="screen-header">
        <h1>Recoup — Case Audit</h1>
        <p className="screen-subtitle">
          One failed payment, end to end: failure reason, classification, every
          guardrail's real verdict, the proposed action, the idempotency key, the
          outcome.
        </p>
      </header>

      <div className="case-picker">
        <label htmlFor="case-select">case:</label>
        <select
          id="case-select"
          value={selected.case_id}
          onChange={(e) => setSelectedId(e.target.value)}
        >
          {cases.map((c) => (
            <option key={c.case_id} value={c.case_id}>
              {c.case_id} {c.case_kind === "crafted" ? "(crafted)" : ""}
              {c.case_id === envelope.data.default_case_id ? " — default" : ""}
            </option>
          ))}
        </select>
      </div>

      <CaseDetail row={selected} manifest={manifest} artifactUrl={CASE_AUDIT_URL} />

      <section className="unreachable-section">
        <h2>Structurally unreachable guardrails</h2>
        <p className="unreachable-intro">
          Not per-case conditions — properties of the harness itself. No case, corpus or
          crafted, can represent them; see each note for why.
        </p>
        <ul>
          {envelope.data.structurally_unreachable_guardrails.map((n) => (
            <li key={n.name}>
              <strong>{n.name}</strong> — {n.why}
            </li>
          ))}
        </ul>
      </section>
    </main>
  );
}

function CaseDetail({
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

  const permittedText =
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
    <section className="case-detail">
      {row.case_kind === "crafted" && (
        <div className="crafted-banner">
          CRAFTED EXAMPLE — not drawn from the corpus. {row.crafted_note}
        </div>
      )}

      <div className="case-grid">
        <div className="case-field">
          <span className="case-field-label">case id</span>
          <Figure value={p(row.case_id)} />
        </div>
        <div className="case-field">
          <span className="case-field-label">failure reason</span>
          <Figure value={p(row.error_reason ?? "(none)")} />
        </div>
        <div className="case-field">
          <span className="case-field-label">decline_class_source</span>
          <Figure value={p(row.decline_class_source)} />
        </div>
        <div className="case-field">
          <span className="case-field-label">classification</span>
          <Figure value={p(row.decline_class)} />
        </div>
        <div className="case-field">
          <span className="case-field-label">amount</span>
          <Figure value={p(`₹${(row.amount_paise / 100).toFixed(2)}`)} />
        </div>
        <div className="case-field">
          <span className="case-field-label">action</span>
          <Figure value={p(permittedText)} />
        </div>
        <div className="case-field case-field-wide">
          <span className="case-field-label">idempotency key (decisive attempt)</span>
          <Figure value={p(decisive ? decisive.idempotency_key : "(none)")} />
        </div>
        <div className="case-field">
          <span className="case-field-label">final status</span>
          <Figure value={p(row.final_status)} />
        </div>
        <div className="case-field">
          <span className="case-field-label">outcome</span>
          <Figure value={p(row.outcome)} />
        </div>
      </div>

      {decisive && (
        <div className="decisive-gate-call">
          <h3>
            decisive gate call — attempt {decisive.attempt_number}
            {row.gate_calls.length > 1 ? ` (of ${row.gate_calls.length} total)` : ""}
          </h3>
          <GuardrailTable call={decisive} />
        </div>
      )}
    </section>
  );
}
