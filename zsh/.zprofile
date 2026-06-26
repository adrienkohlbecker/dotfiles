# .zprofile is loaded after .zshenv for login shells (the shell you get when you first log in). It’s not loaded again when you open more terminals on the machine. It’s also not loaded by remote commands run over ssh (usually).

# Restore path set by ~/.zshenv after executing /etc/zprofile
if [[ -v path_prepend ]]; then
  path=($path_prepend $path)
fi

# Codex runs commands through non-interactive login shells, which read this file
# but not ~/.zshrc. Activate mise here for that path so project envs such as
# python.uv_venv_auto still update PATH.
if [[ ! -o interactive ]] && command -v mise >/dev/null 2>&1; then
  eval "$(mise activate zsh)"
fi

# Start gpg-agent if not running (guarded: gpg may be absent on non-macOS hosts)
command -v gpg-connect-agent >/dev/null && gpg-connect-agent /bye >/dev/null 2>&1

# Added by Obsidian
export PATH="$PATH:/Applications/Obsidian.app/Contents/MacOS"
