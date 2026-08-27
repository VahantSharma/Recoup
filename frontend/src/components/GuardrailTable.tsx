import type { GateCallRow } from "../lib/artifacts/types";

/**
 * One gate call's 8 guardrail rows, in their real checked order (app.gate.
 * GUARDRAIL_ORDER). Per Change 1 of the approved plan: this shows only what actually
 * happened -- evaluation really did stop at the first hit, so everything after that
 * point is marked "not evaluated," never a hypothetical verdict for a guardrail
 * evaluate() never reached.
 */
export function GuardrailTable({ call }: { call: GateCallRow }) {
  return (
    <div className="guardrail-table-wrap">
      <table className="guardrail-table">
        <thead>
          <tr>
            <th>#</th>
            <th>guardrail</th>
            <th>verdict</th>
          </tr>
        </thead>
        <tbody>
          {call.guardrail_table.map((row, i) => {
            const rowClass = row.fired
              ? "guardrail-row-fired"
              : row.evaluated
                ? "guardrail-row-passed"
                : "guardrail-row-skipped";
            const verdict = row.fired ? "FIRED" : row.evaluated ? "passed" : "not evaluated";
            return (
              <tr key={row.name} className={rowClass}>
                <td className="guardrail-row-index">{i + 1}</td>
                <td className="guardrail-row-name">{row.name}</td>
                <td className="guardrail-row-verdict">
                  {verdict}
                  {row.note ? <div className="guardrail-row-note">{row.note}</div> : null}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <p className="guardrail-table-caption">
        decision: <strong>{call.decision}</strong> — reason: <strong>{call.reason}</strong>
        {call.route_to ? <> — routed to <strong>{call.route_to}</strong></> : null}
      </p>
    </div>
  );
}
