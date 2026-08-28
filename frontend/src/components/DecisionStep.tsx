import type { CSSProperties, ReactNode } from "react";
import "./DecisionStep.css";

/**
 * One step of the case audit's five-step decision trace. A numbered circle connected
 * by a vertical rule to the next step, so the eye follows payment-failed ->
 * classified -> gate-evaluated -> action -> outcome as one sequence, not five
 * disconnected cards.
 *
 * The stagger delay is computed from `number` itself, not CSS :nth-child -- the
 * crafted-example banner some cases show sits before these in the DOM, which would
 * throw nth-child-based indexing off by one and silently drop the last step's
 * animation. Deriving it from the prop that's already the source of truth for "which
 * step is this" can't drift out of sync with what's actually rendered.
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
  const style = { "--step-delay": `${40 + (number - 1) * 90}ms` } as CSSProperties;
  return (
    <div className="step" style={style}>
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
