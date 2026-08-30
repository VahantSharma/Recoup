import { useEffect, useMemo, useState } from "react";
import { motion } from "framer-motion";
import "./AssumptionSlidersScreen.css";
import { loadDay3Sweep } from "../lib/artifacts/loader";
import type { ArtifactEnvelope, Day3SweepArtifact, OATParameterSweep } from "../lib/artifacts/types";
import { formatPaise, formatPercent } from "../lib/format";
import { Badge } from "./Badge";
import { ErrorScreen, LoadingSkeleton, Masthead, ProvenanceStrip } from "./ScreenChrome";

type LoadState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; envelope: ArtifactEnvelope<Day3SweepArtifact> };

const SWEEP_URL = "/data/day3_sweep.json";

// Real, previously-published numbers from docs/results.md's "Day 3 sensitivity sweep
// -- CRN recheck" section, not re-derived here -- the pre-fix run's own committed
// lift-spread figures for the two near-tied parameters, kept only so their rank order
// swapping against the current (CRN) run is a real, sourced comparison, never a
// simulated or interpolated "what if."
const HISTORICAL_PRE_FIX: Record<string, number> = {
  card_reuse_factor: 0.2555,
  organic_recovery_rate_bps: 0.2495,
};

const ARM_LABELS: Record<string, string> = {
  rate_control: "control", rate_rules_only: "rules_only", rate_blind_retry: "blind_retry",
};

export function AssumptionSlidersScreen() {
  const [state, setState] = useState<LoadState>({ status: "loading" });
  const [selectedName, setSelectedName] = useState<string | null>(null);
  const [pointIndex, setPointIndex] = useState(2); // default point, index 2 of 5
  const [nearTieHistorical, setNearTieHistorical] = useState(false);

  useEffect(() => {
    loadDay3Sweep()
      .then((envelope) => {
        setState({ status: "ready", envelope });
        setSelectedName(envelope.data.most_consequential[0]);
      })
      .catch((err: unknown) => setState({ status: "error", message: err instanceof Error ? err.message : String(err) }));
  }, []);

  const totalPoints = useMemo(() => {
    if (state.status !== "ready") return { held: 0, total: 0 };
    let held = 0, total = 0;
    for (const p of state.envelope.data.parameters) {
      for (const pt of p.points) {
        total += 1;
        if (pt.rules_beats_control) held += 1;
      }
    }
    return { held, total };
  }, [state]);

  if (state.status === "loading") return <LoadingSkeleton />;
  if (state.status === "error") {
    return <ErrorScreen message={state.message} command="cd backend && python -m scripts.run_day3_sweep" />;
  }

  const { data } = state.envelope;
  const shortSha = state.envelope.manifest.git_sha.slice(0, 7);
  const param = data.parameters.find((p) => p.name === selectedName) ?? data.parameters[0];
  const point = param.points[pointIndex];
  const nearTieTop2 = data.most_consequential.slice(0, 2);

  const armRows = (["rate_control", "rate_rules_only", "rate_blind_retry"] as const).map((key) => ({
    key, label: ARM_LABELS[key], rate: point[key],
  })).sort((a, b) => b.rate - a.rate);

  return (
    <main className="screen">
      <Masthead
        screenId="sliders"
        subtitle={
          <>
            Every one of these 15 parameters has no public source — see{" "}
            <span className="mono-inline">docs/assumptions.md</span>. Move a slider and
            watch whether the arm ranking survives across its entire declared range.
            <strong> Every position is a real, computed measurement — nothing between
            two ticks is ever shown, because nothing between them was ever measured.</strong>
          </>
        }
      />
      <ProvenanceStrip shortSha={shortSha} artifactUrl={SWEEP_URL} />

      <div className="persistent-readout">
        Ranking held at <strong>{totalPoints.held} of {totalPoints.total}</strong> swept
        points (one-at-a-time sweep, {data.parameters.length} parameters × 5 points each,
        n={data.oat_n} cases/point) — plus{" "}
        <strong>{data.joint.rules_beats_control_count} of {data.joint.n_draws}</strong> joint
        random draws where every parameter moved at once (n={data.joint.n_cases_per_draw}
        {" "}cases/draw).
      </div>

      <div className="section">
        <h2 className="section-title">Pick a parameter</h2>
        <div className="param-picker">
          {data.parameters.map((p) => {
            const isNearTie = nearTieTop2.includes(p.name);
            return (
              <button
                key={p.name}
                type="button"
                className={`param-chip${p.name === param.name ? " param-chip-active" : ""}`}
                onClick={() => { setSelectedName(p.name); setPointIndex(2); }}
              >
                {p.name}
                {isNearTie && <span className="param-chip-tag">near-tie</span>}
              </button>
            );
          })}
        </div>
      </div>

      <div className="section slider-section">
        <h2 className="section-title">{param.name}</h2>
        <p className="section-note">
          Declared range [{param.lo}, {param.hi}], default {param.default}. Lift spread
          across this parameter's own range: {param.lift_spread.toFixed(4)} — rank{" "}
          {data.most_consequential.indexOf(param.name) + 1} of {data.parameters.length} by
          consequence.
        </p>

        <GridSlider param={param} index={pointIndex} onChange={setPointIndex} />

        <div className="live-panel">
          <div className="live-panel-arms">
            <h3 className="live-panel-heading">Arm ranking at this point</h3>
            <ul className="arm-rank-list">
              {armRows.map((row, i) => (
                <motion.li key={row.key} layout transition={{ duration: 0.25, ease: "easeOut" }} className="arm-rank-row">
                  <span className="arm-rank-index">{i + 1}</span>
                  <span className="arm-rank-label">{row.label}</span>
                  <div className="arm-rank-bar-track">
                    <motion.div
                      className="arm-rank-bar-fill"
                      style={{ background: row.key === "rate_blind_retry" ? "var(--accent)" : row.key === "rate_rules_only" ? "var(--ok)" : "var(--text-faint)" }}
                      animate={{ width: `${Math.min(100, row.rate * 100)}%` }}
                      transition={{ duration: 0.25, ease: "easeOut" }}
                    />
                  </div>
                  <span className="arm-rank-value">{formatPercent(row.rate)}</span>
                </motion.li>
              ))}
            </ul>
          </div>
          <div className="live-panel-facts">
            <h3 className="live-panel-heading">Does the ranking hold, here?</h3>
            <div className="fact-row">
              <span>rules_only beats control</span>
              <Badge label={point.rules_beats_control ? "holds" : "flipped"} tone={point.rules_beats_control ? "ok" : "stop"} />
            </div>
            <div className="fact-row">
              <span>blind_retry beats rules_only</span>
              <Badge label={point.blind_beats_rules ? "holds" : "flipped"} tone={point.blind_beats_rules ? "ok" : "stop"} />
            </div>
            <div className="fact-row">
              <span>break-even penalty at this point</span>
              <span className="fact-value">{point.break_even_penalty_paise != null ? formatPaise(point.break_even_penalty_paise) : "n/a — 0 violations"}</span>
            </div>
          </div>
        </div>
      </div>

      <div className="section">
        <h2 className="section-title">The disclosed near-tie</h2>
        <p className="section-note">
          <span className="mono-inline">card_reuse_factor</span> and{" "}
          <span className="mono-inline">organic_recovery_rate_bps</span> are, by lift
          spread, effectively tied for most consequential parameter in the whole sweep —
          a documented boundary condition, not an error. A different run's random stream
          has already flipped which one leads (see{" "}
          <span className="mono-inline">docs/results.md</span>'s CRN recheck). Toggle
          below to see it happen with real, previously-published numbers.
        </p>
        <div className="card near-tie-card">
          <button type="button" className="near-tie-toggle" onClick={() => setNearTieHistorical((v) => !v)}>
            showing: {nearTieHistorical ? "pre-fix run (historical, docs/results.md)" : "this run (current artifact)"} — click to flip
          </button>
          <ul className="near-tie-list">
            {[...nearTieTop2]
              .sort((a, b) => {
                const va = nearTieHistorical ? HISTORICAL_PRE_FIX[a] : (data.parameters.find((p) => p.name === a)?.lift_spread ?? 0);
                const vb = nearTieHistorical ? HISTORICAL_PRE_FIX[b] : (data.parameters.find((p) => p.name === b)?.lift_spread ?? 0);
                return vb - va;
              })
              .map((name, i) => {
                const value = nearTieHistorical ? HISTORICAL_PRE_FIX[name] : (data.parameters.find((p) => p.name === name)?.lift_spread ?? 0);
                return (
                  <motion.li key={name} layout transition={{ duration: 0.25, ease: "easeOut" }} className="near-tie-row">
                    <span className="arm-rank-index">{i + 1}</span>
                    <span className="near-tie-name">{name}</span>
                    <span className="near-tie-value">{value.toFixed(4)}</span>
                  </motion.li>
                );
              })}
          </ul>
        </div>
      </div>
    </main>
  );
}

function GridSlider({ param, index, onChange }: { param: OATParameterSweep; index: number; onChange: (i: number) => void }) {
  return (
    <div className="grid-slider">
      <input
        type="range" min={0} max={4} step={1} value={index}
        onChange={(e) => onChange(Number(e.target.value))}
        className="grid-slider-input"
        aria-label={`${param.name} — 5 computed points`}
      />
      <div className="grid-slider-ticks">
        {param.points.map((pt, i) => (
          <button
            key={i}
            type="button"
            className={`grid-slider-tick${i === index ? " grid-slider-tick-active" : ""}`}
            onClick={() => onChange(i)}
          >
            <span className="grid-slider-tick-mark" />
            <span className="grid-slider-tick-value">{pt.value}</span>
          </button>
        ))}
      </div>
      <p className="grid-slider-caption">
        5 real computed points — lo, 25%, default, 75%, hi. The slider snaps to one of
        them; nothing in between was ever run.
      </p>
    </div>
  );
}
