# User Guidelines

Personal conventions that apply across all repositories. Canonical file: `agents/.agents/AGENTS.md` in the dotfiles repo — agent-neutral, like the skills and hooks. `~/.claude/CLAUDE.md` (Claude Code) and `~/.codex/AGENTS.md` (Codex) are stow-installed symlinks that resolve to it via package-relative links (`claude/.claude/CLAUDE.md`, `agents/.codex/AGENTS.md`).

## User-level skills

Generic, repo-agnostic skills live in the dotfiles repo (`agents/.agents/skills/`), symlinked into `~/.claude/skills` and `~/.agents/skills` so both Claude Code and Codex discover them in any repo. Repo-specific skills stay in each repo's `.agents/skills/`. New skills follow the same split: generic → dotfiles, repo-bound → the repo.

- `/cross_review [target]` — have the *other* agent (Claude ↔ Codex) review changes; self-contained — assembles the diff and drives `codex exec` / `claude -p` directly.
- `/split_worktree_commits` — split a multi-finding worktree into per-finding commits via non-interactive `git add -p`. Never stages secret-rendering templates hunk-by-hunk.
- `/improve [target]` — review-first improvement workflow (five independent lenses; findings are approved before any edit). Per-lens variants: `/improve-analysis`, `/improve-prior-art`, `/improve-security`, `/improve-simplification`, `/improve-upstream`.

## Authoring

Comments describe current state, not history. Avoid `this used to...`, `was removed`, or `replaces the old...`; that context belongs in the commit message. Explaining why the current code deliberately avoids an obvious alternative is fine.

Every bash script starts with `set -euo pipefail`. Handle expected failures explicitly, for example with `|| true`, so strict mode remains meaningful.

## Validation

Do not push before full repository validation has passed. Prefer the canonical full check for that repository, such as `mise run lint`, `mise run test`, or the equivalent documented task.

## Committing

Use commits liberally and commit often. Commit each self-contained change separately: if one turn produces several independent changes, land them as several commits instead of batching them together. Always inspect `git diff --staged` before `git commit`. Each commit message should have a concise title and, when useful, one or two short paragraphs explaining why the change was needed and what it changes. Prefix the title with the affected system or module when that makes the scope clearer.

When a worktree holds several independent findings, land them as separate commits via `/split_worktree_commits` rather than one batch commit.
