# User Guidelines

Personal conventions that apply across all repositories. Canonical file: `agents/.agents/AGENTS.md` in the dotfiles repo — agent-neutral, like the skills and hooks. `~/.claude/CLAUDE.md` (Claude Code) and `~/.codex/AGENTS.md` (Codex) are stow-installed symlinks that resolve to it via package-relative links (`claude/.claude/CLAUDE.md`, `agents/.codex/AGENTS.md`).

## Operator

The operator is **Adrien Kohlbecker** — git identity `Adrien Kohlbecker <adrien.kohlbecker@gmail.com>`. When analysing git or MR history, only commits by that exact name/email are his; other "Adrien *" authors (e.g. Adrien Brault `adrien.brault@gmail.com`, Adrien Gooris `adrien.gooris@michelin.com`) are different people — don't attribute their work to him.

- **Never read 1Password values.** Listing and searching item metadata (`op item list`, `op item search`) is fine — for example to find an item id or build an `op://…` reference. Never print a field's value (`op item get`, `op read`); wire `op://…` references through `op run --` so the secret reaches only the consuming command.
- **Never print secret material.** The same applies to every secret store: don't run commands whose output is a secret (`op read`, `security find-generic-password`, `ansible-vault view|decrypt`, `podman secret inspect`, reading a secrets file). Pass references through to the consuming command instead.
- **Don't edit `~/.codex/config.toml`** — it's the operator's live Codex config (hard scope denylist), not a session artifact.
- Workstation, terminal, and cross-repo tooling specifics (macOS, git signing, AWS, mise) live under `## Reference`.

## Working

**Never use the AskUserQuestion tool.** Ask every question — approvals, clarifications, multi-option choices — as plain text in your reply: state the question, enumerate the options with a one-line description each, and wait. Yes/no approvals stay plain text too.

Default to deciding over asking. For mechanical or determinable choices (commit slicing, staging, file layout, tool invocation), first verify the facts that would distinguish the options; if the facts settle it, state the call and proceed — the operator will redirect if needed. Reserve questions for genuine forks you can't resolve from context: security posture, architecture direction, scope, irreversible or externally-visible actions.

For multi-item work (a punch list, several files, a todo list), plan each item concretely (approach, `file:line`, trade-offs), then implement and commit each self-contained change on its own. Review-first skills (`/improve`, `/simplify_review`, `/code-review`, `/security-review`) have an explicit approval gate: present consolidated findings and wait before any edit. When the operator answers with "fix all findings" (or "apply all fixes"), apply the concrete fixes, then propose a recommended fix (the edit and its reason) for each flag-only or low-confidence finding instead of leaving it as a bare flag, and wait for a go before applying those. An "operate autonomously" instruction waives clarifying questions, not skill-defined approval gates.

To wait on slow work (a build, deploy, CI run, or service settling), don't poll with foreground `sleep` or `until` loops — the harness blocks or times them out. In Claude Code, start the command with `run_in_background` and let its completion notification wake you, or wait on a condition with the Monitor tool; bound every wait.

Most of the operator's projects are personal or household — homelab, finances, renovation, notes — not corporate production. Keep solutions proportionate: answer the practical question at the depth it deserves, prefer what one person can maintain and debug alone over an ambitious rewrite, and skip enterprise process. Reserve warnings and stop conditions for concrete, plausible risks. Security is pragmatic too: reasonable hygiene is in scope, and new security machinery needs a concrete threat behind it.

Treat these as provisional until corroborated against the environment where the problem actually appears: a "no bug / safe to remove this safeguard" verdict (yours or a subagent's) — confirm against CI/prod/the original repro, since a passing fixture may simply not be in the failing state; and any reading taken right after a restart/upgrade/deploy — let the system settle and re-check, as transitional state reads like a regression. Before concluding from measured data, check whether an automation was actively suppressing the signal during the data window.

## Project notes

A `notes/` symlink in a repository points to that project's private notes repository in the Obsidian vault (`Code/<name>`). Consult it before non-trivial work and record durable decisions there, following the `project_notes` skill; never copy its content into the code repository.

## User-level skills

Generic, repo-agnostic skills live in the dotfiles repo (`agents/.agents/skills/`), symlinked into `~/.claude/skills` and `~/.agents/skills` so both Claude Code and Codex discover them in any repo. Repo-specific skills stay in each repo's `.agents/skills/`. New skills follow the same split: generic → dotfiles, repo-bound → the repo.

## Code

When choosing names, prefer underscores (`_`) over hyphens (`-`) for identifiers, files, directories, skill names, and other names we control. Preserve hyphens where required by a language, tool, public interface, or upstream convention.

Write simple, idiomatic code in the language at hand. Prefer built-in methods and standard-library APIs over hand-rolled equivalents, don't add a third-party dependency without a demonstrated need, and prefer structured parsers over shell snippets or ad hoc string manipulation. Keep functions small and single-purpose, use descriptive names, and don't extract a value used only once — or one that's self-explanatory — into a named constant.

Let exceptions propagate naturally; add context only when it's meaningful. Raise with descriptive messages and use domain-specific error types rather than returning nil or sentinel values.

Library code takes "now"/"today" (and randomness) as a parameter; only entry points read the clock, so tests stay deterministic.

Preserve compatibility with existing on-disk formats and legacy config keys unless a breaking migration is explicitly requested. When writing config or other shared user state, write atomically (temp file in the same directory, then rename), validate the write, avoid clobbering unrelated entries, and fail closed on malformed input.

## Authoring

Comments describe current state, not history. Avoid `this used to...`, `was removed`, or `replaces the old...`; that context belongs in the commit message. Explaining why the current code deliberately avoids an obvious alternative is fine.

Give each fact one canonical home and link to it instead of copying it; copies drift. Write dates as ISO 8601 (`YYYY-MM-DD`) and quantities with explicit units.

Keep comments sparse and load-bearing: explain non-obvious paths — tricky concurrency, atomic writes, parsing, compatibility shims — and never narrate obvious assignments, with comment length proportional to the subtlety. Document public functions concisely: what it does, why its contract matters, and any non-obvious inputs, outputs, side effects, or failure modes — written for a competent reader new to the code, not an expert in it. Skip prose for trivial getters and setters. End every file with a trailing newline.

One exception to "sparse": when you suppress an exception (`except X: pass`, `contextlib.suppress`), always add a one-line comment stating *why* it's safe — the specific condition that makes it expected and benign. When the *why* outgrows a comment (architecture decision, regression history), put it in a doc/notes file and leave a one-line pointer in the code.

Config defaults depend on provenance. Config derived from an upstream reference keeps its comments, examples, and explicit default-valued settings so it stays comparable with upstream — another exception to "sparse", since the upstream reference *is* current state. Locally authored config pins a value only when it's load-bearing: it documents a dependency, is a deliberate non-default, or is a tuning knob worth surfacing.

Every bash script starts with `set -euo pipefail`. Handle expected failures explicitly, for example with `|| true`, so strict mode remains meaningful. Under `pipefail`, a reader that exits early (`… | head`) can kill the producer with SIGPIPE and fail the pipeline; filter with `awk` or `sed -n` instead.

## Validation

The operator's repos use [mise](https://mise.jdx.dev) as their task runner: start with `mise tasks ls`, run the repo's tasks rather than raw tool invocations, and apply mechanical lint fixes with its fixer task (`mise run fix`, `mise run fmt`) rather than by hand.

Do not push before full repository validation has passed. Prefer the canonical full check for that repository, such as `mise run lint`, `mise run test`, or the equivalent documented task. When you change behavior, add or update the regression test that covers it — exercise the narrowest relevant test in the inner loop, then run the full suite before pushing.

Tests exercise real behavior: assert what the consuming code or service observably does, not that a step wrote the value it was told to write. A tautological check proves nothing beyond the step's own result, so omit it when no functional assertion is possible. Bound every wait in tests and harnesses so a hang surfaces as a quick failure, and fix a flake at its source instead of papering over it with auto-retry.

## Committing

Use commits liberally and commit often. Commit each self-contained change separately: if one turn produces several independent changes, land them as several commits instead of batching them together. Always inspect the **full** staged set (`git diff --cached --stat`, plus per-file `git diff`) before `git commit` — not just the file you added: `git commit` ships the entire index, and the operator may have staged or IDE-edited files between turns; unstage strays first. For `git commit --amend`, confirm with `git log -1` that HEAD is the commit you mean to rewrite. To split entangled changes into separate commits, stage hunks into the index (`git apply --cached`, or the `git add -p` recipe in `/split_worktree_commits`); never temp-revert the working tree. Never mention Claude, Codex, or AI assistance in commit messages.

Some of the operator's repos are public (dotfiles and homelab among them; check a repo's visibility when unsure). Keep personal or household details, production command output, and content from private notes out of their diffs and commit messages.

Write the title in the imperative mood, capitalized, no trailing punctuation, aiming for ~50 characters; prefix it with the affected system or module when that makes the scope clearer. A subject alone is acceptable only for simple mechanical changes or quick fixes. Otherwise, add a blank line followed by one or two short paragraphs (hard-wrapped to 72 columns) summarizing the change and explaining its motivation, preferring lists over prose for detailed changes.

When a worktree holds several independent findings, land them as separate commits via `/split_worktree_commits` rather than one batch commit.

## Reference

Cross-repo facts whose detail lives in a linked file under `~/Work/dotfiles/agents/.agents/notes/`. The pointers below are always in context; read the file when a hook is relevant. Add a pointer here only for facts that apply across repos — repo-specific knowledge belongs in that repo's own memory/docs.

- Dotfiles repo (stow layout, editing workflow, SSH signing, jammy compat, fsmonitor hazard) → `~/Work/dotfiles/agents/.agents/notes/dotfiles.md`
- macOS workstation (Ghostty terminal + terminfo gap, `com.apple.provenance` xattr breaking container copies, NFD filenames and emoji matching) → `~/Work/dotfiles/agents/.agents/notes/macos.md`
- git & forge tooling (SSH-signing traps, `gh` authorship/rate-limit gotchas, private-GitLab → local-git fallback) → `~/Work/dotfiles/agents/.agents/notes/git.md`
- AWS auth (MFA-per-session TOTP collision under bursts) → `~/Work/dotfiles/agents/.agents/notes/aws.md`
- mise tooling (eza macOS backend, CLI-vs-language-runtime config split) → `~/Work/dotfiles/agents/.agents/notes/mise.md`
- Remote Control servers (concurrent sessions share one checkout, a server restart ends its sessions and `--resume` recovery, iCloud Full Disk Access) → `~/Work/dotfiles/agents/.agents/notes/remote_control.md`
