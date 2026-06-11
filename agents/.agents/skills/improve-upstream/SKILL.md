---
name: improve-upstream
description: Run only the upstream-features lens from the improve workflow on a target file, directory, or glob, producing read-only findings about useful built-in capabilities the target is not using.
---

## Instructions

Read `../improve/references/target-and-agent-contract.md` first.

When called directly, resolve the target and build the context brief from the shared contract. When called by `$improve`, use the provided target paths, usage scenarios, target summary, test-file flag, and optional `<user_note>`.

Stay read-only. Return findings using the unified return contract.

## Lens

Identify useful capabilities in tools, libraries, and config formats the target already invokes or depends on but does not use.

First enumerate every external program, library, and configuration file format the target invokes or depends on. For each command, read its man page with `man <cmd>`. For each config file format, read the format man page, such as `man 5 sshd_config`. Use `--help` or `-h` only as a supplement. If no man page exists, do focused research in official documentation.

Report only features that would simplify, harden, or extend this specific target in a concrete way:

- flags
- subcommands
- config directives
- environment variables
- built-in replacements for hand-rolled logic
- modern replacements for deprecated patterns

For each finding, include the feature, why it helps this target, and a concise citation such as a man page section or official URL.

Stay in this lane: add capabilities of already-used or built-in tools. Do not propose broad restructuring, threat-modeling, or peer-project conventions.
