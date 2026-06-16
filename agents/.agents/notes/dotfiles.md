# Dotfiles repo

The operator's dotfiles are a **plain (non-bare) git repo at `~/Work/dotfiles`**, remote `git@github.com:adrienkohlbecker/dotfiles.git`, deployed into `$HOME` with **GNU stow** (`mise run restow` → `stow --restow */` from the repo root). Files in `$HOME` (e.g. `~/.zshrc`, `~/.claude/*`, `~/.codex/*`, `~/.gitconfig`) are **symlinks** into per-package dirs like `~/Work/dotfiles/<pkg>/.../`. This file itself lives at `~/Work/dotfiles/agents/.agents/notes/dotfiles.md`.

## Editing a dotfile

1. Resolve the symlink first — the Edit/Write tools refuse to write through symlinks. Edit the real path under `~/Work/dotfiles/<pkg>/...`.
2. Commit *in that repo*. **Stage by name, never `git add -A`** — it routinely carries unrelated dirty files (`settings.json`, zsh rc, skills).
3. Commits are **SSH-signed** (`gpg.format=ssh`, `commit.gpgsign=true`, allowed_signers at `~/.ssh/allowed_signers`).

The agent-neutral guidelines live at `agents/.agents/AGENTS.md` — the canonical file behind `~/.claude/CLAUDE.md` and `~/.codex/AGENTS.md` (stow symlinks). User-level skills live under `agents/.agents/skills/`, symlinked into `~/.claude/skills` and `~/.agents/skills`.

## SSH signing

Signing key is `~/.ssh/id_ed25519.pub` (migrated from the 2019 `id_rsa` in 2026-05; both stay in `allowed_signers` so old RSA-signed commits still verify). The ed25519 must be in the agent for non-interactive signing — it's passphrase-protected and stored in the macOS keychain. `env -i`-scrubbed shells drop `SSH_AUTH_SOCK` and silently break signing. `id_rsa` remains the **auth** key authorizing homelab hosts.

## Gotchas

- **`.zshenv`, not `.zprofile`** — PATH/env setup lives in `.zshenv` deliberately so non-login shells (launchd/GUI-spawned, scripts, agent shell tools) get the full Homebrew/mise/GNU PATH. Don't "simplify" it into `.zprofile`.
- **Ubuntu jammy compatibility** — these configs (notably `.gitconfig`) are also used on Ubuntu jammy (22.04) hosts running **git 2.34.1**. Any config key that only exists in a newer git *fatally errors* there, so prefer the cross-version-safe value:
  - `conflictstyle = diff3` (universal), not `zdiff3` (needs git >= 2.35 → "unknown style" on merge) — this is why it's pinned to `diff3`.
  - Keys merely *ignored* by old git are fine to add — e.g. `index.skipHash` (git >= 2.40) is ignored on 2.34, honoured on the mac (git 2.51).
  - The mac runs git 2.51, so a feature working locally is not proof it works fleet-wide. The operator flags this as a recurring concern ("the zdiff3/diff3 issue on ubuntu jammy").
- **Never set `core.fsmonitor = true` globally** — a legacy **bare** repo with work-tree `$HOME` still exists at `~/.dotfiles` (no longer the deployment mechanism, but physically present). A global fsmonitor makes any git op on it spawn `git fsmonitor--daemon` to watch the *entire* home dir, which hangs `git add`/`commit`. `core.untrackedCache=true` is safe globally; enable fsmonitor per-repo if wanted.
