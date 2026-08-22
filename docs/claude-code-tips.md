# Claude Code — install, MCP servers, and the setup that actually moves the needle

Verified against Anthropic's own docs (code.claude.com/docs, support.claude.com) rather than assumed. Community "tips" sources are marked as such — treat those as worth trying, not as documented behavior.

## 1. Install the CLI (not the desktop app) in VS Code's terminal

```bash
# macOS / Linux / WSL — recommended, auto-updates in the background
curl -fsSL https://claude.ai/install.sh | bash
```
```powershell
# Windows PowerShell
irm https://claude.ai/install.ps1 | iex
```
Then, from any project folder, open VS Code's integrated terminal (`` Ctrl+` ``) and run:
```bash
claude
```
That's it — no separate VS Code extension is required for this; the CLI runs directly in the integrated terminal and reads the same `CLAUDE.md` / `.mcp.json` / `.claude/` files either way. (There's also an official Claude Code VS Code extension with inline diffs if you want that instead of the terminal — `code.claude.com/docs/en/vs-code`.)

```bash
claude --version   # confirm install
claude doctor       # full health check — install, settings, MCP config
```

npm install works too if you prefer it: `npm install -g @anthropic-ai/claude-code` (never with `sudo`). Requires Node 22+.

## 2. The "famous" MCP servers

Run these **in your terminal**, not inside a `claude` session — `claude mcp add` registers the server; `/mcp` inside a session checks and manages it afterward.

```bash
# Context7 — up-to-date library docs pulled straight into context.
# Hosted, no local process. API key is optional (raises the free rate limit).
claude mcp add --transport http context7 https://mcp.context7.com/mcp \
  --header "Authorization: Bearer YOUR_CONTEXT7_KEY"

# Filesystem — scoped read/write to specific directories beyond the project root
claude mcp add filesystem -- npx -y @modelcontextprotocol/server-filesystem ~/some/other/dir

# Memory — a persistent knowledge graph that survives across sessions
claude mcp add memory -- npx -y @modelcontextprotocol/server-memory

# Playwright — a real browser Claude can navigate, click, and read
claude mcp add playwright -- npx -y @playwright/mcp@latest
```

Verify:
```bash
claude mcp list          # from your shell
```
or inside a session:
```
/mcp
```

**Scope matters.** By default `claude mcp add` registers at `local` scope — private to you, this project only. Add `--scope user` to make a server available in *every* project (good for context7/filesystem/memory/playwright, which aren't project-specific), or `--scope project` to write it into `.mcp.json` so it's shared with anyone who clones the repo (that's what this project's own `.mcp.json` does, for `razorpay` and `github`).

```bash
claude mcp add --scope user context7 --transport http https://mcp.context7.com/mcp \
  --header "Authorization: Bearer YOUR_CONTEXT7_KEY"
```

## 3. Fixing "the Razorpay MCP isn't working"

Diagnose in order — this is the official troubleshooting path, not guesswork:

```bash
claude mcp list              # shows a status per server
claude mcp get razorpay      # shows the exact error / HTTP status
```

The status tells you what to do next:
- **`✘ Failed to connect` / `Connection error`** on a *local* (docker) server — run the underlying command directly in your terminal to see the real error:
  ```bash
  docker run --rm -i -e RAZORPAY_KEY_ID -e RAZORPAY_KEY_SECRET razorpay/mcp
  ```
  If this fails, the problem is Docker (not running, not installed, or the env vars aren't in your shell), not Claude Code.
- **`! Needs authentication`** — the server's reachable but the credential is missing or empty.
- **A `${VAR}` that silently didn't expand** — if a referenced env var isn't set, Claude Code loads the config anyway with a warning and leaves the literal text `${VAR}` in place, so the server connects with a broken credential instead of failing loudly. This is the single most common cause of "it looks configured but doesn't work" — see step 3 in `SETUP.md`: your `.env` values have to actually be exported into the shell Claude Code launches from.

**The fix already in this project's `.mcp.json`:** switched `razorpay` from the local Docker server to Razorpay's **hosted remote server** (`mcp-remote` proxying to `mcp.razorpay.com`), which is what Razorpay itself labels "(Recommended)" — no Docker, no daemon, one less thing that can silently fail. It needs one derived value:
```bash
echo -n "$RAZORPAY_KEY_ID:$RAZORPAY_KEY_SECRET" | base64
```
paste that into `RAZORPAY_MCP_TOKEN` in `.env`, reload your shell (`direnv reload` or re-source), and re-run `claude mcp list`.

## 4. Setup that actually compounds (official + widely-repeated community tips)

**CLAUDE.md discipline.** The single highest-leverage habit, straight from Anthropic's own power-user guide: *any time Claude does something wrong, add a line to CLAUDE.md about it* so it isn't repeated. Treat the file as living, not written once on day one.

**Match reasoning effort to the task.**
```
/effort high      # or: low, medium, xhigh, max, auto
```
Community shorthand for "think hard about this architecture decision" is literally typing **"ultrathink"** in the prompt — it's a real trigger phrase, not just a meme, though `/effort` is the documented, precise control. Save high effort for design decisions and the review-type work; drop it for mechanical edits.

**Plan mode before big changes.** `Shift+Tab` cycles into plan mode — Claude proposes a plan you can edit before anything runs. For exactly the kind of "review the whole plan and correct it" work from earlier in this session, this is the native mechanism.

**Subagents for parallel, isolated work.** Ask Claude to "spawn N subagents" to fan a task out — each gets its own context and tools. This is what the buildathon review effectively did manually; `.claude/agents/` lets you define reusable ones with fixed permissions/models.

**Git worktrees for true parallelism.** `claude --worktree` (or just asking Claude to work in a worktree) runs an isolated session against its own branch/directory — useful for trying two implementations side by side without them stepping on each other. Two live sessions in the *same* directory will conflict; worktrees are the fix, not a nice-to-have.

**Hooks for things that must never be skipped.** `PostToolUse` can auto-format/lint after every edit; `PreToolUse` can block a dangerous command outright; `SessionStart` can preload git status or run `/mcp` automatically. This project's `.claude/commands/safety-check.md` is a manual version of the same idea — a hook would make it automatic on every commit.

**Custom slash commands for anything you'd copy-paste as a prompt twice.** Already used in this project (`/safety-check`, `/guardrail-check`, `/rubric-check`) — any markdown file in `.claude/commands/` becomes one.

**Context hygiene.** `/compact` summarizes and frees context mid-session without losing the thread; `/clear` starts clean. Long sessions degrade if you never do either — don't let one session run for days without a `/compact`.

**Headless mode for scripting.** `claude -p "prompt"` runs one prompt non-interactively and exits — useful in CI, a pre-commit hook, or a cron job, not just interactive work.

**`/permissions` allowlisting.** Pre-approve safe, repeated commands (like `pytest`, `git status`) so you're not confirming the same thing every session — keeps you focused on approvals that actually matter.

**`/statusline` and `/cost`.** A custom statusline showing model/cost/context, and `/cost` for real-time spend — useful once you're running longer sessions and want to notice a runaway loop before it burns budget.

One honest caveat: several of the items above (the exact wording of "ultrathink" as a trigger, some of the community "tips" listicle claims) come from secondary/community sources rather than Anthropic's own docs, and Claude Code ships new features often enough that specifics drift. `/effort`, `/mcp`, `claude doctor`, and `claude mcp list` are the primitives to actually check what's true in your installed version rather than trusting any list — this one included — as gospel six months from now.

## 5. Where to go for more

- Docs home: https://code.claude.com/docs
- MCP quickstart: https://code.claude.com/docs/en/mcp-quickstart
- Full MCP reference (scopes, env expansion, troubleshooting): https://code.claude.com/docs/en/mcp
- Official power-user tips: https://support.claude.com/en/articles/14554000-claude-code-power-user-tips
- MCP server directory (hundreds of servers, official and community): https://code.claude.com/docs/en/mcp#find-and-build-mcp-servers and https://modelcontextprotocol.io
