// Provenance at render -- Change 2 of the approved Day 5 plan, replacing a regex
// hardcoded-figure backstop (lint-grade heuristic, false-positives on axis labels,
// false-negatives on anything that isn't currency/percent) with enforcement by
// construction: every value the screen displays is wrapped with its source artifact
// and manifest before it ever reaches a component. <Figure> (see
// src/components/Figure.tsx) only accepts a Provenanced<T> -- a raw literal doesn't
// typecheck into that slot, so `npm run build` is what catches a hardcoded number, not
// a pattern match against it after the fact.
import type { ArtifactManifest } from "./types";

export interface Provenanced<T> {
  value: T;
  artifactUrl: string;
  manifest: ArtifactManifest;
}

export function withProvenance<T>(value: T, manifest: ArtifactManifest, artifactUrl: string): Provenanced<T> {
  return { value, artifactUrl, manifest };
}
