# .zshrc Loaded after .zshenv and .zprofile for interactive shells. This is you at the terminal. A better default dotfile for certain updates, such as PROMPT, because this is the only time PROMPT really matters.

source "$HOME/.zsh/zsh-autosuggestions/zsh-autosuggestions.zsh"
source "$HOME/.zsh/zsh-syntax-highlighting/zsh-syntax-highlighting.zsh"

[ -f ~/.fzf.zsh ] || $HOME/.zsh/fzf/install --no-update-rc --no-bash --no-fish --completion --key-bindings
[ -f ~/.fzf.zsh ] && source ~/.fzf.zsh

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
alias dotfiles-tig='/usr/bin/env GIT_DIR=$HOME/.dotfiles GIT_WORK_TREE=$HOME command tig status'
alias qmk='PATH="/opt/homebrew/opt/avr-gcc@8/bin:/opt/homebrew/opt/arm-gcc-bin@8/bin:$PATH" command qmk'
alias dkr='docker run -ti --rm -v $(pwd):$(pwd) -w $(pwd)'

# Prompt theme
fpath+=("$HOME/.zsh/pure")
autoload -U promptinit
promptinit
[ ! -d "$HOME/.zsh/pure" ] || prompt pure

if [[ $(uname) == 'Linux' ]]; then
  return
fi

################################################################
# macOS specific settings
################################################################

source "$(brew --prefix)/share/google-cloud-sdk/completion.zsh.inc"

fpath=(${ASDF_DIR}/completions $fpath)

# Brew completions
fpath+=($HOMEBREW_PATH/share/zsh/site-functions)

# compinit
autoload -Uz compinit
compinit
