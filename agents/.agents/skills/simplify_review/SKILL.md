---
name: simplify_review
description: Review-first aggressive code simplification for a target file, directory, or glob, producing numbered findings and applying only user-selected changes.
---

## Instructions

Read `../improve/references/target-and-agent-contract.md` before analyzing.

Goal: make the code more concise, readable, and cohesive. Prefer deletion and
smaller interfaces over moving complexity around.

## Review workflow

1. Resolve the target and build the context brief using the shared improve
   contract.
2. Inspect applicable repository instructions, callers, tests, configuration and
   on-disk formats, hooks, history when useful, and external or operational entry
   points.
3. Analyze the target without modifying files or repository state.
4. Return a numbered list using the shared unified return contract. Make each
   proposed change concrete and independently selectable. Name the evidence that
   makes removals safe; otherwise present the item as a trim candidate and state
   what evidence is missing.
5. Stop after the findings and wait for the user to select findings by number.

Do not edit, stage, commit, or run mutating commands during the review. A request
to operate autonomously does not waive this approval gate.

## Simplification rules

- Remove dead code, unused features, obsolete compatibility paths, and stale
  docs.
- Inline variables, functions, constants, or wrappers that are used once unless
  the name adds real clarity.
- Merge functions, classes, modules, files, or blocks when they are always used
  together or split one concept across places.
- Remove pass-through layers: avoid functions, files, or components that only
  rename, forward, wrap, dispatch, or shuttle data without owning behavior.
- Put behavior where it belongs. After moving logic, pass only facts the caller
  truly owns; derive local paths, defaults, helper locations, locks, output names,
  and internal details in the new owner.
- Avoid replacing one kind of indirection with another. If an extraction adds a
  larger interface than it removes, reconsider it.
- Keep comments and docs concise; describe the current contract and non-obvious
  decisions, not history or obvious assignments.
- Prefer direct calls to capable helpers over shelling, wrapping, or adapting
  unnecessarily.
- Preserve existing behavior unless removing it is explicitly justified as
  unused or not worth its complexity.
- Suggest features to trim when they add significant code or maintenance cost.

## Apply selected findings

After the user selects findings, implement only those findings. Treat the numeric
selection as binding scope. For multiple selected items, present the concrete
implementation and commit plan, then wait for sign-off before editing.

Before removing behavior, confirm the review evidence against the environment
where the behavior appears when practical. Absence of local references is not
proof that an exported or configuration-driven contract is unused.

For each approved finding:

- Preserve unrelated worktree changes.
- Apply the smallest cohesive change that satisfies the finding.
- Review the diff for newly introduced variables, parameters, wrappers,
  dispatcher modes, duplicated config, stale comments, and path/value plumbing.
- Remove any new indirection that does not pay for itself.
- Add or update the narrowest regression test when behavior changes.
- Run the relevant focused validation.
- Stage only the current self-contained item by explicit path or hunk.
- Inspect the complete cached stat and per-file diff, unstage unrelated entries,
  run `git diff --cached --check`, and run `git commit --dry-run` before
  committing.
- Commit each self-contained item separately.

Before committing, specifically re-check whether any removed parameter, config
field, or wrapper was documenting a cross-process, cross-file, or operational
contract rather than merely passing data through.

When all selected findings are complete:

- Review the target afresh and report any additional simplification as new
  numbered findings instead of applying it without approval.
- Before pushing, run the repository's canonical full validation.
- Report each implemented item with its validation and commit SHA, then list
  deferred trim candidates with the missing evidence and any unresolved
  architecture or security forks.

## Guardrails

When simplifying, do not remove explicit data ownership if the value represents
a real domain fact, even if it can currently be derived. Prefer typed source
facts plus local adaptation at the consuming boundary over string sentinels or
caller-side ternaries.

For concurrency, locking, publishing, atomic file swaps, or privilege/security
boundaries, preserve or improve explicit contracts. Do not simplify an interface
by deriving paths or lock names unless you first verify every cooperating reader
and writer uses the same derived path and that the lock is outside any atomically
renamed subtree.

Behavior-preserving structural simplification is in scope, even if it
temporarily adds a small type or helper, provided it removes broader tuple, path,
or string plumbing.
