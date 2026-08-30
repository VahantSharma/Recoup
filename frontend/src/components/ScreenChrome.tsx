import type { ReactNode } from "react";
import "./ScreenChrome.css";
import { screenByHash, SCREENS } from "../lib/screens";
import { GlossaryTerm } from "./GlossaryTerm";

/** `screenId` looks up both the nav-label (`right`) and the one-line purpose
 * statement from lib/screens.ts's single registry -- the same sentence a tour step
 * and a landing card both already agree on, never a fourth independently-worded copy
 * a screen could drift out of sync with. Every screen using this shared Masthead gets
 * the purpose statement for free; a reviewer is never mid-screen wondering what
 * question this particular trace/table/chart is even trying to answer. */
export function Masthead({ screenId, subtitle }: { screenId: string; subtitle: ReactNode }) {
  const meta = screenByHash(`#${screenId}`) ?? SCREENS.find((s) => s.id === screenId);
  return (
    <>
      <div className="masthead">
        <div className="masthead-wordmark">
          <span className="masthead-mark">Recoup</span>
          <span className="masthead-tag">a ledger of every decision, not just the wins</span>
        </div>
        <div className="masthead-right">{meta?.navLabel ?? screenId}</div>
      </div>
      <p className="screen-subtitle">{subtitle}</p>
      {meta && <p className="screen-purpose">{meta.purpose}</p>}
    </>
  );
}

export function ProvenanceStrip({ shortSha, artifactUrl }: { shortSha: string; artifactUrl: string }) {
  return (
    <div className="provenance-strip">
      Every number below has a real{" "}
      <GlossaryTerm term="manifest">receipt</GlossaryTerm> attached to it —{" "}
      <span className="provenance-strip-sha">{shortSha}</span> —{" "}
      <a className="provenance-strip-link" href={artifactUrl} target="_blank" rel="noreferrer">
        open the raw data yourself ↗
      </a>
    </div>
  );
}

export function LoadingSkeleton() {
  return (
    <main className="screen">
      <div className="skeleton" style={{ height: 52 }} />
      <div className="skeleton skeleton-block" />
      <div className="skeleton skeleton-block" />
    </main>
  );
}

export function ErrorScreen({ message, command }: { message: string; command: string }) {
  return (
    <main className="screen">
      <h1>Failed to load</h1>
      <p className="load-error-help">
        This usually means the artifact hasn't been generated yet, or its schema
        changed since the page was built. From the repo root:{" "}
        <span className="load-error-command">{command}</span> then reload.
      </p>
      <pre className="load-error">{message}</pre>
    </main>
  );
}
