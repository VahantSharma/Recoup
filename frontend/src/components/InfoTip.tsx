import { useRef } from "react";
import { createPortal } from "react-dom";
import "./InfoTip.css";
import { useDismissiblePopover } from "../lib/useDismissiblePopover";
import { usePopoverPosition } from "../lib/usePopoverPosition";

/**
 * A small "what does this mean" affordance for a term a reviewer unfamiliar with the
 * product shouldn't have to already know -- decline_class_source, idempotency key,
 * short-circuited, and so on. Click reveals one short, plain-language sentence.
 * Never a wall of text: if it needs more than a sentence, it belongs in copy on the
 * page, not a tooltip.
 *
 * Portaled into document.body for the same reason Figure's popover is -- see
 * usePopoverPosition's docstring. InfoTip sits inside the same `.step` ancestors
 * Figure does, so it was trapped by the identical stacking context, confirmed live
 * the same way.
 */
export function InfoTip({ text }: { text: string }) {
  const bubbleRef = useRef<HTMLSpanElement>(null);
  const { open, setOpen, ref } = useDismissiblePopover<HTMLSpanElement>(bubbleRef);
  const position = usePopoverPosition(ref, open, { placement: "top-center", gap: 7, estimatedWidth: 260 });
  return (
    <span className="infotip" ref={ref}>
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
      {open && position &&
        createPortal(
          <span
            className="infotip-bubble"
            ref={bubbleRef}
            style={{ position: "fixed", top: position.top, left: position.left }}
          >
            {text}
          </span>,
          document.body,
        )}
    </span>
  );
}
