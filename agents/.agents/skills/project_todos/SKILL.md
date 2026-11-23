---
name: project_todos
description: Track a code repository's tasks in `notes/TODO.md`, the one project note the operator's Obsidian task views read, using the ordo CLIs (`tq`, `te`, `tm`). Use when asked to add, list, plan, start, complete, or cancel a todo or task for a repository that has `notes/`, when work leaves a follow-up the operator wants tracked, or when deciding whether something belongs in TODO.md or SOMEDAY.md.
---

# Project todos

`notes/TODO.md` is this repository's task list. It lives in the project's private notes (`<vault>/Code/<name>/TODO.md`, see the `project_notes` skill) and is the only file under `notes/` that the vault's task queries read. A task written there is an Obsidian Tasks line like any other in the vault: it shows on the operator's daily note once it has a scheduled or due date, on the weekly plan when its id is picked, and in the backlog views until it is closed.

So a line in TODO.md is a commitment the operator will see next to the rest of their life, and a growing backlog has a real cost for them. Keep the list short and concrete.

## What goes where

- **TODO.md**: work the operator asked for or agreed to track, phrased as one concrete next action. Add a task when the operator asks, or when work you are finishing leaves a follow-up they said to keep. Otherwise propose it in your report and let them decide.
- **SOMEDAY.md**: ideas, maybes, deferred review findings, in prose. Nothing there is a task; an item moves to TODO.md only when the operator picks it.
- **Other notes**: no tracked tasks. A `- [ ]` checkbox anywhere else in `notes/` is invisible to the task views, so never leave work there expecting it to be seen.
- A harness task list (the session's own plan) is for the current turn. It is not a substitute: what must outlive the session goes in TODO.md.

## The file

Create it on first use, with the frontmatter every project note carries:

```markdown
---
status: current
created_at: 2026-11-23
---

# Todo

This repository's task list, shown in the vault's task views. Default tag: `#p/<tag>`.

- [ ] homelab: Rotate the backup encryption key #p/<tag> #t1 🔼 ➕ 2026-11-23 🆔 k3m9p2
```

The default `#p/` tag comes from the vault's `AGENTS.md` (its "Code-repository tasks" section names one per repository); ask the operator when the repository isn't listed. Keep the list flat, or group it under `##` headings once it is long enough to need them. Done and cancelled tasks stay in the file: the vault's "done" views read them, so never delete or reword a closed task.

## A task line

```text
- [ ] <repo>: <imperative action> #p/<tag> #t<n> <priority> ➕ <today> 🆔 <id>
```

- **Description**: starts with the repository or component name, since the line is read out of context among unrelated tasks. One action, with enough detail to start on it cold; link a note for the rest (`see [design](some_design.md)`).
- **Tags**: the project tag, plus one effort tag: `#t0` 5 minutes, `#t1` 30 minutes, `#t2` 2 hours, `#t3` a day or more. Add `#blocked` when it waits on something outside the repository.
- **Priority**, exactly one: `🔺` must happen this week or there are real consequences, `⏫` actively annoying or getting worse, `🔼` keeps things running, `🔽` would make life better, `⏬` dreams and ideas. A task with no priority shows up as unclassified work for the operator, so always set one; when unsure, `🔽`.
- **`➕`**: today's date. **`🆔`**: a fresh id from `tm --new-id`. Every task carries one, because dashboards and `te` address tasks by id.
- **Dates**: `📅` due only for a real deadline, `🛫` start when the task cannot begin before a date. Leave `⏳` scheduled alone unless the operator named a day: when to do a task is their weekly planning, not yours.
- Everything after the description is one trailing run of tags and emoji fields. An emoji inside the description text is read as prose, not metadata.

## Commands

`tq`, `te` and `tm` come from the `ordo` repository and work on the whole vault, found through `$ORDO_VAULT`. When that is unset, prefix a command with `ORDO_VAULT="$(realpath notes/../..)"`. Paths are relative to the vault, so this repository's list is `Code/<name>/TODO.md`, where `<name>` is `basename "$(realpath notes)"`. `--help` on each command is the full reference.

```sh
tq --path Code/<name>/TODO.md                 # open tasks of this repository
tq --path Code/<name>/TODO.md --status all    # with done and cancelled ones
tm --new-id                                   # an id for a new task line
te status --id k3m9p2 --to in-progress        # mark started
te complete --id k3m9p2                       # mark done and stamp the done date
te cancel --id k3m9p2                         # mark cancelled and stamp the date
te set --id k3m9p2 --priority high --due 2026-12-01 --add-tag '#blocked'
```

- **Add** a task by appending its line to `notes/TODO.md` with your editing tool; there is no add command.
- **Change state or metadata** with `te`, targeting by `--id`. Don't flip a checkbox by hand: `te` stamps the done or cancelled date the vault's views filter on. `--dry-run` previews a change.
- A recurring task (`🔁`) can only be completed in Obsidian; `te complete` refuses it. Tell the operator instead.
- Before adding, run the listing above and check the task isn't already there. If the same task exists twice, close the newer one with `te supersede --id <id>`.

## While working

- At the start of work in the repository, list the open tasks and say which ones the request touches.
- When you begin a listed task, mark it in progress; complete it in the same turn as the change that finishes it, not later from memory.
- When a task turns out to be several, close none of them silently: reword the open line to the first concrete step and add the others as their own lines.
- Report what you added, completed, or cancelled, with ids, so the operator can find them in their views.

## Not versioned

TODO.md is gitignored in the notes repository (`project_notes init` seeds the rule): it is live task state that the operator and `te` edit from the vault all day, so tracking it would keep the notes repository dirty. Never commit it or `git add -f` it, and expect `git -C notes status` to stay silent about it. Its history is the tasks themselves: closed tasks stay in the file with their done or cancelled date. If `git -C notes status` does list TODO.md, the notes repository predates the rule: add a `TODO.md` line to its `.gitignore` and commit that.
