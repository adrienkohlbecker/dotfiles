# User Guidelines

Personal conventions that apply across all repositories. Canonical file: `agents/.agents/AGENTS.md` in the dotfiles repo — agent-neutral, like the skills and hooks. `~/.claude/CLAUDE.md` (Claude Code) and `~/.codex/AGENTS.md` (Codex) are stow-installed symlinks that resolve to it via package-relative links (`claude/.claude/CLAUDE.md`, `agents/.codex/AGENTS.md`).

## Operator

The operator is **Adrien Kohlbecker** — git identity `Adrien Kohlbecker <adrien.kohlbecker@gmail.com>`. When analysing git or MR history, only commits by that exact name/email are his; other "Adrien *" authors (e.g. Adrien Brault `adrien.brault@gmail.com`, Adrien Gooris `adrien.gooris@michelin.com`) are different people — don't attribute their work to him.

- **1Password is a black box.** Never enumerate or read its contents (`op item list`, `op vault list`, `op item get`, `op item search`). The operator hands you `op://…` references directly; wire them through `op run --`. No discovery, no listing, no inspection — even to find an item id.
- **Don't edit `~/.codex/config.toml`** — it's the operator's live Codex config (hard scope denylist), not a session artifact.
- Workstation, terminal, and cross-repo tooling specifics (macOS, git signing, AWS, mise) live under `## Reference`.

## Working

**Never use the AskUserQuestion tool.** Ask every question — approvals, clarifications, multi-option choices — as plain text in your reply: state the question, enumerate the options with a one-line description each, and wait. Yes/no approvals stay plain text too.

Default to deciding over asking. For mechanical or determinable choices (commit slicing, staging, file layout, tool invocation), first verify the facts that would distinguish the options; if the facts settle it, state the call and proceed — the operator will redirect if needed. Reserve questions for genuine forks you can't resolve from context: security posture, architecture direction, scope, irreversible or externally-visible actions.

For multi-item work (a punch list, several files, a todo list), plan each item concretely (approach, `file:line`, trade-offs), surface the plan, and wait for sign-off before implementing — then commit each self-contained change on its own. Review-first skills (`/improve`, `/code-review`, `/security-review`) have an explicit approval gate: present consolidated findings and wait before any edit. An "operate autonomously" instruction waives clarifying questions, not skill-defined approval gates.

Treat these as provisional until corroborated against the environment where the problem actually appears: a "no bug / safe to remove this safeguard" verdict (yours or a subagent's) — confirm against CI/prod/the original repro, since a passing fixture may simply not be in the failing state; and any reading taken right after a restart/upgrade/deploy — let the system settle and re-check, as transitional state reads like a regression. Before concluding from measured data, check whether an automation was actively suppressing the signal during the data window.

## User-level skills

Generic, repo-agnostic skills live in the dotfiles repo (`agents/.agents/skills/`), symlinked into `~/.claude/skills` and `~/.agents/skills` so both Claude Code and Codex discover them in any repo. Repo-specific skills stay in each repo's `.agents/skills/`. New skills follow the same split: generic → dotfiles, repo-bound → the repo.

- `/cross_review [target]` — have the *other* agent (Claude ↔ Codex) review changes; self-contained — assembles the diff and drives `codex exec` / `claude -p` directly.
- `/split_worktree_commits` — split a multi-finding worktree into per-finding commits via non-interactive `git add -p`. Never stages secret-rendering templates hunk-by-hunk.
- `/improve [target]` — review-first improvement workflow (five independent lenses; findings are approved before any edit). Per-lens variants: `/improve-analysis`, `/improve-prior-art`, `/improve-security`, `/improve-simplification`, `/improve-upstream`.

## Code

Write simple, idiomatic code in the language at hand. Prefer built-in methods and standard-library APIs over hand-rolled equivalents, and structured parsers over shell snippets or ad hoc string manipulation. Keep functions small and single-purpose, use descriptive names, and don't extract a value used only once — or one that's self-explanatory — into a named constant.

Let exceptions propagate naturally; add context only when it's meaningful. Raise with descriptive messages and use domain-specific error types rather than returning nil or sentinel values.

Preserve compatibility with existing on-disk formats and legacy config keys unless a breaking migration is explicitly requested. When writing config or other shared user state, validate the write, avoid clobbering unrelated entries, and fail closed on malformed input.

## Authoring

Comments describe current state, not history. Avoid `this used to...`, `was removed`, or `replaces the old...`; that context belongs in the commit message. Explaining why the current code deliberately avoids an obvious alternative is fine.

Keep comments sparse and load-bearing: explain non-obvious paths — tricky concurrency, atomic writes, parsing, compatibility shims — and never narrate obvious assignments, with comment length proportional to the subtlety. Document public functions concisely: what it does, why its contract matters, and any non-obvious inputs, outputs, side effects, or failure modes — written for a competent reader new to the code, not an expert in it. Skip prose for trivial getters and setters. End every file with a trailing newline.

One exception to "sparse": when you suppress an exception (`except X: pass`, `contextlib.suppress`), always add a one-line comment stating *why* it's safe — the specific condition that makes it expected and benign. When the *why* outgrows a comment (architecture decision, regression history), put it in a doc/notes file and leave a one-line pointer in the code.

Every bash script starts with `set -euo pipefail`. Handle expected failures explicitly, for example with `|| true`, so strict mode remains meaningful.

## Validation

Do not push before full repository validation has passed. Prefer the canonical full check for that repository, such as `mise run lint`, `mise run test`, or the equivalent documented task. When you change behavior, add or update the regression test that covers it — exercise the narrowest relevant test in the inner loop, then run the full suite before pushing.

## Committing

Use commits liberally and commit often. Commit each self-contained change separately: if one turn produces several independent changes, land them as several commits instead of batching them together. Always inspect the **full** staged set (`git diff --cached --stat`, plus per-file `git diff`) before `git commit` — not just the file you added: `git commit` ships the entire index, and the operator may have staged or IDE-edited files between turns; unstage strays first. For `git commit --amend`, confirm with `git log -1` that HEAD is the commit you mean to rewrite. To split entangled changes into separate commits, stage hunks into the index (`git apply --cached`); never temp-revert the working tree. Never mention Claude, Codex, or AI assistance in commit messages.

Write the title in the imperative mood, capitalized, no trailing punctuation, aiming for ~50 characters; prefix it with the affected system or module when that makes the scope clearer. A subject alone is often enough; when it isn't, add a blank line followed by one or two short paragraphs (hard-wrapped to 72 columns) explaining why the change was needed and what it changes, preferring lists over prose for detailed changes.

When a worktree holds several independent findings, land them as separate commits via `/split_worktree_commits` rather than one batch commit.

## Reference

Cross-repo facts whose detail lives in a linked file under `~/Work/dotfiles/agents/.agents/notes/`. The pointers below are always in context; read the file when a hook is relevant. Add a pointer here only for facts that apply across repos — repo-specific knowledge belongs in that repo's own memory/docs.

- Dotfiles repo (stow layout, editing workflow, SSH signing, jammy compat, fsmonitor hazard) → `~/Work/dotfiles/agents/.agents/notes/dotfiles.md`
- macOS workstation (Ghostty terminal + terminfo gap, `com.apple.provenance` xattr breaking container copies) → `~/Work/dotfiles/agents/.agents/notes/macos.md`
- git & forge tooling (SSH-signing traps, `gh` authorship/rate-limit gotchas, private-GitLab → local-git fallback) → `~/Work/dotfiles/agents/.agents/notes/git.md`
- AWS auth (MFA-per-session TOTP collision under bursts) → `~/Work/dotfiles/agents/.agents/notes/aws.md`
- mise tooling (eza macOS backend, CLI-vs-language-runtime config split) → `~/Work/dotfiles/agents/.agents/notes/mise.md`
