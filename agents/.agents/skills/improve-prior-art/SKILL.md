---
name: improve-prior-art
description: Run only the prior-art and convention lens from the improve workflow on a target file, directory, or glob, producing read-only findings based on mature implementations and local sibling patterns.
---

## Instructions

Read `../improve/references/target-and-agent-contract.md` first.

When called directly, resolve the target and build the context brief from the shared contract. When called by `$improve`, use the provided target paths, usage scenarios, target summary, test-file flag, and optional `<user_note>`.

Stay read-only. Return findings using the unified return contract.

## Lens

Identify how the same problem is solved elsewhere and report specific patterns this target should adopt.

Find 1-3 mature, well-regarded implementations of the same job. These may be open-source tools, standard library modules, or established patterns in the language or ecosystem. Read enough to understand the shape of the solution, not just its existence.

If the target sits inside a larger repository, also scan sibling code that solves similar problems. Flag inconsistencies in style, error handling, configuration, or interfaces that the target should plausibly match.

Report specific patterns or idioms:

- naming
- structure
- error contracts
- defaults
- extension points
- testing shape

For each finding, cite the prior art with a file path or URL and explain why it fits this target. Skip generic "follow conventions" advice.

Stay in this lane: concrete patterns from peer projects or local siblings. Do not threat-model, simplify, or enumerate upstream flags as the main argument.
