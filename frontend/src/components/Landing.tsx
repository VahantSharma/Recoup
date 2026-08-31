import { useEffect, useState } from "react";
import "./Landing.css";
import { loadDay3Ablation } from "../lib/artifacts/loader";
import { withProvenance } from "../lib/artifacts/provenance";
import type { ArtifactEnvelope, Day3AblationArtifact } from "../lib/artifacts/types";
import { formatPaise } from "../lib/format";
import { ErrorScreen, LoadingSkeleton } from "./ScreenChrome";
import { Badge } from "./Badge";
import { Figure } from "./Figure";
import { SCREENS } from "../lib/screens";

type LoadState =
  | { status: "loading" }
  | { status: "error"; message: string; command: string }
  | { status: "ready"; ablation: ArtifactEnvelope<Day3AblationArtifact> };

const EVIDENCE_TIERS = [
  {
    tone: "ok" as const,
    label: "Verified live",
    body: "We watched this happen ourselves, for real, this session — like the one real failed payment on the Case Audit screen, and the AI model that actually answered when we called it.",
  },
  {
    tone: "policy" as const,
    label: "Documented",
    body: "Razorpay published this — we didn't watch it happen ourselves, we're taking their word for it. Example: the 17 real reasons a card payment can fail, straight from their docs.",
  },
  {
    tone: "warn" as const,
    label: "Our own work",
    body: "We built this ourselves, on top of the facts above — like which failures are worth retrying, and every safety rule the system follows.",
  },
  {
    tone: "stop" as const,
    label: "Assumed",
    body: "Nobody publishes this number, so we made an honest, clearly-labeled guess — then tested what happens if that guess is wrong, across a wide range, instead of hoping we guessed right.",
  },
];

export function Landing({ onNavigate }: { onNavigate: (hash: string) => void }) {
  const [state, setState] = useState<LoadState>({ status: "loading" });

  useEffect(() => {
    loadDay3Ablation()
      .then((ablation) => setState({ status: "ready", ablation }))
      .catch((err: unknown) =>
        setState({
          status: "error",
          message: err instanceof Error ? err.message : String(err),
          command: "cd backend && python -m scripts.run_day3_ablation",
        }),
      );
  }, []);

  if (state.status === "loading") return <LoadingSkeleton />;
  if (state.status === "error") return <ErrorScreen message={state.message} command={state.command} />;

  const { ablation } = state;
  const liftRow = ablation.data.lifts.find((l) => l.arm_a === "rules_only" && l.arm_b === "control")!;
  const rulesOnlyArm = ablation.data.arms.find((a) => a.arm === "rules_only")!;
  const violations = ablation.data.compliance.violations_blind_retry;
  // Deliberately a Day 3 number, not Day 4's bound-decomposition headroom figure --
  // docs/results.md flags every Day 4 number "pending verification" (it hasn't been
  // regenerated since the state-machine-ordering fix changed the corpus RNG stream).
  // A landing-page headline stat is the single most-seen number on this whole site;
  // it doesn't get to be the one place that claim's caveat goes unshown. This is real,
  // current, and traces to the same manifest as the other two stats above.
  const realGuardrails = ablation.data.guardrail_reachability.filter((g) => g.name !== "permitted");
  const reachableCount = realGuardrails.filter((g) => g.reachable).length;

  return (
    <main className="landing">
      <section className="landing-hero">
        <p className="landing-kicker">AI Revenue Recovery — Razorpay Buildathon</p>
        <h1 className="landing-headline">
          A payment fails. Most of that money just gets written off.
        </h1>
        <p className="landing-lede">
          Recoup looks at the payment after it fails: figures out why, decides whether
          it's safe to try again, checks that decision against a fixed set of rules, and
          then measures whether trying again actually helped — compared to a group of
          identical payments where we did nothing at all.
        </p>
        <p className="landing-promise">
          Ask a hard question about any number here and it holds up.{" "}
          <strong>Check any of them yourself</strong> — click one to see exactly which
          run produced it.
        </p>

        <div className="landing-money">
          <div className="landing-money-row">
            <span className="landing-money-label">Money recovered across the batch</span>
            <span className="landing-money-value">
              <Figure
                mono
                value={withProvenance(
                  formatPaise(rulesOnlyArm.recovered_amount_paise),
                  ablation.manifest,
                  "/data/day3_ablation.json",
                )}
              />
              <span className="landing-money-n">n = {ablation.data.n.toLocaleString("en-IN")} cases</span>
            </span>
          </div>
          <div className="landing-money-row">
            <span className="landing-money-label">Incremental over control</span>
            <span className="landing-money-value">
              <Figure
                mono
                value={withProvenance(
                  `${formatPaise(liftRow.amount_lift_paise)} [${formatPaise(liftRow.amount_lift_ci_low_paise)}–${formatPaise(liftRow.amount_lift_ci_high_paise)}]`,
                  ablation.manifest,
                  "/data/day3_ablation.json",
                )}
              />
            </span>
          </div>
          <p className="landing-money-why">
            <strong>Why the second number is the honest one:</strong> some payments
            recover on their own; claiming those is what makes recovery vendors
            untrustworthy. The gross figure above is real and traces to the same run —
            we're not hiding it — but the incremental number is the one we'd stake a
            claim on.
          </p>
        </div>

        <div className="landing-stats">
          <div className="landing-stat">
            <Figure
              mono
              value={withProvenance(
                `+${(liftRow.rate_lift * 100).toFixed(1)}pp`,
                ablation.manifest,
                "/data/day3_ablation.json",
              )}
            />
            <p className="landing-stat-caption">
              More payments recovered than if we had done nothing at all. We know this
              because we also ran a matching group of payments with no action taken, and
              compared the two — so this isn't just money that would have come back on
              its own with a new label on it.
            </p>
          </div>
          <div className="landing-stat">
            <Figure
              mono
              value={withProvenance(violations.toLocaleString("en-IN"), ablation.manifest, "/data/day3_ablation.json")}
            />
            <p className="landing-stat-caption">
              How many times a "just retry everything, no rules" approach would have
              tried a payment our own safety rules say to leave alone. This is what
              skipping the rules actually costs — measured, not guessed at.
            </p>
          </div>
          <div className="landing-stat">
            <Figure
              mono
              value={withProvenance(
                `${reachableCount} of ${realGuardrails.length}`,
                ablation.manifest,
                "/data/day3_ablation.json",
              )}
            />
            <p className="landing-stat-caption">
              How many of our safety rules actually stopped a payment in this batch —
              checked against a real run, not just declared in a doc. The rest didn't
              get a chance to fire on this particular batch of payments, and the case
              audit screen says exactly why each one didn't, one by one.
            </p>
          </div>
        </div>

        <button type="button" className="btn-primary landing-tour-cta" onClick={() => onNavigate("#tour/0")}>
          Take the guided tour →
        </button>
      </section>

      <section className="landing-cards">
        <h2 className="landing-section-title">Five questions, five screens</h2>
        <p className="landing-section-note">
          Each one answers a real question you'd actually want to ask. Click a card to
          go straight there — you'll get the same "next" and "back" buttons either way.
        </p>
        <div className="landing-card-grid">
          {SCREENS.map((s, i) => (
            <a
              key={s.id}
              href={`#tour/${i}`}
              className="landing-card"
              onClick={(e) => {
                e.preventDefault();
                onNavigate(`#tour/${i}`);
              }}
            >
              <span className="landing-card-question">{s.question}</span>
              <span className="landing-card-summary">{s.summary}</span>
              <span className="landing-card-goto">{s.navLabel} →</span>
            </a>
          ))}
        </div>
      </section>

      <section className="landing-evidence">
        <h2 className="landing-section-title">Where every number on this site actually comes from</h2>
        <p className="landing-section-note">
          We're telling you upfront how sure we are about each kind of number here,
          instead of burying it in the fine print — how confident we are matters as
          much as the number itself.
        </p>
        <div className="landing-evidence-grid">
          {EVIDENCE_TIERS.map((tier) => (
            <div key={tier.label} className="landing-evidence-tier">
              <div className="landing-evidence-badge">
                <Badge label={tier.label} tone={tier.tone} />
              </div>
              <p className="landing-evidence-body">{tier.body}</p>
            </div>
          ))}
        </div>
      </section>
    </main>
  );
}
