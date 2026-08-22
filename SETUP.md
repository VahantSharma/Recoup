# Setting this up in VS Code

## What each piece is actually doing

- **`CLAUDE.md`** — auto-loaded into every Claude Code session opened in this folder. This is how "the environment has the entire context": you don't re-explain the track, the guardrails, or the stack every session — it's already there. It `@`-imports `docs/buildathon-plan.md` so the full plan loads too, without bloating the top of the file.
- **`.mcp.json`** — project-scoped MCP servers, checked into git so every session (yours, a teammate's, a future one) gets the same tools automatically. No secrets live in this file — it references `${VAR}` names that get filled from your actual shell environment at launch. Six servers: `razorpay` (hosted remote — real test-mode API calls), `context7` (current library docs), `filesystem` (scoped access beyond this folder), `memory` (a knowledge graph that persists across sessions), `playwright` (a real browser Claude can drive), `github` (repo operations).
- **`.claude/commands/`** — three custom slash commands (`/safety-check`, `/guardrail-check`, `/rubric-check`) that turn the guardrails and the rubric into things Claude Code can actually check the repo against, on demand.
- **`docs/claude-code-tips.md`** — install commands, MCP setup for the standalone servers, and a curated setup checklist beyond this one project.

## 1. Prerequisites

- The **Claude Code CLI**, installed and signed in — `curl -fsSL https://claude.ai/install.sh | bash` (macOS/Linux/WSL) or the PowerShell equivalent for Windows. Run it from VS Code's integrated terminal; no separate extension required. Full commands: `docs/claude-code-tips.md`.
- **Node.js 18+** (all six MCP servers here run via `npx`; nothing needs Docker anymore).
- A **Razorpay test-mode** account — dashboard.razorpay.com → Settings → API Keys → Test Mode → generate a Key ID and Key Secret. (Free, no live business verification needed for test mode.)
- An **Anthropic API key** — console.anthropic.com → API keys.
- Optional: a **Context7 API key** (context7.com) for a higher free rate limit — the server works without one.
- Optional: a **GitHub personal access token** (repo scope) if you want the `github` MCP server wired up too.

## 2. Fill in real secrets

```bash
cp .env.example .env
```

Open `.env` and paste in your real `RAZORPAY_KEY_ID`, `RAZORPAY_KEY_SECRET`, `ANTHROPIC_API_KEY`, and (optional) `CONTEXT7_API_KEY` / `GITHUB_PAT`. **Never commit this file** — `.gitignore` already excludes it.

Then derive the one value you can't just paste — Razorpay's remote MCP server authenticates with HTTP Basic auth, base64-encoded:
```bash
echo -n "$RAZORPAY_KEY_ID:$RAZORPAY_KEY_SECRET" | base64
```
Paste the output into `RAZORPAY_MCP_TOKEN` in `.env`.

## 3. Get those variables into your actual shell environment

Claude Code doesn't read `.env` files on its own — the `${VAR}` references in `.mcp.json` are filled from your shell's environment when VS Code / Claude Code launches. Two ways to do this reliably:

**Quick (manual, per terminal session):**
```bash
set -a; source .env; set +a
code .
```

**Robust (recommended — stays correct automatically):** install [direnv](https://direnv.net/), then:
```bash
echo "dotenv" > .envrc
direnv allow
```
Now any terminal that `cd`s into this folder — including VS Code's integrated terminal — has the variables loaded automatically, every time, without you remembering to source anything.

## 4. Verify the MCP servers actually connect

Open this folder in VS Code, start a Claude Code session, and run:
```
/mcp
```
You should see `razorpay`, `context7`, `filesystem`, `memory`, `playwright`, and (if configured) `github` listed as connected.

**If `razorpay` (or any server) fails to connect:** don't guess — run `claude mcp get razorpay` for the exact error, and see the troubleshooting section in `docs/claude-code-tips.md`. The most common cause by far is step 3 above not actually happening — the `.env` values were filled in, but never got exported into the shell VS Code launched from, so every `${VAR}` in `.mcp.json` silently resolved to empty.

## 5. Prove the context is actually loaded

Ask the session, cold, with no other prompting:

> "What track are we building for, and what's the headline metric — and what must it never be?"

If it answers "AI Revenue Recovery" and "incremental lift vs. a control arm — never gross recovery" without you re-explaining anything, `CLAUDE.md` is wired correctly.

## 6. Prove the Razorpay integration is real, before writing any app code

Ask:

> "Using the razorpay MCP server, create a test-mode payment link for ₹100 and show me the response."

A real `short_url` coming back from Razorpay's API means the hardest integration risk is retired on day one — not discovered on day four.

## 7. Initialize git and push

```bash
git init
git add .
git commit -m "scaffold: CLAUDE.md, MCP config, buildathon plan"
```
Create the GitHub repo yourself, or — since the `github` MCP server is already connected — just ask Claude Code to create it and push for you.

## Notes on robustness

- `.mcp.json` is committed to git on purpose, so the environment is reproducible for anyone (including a future you) who clones this repo and follows steps 1–4. It carries zero secrets — only variable *names*.
- Every guardrail and rubric line lives in `CLAUDE.md` in plain language specifically so Claude Code can't "forget" them mid-session or invent a shortcut around them under time pressure.
- If something in this guide turns out stale (an MCP config field renamed, a flag changed), that's expected — MCP tooling moves fast. Run `/mcp` and check each server's own `--help` output as the source of truth over this file.
