---
name: simplify
description: Aggressive simplification of the code
---

## Instructions

Resolve the target and simplify the code in it now, not read-only.

Goal: make the code more concise, readable, and cohesive. Prefer deletion and smaller interfaces over moving complexity around.

Simplification rules:
- Remove dead code, unused features, obsolete compatibility paths, and stale docs.
- Inline variables, functions, constants, or wrappers that are used once unless the name adds real clarity.
- Merge functions, classes, modules, files, or blocks when they are always used together or split one concept across places.
- Remove pass-through layers: avoid functions/files/components that only rename, forward, wrap, dispatch, or shuttle data without owning behavior.
- Put behavior where it belongs. After moving logic, pass only facts the caller truly owns; derive local paths, defaults, helper locations, locks, output names, and internal details in the new owner.
- Avoid replacing one kind of indirection with another. If an extraction adds a larger interface than it removes, reconsider it.
- Keep comments and docs concise; describe the current contract and non-obvious decisions, not history or obvious assignments.
- Prefer direct calls to capable helpers over shelling/wrapping/adapting unnecessarily.
- Preserve existing behavior unless removing it is explicitly justified as unused or not worth its complexity.
- Suggest features to trim when they add significant code or maintenance cost.

Before committing:
- Review your own diff for newly introduced variables, parameters, wrappers, dispatcher modes, duplicated config, stale comments, and path/value plumbing.
- Remove any new indirection that does not pay for itself.
- Add or update the narrowest regression test when behavior changes.
- Run the relevant focused validation for the current item.
- Inspect the worktree and preserve unrelated changes.
- Stage only the current self-contained item by explicit path or hunk.
- Inspect the complete cached stat and per-file diff, unstage unrelated entries, and run `git commit --dry-run` before committing.
- Commit each self-contained item separately.

When simplifying, do not remove explicit data ownership if the value represents
a real domain fact, even if it can currently be derived. Prefer typed source
facts plus local adaptation at the consuming boundary over string sentinels or
caller-side ternaries.

For concurrency, locking, publishing, atomic file swaps, or privilege/security
boundaries, preserve or improve explicit contracts. Do not simplify an interface
by deriving paths or lock names unless you first verify every cooperating reader
and writer uses the same derived path and that the lock is outside any atomically
renamed subtree.

Before committing, specifically re-check whether any removed parameter, config
field, or wrapper was documenting a cross-process, cross-file, or operational
contract rather than merely passing data through.

Behavior-preserving structural simplification is in scope, even if it temporarily adds a small type/helper, provided it removes broader tuple/path/string plumbing.

Implementation is approved; do not stop for a planning gate unless you find a real architecture/security fork.
Before removing behavior, inspect applicable repository instructions, callers,
tests, configuration and on-disk formats, hooks, history when useful, and
external or operational entry points. Absence of local references is not proof
that an exported or configuration-driven contract is unused.

Remove code only when this evidence proves it unused, and name the evidence.
Otherwise preserve it and list it separately as a trim candidate.

Commit each individual self-contained work item as you go. After the first pass,
review the target afresh and continue only when another behavior-preserving or
proven-unused simplification remains.

Before pushing, run the repository's canonical full validation. Report each
implemented item with its validation and commit SHA, then list deferred trim
candidates with the missing evidence and any unresolved architecture or
security forks.
