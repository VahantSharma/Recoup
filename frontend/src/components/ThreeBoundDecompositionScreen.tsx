import { useEffect, useState } from "react";
import { Bar, BarChart, CartesianGrid, Cell, ErrorBar, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import "./ThreeBoundDecompositionScreen.css";
import { loadDay4BoundDecomposition } from "../lib/artifacts/loader";
import type { ArtifactEnvelope, Day4BoundDecompositionArtifact, GapStat } from "../lib/artifacts/types";
import { formatPaise, formatPercent, formatSigned } from "../lib/format";
import { armLabel, declineClassLabel } from "../lib/plainLanguage";
import { ErrorScreen, LoadingSkeleton, Masthead, ProvenanceStrip } from "./ScreenChrome";

type LoadState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; envelope: ArtifactEnvelope<Day4BoundDecompositionArtifact> };

const URL = "/data/day4_bound_decomposition.json";

interface ArmBar {
  name: string;
  mean: number;
  range: [number, number];
}

function heldOutStats<T extends { seed: number }>(
  rows: T[], heldOutSeeds: number[], key: keyof T,
): { mean: number; range: [number, number] } {
  const values = rows.filter((r) => heldOutSeeds.includes(r.seed)).map((r) => r[key] as unknown as number);
  const mean = values.reduce((a, b) => a + b, 0) / values.length;
  const min = Math.min(...values);
  const max = Math.max(...values);
  return { mean, range: [mean - min, max - mean] };
}

export function ThreeBoundDecompositionScreen() {
  const [state, setState] = useState<LoadState>({ status: "loading" });

  useEffect(() => {
    loadDay4BoundDecomposition()
      .then((envelope) => setState({ status: "ready", envelope }))
      .catch((err: unknown) => setState({ status: "error", message: err instanceof Error ? err.message : String(err) }));
  }, []);

  if (state.status === "loading") return <LoadingSkeleton />;
  if (state.status === "error") {
    return <ErrorScreen message={state.message} command="cd backend && python -m scripts.run_bound_decomposition" />;
  }

  const { data } = state.envelope;
  const shortSha = state.envelope.manifest.git_sha.slice(0, 7);

  const rateData: ArmBar[] = [
    { name: armLabel("rules_only"), ...heldOutStats(data.rate_by_seed, data.held_out_seeds, "rules_only") },
    { name: armLabel("observable_optimal"), ...heldOutStats(data.rate_by_seed, data.held_out_seeds, "observable_optimal") },
    { name: armLabel("oracle_upper_bound"), ...heldOutStats(data.rate_by_seed, data.held_out_seeds, "oracle_upper_bound") },
  ];
  const netValueData: ArmBar[] = [
    { name: armLabel("rules_only"), ...heldOutStats(data.net_value_by_seed_paise, data.held_out_seeds, "rules_only_paise") },
    { name: armLabel("observable_optimal"), ...heldOutStats(data.net_value_by_seed_paise, data.held_out_seeds, "observable_optimal_paise") },
    { name: armLabel("oracle_value_maximizing"), ...heldOutStats(data.net_value_by_seed_paise, data.held_out_seeds, "oracle_value_maximizing_paise") },
  ];

  return (
    <main className="screen">
      <Masthead
        screenId="decomposition"
        subtitle={
          <>
            Two tables below measure the same three-step chain two different ways — and
            they disagree about whether "the best we could do with only real
            information" is actually an improvement over "our rules engine." That
            disagreement is the real finding here, not a footnote we resolved by
            quietly picking whichever table looks better.
          </>
        }
      />
      <ProvenanceStrip shortSha={shortSha} artifactUrl={URL} />

      <div className="bound-grid">
        <BoundPanel
          title="How many payments come back"
          data={rateData}
          formatValue={(v) => formatPercent(v)}
          gap1={data.rate_gap1}
          gap2={data.rate_gap2}
          gap2Label="Best-with-real-info → perfect crystal ball"
          formatGap={(v) => formatSigned(v, 2)}
        />
        <BoundPanel
          title="How much money it's actually worth"
          data={netValueData}
          formatValue={(v) => formatPaise(v)}
          gap1={data.net_value_gap1_paise}
          gap2={data.net_value_gap2_paise}
          gap2Label="Best-with-real-info → perfect crystal ball (money-matched)"
          formatGap={(v) => formatPaise(v)}
        />
      </div>

      <div className="section">
        <div className="card disagreement-card">
          <h2 className="section-title">The disagreement, stated plainly</h2>
          <p className="section-note disagreement-note">
            Count <strong>how many payments come back</strong>, and "the best we could
            do with only real information" looks worse than our rules engine — it ends
            up recovering fewer payments, just bigger and cheaper ones. Count{" "}
            <strong>actual rupees, minus what it cost to try</strong>, and it looks
            better. Which one matters more is a real business call, not something this
            project gets to decide quietly — so we're showing both tables, not just the
            one that flatters the result.
          </p>
          <p className="section-note">
            Retry attempts saved by a perfect crystal ball, compared to our rules
            engine (on the one test batch we tuned against):{" "}
            <strong>{data.attempts_conserved_net}</strong> fewer attempts overall — it
            skipped retrying payments that could never succeed (
            {Object.entries(data.attempts_reduced_by_class).map(([k, v]) => `${declineClassLabel(k)}: ${v}`).join(", ")}),
            and used those freed-up card slots on payments sharing the same card instead
            ({Object.entries(data.attempts_increased_by_class).map(([k, v]) => `${declineClassLabel(k)}: ${v}`).join(", ")}).
          </p>
        </div>
      </div>
    </main>
  );
}

function BoundPanel({
  title, data, formatValue, gap1, gap2, gap2Label, formatGap,
}: {
  title: string; data: ArmBar[]; formatValue: (v: number) => string;
  gap1: GapStat; gap2: GapStat; gap2Label: string; formatGap: (v: number) => string;
}) {
  return (
    <div className="card bound-panel">
      <h2 className="section-title">{title}</h2>
      <p className="section-note">
        Each bar: the average across {gap1.total_points - 1} test batches this wasn't
        tuned on. The thin lines: the real best-to-worst range across those batches, not
        an estimate.
      </p>
      <ResponsiveContainer width="100%" height={200}>
        <BarChart data={data} layout="vertical" margin={{ top: 4, right: 40, bottom: 4, left: 4 }}>
          <CartesianGrid strokeDasharray="2 4" stroke="var(--border)" horizontal={false} />
          <XAxis
            type="number" tickFormatter={formatValue}
            tick={{ fill: "var(--text-dim)", fontSize: 10.5, fontFamily: "var(--font-mono)" }}
            axisLine={{ stroke: "var(--border)" }} tickLine={false}
          />
          <YAxis
            type="category" dataKey="name" width={172}
            tick={{ fill: "var(--text)", fontSize: 10.5, fontFamily: "var(--font-mono)" }}
            axisLine={{ stroke: "var(--border)" }} tickLine={false}
          />
          <Tooltip
            contentStyle={{ background: "var(--bg)", border: "1px solid var(--border-strong)", borderRadius: "var(--radius-card)", fontFamily: "var(--font-mono)", fontSize: 12 }}
            formatter={(value) => [formatValue(Number(value)), "average on unseen batches"]}
          />
          <Bar dataKey="mean" radius={4} barSize={26} isAnimationActive={false}>
            {data.map((d, i) => (
              <Cell key={d.name} fill={i === 0 ? "var(--text-dim)" : i === 1 ? "var(--ok)" : "var(--text-faint)"} />
            ))}
            <ErrorBar dataKey="range" width={5} strokeWidth={1.5} stroke="var(--text-dim)" direction="x" />
          </Bar>
        </BarChart>
      </ResponsiveContainer>

      <div className="gap-callouts">
        <div className="gap-callout gap-callout-reachable">
          <span className="gap-callout-label">Our rules engine → best with real info</span>
          <span className="gap-callout-desc">value we're leaving on the table today, using information we already have — a real gap a v2 could close</span>
          <span className="gap-callout-value">
            {formatGap(gap1.held_out_mean)}{" "}
            <span className="gap-callout-range">(on the batch we tuned against: {formatGap(gap1.in_sample)})</span>
          </span>
        </div>
        <div className="gap-callout gap-callout-ceiling">
          <span className="gap-callout-label">{gap2Label}</span>
          <span className="gap-callout-desc">information no real system will ever have — this part of the gap can't be closed</span>
          <span className="gap-callout-value">
            {formatGap(gap2.held_out_mean)}{" "}
            <span className="gap-callout-range">(on the batch we tuned against: {formatGap(gap2.in_sample)})</span>
          </span>
        </div>
      </div>
    </div>
  );
}
