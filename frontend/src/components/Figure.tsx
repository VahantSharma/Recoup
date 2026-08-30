import { useRef } from "react";
import { createPortal } from "react-dom";
import "./Badge.css";
import "./Figure.css";
import { useDismissiblePopover } from "../lib/useDismissiblePopover";
import { usePopoverPosition } from "../lib/usePopoverPosition";
import type { Provenanced } from "../lib/artifacts/provenance";
import type { Tone } from "../lib/outcome";
import { commitUrl, scriptUrl } from "../lib/repo";

/**
 * The only sanctioned way to display a value that came from an artifact. Takes a
 * Provenanced<T> -- not a bare T -- so a hardcoded literal doesn't typecheck into this
 * slot; `npm run build` fails if a component tries. A dotted underline marks every
 * such value as clickable; hover solidifies it to --accent. Click reveals the manifest
 * (git SHA, seed, corpus hash, simulator params) behind the number, PLUS a real link to
 * the raw artifact JSON itself -- CLAUDE.md's "every number resolves to a manifest,"
 * made literal enough that a reviewer can actually open the file, not just read a
 * summary of it.
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
  const popoverRef = useRef<HTMLDivElement>(null);
  const { open, setOpen, ref } = useDismissiblePopover<HTMLSpanElement>(popoverRef);
  const position = usePopoverPosition(ref, open, { placement: "bottom-start", estimatedWidth: 320 });
  const displayValue = typeof value.value === "string" || typeof value.value === "number"
    ? String(value.value)
    : JSON.stringify(value.value);

  const className = badgeTone
    ? `figure-value figure-value-badge badge badge-${badgeTone}`
    : `figure-value${mono ? " figure-value-mono" : ""}`;

  return (
    <span className="figure" ref={ref}>
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
      {open && position &&
        createPortal(
          // Rendered into document.body via a portal, positioned with `position: fixed`
          // from `position` (computed from the trigger's real screen coordinates) --
          // never `position: absolute` relative to this span. An ancestor `.step` (or
          // any future ancestor) leaving behind a settled, visually-identity `transform`
          // from an entrance animation creates a stacking context that traps an
          // absolutely-positioned popover behind the NEXT sibling's own stacking
          // context, no matter how high z-index is set inside it -- confirmed live via
          // document.elementFromPoint() landing on a sibling .step-card, not this
          // popover, before this fix. See usePopoverPosition's docstring.
          <div
            className="figure-popover"
            role="dialog"
            ref={popoverRef}
            style={{
              position: "fixed",
              top: position.top,
              left: position.left,
              // Inline, not just the CSS class's own cap -- this is the one computed
              // from the trigger's REAL on-screen position (see usePopoverPosition),
              // so expanding policy_params/simulator_params below can never push the
              // popover's own bottom edge past the actual window, wherever on the
              // page the trigger happens to sit.
              maxHeight: position.maxHeight,
            }}
          >
            <p className="figure-popover-intro">
              Computed in a real, reproducible run — not asserted. Re-run{" "}
              <span className="figure-mono">{value.manifest.script}</span> at this exact
              commit and every figure on this screen reproduces.
            </p>
            <div className="figure-popover-row">
              <span className="figure-popover-key">artifact</span>
              <a className="figure-popover-link" href={value.artifactUrl} target="_blank" rel="noreferrer">
                {value.artifactUrl} ↗
              </a>
            </div>
            <div className="figure-popover-row">
              <span className="figure-popover-key">script</span>
              <a
                className="figure-popover-link figure-mono"
                href={scriptUrl(value.manifest.git_sha, value.manifest.script)}
                target="_blank"
                rel="noreferrer"
                title="Open this exact script on GitHub, at the commit that produced this number"
              >
                {value.manifest.script} ↗
              </a>
            </div>
            <div className="figure-popover-row">
              <span className="figure-popover-key">git_sha</span>
              <a
                className="figure-popover-link figure-mono"
                href={commitUrl(value.manifest.git_sha)}
                target="_blank"
                rel="noreferrer"
                title="Open this exact commit on GitHub"
              >
                {value.manifest.git_sha} ↗
              </a>
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
          </div>,
          document.body,
        )}
    </span>
  );
}
