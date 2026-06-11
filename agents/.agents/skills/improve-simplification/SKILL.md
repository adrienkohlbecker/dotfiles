---
name: improve-simplification
description: Run only the radical-simplification lens from the improve workflow on a target file, directory, or glob, producing read-only findings about subtractive or restructuring improvements.
---

## Instructions

Read `../improve/references/target-and-agent-contract.md` first.

When called directly, resolve the target and build the context brief from the shared contract. When called by `$improve`, use the provided target paths, usage scenarios, target summary, test-file flag, and optional `<user_note>`.

Stay read-only. Return findings using the unified return contract.

## Lens

Ask whether 80% of the target's value can be delivered with 20% of the code or maintenance burden.

Start by restating the target's essential job in one sentence: the outcome the user actually wants. Then list which features are load-bearing for that outcome and which are incidental.

Explore these angles:

1. An alternative tool already designed for this job.
2. Creative reuse of tools already present in the environment to cover the same ground.
3. A from-scratch rewrite that drops incidental complexity.

For each real angle, sketch what it would look like and what would be lost. Skip an angle with one sentence when it is not a real option. Be specific and honest: name the dropped feature and the migration cost.

End with a recommendation: keep as-is, incremental simplification, or rewrite, with reasoning.

Stay in this lane: subtractive and restructuring changes. Do not add new flags, threat-model, or cite conventions as the main argument.
