# .zshrc Loaded after .zshenv and .zprofile for interactive shells. This is you at the terminal. A better default dotfile for certain updates, such as PROMPT, because this is the only time PROMPT really matters.

source "$HOME/.zsh/zsh-autosuggestions/zsh-autosuggestions.zsh"
source "$HOME/.zsh/zsh-syntax-highlighting/zsh-syntax-highlighting.zsh"
ZSH_HIGHLIGHT_HIGHLIGHTERS+=(brackets)

[ -f ~/.fzf.zsh ] || $HOME/.zsh/fzf/install --no-update-rc --no-bash --no-fish --completion --key-bindings
[ -f ~/.fzf.zsh ] && source ~/.fzf.zsh

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
setopt hist_ignore_dups       # ignore duplicated commands history list
setopt hist_ignore_space      # ignore commands that start with space
setopt hist_verify            # show command with history expansion to user before running it
setopt share_history          # share command history data
setopt hist_reduce_blanks     # Remove superfluous blanks before recording entry.
setopt hist_save_no_dups      # On flush to HISTFILE, drop entries already present (not just consecutive).
setopt hist_no_store          # Don't record `history` / `fc` invocations themselves.
setopt hist_fcntl_lock        # Use fcntl() locking on HISTFILE; safer than link()-based with share_history.

# Strip trailing whitespace/newlines (e.g. from bracketed paste) before recording,
# and drop a small allowlist of no-op commands not worth keeping.
# hist_reduce_blanks only collapses internal runs, not trailing chars.
zshaddhistory() {
  emulate -L zsh
  setopt extended_glob
  local trimmed=${1%%[[:space:]]##}
  case $trimmed in
    ls|ll|la|pwd|clear|cd|'cd -'|'cd ..') return 1 ;;
    tig|dotfiles-tig|claude|exit) return 1 ;;
    'podman ps'|'echo $?'|'git remote -v'|'git br') return 1 ;;
  esac
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
alias dotfiles='/usr/bin/env git --git-dir=$HOME/.dotfiles --work-tree=$HOME'
alias dotfiles-tig='/usr/bin/env GIT_DIR=$HOME/.dotfiles GIT_WORK_TREE=$HOME tig status'
alias dkr='docker run -ti --rm -v $(pwd):$(pwd) -w $(pwd)'

# Prompt theme
fpath+=("$HOME/.zsh/pure")
autoload -U promptinit
promptinit
[ ! -d "$HOME/.zsh/pure" ] || prompt pure

if [[ $(uname) == 'DARWIN' ]]; then
  ################################################################
  # macOS specific settings
  ################################################################

  source "$(brew --prefix)/share/google-cloud-sdk/completion.zsh.inc"

  # Brew completions
  fpath+=($HOMEBREW_PATH/share/zsh/site-functions)

  export PATH="/opt/homebrew/opt/dotnet@8/bin:$PATH"

  alias qmk='PATH="/opt/homebrew/opt/avr-gcc@8/bin:/opt/homebrew/opt/arm-gcc-bin@8/bin:$PATH" qmk'

  # Added by LM Studio CLI (lms)
  export PATH="$PATH:/Users/ak/.lmstudio/bin"
  # End of LM Studio CLI section
fi

eval "$(zoxide init zsh)"

eval "$(mise activate zsh)"
fpath+=($HOME/.local/share/mise/completions $fpath)

# atuin: SQLite-backed history.
eval "$(atuin init zsh  --disable-up-arrow --disable-ctrl-r)"

# Replace stock fzf-history-widget with the atuin-backed one (Ctrl-R search,
# Ctrl-O cycles atuin filter modes). Must come after ~/.fzf.zsh so __fzfcmd
# is defined; the widget reuses it.
source "$HOME/.zsh/fzf-atuin-widget.zsh"

# csearch <keyword> — fzf picker over Claude Code session transcripts.
source "$HOME/.zsh/claude-search.zsh"

# compinit
autoload -Uz compinit
compinit


# Scaleway CLI autocomplete initialization.
eval "$(scw autocomplete script shell=zsh)"
