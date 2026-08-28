import type { ReactNode } from "react";
import "./DecisionStep.css";

/**
 * One step of the case audit's five-step decision trace. A numbered circle connected
 * by a vertical rule to the next step, so the eye follows payment-failed ->
 * classified -> gate-evaluated -> action -> outcome as one sequence, not five
 * disconnected cards.
 */
export function DecisionStep({
  number,
  title,
  isLast,
  children,
}: {
  number: number;
  title: string;
  isLast?: boolean;
  children: ReactNode;
}) {
  return (
    <div className="step">
      <div className="step-rail">
        <div className="step-circle">{number}</div>
        {!isLast && <div className="step-connector" aria-hidden="true" />}
      </div>
      <div className="step-body">
        <h2 className="step-title">{title}</h2>
        <div className="step-card">{children}</div>
      </div>
    </div>
  );
}
