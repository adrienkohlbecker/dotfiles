# git & forge tooling

## SSH commit-signing: don't scrub the environment

The operator's repos are SSH-signed (`gpg.format=ssh`, signing key `~/.ssh/id_ed25519`). Running `git commit` inside a scrubbed `env -i HOME=$HOME PATH=…` shell drops `SSH_AUTH_SOCK`, so git can't reach the agent, falls back to the on-disk encrypted key, and dies with `Enter passphrase … incorrect passphrase supplied … fatal: failed to write commit object` (exit 128) — no signature, no commit.

**Apply:** commit in a normal shell that inherits the session env (a plain `bash -c`, the default tool invocation), never `env -i`. If PATH is noisy (mise/zoxide), set `export _ZO_DOCTOR=0` and use absolute tool paths (`/usr/bin/git`) instead of scrubbing the whole environment. Verify with `git log --format='%h %G?'` → `G` (good) or `U` (valid-but-untrusted), never `N`.

## Don't set `core.fsmonitor` globally

Never set `core.fsmonitor = true` in the global `~/.gitconfig`. A legacy **bare** git repo with work-tree `$HOME` still exists at `~/.dotfiles` (no longer the deployment mechanism — stow at `~/Work/dotfiles` is — but physically present). A global fsmonitor makes any git op on it spawn `git fsmonitor--daemon` watching the *entire* home dir, which hangs `git add`/`commit` (`could not read IPC response`) and respawns daemons. `core.untrackedCache=true` is safe globally; enable fsmonitor per-repo if wanted. After a hang: remove the global line first, then `fsmonitor--daemon stop` + `pkill -9 -f fsmonitor--daemon`.

## `gh` (GitHub) gotchas

- **PR authorship:** the `author:` lines in `gh pr view <id> --comments` are *commenters/reviewers*, not the PR author — misreading them has produced false "not your work" calls. Get the real author via `gh pr view <id> --repo <o>/<r> --json author,commits` (`author.login` = opener, `commits[].authors[].email` = per-commit), or plain `gh pr view <id>` (header), or for local clones `git log --format='%H | %an <%ae> | %s' <merge>^1..<merge>`.
- **Rate limits:** a failed/empty/denied `gh` call may be transient rate-limiting (60/hr unauth, 5000/hr auth, stricter secondary limits), not a real permission problem — retry once or twice with a short backoff before treating it as terminal. 5+ concurrent `gh` calls against one repo is exactly the burst shape that trips secondary limits; stagger or retry. Distinguish harness permission-denial (tool blocked before `gh` runs) from GitHub-side 403/429 — retry first either way.

## Private GitLab repos → local git, not `glab`/API

Some GitLab projects the operator works on are private or on `ops.gitlab.net`, and the current `glab` auth doesn't cover them (confirmed 404 for `tanuki-inc`; `chef-repo` access was removed when he left GitLab). Public OSS projects (`gitlab-runner`, `gitlab`, …) work normally.

**Apply:** probe once (`glab mr show <id>` on one MR) before fanning out. On 404, fall back to local git against the clone: `git show <merge-sha>`, `git log <first-parent>..<second-parent> --stat -p`, `git show -s --format=%B <sha>` (the merge-commit body usually carries the MR title + description). Only prefer `glab` when it works (richer: comments, reviewers, labels) or when you specifically need MR discussion (not in git). Check `glab auth status` before attempting against an unfamiliar host.
