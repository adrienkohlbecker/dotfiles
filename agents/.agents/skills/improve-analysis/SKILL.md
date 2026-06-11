---
name: improve-analysis
description: Run only the first-principles analysis lens from the improve workflow on a target file, directory, or glob, producing read-only findings without applying edits.
---

## Instructions

Read `../improve/references/target-and-agent-contract.md` first.

When called directly, resolve the target and build the context brief from the shared contract. When called by `$improve`, use the provided target paths, usage scenarios, target summary, test-file flag, and optional `<user_note>`.

Stay read-only. Return findings using the unified return contract.

## Lens

Analyze the target from first principles. Do not assume AGENTS.md, CLAUDE.md, README files, or other documentation has the right answer. Read the code and judge it directly.

Mentally walk the usage scenarios. Look for gaps that surface against real use: unsupported invocation shapes, ambiguous output, untreated user input flowing into templates, awkward parameter ergonomics, missing extension points, undocumented load-bearing assumptions, and missing or weak tests where tests are warranted.

Stay in this lane:

- Do not enumerate flags or upstream features.
- Do not threat-model except when needed to explain an analysis finding at a high level.
- Do not propose rewrites or restructuring as the main point.
- Do not compare to other projects except to clarify a concrete inconsistency.

For test targets, use two lenses:

- Coverage, additive: read the system under test and flag observable contracts the target does not exercise. State-only checks against behavior worth exercising functionally count as gaps.
- Smell, subtractive: flag duplicated setup that should be a fixture, near-identical cases that should be parametrized, over-mocking, brittle assertions, timing-dependent flakes, unseeded randomness, magic numbers, private-implementation assertions, and missing arrange/act/assert structure.

The target is primary, but proposed changes may touch callers, tests, or sibling files when the finding requires it or repository consistency calls for it. Do not propose stylistic preference alone; every change needs a concrete correctness, complexity, security, ergonomics, consistency, or readability reason.
