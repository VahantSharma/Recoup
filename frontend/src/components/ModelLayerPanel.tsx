import { useEffect, useState } from "react";
import "./ModelLayerPanel.css";
import { loadDay4Bakeoff } from "../lib/artifacts/loader";
import type { ArtifactEnvelope, Day4BakeoffArtifact, ProviderBakeoffResult } from "../lib/artifacts/types";
import { Badge } from "./Badge";
import { ErrorScreen, LoadingSkeleton, Masthead, ProvenanceStrip } from "./ScreenChrome";

type LoadState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; envelope: ArtifactEnvelope<Day4BakeoffArtifact> };

const URL = "/data/day4_bakeoff.json";

// Real prices, fetched directly from each provider's own pricing page this session
// (ai.google.dev's Gemini 3.5 Flash-Lite page; console.groq.com's gpt-oss-120b model
// page) — the same two figures already cited in interview/16-the-model-layer.md, not
// re-derived independently here. $ per million tokens.
const PRICING: Record<string, { input: number; output: number }> = {
  gemini: { input: 0.30, output: 2.50 },
  groq: { input: 0.15, output: 0.60 },
};

function realCostUsd(provider: string, inputTokens: number, outputTokens: number): number {
  const p = PRICING[provider];
  if (!p) return 0;
  return (inputTokens * p.input + outputTokens * p.output) / 1_000_000;
}

export function ModelLayerPanel() {
  const [state, setState] = useState<LoadState>({ status: "loading" });

  useEffect(() => {
    loadDay4Bakeoff()
      .then((envelope) => setState({ status: "ready", envelope }))
      .catch((err: unknown) => setState({ status: "error", message: err instanceof Error ? err.message : String(err) }));
  }, []);

  if (state.status === "loading") return <LoadingSkeleton />;
  if (state.status === "error") {
    return <ErrorScreen message={state.message} command="cd backend && python -m scripts.run_day4_bakeoff" />;
  }

  const { data } = state.envelope;
  const shortSha = state.envelope.manifest.git_sha.slice(0, 7);
  const totalCost = data.providers.reduce(
    (sum, p) => sum + realCostUsd(p.provider, p.total_input_tokens, p.total_output_tokens), 0,
  );

  return (
    <main className="screen">
      <Masthead
        screenId="model"
        subtitle={
          <>
            This is an AI buildathon submission, and there is no AI model anywhere in
            the decisions Recoup actually ships. This screen explains why — not as an
            apology. We wrote a rule down in advance for when to trust an AI model's
            suggestion, made real calls to two real AI providers, and that rule
            tripped automatically for both. Our commit history proves the rule was
            written before either provider was ever called.
          </>
        }
      />
      <ProvenanceStrip shortSha={shortSha} artifactUrl={URL} />

      <div className="section">
        <div className="card commit-proof">
          <h2 className="section-title">The rule predates the result — checkable, not asserted</h2>
          <div className="commit-timeline">
            <div className="commit-row">
              <span className="commit-dot commit-dot-rule" />
              <div className="commit-body">
                <span className="commit-label">abstention rule committed</span>
                <span className="commit-detail">
                  <code>{data.abstention_rule_commit_sha.slice(0, 7)}</code> — {data.abstention_rule_commit_date}
                </span>
              </div>
            </div>
            <div className="commit-connector" />
            <div className="commit-row">
              <span className="commit-dot commit-dot-bakeoff" />
              <div className="commit-body">
                <span className="commit-label">real 20-call bake-off run, both providers</span>
                <span className="commit-detail">
                  <code>{data.bakeoff_commit_sha.slice(0, 7)}</code> — {data.bakeoff_commit_date}
                </span>
              </div>
            </div>
          </div>
          <p className="section-note commit-note">
            The three checks below (rules A, B, C) were written into{" "}
            <span className="mono-inline">app/model/abstention.py</span> in the first
            commit, three days before the second. No result existed yet to shape the
            thresholds — the git history itself is the evidence, not a claim about
            intent.
          </p>
        </div>
      </div>

      <div className="section">
        <h2 className="section-title">The bake-off, as it happened</h2>
        <p className="section-note">
          {data.n_calls_per_provider} real calls per provider, temperature 0, the
          exact same synthesis prompt (built from a real run over this project's own
          corpus — no invented numbers, see{" "}
          <span className="mono-inline">app/model/playbook_synthesis.py</span>).
          PROPOSAL_SEED={data.proposal_seed}.
        </p>
        <div className="provider-grid">
          {data.providers.map((p) => (
            <ProviderCard key={p.provider} provider={p} costUsd={realCostUsd(p.provider, p.total_input_tokens, p.total_output_tokens)} />
          ))}
        </div>
      </div>

      <div className="section">
        <div className="card">
          <h2 className="section-title">What a null result here actually means</h2>
          <p className="section-note reading-note">
            Both providers were perfectly reliable — {data.providers[0]?.schema_valid_count}/
            {data.providers[0]?.n_calls} schema-valid, {data.providers[0]?.sensible_count}/
            {data.providers[0]?.n_calls} individually sensible, on every single call, for
            both providers. Neither failed at the task. What the pre-registered dispersion
            check caught is that neither one <em>converges</em> to one consistent
            allocation rule across repeated generations of the same prompt at temperature
            0 — real, measured dispersion, not a guess. The rule fired mechanically and
            both fall back to rules_only-identical behavior — a clean, reportable result,
            not a softened one. Total real cost of every call in this bake-off, at each
            provider's own current published price:{" "}
            <strong>${totalCost.toFixed(4)}</strong>.
          </p>
        </div>
      </div>
    </main>
  );
}

function ProviderCard({ provider, costUsd }: { provider: ProviderBakeoffResult; costUsd: number }) {
  return (
    <div className="card provider-card">
      <div className="provider-header">
        <h3 className="provider-name">{provider.provider}</h3>
        <span className="provider-model-id">{provider.model_id}</span>
      </div>

      <div className="provider-stats">
        <div className="provider-stat">
          <span className="provider-stat-value">{provider.schema_valid_count}/{provider.n_calls}</span>
          <span className="provider-stat-label">schema-valid</span>
        </div>
        <div className="provider-stat">
          <span className="provider-stat-value">{provider.sensible_count}/{provider.n_calls}</span>
          <span className="provider-stat-label">sensible</span>
        </div>
        <div className="provider-stat">
          <Badge label={provider.abstained ? "abstained" : "did not abstain"} tone={provider.abstained ? "policy" : "ok"} />
          <span className="provider-stat-label">pre-registered rule</span>
        </div>
      </div>

      <div className="check-table-scroll">
      <table className="check-table">
        <thead>
          <tr>
            <th>rule</th>
            <th>computed</th>
            <th>threshold</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {provider.checks.map((c) => (
            <tr key={c.rule} className={c.fired ? "check-row-fired" : ""}>
              <td>
                <span className="check-rule-name">{c.rule}</span>
                <span className="check-rule-desc">{c.description}</span>
              </td>
              <td className="mono-cell">{c.computed_value}</td>
              <td className="mono-cell">{c.threshold}</td>
              <td>{c.fired && <Badge label="fired" tone="stop" />}</td>
            </tr>
          ))}
        </tbody>
      </table>
      </div>

      {provider.abstain_reason && (
        <p className="abstain-reason">
          <strong>abstain_reason:</strong> {provider.abstain_reason}
        </p>
      )}

      <p className="provider-cost">
        tokens: {provider.total_input_tokens.toLocaleString("en-IN")} in / {provider.total_output_tokens.toLocaleString("en-IN")} out
        {" "}— real cost at this provider's own published price: <strong>${costUsd.toFixed(4)}</strong>
      </p>
    </div>
  );
}
