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
autoload -U promptinit; promptinit
prompt pure

# editor
export EDITOR=vim

# Start gpg-agent if not running
gpg-connect-agent /bye

if [[ `uname` == 'Linux' ]]; then
  exit 0
fi

################################################################
# macOS specific settings
################################################################

if [[ `uname -m` == 'arm64' ]]; then
  DEFAULT_HOMEBREW_PATH=/opt/homebrew
else
  DEFAULT_HOMEBREW_PATH=/usr/local
fi
HOMEBREW_PATH="${HOMEBREW_PATH:-$DEFAULT_HOMEBREW_PATH}"

export PATH=""
export MANPATH=""
export INFOPATH=""
eval `/usr/libexec/path_helper -s`

export HOMEBREW_PREFIX=""
export HOMEBREW_CELLAR=""
export HOMEBREW_REPOSITORY=""
export HOMEBREW_SHELLENV_PREFIX=""
export HOMEBREW_PREFIX=""
eval "$($HOMEBREW_PATH/bin/brew shellenv)"

# unprefixed utils
export PATH="$HOMEBREW_PATH/opt/findutils/libexec/gnubin:$PATH"
export PATH="$HOMEBREW_PATH/opt/grep/libexec/gnubin:$PATH"
#export PATH="$HOMEBREW_PATH/opt/gnu-sed/libexec/gnubin:$PATH"
export PATH="$HOMEBREW_PATH/opt/gnu-tar/libexec/gnubin:$PATH"
export PATH="$HOMEBREW_PATH/opt/coreutils/libexec/gnubin:$PATH"
export PATH="$HOMEBREW_PATH/opt/curl/bin:$PATH"
export PATH="$HOMEBREW_PATH/opt/postgresql@12/bin:$PATH"
export PATH="$HOMEBREW_PATH/opt/python@3.9/libexec/bin:$PATH"

# Gopath
export GOPATH=$HOME/.gopath
export PATH=$GOPATH/bin:$PATH

source "$HOMEBREW_PATH/Caskroom/google-cloud-sdk/latest/google-cloud-sdk/path.zsh.inc"
source "$HOMEBREW_PATH/Caskroom/google-cloud-sdk/latest/google-cloud-sdk/completion.zsh.inc"

# ASDF
. $HOME/.asdf/asdf.sh
fpath=(${ASDF_DIR}/completions $fpath)

# Brew completions
fpath+=($HOMEBREW_PATH/share/zsh/site-functions)

# compinit
autoload -Uz compinit
compinit

export PKG_CONFIG_PATH=""

# Added by GDK bootstrap
export PKG_CONFIG_PATH="$HOMEBREW_PATH/opt/icu4c/lib/pkgconfig:${PKG_CONFIG_PATH}"

# Added by GDK bootstrap
export RUBY_CONFIGURE_OPTS="--with-openssl-dir=$HOMEBREW_PATH/opt/openssl@1.1 --with-readline-dir=$HOMEBREW_PATH/opt/readline"

function gdk {
  (
    HOMEBREW_PATH=/usr/local source ~/.zshrc
    cd ~/Work/gitlab/gdk
    command gdk "$@"
  )
}

function tf {
  if [ -z "$1" ]; then echo "Usage: tf ENV ARGS..."; return 1; fi
  (
    cd ~/Work/gitlab/gitlab-com-infrastructure/environments/$1 || return 1
    shift
    ~/Work/gitlab/gitlab-com-infrastructure/bin/tf "$@"
  )
}
