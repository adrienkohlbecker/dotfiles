source /usr/local/share/zsh-autosuggestions/zsh-autosuggestions.zsh
source /usr/local/share/zsh-syntax-highlighting/zsh-syntax-highlighting.zsh

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

# command aliases
alias history="builtin fc -l -i -D"
alias tig="command tig status"
alias dotfiles='/usr/bin/env git --git-dir=$HOME/.dotfiles --work-tree=$HOME'
alias dkr='docker run -ti --rm -v $(pwd):$(pwd) -w $(pwd)'

# Prompt theme
fpath+=("$HOME/.zsh/pure")
autoload -U promptinit; promptinit
prompt pure

# Gopath
export GOPATH=$HOME/.gopath
export PATH=$GOPATH/bin:$PATH

# GPG
if [[ -z "$GPG_AGENT_INFO" && ! -S "${GNUPGHOME:-$HOME/.gnupg}/S.gpg-agent" ]]; then
  # Start gpg-agent if not started.
  gpg-agent --daemon
fi

# unprefixed utils
export PATH="/usr/local/opt/findutils/libexec/gnubin:$PATH"
export PATH="/usr/local/opt/grep/libexec/gnubin:$PATH"
export PATH="/usr/local/opt/gnu-sed/libexec/gnubin:$PATH"
export PATH="/usr/local/opt/gnu-tar/libexec/gnubin:$PATH"
export PATH="/usr/local/opt/coreutils/libexec/gnubin:$PATH"
export PATH="/usr/local/opt/curl/bin:$PATH"

# editor
export EDITOR=vim

# ASDF
. $HOME/.asdf/asdf.sh
fpath=(${ASDF_DIR}/completions $fpath)

# Brew completions
fpath+=(/usr/local/share/zsh/site-functions)

# compinit
autoload -Uz compinit
compinit
