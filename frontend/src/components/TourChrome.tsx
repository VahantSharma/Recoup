import { useEffect } from "react";
import "./TourChrome.css";
import { SCREENS } from "../lib/screens";

/**
 * The guided tour's bottom bar -- sticky, so it stays in frame regardless of scroll
 * position within a step (also what keeps it inside a 1440x810 video frame without
 * hunting for it). Progress shows every step's name up front, not just a dot count,
 * so "the shape of the argument" is visible from step 0, per the plan. Left/Right
 * arrow keys move between steps whenever focus isn't inside a text input (sliders and
 * other screens may have their own arrow-key-driven controls that must win locally).
 */
export function TourChrome({
  stepIndex,
  onNavigate,
  onExit,
}: {
  stepIndex: number;
  onNavigate: (hash: string) => void;
  onExit: () => void;
}) {
  const isFirst = stepIndex === 0;
  const isLast = stepIndex === SCREENS.length - 1;

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      const tag = target?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || target?.isContentEditable) return;
      if (e.key === "ArrowRight" && !isLast) onNavigate(`#tour/${stepIndex + 1}`);
      else if (e.key === "ArrowLeft" && !isFirst) onNavigate(`#tour/${stepIndex - 1}`);
      else if (e.key === "Escape") onExit();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [stepIndex, isFirst, isLast, onNavigate, onExit]);

  return (
    <div className="tour-chrome" role="navigation" aria-label="Guided tour">
      <div className="tour-progress">
        {SCREENS.map((s, i) => (
          <a
            key={s.id}
            href={`#tour/${i}`}
            className={`tour-step${i === stepIndex ? " tour-step-active" : ""}${i < stepIndex ? " tour-step-done" : ""}`}
            onClick={(e) => {
              e.preventDefault();
              onNavigate(`#tour/${i}`);
            }}
            aria-current={i === stepIndex ? "step" : undefined}
          >
            <span className="tour-step-index">{i + 1}</span>
            <span className="tour-step-name">{s.navLabel}</span>
          </a>
        ))}
      </div>
      <div className="tour-controls">
        <button type="button" className="tour-btn" onClick={onExit}>
          Exit tour
        </button>
        <button
          type="button"
          className="tour-btn"
          disabled={isFirst}
          onClick={() => onNavigate(`#tour/${stepIndex - 1}`)}
        >
          ← Back
        </button>
        <button
          type="button"
          className="tour-btn tour-btn-primary"
          disabled={isLast}
          onClick={() => onNavigate(`#tour/${stepIndex + 1}`)}
        >
          {isLast ? "Tour complete" : "Next →"}
        </button>
      </div>
    </div>
  );
}
