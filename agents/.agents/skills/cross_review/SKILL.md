---
name: cross_review
description: Ask the other coding agent (Claude ↔ Codex) to review the relevant changes
argument-hint: "[pathspec|commit|range]"
---

# Cross review

Have the **other** agent review changes in the current repository and return its review verbatim. Self-contained: assemble the diff and prompt yourself, then drive the other agent's CLI directly — no repo tooling required.

## 1. Resolve the scope

Work from the repo root of the directory you were invoked in (`git rev-parse --show-toplevel`). Apply the first matching rule; `$ARGUMENTS` beyond a range/commit are treated as a pathspec filter throughout.

1. Argument contains `..` → explicit revision range:
   `git diff --stat --patch --find-renames --find-copies <range> > "$diff_file"`
2. Argument resolves via `git rev-parse --verify -q "<arg>^{commit}"` → explicit commit:
   `git show --stat --patch --find-renames --find-copies --format=fuller <commit> > "$diff_file"`
3. In a linked worktree (repo root ≠ first entry of `git worktree list --porcelain`) → branch diff plus local changes:
   `git diff --stat --patch --find-renames --find-copies <base>...HEAD -- <pathspec>` where `<base>` is the main worktree's checked-out branch (typically `master` or `main`), then append tracked changes vs `HEAD` and untracked files as in step 4.
4. Uncommitted changes exist (`git diff --quiet HEAD -- <pathspec>` fails, or untracked files match) → those changes:
   `git diff --stat --patch --find-renames --find-copies HEAD -- <pathspec>`, then for each file from `git ls-files --others --exclude-standard -- <pathspec>` append `git diff --no-index -- /dev/null <file> || true`.
5. Otherwise → last commit touching the pathspec:
   `git show --stat --patch --find-renames --find-copies --format=fuller $(git log -1 --format=%H -- <pathspec>)`

If the resulting diff is empty, stop and tell the user — do not send an empty review request.

## 2. Write the prompt file

Write the diff and this prompt to a temp file (`mktemp`), substituting `<scope>` (a one-line description of what rule 1–5 selected), `<repo>`, and `<branch>`:

```text
You are an expert code reviewer working INSIDE a live checkout of this
repository. This is not a paper review: your working directory IS the repo,
and you have read-only tools (file reads, grep, read-only shell commands like
git log / git blame / git show, plus web search and fetch where available).
Use them aggressively. A review that only reads the diff is shallow and not
what is wanted here.

You are running under a read-only sandbox. Do not edit files, stage changes,
commit, push, or run state-mutating commands. Diagnostic reads are expected.

Scope: <scope>
Repository: <repo>
Branch: <branch>

Investigate before you report. For every hunk:
- Open the changed files and read the surrounding code the diff omits — the
  callers, the callees, the producer of any value consumed here, the consumer
  of any value produced here. Most real bugs live in the seam between the diff
  and the code it touches, which the diff does not show.
- VERIFY every claim the code makes rather than trusting it:
  - Comments & docstrings: does the comment still describe what the code now
    does? Stale, misleading, or aspirational comments are findings.
  - Assumptions: if the code assumes a file/dir/var/secret/unit exists, a
    command is on PATH, a value has a given type/shape, or a default applies —
    confirm it against the actual tree (grep for the definition, read the
    producer, check the code that is supposed to create it).
  - API / library / CLI usage: confirm flags, subcommands, function signatures,
    return shapes and behavior against ground truth — vendored source, installed
    `--help`/man output, or upstream docs on the web. Flag invented flags,
    wrong signatures, deprecated forms, and version-skew between what the code
    calls and what is actually available.
  - Cross-references: when the diff names a value defined elsewhere (a var,
    port, unit, config key), open that definition and confirm name, type,
    default, scope and precedence line up.
- Check repo conventions: if AGENTS.md or CLAUDE.md exists at the repo root,
  it encodes hard rules and load-bearing idioms. Flag violations with the
  specific rule.

Hunt for: correctness bugs, behavioral regressions, idempotence breaks,
security/privacy leaks (plaintext secrets, PII, over-broad perms),
error-handling and edge-case gaps, races/ordering hazards, missing or wrong
tests, and maintainability surprises.

Method: form a hypothesis from the diff, then PROVE or DISPROVE it against the
real tree before writing it down. Do not speculate when you can check. When you
assert something is wrong, cite the evidence — the exact file:line you read or
the command output that confirmed it. Distinguish "verified" from "suspected"
and say which.

Output format:
- Lead with findings, ordered by severity: Critical, High, Medium, Low, Nit.
- Each finding: severity tag, `file:line` (or diff hunk), what is wrong, why it
  matters, the evidence you used to confirm it, and a concrete suggested fix.
- A brief summary AFTER the findings.
- If you genuinely find nothing, say so plainly, then state what you verified
  and what residual risk or test gap remains. Do not pad.

Be thorough, concrete, and detailed. The selected changes follow.
```

Then append the diff fenced as ` ```diff … ``` `.

## 3. Run the other agent

The review takes several minutes — use a generous timeout (10+ minutes) and let it finish.

- **If you are Claude**, run Codex read-only against the repo:

  ```sh
  codex exec --sandbox read-only --cd "$repo" - < "$prompt_file"
  ```

- **If you are Codex**, run Claude outside the Codex sandbox, in print mode, with Claude itself kept read-only (`dontAsk` auto-allows read-only Bash like git log/blame/show and auto-denies mutations):

  ```sh
  claude -p --permission-mode dontAsk \
    --allowed-tools "Read,Grep,Glob,Bash,WebFetch,WebSearch" \
    --disallowed-tools "Edit,Write,NotebookEdit" < "$prompt_file"
  ```

  In Codex environments, request unsandboxed command execution for this `claude` invocation only when the approval policy allows repository diffs/prompts to be sent to the external Claude service. If that escalation is rejected by the policy layer, do **not** retry, do **not** delete the temp prompt/diff files yet, and do **not** report the review as complete. Instead, tell the user that local policy blocked the unsandboxed Claude call, give them the exact command above with the concrete `$prompt_file` path to run in their own terminal, and ask them to paste the output back for verbatim reporting.

## 4. Report

Return the other agent's review **verbatim** — do not summarize, filter, or editorialize it. Clean up the temp files after a successful review. If execution was handed off to the user because policy blocked the unsandboxed Claude call, leave the temp files in place and report their paths.
