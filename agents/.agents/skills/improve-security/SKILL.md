---
name: improve-security
description: Run only the security and threat-model lens from the improve workflow on a target file, directory, or glob, producing read-only adversarial findings.
---

## Instructions

Read `../improve/references/target-and-agent-contract.md` first.

When called directly, resolve the target and build the context brief from the shared contract. When called by `$improve`, use the provided target paths, usage scenarios, target summary, test-file flag, and optional `<user_note>`.

Stay read-only. Return findings using the unified return contract.

## Lens

Perform an adversarial read of the target.

Map trust boundaries:

- inputs from users, environment variables, files, network, or other processes
- privileges the target runs with
- files, sockets, services, or commands it writes or executes
- secrets or credentials it touches

For each reachable boundary, enumerate concrete threats:

- command, SQL, or template injection
- path traversal
- TOCTOU
- unsafe deserialization
- secret leakage to logs, files, or process listings
- world-readable sensitive files
- races on shared state
- supply-chain trust in fetched scripts or pinned-by-tag dependencies
- missing input validation that reaches a shell, eval, template, or privileged action

Each finding must include the specific line or construct, the exploit shape in one sentence, the concrete fix, and severity. Skip theoretical risks that do not apply. If the target is a pure test file with no meaningful adversarial surface, return "not applicable" with one sentence and the biggest single win line.

Stay in this lane: adversarial threats only. Do not propose simplifications, feature additions, or style nits.
