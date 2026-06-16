# User Guidelines

Personal conventions that apply across all repositories. Canonical file: `agents/.agents/AGENTS.md` in the dotfiles repo — agent-neutral, like the skills and hooks. `~/.claude/CLAUDE.md` (Claude Code) and `~/.codex/AGENTS.md` (Codex) are stow-installed symlinks that resolve to it via package-relative links (`claude/.claude/CLAUDE.md`, `agents/.codex/AGENTS.md`).

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

Every bash script starts with `set -euo pipefail`. Handle expected failures explicitly, for example with `|| true`, so strict mode remains meaningful.

## Validation

Do not push before full repository validation has passed. Prefer the canonical full check for that repository, such as `mise run lint`, `mise run test`, or the equivalent documented task. When you change behavior, add or update the regression test that covers it — exercise the narrowest relevant test in the inner loop, then run the full suite before pushing.

## Committing

Use commits liberally and commit often. Commit each self-contained change separately: if one turn produces several independent changes, land them as several commits instead of batching them together. Always inspect `git diff --staged` before `git commit`. Never mention Claude, Codex, or AI assistance in commit messages.

Write the title in the imperative mood, capitalized, no trailing punctuation, aiming for ~50 characters; prefix it with the affected system or module when that makes the scope clearer. A subject alone is often enough; when it isn't, add a blank line followed by one or two short paragraphs (hard-wrapped to 72 columns) explaining why the change was needed and what it changes, preferring lists over prose for detailed changes.

When a worktree holds several independent findings, land them as separate commits via `/split_worktree_commits` rather than one batch commit.

## Reference

Cross-repo facts whose detail lives in a linked file under `~/Work/dotfiles/agents/.agents/notes/`. The pointers below are always in context; read the file when a hook is relevant. Add a pointer here only for facts that apply across repos — repo-specific knowledge belongs in that repo's own memory/docs.

- Dotfiles repo (stow layout, editing workflow, SSH signing, jammy compat, fsmonitor hazard) → `~/Work/dotfiles/agents/.agents/notes/dotfiles.md`
