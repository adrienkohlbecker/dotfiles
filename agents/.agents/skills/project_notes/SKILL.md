---
name: project_notes
description: Read, write, and commit a code repository's private notes in its `notes/` folder (design docs, investigations, runbooks, deployed-state records, the SOMEDAY backlog), or set notes up for a repository. Use at the start of non-trivial work in a repository that has `notes/`, when a decision or investigation is worth keeping, or when asked to create, migrate, or check a project's notes.
---

# Project notes

`notes/` in a code repository is a symlink to that project's private notes repository at `<vault>/Code/<name>` in the Obsidian vault (iCloud), with its git dir at `~/.local/share/project_notes/<name>.git`. Every worktree links to the same notes repository, so notes written from any worktree land on one history — no per-worktree branches or merges. The `project_notes` CLI (`init`, `migrate`, `link`, `doctor`, `lint`) manages the plumbing; the global git hooks link new worktrees and stamp each notes commit with a `Code: <repo>@<sha>` trailer.

## Reading

- Before non-trivial work, list `notes/` and read the notes whose names or `status` bear on the task. The repository's AGENTS.md links the load-bearing ones.
- Trust by status: `runbook` and `current` describe how things are; `planned` and `deferred` are intentions; `rejected` records why not; `completed` points at code and git history as the source of truth.
- `SOMEDAY.md` is a backlog, not standing instructions — never enact an item without the operator's confirmation.

## Writing

Write a note for what outlives the session and isn't derivable from the code: design decisions and their rejected alternatives, investigations and measurements, operational runbooks, deployed state, cross-cutting conventions. Agent memory is not a substitute — it is per-path (so per-worktree) and invisible to the operator.

- Filename: `snake_case.md`, named for the topic, not the date. Runbooks go in `runbooks/`.
- Every note opens with frontmatter:

  ```yaml
  ---
  status: planned
  created_at: 2026-10-20
  ---
  ```

  Statuses: `runbook` (active procedure) · `current` (deployed state) · `planned` (near-term) · `deferred` (valid, not imminent) · `rejected` (kept for context) · `completed` (outcome in code/git) · `reference` (static lookup).
- Update a note's `status` as its work lands; move notes that no longer inform anything to `archive/`.
- Link with relative Markdown links (`[x](runbooks/y.md)`), not wikilinks, so links work on the git forge and in Obsidian alike.
- Write in the repository's language and register; keep the same "current state, not history" rule as code comments, except in explicitly historical notes (investigations, rejected designs).

## Committing

- Commit inside the notes repository (`git -C notes …`), separately from code commits, with the same message conventions. Push when the work is done.
- Never copy notes content, personal details, or production output into the code repository's commits or files — many code repositories are public.
- The notes repository is shared by every worktree: commit only the notes you changed, and inspect `git -C notes status` first because other sessions may have edits in flight.

## Setting up or checking

- New project: `project_notes init` from a checkout (creates the vault folder, git dir, `origin` from `git config --global projectnotes.remotebase`, and links every worktree). Gitea's push-to-create makes the (private) remote repository on the first push.
- Existing in-checkout clone (`notes/.git` is a directory): `project_notes migrate`.
- A worktree without `notes/`: `project_notes link`. Codex app worktrees always start that way — Codex runs git with hooks disabled — unless the repository's Codex setup script (`.codex/environments/*.toml`) runs `project_notes link`; add that when setting up notes for a repository Codex works in.
- `project_notes doctor` reports broken links, unpushed or uncommitted notes, iCloud conflict copies (`foo 2.md`) and evicted files, and frontmatter errors; `project_notes lint` runs just the checks on the notes themselves.
