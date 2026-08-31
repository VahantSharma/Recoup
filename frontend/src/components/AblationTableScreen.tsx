import { useEffect, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ErrorBar,
  LabelList,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import "./AblationTableScreen.css";
import { loadDay3Ablation, loadDay4HeldOutAblation } from "../lib/artifacts/loader";
import { withProvenance } from "../lib/artifacts/provenance";
import type { ArmHeldOutRow, ArtifactEnvelope, Day3AblationArtifact, Day4HeldOutAblationArtifact } from "../lib/artifacts/types";
import { formatPaise, formatPercent, formatSigned } from "../lib/format";
import { armLabel } from "../lib/plainLanguage";
import { Badge } from "./Badge";
import { Figure } from "./Figure";
import { GlossaryTerm } from "./GlossaryTerm";
import { ErrorScreen, LoadingSkeleton, Masthead, ProvenanceStrip } from "./ScreenChrome";

type LoadState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | {
      status: "ready";
      ablation: ArtifactEnvelope<Day4HeldOutAblationArtifact>;
      compliance: ArtifactEnvelope<Day3AblationArtifact>;
    };

const HELD_OUT_URL = "/data/day4_held_out_ablation.json";

interface LiftDatum {
  name: string;
  mean: number;
  range: [number, number]; // [delta below mean to min, delta above mean to max]
}

function liftData(arms: ArmHeldOutRow[]): LiftDatum[] {
  return arms
    .filter((a) => a.lift_vs_rules_only != null)
    .map((a) => {
      const d = a.lift_vs_rules_only!;
      return { name: armLabel(a.arm), mean: d.mean, range: [d.mean - d.min, d.max - d.mean] };
    });
}

export function AblationTableScreen() {
  const [state, setState] = useState<LoadState>({ status: "loading" });

  useEffect(() => {
    Promise.all([loadDay4HeldOutAblation(), loadDay3Ablation()])
      .then(([ablation, compliance]) => setState({ status: "ready", ablation, compliance }))
      .catch((err: unknown) => setState({ status: "error", message: err instanceof Error ? err.message : String(err) }));
  }, []);

  if (state.status === "loading") return <LoadingSkeleton />;
  if (state.status === "error") {
    return <ErrorScreen message={state.message} command="cd backend && python -m scripts.run_day4_ablation && python -m scripts.run_day3_ablation" />;
  }

  const { data } = state.ablation;
  const shortSha = state.ablation.manifest.git_sha.slice(0, 7);
  const shippable = data.arms.filter((a) => a.is_shippable);
  const analysisOnly = data.arms.filter((a) => !a.is_shippable);
  const shippableLift = liftData(shippable);
  const analysisLift = liftData(analysisOnly);
  const compliance = state.compliance.data.compliance;
  const rulesOnlyArm = state.compliance.data.arms.find((a) => a.arm === "rules_only")!;
  const controlLift = state.compliance.data.lifts.find((l) => l.arm_a === "rules_only" && l.arm_b === "control")!;

  return (
    <main className="screen">
      <Masthead
        screenId="ablation"
        subtitle={
          <>
            All eight approaches, tested on ten batches of payments none of them were
            ever tuned on. Every result is measured against <em>our rules engine</em> —
            the safe, compliant baseline every AI-assisted or reference approach is
            judged against, not against doing nothing.
          </>
        }
      />
      <ProvenanceStrip shortSha={shortSha} artifactUrl={HELD_OUT_URL} />

      <div className="section money-section">
        <h2 className="section-title">How much money did this actually recover?</h2>
        <div className="card money-block">
          <div className="money-row">
            <span className="money-label">Money recovered across the batch</span>
            <span className="money-value">
              <Figure
                mono
                value={withProvenance(
                  formatPaise(rulesOnlyArm.recovered_amount_paise),
                  state.compliance.manifest,
                  "/data/day3_ablation.json",
                )}
              />
              <span className="money-n">n = {state.compliance.data.n.toLocaleString("en-IN")} cases</span>
            </span>
          </div>
          <div className="money-row">
            <span className="money-label">Incremental over control</span>
            <span className="money-value">
              <Figure
                mono
                value={withProvenance(
                  `${formatPaise(controlLift.amount_lift_paise)} [${formatPaise(controlLift.amount_lift_ci_low_paise)}–${formatPaise(controlLift.amount_lift_ci_high_paise)}]`,
                  state.compliance.manifest,
                  "/data/day3_ablation.json",
                )}
              />
            </span>
          </div>
          <p className="money-why">
            <strong>Why the second number is the honest one:</strong> some payments
            recover on their own; claiming those is what makes recovery vendors
            untrustworthy. The gross figure above is real and traces to the same run —
            we're not hiding it — but the incremental number is the one we'd stake a
            claim on.
          </p>
        </div>
      </div>

      <div className="section">
        <h2 className="section-title">How much extra do we recover, compared to our rules engine? (Approaches we could actually ship)</h2>
        <p className="section-note">
          Each bar: the average extra recovery across {data.held_out_seeds.length} separate
          test batches. The thin lines: the real best-to-worst range across those batches,
          not a fitted estimate. Green means this approach beat our rules engine on
          average; red means it didn't.
        </p>
        <div className="card">
          <LiftChart data={shippableLift} height={Math.max(120, shippableLift.length * 56)} />
        </div>
      </div>

      <div className="section">
        <h2 className="section-title">Reference bounds — not shippable</h2>
        <p className="section-note">
          These two arms read the simulator's own ground truth or fit under perfect
          information — no real system could ever run this way. They exist only to show
          a ceiling, never as candidates this project would ship. Kept visually and
          structurally apart from the arms above for exactly that reason.
        </p>
        <div className="card card-analysis">
          <LiftChart data={analysisLift} height={Math.max(120, analysisLift.length * 56)} muted />
        </div>
      </div>

      <div className="section">
        <h2 className="section-title">Every approach — how much it recovered, and how many rules it broke to get there</h2>
        <p className="section-note">
          A raw recovery number on its own is misleading — an approach that ignores
          every safety rule will always recover more, just by cheating. So how many
          rules it broke sits right beside it, in the same row, not hidden in a
          separate table you could skim past.
        </p>
        <ArmTable arms={data.arms} modalRanking={data.modal_ranking} holdCount={data.modal_ranking_hold_count} totalSeeds={data.held_out_seeds.length} />
      </div>

      <div className="section">
        <h2 className="section-title">Do the card networks' penalties actually make the rules worth following?</h2>
        <p className="section-note">
          The break-even point: how expensive would a single broken rule have to be
          before "retry everything, no rules" stops being worth it, ₹-for-₹ against
          our rules engine? Worked out on real net value (money recovered minus what
          it cost to try), never on the raw amount recovered — see{" "}
          <span className="mono-inline">app/harness/compliance.py</span>.
          From <span className="mono-inline">day3_ablation.json</span>, manifest{" "}
          {state.compliance.manifest.git_sha.slice(0, 7)}.
        </p>
        <div className="card">
          <ComplianceStrip compliance={compliance} />
        </div>
      </div>
    </main>
  );
}

function LiftChart({ data, height, muted }: { data: LiftDatum[]; height: number; muted?: boolean }) {
  if (data.length === 0) return <p className="empty-note">No arms in this group.</p>;

  // Recharts' auto domain on all-exactly-zero data (a real, disclosed finding here --
  // both model arms landed exactly on rules_only's own fallback, see
  // docs/results.md's Day 4 section) picks an arbitrary wide range with no visible
  // bar at all. Compute an explicit domain from the real data instead, with a small
  // floor so a zero-width bar still renders as a visible hairline, not empty space.
  const allEdges = data.flatMap((d) => [d.mean - d.range[0], d.mean + d.range[1]]);
  const spread = Math.max(0.02, Math.max(...allEdges) - Math.min(...allEdges, 0));
  const domainMin = Math.min(0, ...allEdges) - spread * 0.08;
  const domainMax = Math.max(0, ...allEdges) + spread * 0.08;
  const allExactZero = data.every((d) => d.mean === 0 && d.range[0] === 0 && d.range[1] === 0);

  return (
    <>
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} layout="vertical" margin={{ top: 4, right: 72, bottom: 4, left: 4 }}>
        <CartesianGrid strokeDasharray="2 4" stroke="var(--border)" horizontal={false} />
        <XAxis
          type="number"
          domain={[domainMin, domainMax]}
          tickFormatter={(v: number) => formatSigned(v, 0)}
          tick={{ fill: "var(--text-dim)", fontSize: 11, fontFamily: "var(--font-mono)" }}
          axisLine={{ stroke: "var(--border)" }}
          tickLine={false}
        />
        <YAxis
          type="category"
          dataKey="name"
          width={190}
          tick={{ fill: "var(--text)", fontSize: 12, fontFamily: "var(--font-mono)" }}
          axisLine={{ stroke: "var(--border)" }}
          tickLine={false}
        />
        <ReferenceLine x={0} stroke="var(--border-strong)" />
        <Tooltip
          contentStyle={{
            background: "var(--bg)", border: "1px solid var(--border-strong)", borderRadius: "var(--radius-card)",
            fontFamily: "var(--font-mono)", fontSize: 12,
          }}
          formatter={(value) => [formatSigned(Number(value), 2), "mean lift"]}
        />
        <Bar dataKey="mean" radius={4} barSize={22} minPointSize={2} isAnimationActive={false}>
          {data.map((d) => (
            <Cell key={d.name} fill={muted ? "var(--text-faint)" : d.mean >= 0 ? "var(--ok)" : "var(--stop)"} fillOpacity={muted ? 0.55 : 1} />
          ))}
          <ErrorBar dataKey="range" width={5} strokeWidth={1.5} stroke="var(--text-dim)" direction="x" />
          <LabelList
            dataKey="mean"
            position="right"
            formatter={(v) => (Number(v) === 0 ? "exact tie" : formatSigned(Number(v), 2))}
            style={{ fill: "var(--text-dim)", fontFamily: "var(--font-mono)", fontSize: 11 }}
          />
        </Bar>
      </BarChart>
    </ResponsiveContainer>
    {allExactZero && (
      <p className="lift-chart-tie-note">
        Every approach here lands at exactly the same number as our rules engine — not
        just close, identical — across all 10 separate{" "}
        <GlossaryTerm term="seed">random-number seeds</GlossaryTerm> we tested it on. See{" "}
        <span className="mono-inline">docs/results.md</span>'s Day 4 section.
      </p>
    )}
    </>
  );
}

function ArmTable({
  arms, modalRanking, holdCount, totalSeeds,
}: { arms: ArmHeldOutRow[]; modalRanking: string[]; holdCount: number; totalSeeds: number }) {
  const rankIndex = new Map(modalRanking.map((name, i) => [name, i + 1]));
  return (
    <div className="card ablation-table-wrap">
      <p className="ranking-hold-line">
        This same ranking held in <strong>{holdCount} of {totalSeeds}</strong> separate
        test batches:{" "}
        <span className="ranking-chain">{modalRanking.map(armLabel).join(" > ")}</span>
      </p>
      <table className="ablation-table">
        <thead>
          <tr>
            <th>#</th>
            <th>approach</th>
            <th>average recovery rate</th>
            <th>safety rules broken</th>
            <th>times it gave up its turn</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {arms.map((a) => (
            <tr key={a.arm} className={a.is_shippable ? "" : "row-analysis"}>
              <td className="rank-cell">{rankIndex.get(a.arm)}</td>
              <td className="arm-cell">
                {armLabel(a.arm)}
                <span className="arm-cell-raw">{a.arm}</span>
              </td>
              <td className="num-cell">{formatPercent(a.mean_recovery_rate)}</td>
              <td className={`num-cell${a.total_violations > 0 ? " violation-cell" : ""}`}>
                {a.total_violations.toLocaleString("en-IN")}
              </td>
              <td className="num-cell">{a.total_yields != null ? a.total_yields.toLocaleString("en-IN") : "—"}</td>
              <td>
                <Badge label={a.is_shippable ? "could ship this" : "measurement only"} tone={a.is_shippable ? "ok" : "policy"} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ComplianceStrip({ compliance }: { compliance: Day3AblationArtifact["compliance"] }) {
  const maxAxis = Math.max(compliance.break_even_penalty_paise, compliance.mastercard_high_paise) * 1.15;
  const rows = [{ name: "break-even penalty", value: compliance.break_even_penalty_paise }];
  return (
    <>
      <ResponsiveContainer width="100%" height={130}>
        <BarChart data={rows} layout="vertical" margin={{ top: 28, right: 24, bottom: 4, left: 4 }}>
          <XAxis
            type="number" domain={[0, maxAxis]}
            tickFormatter={(v: number) => formatPaise(v)}
            tick={{ fill: "var(--text-dim)", fontSize: 11, fontFamily: "var(--font-mono)" }}
            axisLine={{ stroke: "var(--border)" }} tickLine={false}
          />
          <YAxis type="category" dataKey="name" width={0} tick={false} axisLine={false} tickLine={false} />
          <ReferenceLine x={compliance.visa_penalty_paise} stroke="var(--stop)" strokeDasharray="3 3"
            label={{ value: "Visa", position: "top", fill: "var(--stop)", fontSize: 10, fontFamily: "var(--font-mono)" }} />
          <ReferenceLine x={compliance.mastercard_low_paise} stroke="var(--ok)" strokeDasharray="3 3"
            label={{ value: "Mastercard (mo. 1)", position: "top", fill: "var(--ok)", fontSize: 10, fontFamily: "var(--font-mono)" }} />
          <ReferenceLine x={compliance.mastercard_high_paise} stroke="var(--ok)" strokeDasharray="3 3"
            label={{ value: "Mastercard (later)", position: "top", fill: "var(--ok)", fontSize: 10, fontFamily: "var(--font-mono)" }} />
          <Bar dataKey="value" fill="var(--accent)" radius={4} barSize={20} isAnimationActive={false} />
        </BarChart>
      </ResponsiveContainer>
      <p className="compliance-readout">
        {formatPaise(compliance.break_even_penalty_paise)} per broken rule (${compliance.break_even_penalty_usd.toFixed(2)} at
        1 USD = ₹{compliance.usd_to_inr}) — above what Visa actually charges per excess retry, below what Mastercard
        charges. At this one point, following the rules pays for itself under Mastercard's fees, but not under Visa's;
        the full range we tested is in{" "}
        <span className="mono-inline">docs/results.md</span>.
      </p>
    </>
  );
}
