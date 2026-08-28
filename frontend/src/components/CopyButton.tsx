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
    <button type="button" className="copy-button" onClick={onClick} title="Copy full value">
      {copied ? "copied" : "copy"}
    </button>
  );
}
