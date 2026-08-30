// The one place allowed to read a committed artifact (frontend/scripts/
// check-artifact-import-boundary.mjs enforces that structurally). Fetches
// /data/<schema>.json, checks its schema_name/schema_version, and THROWS LOUDLY on any
// mismatch -- a stale-schema render is the same bug class as the DATABASE_URL and CRN
// bugs (docs/results.md), never a silent fallback to whatever shape happened to be on
// disk. Per the plan's one addition on top of the approved design.
import type {
  ArtifactEnvelope,
  CaseAuditArtifact,
  Day3AblationArtifact,
  Day3SweepArtifact,
  Day4BakeoffArtifact,
  Day4BoundDecompositionArtifact,
  Day4HeldOutAblationArtifact,
} from "./types";

const CASE_AUDIT_SCHEMA_NAME = "case_audit";
const CASE_AUDIT_SCHEMA_VERSION = "1.0.0";
const DAY3_ABLATION_SCHEMA_VERSION = "1.0.0";
const DAY3_SWEEP_SCHEMA_VERSION = "1.0.0";
const DAY4_HELD_OUT_ABLATION_SCHEMA_VERSION = "1.0.0";
const DAY4_BOUND_DECOMPOSITION_SCHEMA_VERSION = "1.0.0";
const DAY4_BAKEOFF_SCHEMA_VERSION = "1.0.0";

async function fetchEnvelope<T>(schemaName: string, expectedVersion: string): Promise<ArtifactEnvelope<T>> {
  const url = `/data/${schemaName}.json`;
  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(`artifact loader: ${url} fetch failed with HTTP ${res.status}`);
  }
  // A genuinely missing file under Vite's dev server (and some static hosts' SPA
  // fallback rewriting) returns index.html at HTTP 200, not a 404 -- res.ok alone
  // doesn't catch that. Confirmed live: deleting the committed artifact and reloading
  // produced "Unexpected token '<', <!doctype..." instead of a clear diagnosis. Caught
  // here by content-type before the parse failure can happen at all, so the message
  // names the real problem instead of a JSON syntax error that has nothing to do with
  // JSON syntax.
  const contentType = res.headers.get("content-type") ?? "";
  if (!contentType.includes("json")) {
    throw new Error(
      `artifact loader: ${url} did not return JSON (content-type: ${contentType || "(none)"}) -- ` +
        `the file is likely missing. Regenerate it: the script named in this artifact's own ` +
        `manifest, from the repo root.`,
    );
  }
  const envelope = (await res.json()) as ArtifactEnvelope<T>;
  if (envelope.schema_name !== schemaName) {
    throw new Error(
      `artifact loader: ${url} declares schema_name=${JSON.stringify(envelope.schema_name)}, ` +
        `expected ${JSON.stringify(schemaName)} -- refusing to render a mismatched artifact.`,
    );
  }
  if (envelope.schema_version !== expectedVersion) {
    throw new Error(
      `artifact loader: ${url} declares schema_version=${JSON.stringify(envelope.schema_version)}, ` +
        `expected ${JSON.stringify(expectedVersion)} -- the frontend's types have drifted from what ` +
        `the backend last exported. Regenerate the artifact or update EXPECTED version, never ignore.`,
    );
  }
  return envelope;
}

export async function loadCaseAudit(): Promise<ArtifactEnvelope<CaseAuditArtifact>> {
  return fetchEnvelope<CaseAuditArtifact>(CASE_AUDIT_SCHEMA_NAME, CASE_AUDIT_SCHEMA_VERSION);
}

export async function loadDay3Ablation(): Promise<ArtifactEnvelope<Day3AblationArtifact>> {
  return fetchEnvelope<Day3AblationArtifact>("day3_ablation", DAY3_ABLATION_SCHEMA_VERSION);
}

export async function loadDay3Sweep(): Promise<ArtifactEnvelope<Day3SweepArtifact>> {
  return fetchEnvelope<Day3SweepArtifact>("day3_sweep", DAY3_SWEEP_SCHEMA_VERSION);
}

export async function loadDay4HeldOutAblation(): Promise<ArtifactEnvelope<Day4HeldOutAblationArtifact>> {
  return fetchEnvelope<Day4HeldOutAblationArtifact>("day4_held_out_ablation", DAY4_HELD_OUT_ABLATION_SCHEMA_VERSION);
}

export async function loadDay4BoundDecomposition(): Promise<ArtifactEnvelope<Day4BoundDecompositionArtifact>> {
  return fetchEnvelope<Day4BoundDecompositionArtifact>(
    "day4_bound_decomposition", DAY4_BOUND_DECOMPOSITION_SCHEMA_VERSION,
  );
}

export async function loadDay4Bakeoff(): Promise<ArtifactEnvelope<Day4BakeoffArtifact>> {
  return fetchEnvelope<Day4BakeoffArtifact>("day4_bakeoff", DAY4_BAKEOFF_SCHEMA_VERSION);
}
