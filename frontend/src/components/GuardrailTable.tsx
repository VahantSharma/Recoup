import "./GuardrailTable.css";
import { toneForRouteTo } from "../lib/outcome";
import type { GateCallRow } from "../lib/artifacts/types";

/**
 * One gate call's 8 guardrail rows, in their real checked order (app.gate.
 * GUARDRAIL_ORDER). Per Change 1 of the original approved plan: this shows only what
 * actually happened -- evaluation really did stop at the first hit, so everything
 * after that point is marked "not evaluated," never a hypothetical verdict for a
 * guardrail evaluate() never reached.
 *
 * Hierarchy is the whole point of this component: passed rows recede (small, faint),
 * the deciding row dominates (full-width band, its reason shown inline), and
 * not-evaluated rows read clearly as never having run.
 */
export function GuardrailTable({ call }: { call: GateCallRow }) {
  return (
    <div className="gr-table">
      {call.reason === "permitted" && (
        <div className="gr-row gr-row-approved">
          <span className="gr-check" aria-hidden="true">✓</span>
          <span>all 8 guardrails cleared — action permitted</span>
        </div>
      )}
      {call.guardrail_table.map((row, i) => {
        if (row.fired) {
          const tone = toneForRouteTo(call.route_to);
          return (
            <div key={row.name} className={`gr-row gr-row-fired gr-tone-${tone}`}>
              <span className="gr-index">{i + 1}</span>
              <div className="gr-fired-body">
                <span className="gr-fired-name">{row.name}</span>
                <span className="gr-fired-reason">FIRED — {call.reason}</span>
              </div>
            </div>
          );
        }
        if (row.evaluated) {
          return (
            <div key={row.name} className="gr-row gr-row-passed">
              <span className="gr-index">{i + 1}</span>
              <span className="gr-check" aria-hidden="true">✓</span>
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
