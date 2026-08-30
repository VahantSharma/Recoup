import { useRef, type ReactNode } from "react";
import { createPortal } from "react-dom";
import "./GlossaryTerm.css";
import { useDismissiblePopover } from "../lib/useDismissiblePopover";
import { usePopoverPosition } from "../lib/usePopoverPosition";
import { GLOSSARY } from "../lib/glossary";

/**
 * Wraps a term wherever it's actually used in a sentence -- a dotted underline under
 * the word itself, not a separate "what does this mean" icon a reviewer has to
 * notice first. Click or tap reveals the one-sentence definition from
 * lib/glossary.ts, the same portal-and-position mechanism InfoTip already uses (see
 * that component's own comments for why a portal: an ancestor's settled entrance
 * animation can trap an ordinarily-positioned popover behind later content no matter
 * how high its z-index is set).
 */
export function GlossaryTerm({ term, children }: { term: keyof typeof GLOSSARY; children: ReactNode }) {
  const bubbleRef = useRef<HTMLSpanElement>(null);
  const { open, setOpen, ref } = useDismissiblePopover<HTMLSpanElement>(bubbleRef);
  const position = usePopoverPosition(ref, open, { placement: "top-center", gap: 7, estimatedWidth: 280 });
  const definition = GLOSSARY[term];

  return (
    <span className="glossary-term" ref={ref}>
      <button
        type="button"
        className="glossary-term-trigger"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        aria-label={`What does "${term}" mean?`}
      >
        {children}
      </button>
      {open &&
        position &&
        createPortal(
          <span
            className="glossary-term-bubble"
            ref={bubbleRef}
            style={{ position: "fixed", top: position.top, left: position.left }}
          >
            <strong className="glossary-term-name">{term}</strong>
            <span className="glossary-term-def">{definition}</span>
          </span>,
          document.body,
        )}
    </span>
  );
}
