import { useState } from "react";
import "./Badge.css";
import "./Figure.css";
import type { Provenanced } from "../lib/artifacts/provenance";
import type { Tone } from "../lib/outcome";

/**
 * The only sanctioned way to display a value that came from an artifact. Takes a
 * Provenanced<T> -- not a bare T -- so a hardcoded literal doesn't typecheck into this
 * slot; `npm run build` fails if a component tries. A dotted underline marks every
 * such value as clickable; hover solidifies it to --accent. Click reveals the manifest
 * (git SHA, seed, corpus hash, simulator params, artifact link) behind the number --
 * CLAUDE.md's "every number resolves to a manifest," made literal in one gesture.
 *
 * badgeTone renders the value as a colored pill instead of underlined text (e.g.
 * decline_class_source) -- still the same clickable Figure underneath, provenance
 * included, just styled to read as a badge on the page.
 */
export function Figure<T>({
  value,
  label,
  mono,
  badgeTone,
}: {
  value: Provenanced<T>;
  label?: string;
  mono?: boolean;
  badgeTone?: Tone;
}) {
  const [open, setOpen] = useState(false);
  const displayValue = typeof value.value === "string" || typeof value.value === "number"
    ? String(value.value)
    : JSON.stringify(value.value);

  const className = badgeTone
    ? `figure-value figure-value-badge badge-${badgeTone}`
    : `figure-value${mono ? " figure-value-mono" : ""}`;

  return (
    <span className="figure">
      <button
        type="button"
        className={className}
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        title="Click to see the run manifest this value resolves to"
      >
        {label ? <span className="figure-label">{label}: </span> : null}
        {displayValue}
      </button>
      {open && (
        <div className="figure-popover" role="dialog">
          <div className="figure-popover-row">
            <span className="figure-popover-key">artifact</span>
            <span className="figure-popover-val">{value.artifactUrl}</span>
          </div>
          <div className="figure-popover-row">
            <span className="figure-popover-key">git_sha</span>
            <span className="figure-popover-val figure-mono">{value.manifest.git_sha}</span>
          </div>
          <div className="figure-popover-row">
            <span className="figure-popover-key">seed</span>
            <span className="figure-popover-val">{JSON.stringify(value.manifest.seed)}</span>
          </div>
          <div className="figure-popover-row">
            <span className="figure-popover-key">corpus_hash</span>
            <span className="figure-popover-val figure-mono">
              {value.manifest.corpus_hash ?? "(none)"}
            </span>
          </div>
          <div className="figure-popover-row">
            <span className="figure-popover-key">CRN</span>
            <span className="figure-popover-val">
              {value.manifest.use_common_random_numbers ? "on" : "off"}
            </span>
          </div>
          <div className="figure-popover-row">
            <span className="figure-popover-key">generated_at</span>
            <span className="figure-popover-val">{value.manifest.generated_at}</span>
          </div>
          <details className="figure-popover-details">
            <summary>simulator_params</summary>
            <pre>{JSON.stringify(value.manifest.simulator_params, null, 2)}</pre>
          </details>
          <details className="figure-popover-details">
            <summary>policy_params</summary>
            <pre>{JSON.stringify(value.manifest.policy_params, null, 2)}</pre>
          </details>
        </div>
      )}
    </span>
  );
}
