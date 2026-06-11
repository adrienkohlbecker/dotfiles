---
name: improve
description: Run the full review-first improvement workflow for a target file, directory, or glob by dispatching the five independent improve components, consolidating findings, then applying only user-selected changes.
---

## Instructions

This is the orchestrator. For a single lens, call the component skills directly:

- `$improve-analysis`
- `$improve-upstream`
- `$improve-simplification`
- `$improve-security`
- `$improve-prior-art`

Read `references/target-and-agent-contract.md` before dispatching any component. Read `references/consolidate-and-act.md` before presenting findings or editing files.

## Workflow

1. Parse `$ARGUMENTS` with the shared argument contract.
2. Resolve the target to the exact file list with the shared target-resolution rules.
3. Read the target lightly and produce the shared context brief:
   - resolved target paths
   - what the target appears to do
   - 2-3 concrete usage scenarios
   - test-file flag, when applicable
   - optional `<user_note>` emphasis, when applicable
4. Inspect the tokens after the target:
   - If every trailing token exactly matches one of `analysis`, `upstream`, `simplification`, `security`, or `prior-art` case-insensitively, dispatch only those components.
   - Otherwise, dispatch all five components and pass the whole trailing-token remainder as `<user_note>` emphasis.
5. Dispatch the selected components in parallel as read-only subagents. Tell each subagent to follow the matching component skill:
   - `analysis` -> `.agents/skills/improve-analysis/SKILL.md`
   - `upstream` -> `.agents/skills/improve-upstream/SKILL.md`
   - `simplification` -> `.agents/skills/improve-simplification/SKILL.md`
   - `security` -> `.agents/skills/improve-security/SKILL.md`
   - `prior-art` -> `.agents/skills/improve-prior-art/SKILL.md`
6. Consolidate reports with `references/consolidate-and-act.md`.
7. Stop after presenting findings. Do not edit until the user chooses which numbered findings to apply.

If a component returns empty, off-topic, errors out, or fails to return, note it in the consolidation and proceed. Do not re-dispatch unless the user asks.
