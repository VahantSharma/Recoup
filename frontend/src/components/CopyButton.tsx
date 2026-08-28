import { useState } from "react";
import "./CopyButton.css";

/** A small "copy full value" affordance for a truncated display value (e.g. the
 * idempotency key) -- the full value is always copyable even though only a prefix is
 * ever shown on screen. */
export function CopyButton({ value }: { value: string }) {
  const [copied, setCopied] = useState(false);

  const onClick = async () => {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      setTimeout(() => setCopied(false), 1200);
    } catch {
      // Clipboard API can be unavailable (e.g. insecure context) -- fail silently,
      // this is a convenience affordance, never load-bearing.
    }
  };

  return (
    <button
      type="button"
      className={`copy-button${copied ? " copy-button-copied" : ""}`}
      onClick={onClick}
      title="Copy full value"
    >
      {copied ? (
        <span className="copy-button-done">
          copied
          <svg width="9" height="9" viewBox="0 0 16 16" fill="none" aria-hidden="true">
            <path d="M3 8.5 6.5 12 13 4" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </span>
      ) : (
        "copy"
      )}
    </button>
  );
}
