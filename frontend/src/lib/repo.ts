/**
 * Turns a manifest's `git_sha` / `script` into real GitHub links, so a reviewer can
 * jump straight from a number on the page to the exact commit and the exact script
 * that produced it — instead of copying a 40-character hash out of a popover and
 * pasting it into GitHub's own search box by hand. That copy-paste detour is exactly
 * the kind of friction that makes a reviewer stop checking a number rather than start.
 *
 * IMPORTANT — these links only resolve once the commit they point to has actually
 * been pushed to `origin`. A manifest's git_sha is always the real local HEAD at the
 * moment that artifact was generated (`app/manifest.py::git_sha`), which is correct
 * and honest, but if that commit hasn't been pushed yet, GitHub simply doesn't have
 * it — the link 404s until `git push` happens. Nothing here can detect that from the
 * browser; don't treat a working link as proof of anything beyond "this was pushed."
 */
const REPO_URL = "https://github.com/VahantSharma/Recoup";

export function commitUrl(gitSha: string): string {
  return `${REPO_URL}/commit/${gitSha}`;
}

// Every manifest's `script` field is written relative to `backend/` (e.g.
// "scripts/run_day3_ablation.py" -> backend/scripts/run_day3_ablation.py) — confirmed
// against every committed artifact in frontend/public/data/, not assumed.
export function scriptUrl(gitSha: string, script: string): string {
  return `${REPO_URL}/blob/${gitSha}/backend/${script}`;
}
