import "./CaseList.css";
import { Badge } from "./Badge";
import { InfoTip } from "./InfoTip";
import { decisiveReason, describeOutcome } from "../lib/outcome";
import type { CaseAuditRow, UnreachableGuardrailNote } from "../lib/artifacts/types";

/**
 * The case list, always visible -- no dropdown. A judge sees the VARIETY of outcomes
 * at a glance: each row carries an outcome badge and the guardrail that decided it,
 * so the variety that makes this screen worth looking at isn't hidden behind a click.
 */
export function CaseList({
  cases,
  selectedId,
  onSelect,
  liveCaseId,
  unreachable,
}: {
  cases: CaseAuditRow[];
  selectedId: string;
  onSelect: (id: string) => void;
  liveCaseId: string;
  unreachable: UnreachableGuardrailNote[];
}) {
  return (
    <nav className="case-list" aria-label="cases">
      <div className="case-list-label">
        Cases in this batch
        <InfoTip text="Every row is a real outcome from one deterministic run, not a hand-picked example — one per guardrail this gate can actually fire, plus the one real payment." />
      </div>
      <ul className="case-list-items">
        {cases.map((row) => {
          const outcome = describeOutcome(row);
          const reason = decisiveReason(row) ?? "(no action proposed)";
          const isSelected = row.case_id === selectedId;
          const isLive = row.case_id === liveCaseId;
          return (
            <li key={row.case_id}>
              <button
                type="button"
                className={`case-row${isSelected ? " case-row-selected" : ""}`}
                onClick={() => onSelect(row.case_id)}
                aria-current={isSelected}
              >
                <div className="case-row-top">
                  <span className="case-row-id" title={row.case_id}>{row.case_id}</span>
                  {isLive && <Badge label="verified live" tone="ok" />}
                </div>
                <div className="case-row-mid">
                  <Badge label={outcome.label} tone={outcome.tone} />
                </div>
                <div className="case-row-reason">{reason}</div>
              </button>
            </li>
          );
        })}
      </ul>

      <details className="unreachable-collapsed">
        <summary>
          {unreachable.length} guardrails this batch can't demonstrate
        </summary>
        <ul className="unreachable-list">
          {unreachable.map((n) => (
            <li key={n.name}>
              <span className="unreachable-name">{n.name}</span>
              <p className="unreachable-why">{n.why}</p>
            </li>
          ))}
        </ul>
      </details>
    </nav>
  );
}
