---
name: merge_worktree
description: Update a Git worktree onto its local integration branch, review changes pulled in between the old and new merge bases against the worktree patch series, adapt and validate the result, and fast-forward merge only the reviewed tip. Use when the user asks to update, rebase, verify, integrate, or merge a detached or branched worktree while preserving linear history.
---

# Merge worktree

Integrate a finished worktree without treating a clean rebase as proof of compatibility. Review both patch series, validate the combined result, and merge the exact reviewed commit.

## Safety contract

- Operate on local refs. Do not fetch, pull, push, or remove a worktree unless the user explicitly asks.
- Preserve pre-existing target-checkout changes. Never stage or edit them.
- Require the side worktree to contain only committed changes before rebasing.
- Treat path overlap as a starting point, not the compatibility verdict. Inspect semantic dependencies too.
- Merge only the exact tip that passed review and validation, using fast-forward-only integration.
- Stop before merging on unresolved conflicts, unexplained patch changes, relevant validation failures, or ambiguous target selection.

## 1. Resolve the integration boundary

1. Read the applicable `AGENTS.md` and any repository-native worktree helpers.
2. Use the path supplied by the user as the side worktree; otherwise use the current worktree root.
3. Inspect `git worktree list --porcelain`. Identify:
   - the target checkout and its checked-out integration branch;
   - the side worktree, which may be detached or branched.
4. Verify both paths share the same Git common directory. Do not infer a target branch from `origin/HEAD` when a local integration checkout is available.
5. Inspect both statuses and the full worktree list:

   ```bash
   git -C "$side" status --short --branch
   git -C "$target" status --short --branch
   git -C "$side" worktree list --porcelain
   ```

6. Record any pre-existing target-checkout dirt with status, unstaged diff, staged diff, and untracked paths. Refuse to proceed if the side worktree is dirty or a merge or rebase is already in progress.

## 2. Snapshot before updating

Capture immutable object IDs before any rebase:

```bash
old_tip=$(git -C "$side" rev-parse HEAD)
target_tip=$(git -C "$target" rev-parse HEAD)
old_base=$(git -C "$side" merge-base "$old_tip" "$target_tip")
```

Confirm the target checkout is still on the intended branch and `target_tip` is that branch's tip. If `old_tip` equals `old_base`, report that the worktree has no commits to merge.

The two pre-update ranges have distinct meanings:

- worktree series: `old_base..old_tip`
- changes to pull in: `old_base..target_tip`

Inventory both before mutation:

```bash
git -C "$side" log --oneline --decorate "$old_base..$old_tip"
git -C "$side" diff --stat "$old_base..$old_tip"
git -C "$side" diff --name-status "$old_base..$old_tip"
git -C "$side" log --oneline --decorate "$old_base..$target_tip"
git -C "$side" diff --stat "$old_base..$target_tip"
git -C "$side" diff --name-status "$old_base..$target_tip"
```

## 3. Review pulled-in changes against the worktree

Review the exact old-base-to-new-base delta, not merely the post-rebase worktree diff.

1. Compare the two changed-path sets and inspect every direct overlap.
2. Compare the integration paths with pre-existing target-checkout dirt. Stop if they overlap.
3. Inspect relevant upstream diffs even when the intersection is empty. Follow dependencies in both directions with `rg`:
   - helpers, libraries, roles, modules, or functions consumed by worktree changes;
   - schemas, variable contracts, defaults, templates, generated inputs, and configuration keys;
   - tests, fixtures, build tasks, linters, deployment code, and runtime wrappers that exercise the changed area;
   - renamed or deleted interfaces referenced by the worktree.
4. Read upstream commits or focused diffs until each plausible interaction is resolved.
5. Record a concise compatibility conclusion: no impact, compatible behavioral change, or adaptation required.

Do not conclude "no impact" solely because file paths do not overlap.

## 4. Update the side worktree

Prefer a repository-native update helper after reading its implementation and confirming it rebases onto the intended local target branch. Otherwise rebase onto the captured target commit:

```bash
git -C "$side" rebase "$target_tip"
```

On conflicts, resolve only when intent is unambiguous and remains within the requested scope. Otherwise pause with the conflicting files and competing behavior summarized. Never merge a partially resolved rebase.

After the update, capture and verify:

```bash
new_tip=$(git -C "$side" rev-parse HEAD)
new_base=$(git -C "$side" merge-base "$new_tip" "$target_tip")
test "$new_base" = "$target_tip"
git -C "$side" range-diff "$old_base..$old_tip" "$target_tip..$new_tip"
```

Every original commit should normally appear with `=` in `range-diff`. Inspect every `!`, missing commit, reordered commit, or unexpected added commit. A conflict resolution may legitimately change a patch, but it must be explained and re-reviewed.

## 5. Adapt and validate

If the pulled-in delta requires a straightforward compatibility fix, make it in the side worktree, add or update the narrowest regression test, and commit it separately. Before committing, inspect the full staged set and follow the repository's commit rules. Pause for user direction if the fix requires a material scope or architecture choice.

Run validation against the rebased combined state:

1. Run focused checks for the worktree changes and any affected upstream dependency.
2. Run the repository's canonical full lint and test commands before merging.
3. Do not hide failures with automatic retries or bypass hooks. Distinguish a proven unrelated infrastructure failure from a code failure, but do not merge over it without explicit user acceptance.
4. Recheck `git status` and confirm the side worktree is clean.

If adaptations added commits, update `new_tip` after validation and account for those commits explicitly in the final report.

## 6. Guard against target movement

Immediately before merging, compare the target branch tip with the reviewed `target_tip`:

```bash
current_target=$(git -C "$target" rev-parse HEAD)
test "$current_target" = "$target_tip"
```

Also confirm the target checkout is still on the intended branch and its pre-existing dirt is unchanged. If the target advanced, do not merge. Restart from the snapshot step using the current side tip as `old_tip`; review the new base delta, update again, and rerun affected validation.

## 7. Merge the reviewed tip

Use a repository-native merge helper only if its implementation fast-forwards the target to the already-reviewed `new_tip` without rebasing or otherwise changing that tip. If the helper always rebases again, preserve the verification boundary with:

```bash
git -C "$target" merge --ff-only "$new_tip"
```

Do not create a merge commit, squash, cherry-pick, push, or remove the worktree unless separately requested.

## 8. Verify and report

Verify all postconditions:

```bash
test "$(git -C "$target" rev-parse HEAD)" = "$new_tip"
git -C "$target" status --short --branch
git -C "$side" status --short --branch
git -C "$target" worktree list --porcelain
git -C "$target" log -1 --oneline
```

Confirm the target remains on the intended branch and its status and diffs match the recorded pre-existing dirt. Report:

- old base, reviewed target base, and merged tip;
- pulled-in changes inspected, including semantic dependencies;
- `range-diff` result and any intentional patch changes;
- compatibility adaptations, if any;
- focused and full validation results;
- merge result, remaining worktree state, and that nothing was pushed or removed.
