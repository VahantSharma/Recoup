import { useState } from "react";
import "./LiveVerificationPanel.css";
import { CopyButton } from "./CopyButton";
import { InfoTip } from "./InfoTip";
import { LiveApiUnreachableError, verifyRecoveryAction, type LiveActionResponse } from "../lib/liveApi";
import { guardrailPlainLanguage } from "../lib/plainLanguage";

type RunState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "done"; result: LiveActionResponse };

const ACTION_TAKEN_LABEL: Record<LiveActionResponse["action_taken"], string> = {
  created: "Created a real test-mode Payment Link, right now.",
  replayed_no_op: "Recognized as a replay — no second Payment Link was created.",
  refused: "Refused — no Payment Link was created.",
};

/**
 * The one deliberately live thing on this screen: a real POST to a real, running
 * FastAPI server, which makes a real reconcile call against Razorpay test mode, right
 * now, on the real Day 1 harvested payment. Everything else here reads a committed
 * artifact; this is the exception, and it says so.
 */
export function LiveVerificationPanel() {
  const [attemptNumber, setAttemptNumber] = useState(1);
  const [simulateResolvedElsewhere, setSimulateResolvedElsewhere] = useState(false);
  const [run, setRun] = useState<RunState>({ status: "idle" });

  const execute = async (n: number, override: boolean) => {
    setRun({ status: "loading" });
    try {
      const result = await verifyRecoveryAction(n, override);
      setRun({ status: "done", result });
    } catch (err) {
      const message = err instanceof LiveApiUnreachableError || err instanceof Error
        ? err.message
        : String(err);
      setRun({ status: "error", message });
    }
  };

  return (
    <section className="live-panel">
      <div className="live-panel-head">
        <span className="live-panel-badge">LIVE</span>
        <h2 className="live-panel-title">Verify this, live</h2>
      </div>
      <p className="live-panel-intro">
        Everything above reads a committed run's results. This button instead calls a
        real server on your machine, which reconciles against Razorpay's real test-mode
        API right now, then either acts or refuses — live, in front of you.
      </p>

      <div className="live-panel-controls">
        <label className="live-panel-field">
          <span className="live-panel-field-label">attempt #</span>
          <input
            className="live-panel-input"
            type="number"
            min={1}
            value={attemptNumber}
            onChange={(e) => setAttemptNumber(Math.max(1, Number(e.target.value) || 1))}
          />
        </label>
        <label className="live-panel-checkbox">
          <input
            type="checkbox"
            checked={simulateResolvedElsewhere}
            onChange={(e) => setSimulateResolvedElsewhere(e.target.checked)}
          />
          pretend this payment resolved elsewhere
          <InfoTip text="The real payment stays 'failed' in test mode forever, so the refusal path can otherwise never be seen live. Checking this forces that one value before the gate decides — the real fetched status is still shown, never hidden." />
        </label>
        <button
          type="button"
          className="live-panel-run"
          disabled={run.status === "loading"}
          onClick={() => execute(attemptNumber, simulateResolvedElsewhere)}
        >
          {run.status === "loading" ? "Calling Razorpay…" : "Verify live"}
        </button>
      </div>

      {run.status === "error" && (
        <div className="live-panel-error">
          <strong>Could not run this live.</strong> {run.message}
        </div>
      )}

      {run.status === "done" && <LiveResult result={run.result} onReplay={() => execute(attemptNumber, simulateResolvedElsewhere)}
        onFresh={() => { const next = attemptNumber + 1; setAttemptNumber(next); execute(next, simulateResolvedElsewhere); }} />}
    </section>
  );
}

function LiveResult({
  result,
  onReplay,
  onFresh,
}: {
  result: LiveActionResponse;
  onReplay: () => void;
  onFresh: () => void;
}) {
  return (
    <div className="live-result">
      <div className="live-result-row">
        <span className="live-result-label">reconciled status (real, just now)</span>
        <span className="live-result-value">{result.reconciled_status_real}</span>
      </div>
      {result.reconcile_overridden && (
        <div className="live-result-row">
          <span className="live-result-label">status fed to the gate (forced)</span>
          <span className="live-result-value">{result.reconciled_status_used}</span>
        </div>
      )}
      <div className="live-result-row">
        <span className="live-result-label">gate decision</span>
        <span className="live-result-value">
          {result.gate_decision} — {guardrailPlainLanguage(result.gate_reason)}
        </span>
      </div>
      <div className="live-result-row">
        <span className="live-result-label">what happened</span>
        <span className="live-result-value">{ACTION_TAKEN_LABEL[result.action_taken]}</span>
      </div>
      {result.idempotency_key && (
        <div className="live-result-row">
          <span className="live-result-label">idempotency key</span>
          <span className="live-result-value live-result-mono">
            {result.idempotency_key.slice(0, 12)}…
            <CopyButton value={result.idempotency_key} />
          </span>
        </div>
      )}
      {result.payment_link_short_url && (
        <div className="live-result-row">
          <span className="live-result-label">payment link</span>
          <a className="live-result-link" href={result.payment_link_short_url} target="_blank" rel="noreferrer">
            {result.payment_link_short_url} — open the real link Razorpay just created ↗
          </a>
        </div>
      )}

      <div className="live-result-actions">
        <button type="button" className="live-panel-secondary" onClick={onReplay}>
          Replay attempt #{result.attempt_number} again
        </button>
        <button type="button" className="live-panel-secondary" onClick={onFresh}>
          Try a fresh attempt (#{result.attempt_number + 1})
        </button>
      </div>
    </div>
  );
}
