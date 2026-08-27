// The one place allowed to read a committed artifact (frontend/scripts/
// check-artifact-import-boundary.mjs enforces that structurally). Fetches
// /data/<schema>.json, checks its schema_name/schema_version, and THROWS LOUDLY on any
// mismatch -- a stale-schema render is the same bug class as the DATABASE_URL and CRN
// bugs (docs/results.md), never a silent fallback to whatever shape happened to be on
// disk. Per the plan's one addition on top of the approved design.
import type { ArtifactEnvelope, CaseAuditArtifact } from "./types";

const CASE_AUDIT_SCHEMA_NAME = "case_audit";
const CASE_AUDIT_SCHEMA_VERSION = "1.0.0";

async function fetchEnvelope<T>(schemaName: string, expectedVersion: string): Promise<ArtifactEnvelope<T>> {
  const url = `/data/${schemaName}.json`;
  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(`artifact loader: ${url} fetch failed with HTTP ${res.status}`);
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
