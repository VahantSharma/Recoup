import "./GuardrailTable.css";
import { toneForRouteTo } from "../lib/outcome";
import { guardrailPlainLanguage } from "../lib/plainLanguage";
import type { GateCallRow } from "../lib/artifacts/types";

const CHECK = (
  <svg width="12" height="12" viewBox="0 0 16 16" fill="none" aria-hidden="true">
    <path d="M3 8.5 6.5 12 13 4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);

const STAMP_TEXT: Record<string, string> = {
  stop: "stopped",
  warn: "review",
  policy: "by design",
};

/**
 * One gate call's 8 guardrail rows, in their real checked order (app.gate.
 * GUARDRAIL_ORDER). This shows only what actually happened -- evaluation really did
 * stop at the first hit, so everything after that point is marked "not evaluated,"
 * never a hypothetical verdict for a guardrail evaluate() never reached.
 *
 * A one-line legend precedes the rows so a reviewer who has never seen this screen
 * before understands the three states in two seconds, without reading all 8 rows
 * individually -- the hierarchy (passed recedes, the decision dominates, skipped reads
 * as skipped) does the rest. The legend's middle dot is neutral ink, not a fixed color
 * -- the real stamp underneath can be red (stop), amber (human review), or bronze (a
 * deliberate not-worked, a different KIND of thing from a stop -- see toneForRouteTo).
 */
export function GuardrailTable({ call }: { call: GateCallRow }) {
  return (
    <div className="gr-table">
      <div className="gr-legend">
        <span className="gr-legend-item"><span className="gr-legend-glyph gr-legend-glyph-ok">{CHECK}</span>passed</span>
        <span className="gr-legend-item"><span className="gr-legend-dot" />decided this case</span>
        <span className="gr-legend-item gr-legend-skip">didn't run — an earlier check already decided</span>
      </div>

      {call.reason === "permitted" && (
        <div className="gr-row gr-row-approved">
          <span className="gr-check-lg" aria-hidden="true">{CHECK}</span>
          <span>all 8 guardrails cleared — {guardrailPlainLanguage("permitted")}</span>
        </div>
      )}
      {call.guardrail_table.map((row, i) => {
        if (row.fired) {
          const tone = toneForRouteTo(call.route_to);
          return (
            <div key={row.name} className={`gr-row gr-row-fired gr-tone-${tone}`}>
              <span className="gr-index">{i + 1}</span>
              <div className="gr-fired-body">
                <span className="gr-fired-plain">{guardrailPlainLanguage(call.reason)}</span>
                <span className="gr-fired-name">{row.name} — decided this case, step {i + 1} of 8</span>
              </div>
              <span className="gr-stamp">{STAMP_TEXT[tone]}</span>
            </div>
          );
        }
        if (row.evaluated) {
          return (
            <div key={row.name} className="gr-row gr-row-passed">
              <span className="gr-index">{i + 1}</span>
              <span className="gr-check" aria-hidden="true">{CHECK}</span>
              <span className="gr-name">{row.name}</span>
            </div>
          );
        }
        return (
          <div key={row.name} className="gr-row gr-row-skipped">
            <span className="gr-index">{i + 1}</span>
            <span className="gr-name">{row.name}</span>
            <span className="gr-skipped-note">{row.note}</span>
          </div>
        );
      })}
    </div>
  );
}
