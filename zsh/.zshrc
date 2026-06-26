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
alias history="builtin fc -l -i -D 1"
alias tig="command tig status"
# `dotfiles` is a function in ~/.zshenv (works in non-interactive shells too).
# dotfiles-tig: tig in the dotfiles repo (path resolved by _dotfiles_dir).
dotfiles-tig() { local d; d="$(_dotfiles_dir)" || return 1; (builtin cd -- "$d" && command tig status) }
alias dkr='docker run -ti --rm -v $(pwd):$(pwd) -w $(pwd)'

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

# Prompt theme (pure, installed via the mise http backend — see config.toml).
# mise creates several version-alias symlinks per tool; any resolves to the same
# content, so glob the install dir and take one. Guard skips on a host where
# `mise install` hasn't run yet.
_pure=( "$HOME"/.local/share/mise/installs/http-pure/*(-/N[1]) )
if (( $#_pure )); then
  fpath+=("$_pure[1]")
  autoload -U promptinit
  promptinit
  zstyle ':prompt:pure:prompt:success' color green
  prompt pure
fi
unset _pure

if [[ $(uname) == 'Darwin' ]]; then
  ################################################################
  # macOS specific settings (interactive: completions + aliases)
  # PATH/env for macOS lives in .zshenv so non-interactive shells get it too.
  ################################################################

  alias qmk='PATH="/opt/homebrew/opt/avr-gcc@8/bin:/opt/homebrew/opt/arm-gcc-bin@8/bin:$PATH" qmk'
fi

# Managed completions — brew ships stale _mise/_uv for mise-managed versions;
# regenerate on every shell start (~110ms) and prepend to fpath so these win.
_managed_comp="$HOME/.local/share/mise/completions"
[[ -d "$_managed_comp" ]] || mkdir -p "$_managed_comp"
mise completion zsh > "$_managed_comp/_mise" 2>/dev/null
"$HOME/.local/share/mise/shims/uv" generate-shell-completion zsh > "$_managed_comp/_uv" 2>/dev/null
unset _managed_comp

# Completion system — must run before the tool inits below (zoxide/mise/atuin/scw
# all call compdef). Rebuild the dump at most once a day, otherwise load the cache.
# brew shellenv (in .zshenv) already adds homebrew's site-functions to fpath AND
# exports FPATH; typeset -U deduplicates after the prepend.
typeset -U fpath
fpath=($HOME/.local/share/mise/completions $fpath)
autoload -Uz compinit
if [[ -n ~/.zcompdump(Nmh+24) ]]; then
  compinit
else
  compinit -C
fi

# gcloud argcomplete (bash-style). Sourced after compinit so its guarded
# `if ! compdef; then compinit` no-ops instead of triggering an early uncached
# compinit.
if [[ $(uname) == 'Darwin' ]]; then
  [ -f "$HOMEBREW_PATH/share/google-cloud-sdk/completion.zsh.inc" ] && source "$HOMEBREW_PATH/share/google-cloud-sdk/completion.zsh.inc"
fi

# mise must activate before the inits below — fzf, zoxide and atuin are all
# mise-managed, so their binaries are only on PATH after activation runs.
eval "$(mise activate zsh)"

# fzf keybindings + completion. Must come after `mise activate` (fzf is now
# mise-provided, on PATH only post-activation) and before the atuin widget
# below, which reuses fzf's __fzfcmd. `fzf --zsh` replaces the old ~/.zsh/fzf
# submodule's generated ~/.fzf.zsh.
command -v fzf >/dev/null && eval "$(fzf --zsh)"

# eza (modern ls). Defined here, after `mise activate`, rather than in the alias
# block above: eza is mise-managed (config.toml, all hosts), so the guard only
# passes once mise is on PATH — placing it earlier silently fell back to plain
# ls except where a brew eza happened to be present.
if command -v eza >/dev/null 2>&1; then
  alias ls='eza --group-directories-first --icons=auto'
  alias ll='eza -lah --group-directories-first --icons=auto --git'
  alias la='eza -a --group-directories-first --icons=auto'
  alias lt='eza --tree --level=2 --group-directories-first --icons=auto'
fi

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

# zsh-autosuggestions + zsh-syntax-highlighting, installed via the mise http
# backend (see config.toml). Highlighting must load after every widget-defining
# init above (atuin/fzf/edit-command-line) so it wraps them; autosuggestions just
# before it. Globs resolve one of mise's version-alias dirs; the guard skips a
# plugin not yet installed (fresh host before `mise install`).
_as=( "$HOME"/.local/share/mise/installs/http-zsh-autosuggestions/*/zsh-autosuggestions.zsh(N[1]) )
(( $#_as )) && source "$_as[1]"
_sh=( "$HOME"/.local/share/mise/installs/http-zsh-syntax-highlighting/*/zsh-syntax-highlighting.zsh(N[1]) )
if (( $#_sh )); then
  source "$_sh[1]"
  _dr=( "$HOME"/.local/share/mise/installs/http-dracula-zsh-syntax-highlighting/*/zsh-syntax-highlighting.sh(N[1]) )
  if (( $#_dr )); then
    source "$_dr[1]"
  fi
  ZSH_HIGHLIGHT_HIGHLIGHTERS+=(brackets)
  # Dracula theme (sourced above) handles ZSH_HIGHLIGHT_STYLES via hex. The
  # Ctrl-R popup (fzf-atuin-widget.py _token_color) mirrors the same palette
  # using SGR codes — keep the two in sync when changing themes.
fi
unset _as _sh _dr

# zoxide last so its chpwd hook is the last one registered and no later init
# reorders it out. Safe after syntax-highlighting — zoxide adds a chpwd hook and
# shell functions, no ZLE widgets that would need wrapping. `--cmd cd` shadows
# `cd`: every cd trains the db, `cd <partial>` frecency-jumps, `cdi` opens an fzf
# picker.
eval "$(zoxide init zsh --cmd cd)"
# Alias for interactive selection using fzf
alias zi='__zoxide_zi'

# Added by LM Studio CLI (lms)
export PATH="$PATH:/Users/ak/.lmstudio/bin"
# End of LM Studio CLI section

