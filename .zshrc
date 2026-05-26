# .zshrc Loaded after .zshenv and .zprofile for interactive shells. This is you at the terminal. A better default dotfile for certain updates, such as PROMPT, because this is the only time PROMPT really matters.

# support comments in shell commands
setopt interactivecomments

## History file configuration
[ -z "$HISTFILE" ] && HISTFILE="$HOME/.zsh_history"
[ "$HISTSIZE" -lt 100000 ] && HISTSIZE=100000
[ "$SAVEHIST" -lt 100000 ] && SAVEHIST=100000

## History command configuration
setopt inc_append_history     # write immediately after each command
setopt hist_find_no_dups      # don't show dups in Ctrl+R
setopt extended_history       # record timestamp of command in HISTFILE
setopt hist_expire_dups_first # delete duplicates first when HISTFILE size exceeds HISTSIZE
setopt hist_ignore_all_dups   # drop any older duplicate of a new entry, not just consecutive ones
setopt hist_ignore_space      # ignore commands that start with space
setopt hist_verify            # show command with history expansion to user before running it
setopt share_history          # share command history data
setopt hist_lex_words         # split entries into words lexically so dedup is correct across sessions
setopt hist_reduce_blanks     # Remove superfluous blanks before recording entry.
setopt hist_save_no_dups      # On flush to HISTFILE, drop entries already present (not just consecutive).
setopt hist_no_store          # Don't record `history` / `fc` invocations themselves.
setopt hist_fcntl_lock        # Use fcntl() locking on HISTFILE; safer than link()-based with share_history.

# Strip trailing whitespace/newlines (e.g. from bracketed paste) before recording.
# hist_reduce_blanks only collapses internal runs, not trailing chars. The no-op
# command denylist lives solely in atuin's history_filter (~/.config/atuin/config.toml),
# the backend Ctrl-R actually searches.
zshaddhistory() {
  emulate -L zsh
  setopt extended_glob
  local trimmed=${1%%[[:space:]]##}
  [[ $trimmed == $1 ]] && return 0
  print -sr -- $trimmed
  return 1
}

# Edit the current command line in $EDITOR
autoload -U edit-command-line
zle -N edit-command-line
bindkey '\C-x\C-e' edit-command-line

## keybindings
bindkey "^A" beginning-of-line
bindkey "^E" end-of-line
bindkey "^[[A" history-beginning-search-backward
bindkey "^[[B" history-beginning-search-forward

# command aliases
alias history="builtin fc -l -i -D"
alias tig="command tig status"
# `dotfiles` is a function in ~/.zshenv (works in non-interactive shells too).
alias dotfiles-tig='/usr/bin/env GIT_DIR=$HOME/.dotfiles GIT_WORK_TREE=$HOME tig status'
alias dkr='docker run -ti --rm -v $(pwd):$(pwd) -w $(pwd)'
# eza (modern ls) — guarded: mac-only install, jammy keeps coreutils ls.
if command -v eza >/dev/null 2>&1; then
  alias ls='eza --group-directories-first --icons=auto'
  alias ll='eza -lah --group-directories-first --icons=auto --git'
  alias la='eza -a --group-directories-first --icons=auto'
  alias lt='eza --tree --level=2 --group-directories-first --icons=auto'
fi

# mtmux <host> [session] — mosh in and attach (or create) a persistent tmux
# session on the host, so a dropped link never loses the session. mosh keeps the
# transport alive across roaming/sleep; tmux survives a hard disconnect. Guarded:
# mosh is a mac-only install.
if command -v mosh >/dev/null 2>&1; then
  mtmux() {
    local host=${1:?usage: mtmux <host> [session]} session=${2:-main}
    mosh "$host" -- tmux new-session -A -s "$session"
  }
fi

# Prompt theme
fpath+=("$HOME/.zsh/pure")
autoload -U promptinit
promptinit
[ -f "$HOME/.zsh/pure/pure.zsh" ] && prompt pure

if [[ $(uname) == 'Darwin' ]]; then
  ################################################################
  # macOS specific settings (interactive: completions + aliases)
  # PATH/env for macOS lives in .zshenv so non-interactive shells get it too.
  ################################################################

  [ -f "$HOMEBREW_PATH/share/google-cloud-sdk/completion.zsh.inc" ] && source "$HOMEBREW_PATH/share/google-cloud-sdk/completion.zsh.inc"

  # Brew completions
  fpath+=($HOMEBREW_PATH/share/zsh/site-functions)

  alias qmk='PATH="/opt/homebrew/opt/avr-gcc@8/bin:/opt/homebrew/opt/arm-gcc-bin@8/bin:$PATH" qmk'
fi

# Completion system — must run before the tool inits below (zoxide/mise/atuin/scw
# all call compdef). Rebuild the dump at most once a day, otherwise load the cache.
fpath+=($HOME/.local/share/mise/completions $fpath)
autoload -Uz compinit
if [[ -n ~/.zcompdump(Nmh+24) ]]; then
  compinit
else
  compinit -C
fi

# mise must activate before the inits below — fzf, zoxide and atuin are all
# mise-managed, so their binaries are only on PATH after activation runs.
eval "$(mise activate zsh)"

# fzf keybindings + completion. Must come after `mise activate` (fzf is now
# mise-provided, on PATH only post-activation) and before the atuin widget
# below, which reuses fzf's __fzfcmd. `fzf --zsh` replaces the old ~/.zsh/fzf
# submodule's generated ~/.fzf.zsh.
command -v fzf >/dev/null && eval "$(fzf --zsh)"

# yazi (TUI file manager): the `y` wrapper cd's the shell to wherever you exited
# in yazi (plain `yazi` leaves you in the original dir). Defined here, after
# `mise activate`, rather than next to the eza aliases above — yazi is a mise-only
# install with no brew fallback, so the guard only passes once mise is on PATH.
if command -v yazi >/dev/null 2>&1; then
  y() {
    local tmp cwd
    tmp="$(mktemp -t yazi-cwd.XXXXXX)"
    yazi "$@" --cwd-file="$tmp"
    if cwd="$(command cat -- "$tmp")" && [ -n "$cwd" ] && [ "$cwd" != "$PWD" ]; then
      builtin cd -- "$cwd"
    fi
    rm -f -- "$tmp"
  }
fi

# --cmd cd shadows `cd`: every cd trains the db, `cd <partial>` frecency-jumps to
# the best match, and `cdi` opens an fzf picker over visited dirs.
eval "$(zoxide init zsh --cmd cd)"

# atuin: SQLite-backed history.
eval "$(atuin init zsh  --disable-up-arrow --disable-ctrl-r)"

# Replace stock fzf-history-widget with the atuin-backed one (Ctrl-R search,
# Ctrl-O cycles atuin filter modes). Must come after the `fzf --zsh` eval above
# so __fzfcmd is defined; the widget reuses it.
source "$HOME/.zsh/fzf-atuin-widget.zsh"

# csearch <keyword> — fzf picker over Claude Code session transcripts.
source "$HOME/.zsh/claude-search.zsh"

# Scaleway CLI autocomplete initialization.
command -v scw >/dev/null && eval "$(scw autocomplete script shell=zsh)"

# Machine-local overrides (untracked, not in the dotfiles repo)
[ -f ~/.zshrc.local ] && source ~/.zshrc.local

# zsh-syntax-highlighting must be sourced last so it wraps every widget defined above
# (atuin/fzf/edit-command-line). autosuggestions is sourced just before it.
# Guarded so a not-yet-checked-out submodule doesn't hard-error on a fresh clone.
[ -f "$HOME/.zsh/zsh-autosuggestions/zsh-autosuggestions.zsh" ] && source "$HOME/.zsh/zsh-autosuggestions/zsh-autosuggestions.zsh"
if [ -f "$HOME/.zsh/zsh-syntax-highlighting/zsh-syntax-highlighting.zsh" ]; then
  source "$HOME/.zsh/zsh-syntax-highlighting/zsh-syntax-highlighting.zsh"
  ZSH_HIGHLIGHT_HIGHLIGHTERS+=(brackets)
fi
