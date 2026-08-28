import { useState } from "react";
import "./InfoTip.css";

/**
 * A small "what does this mean" affordance for a term a reviewer unfamiliar with the
 * product shouldn't have to already know -- decline_class_source, idempotency key,
 * short-circuited, and so on. Click/hover reveals one short, plain-language sentence.
 * Never a wall of text: if it needs more than a sentence, it belongs in copy on the
 * page, not a tooltip.
 */
export function InfoTip({ text }: { text: string }) {
  const [open, setOpen] = useState(false);
  return (
    <span className="infotip">
      <button
        type="button"
        className="infotip-trigger"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        aria-label="What does this mean?"
      >
        <svg width="12" height="12" viewBox="0 0 16 16" fill="none">
          <circle cx="8" cy="8" r="6.5" stroke="currentColor" strokeWidth="1.2" />
          <circle cx="8" cy="5.1" r="0.9" fill="currentColor" />
          <path d="M8 7.4V11.2" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" />
        </svg>
      </button>
      {open && <span className="infotip-bubble">{text}</span>}
    </span>
  );
}
