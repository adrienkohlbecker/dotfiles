# .zshenv This is ALWAYS loaded first, for your user account for all shells.

# editor
export EDITOR=vim

if [[ $(uname) == 'Linux' ]]; then
  return
fi

################################################################
# macOS specific settings
################################################################

HOMEBREW_PATH="${HOMEBREW_PATH:-/opt/homebrew}"

export PATH=""
export MANPATH=""
export INFOPATH=""
eval $(/usr/libexec/path_helper -s)

export HOMEBREW_PREFIX=""
export HOMEBREW_CELLAR=""
export HOMEBREW_REPOSITORY=""
eval "$($HOMEBREW_PATH/bin/brew shellenv)"

# unprefixed utils
export PATH="$HOMEBREW_PATH/opt/findutils/libexec/gnubin:$PATH"
export PATH="$HOMEBREW_PATH/opt/grep/libexec/gnubin:$PATH"
#export PATH="$HOMEBREW_PATH/opt/gnu-sed/libexec/gnubin:$PATH"
export PATH="$HOMEBREW_PATH/opt/gnu-tar/libexec/gnubin:$PATH"
#export PATH="$HOMEBREW_PATH/opt/coreutils/libexec/gnubin:$PATH"
export PATH="$HOMEBREW_PATH/opt/curl/bin:$PATH"
export PATH="$HOMEBREW_PATH/opt/postgresql@12/bin:$PATH"
export PATH="$HOME/.platformio/penv/bin:$PATH"

# fzf
export PATH="$HOME/.zsh/fzf/bin:$PATH"

# Gopath
export GOPATH=$HOME/.gopath
export PATH=$GOPATH/bin:$PATH

source "$(brew --prefix)/share/google-cloud-sdk/path.zsh.inc"

# ASDF
. $HOME/.asdf/asdf.sh

# On macOS, /etc/zprofile reorders the path by executing path_helper. The following lines, coupled with code in ~/.zprofile,
# ensure that the PATH we set in this file take precedence
typeset -U path
path_prepend=($path)
