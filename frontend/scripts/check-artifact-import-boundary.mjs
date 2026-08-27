#!/usr/bin/env node
// Structural enforcement, not convention -- same spirit as backend's
// tests/test_import_boundary.py. Day 5's standing rule: no number reaches the screen
// except through a committed artifact, read by exactly one loader. Nothing outside
// src/lib/artifacts/ may import a *.json file -- that's what makes "the loader is the
// only JSON reader" a fact a script checks on every run, not a convention someone can
// quietly violate under time pressure.
//
// Run via `npm run check:imports` (also wired into `npm run lint`).

import { readFileSync, readdirSync, statSync } from "node:fs";
import { extname, join, relative } from "node:path";
import { fileURLToPath } from "node:url";

const SRC_DIR = join(fileURLToPath(new URL(".", import.meta.url)), "..", "src");
const EXEMPT_PREFIX = join("src", "lib", "artifacts");
const CHECKED_EXTENSIONS = new Set([".ts", ".tsx"]);
// Matches: import ... from "...json"  |  import("...json")  |  require("...json")
const JSON_IMPORT_RE = /(?:from\s+|import\s*\(\s*|require\s*\(\s*)["']([^"']+\.json)["']/g;

function walk(dir) {
  const out = [];
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    const st = statSync(full);
    if (st.isDirectory()) out.push(...walk(full));
    else if (CHECKED_EXTENSIONS.has(extname(full))) out.push(full);
  }
  return out;
}

function main() {
  const offenders = [];
  for (const file of walk(SRC_DIR)) {
    const rel = relative(process.cwd(), file);
    if (rel.split(/[\\/]/).join("/").includes(EXEMPT_PREFIX.split(/[\\/]/).join("/"))) continue;
    const text = readFileSync(file, "utf-8");
    let m;
    while ((m = JSON_IMPORT_RE.exec(text)) !== null) {
      offenders.push(`${rel}: imports ${m[1]}`);
    }
  }
  if (offenders.length > 0) {
    console.error(
      "check:imports FAILED -- a *.json file is imported outside src/lib/artifacts/.\n" +
      "Every number on screen must come from the artifact loader, never a direct import:\n"
    );
    for (const o of offenders) console.error(`  ${o}`);
    process.exit(1);
  }
  console.log("check:imports OK -- no *.json import outside src/lib/artifacts/");
}

main();
