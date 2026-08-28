import { useState } from "react";
import "./CopyButton.css";

type CopyState = "idle" | "copied" | "failed";

/** A small "copy full value" affordance for a truncated display value (e.g. the
 * idempotency key) -- the full value is always copyable even though only a prefix is
 * ever shown on screen. A failed clipboard write (insecure context, permission denied)
 * shows a real failure state -- a reviewer who clicks this and sees nothing happen has
 * no way to tell it's broken versus just slow; silence is never the right answer here. */
export function CopyButton({ value }: { value: string }) {
  const [state, setState] = useState<CopyState>("idle");

  const onClick = async () => {
    try {
      await navigator.clipboard.writeText(value);
      setState("copied");
    } catch {
      setState("failed");
    }
    setTimeout(() => setState("idle"), 1600);
  };

  return (
    <button
      type="button"
      className={`copy-button${state === "copied" ? " copy-button-copied" : ""}${state === "failed" ? " copy-button-failed" : ""}`}
      onClick={onClick}
      title="Copy full value"
    >
      {state === "copied" && (
        <span className="copy-button-done">
          copied
          <svg width="9" height="9" viewBox="0 0 16 16" fill="none" aria-hidden="true">
            <path d="M3 8.5 6.5 12 13 4" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </span>
      )}
      {state === "failed" && "couldn't copy"}
      {state === "idle" && "copy"}
    </button>
  );
}
