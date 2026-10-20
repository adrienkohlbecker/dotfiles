# Claude Code Remote Control servers

The workstation keeps one Claude Code Remote Control server per project, each a launchd agent managed by `~/Work/laptop/remote_control/rc_project` (`start|stop|list|logs|refresh <project>`), so projects are reachable from the Claude mobile app. Full mechanics: the "Remote Control servers" section of `~/Work/laptop/CLAUDE.md`. What matters when working in any repo:

## Concurrent sessions share one checkout

Servers run with `--spawn same-dir`, so every session for a project — including ones the operator starts from the phone while you work — edits the same checkout. Files can change or get staged under you between turns.

**Apply:** stage by name, inspect the full index before committing (see `## Committing`), and use a worktree for work that must stay isolated.

## A server exit ends its sessions

Stopping or restarting a project's server ends the sessions it serves, including the one running the command if it's served from that project. The daily refresh (`com.ak.claude_rc_refresh`, 04:30) restarts servers whose `claude` binary is outdated and interrupts any turn in progress. The transcript survives at `~/.claude/projects/<slug>/<session-id>.jsonl`; recover with `cd <project> && claude --resume <session-id>` (add `--fork-session` to leave the original untouched). Remote Control sessions (`entrypoint: sdk-cli`) are not offered by `--resume`'s picker, so recovery needs the id.

## Environment and iCloud access

Sessions run under `zsh -lic`, so they inherit the interactive shell environment (mise, PATH, exports). launchd jobs can't answer macOS privacy prompts: folders under `~/Library/Mobile Documents` (the iCloud Obsidian vaults) are unreadable unless `/bin/zsh` has Full Disk Access. An "Operation not permitted" on the vault from a served session means that grant is missing — the operator fixes it in System Settings → Privacy & Security.
