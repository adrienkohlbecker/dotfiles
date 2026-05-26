# .zshenv This is ALWAYS loaded first, for your user account for all shells.

if [[ $(uname) == 'Darwin' ]]; then

  ################################################################
  # macOS specific settings
  ################################################################

  HOMEBREW_PATH="${HOMEBREW_PATH:-/opt/homebrew}"

  export PATH=""
  export MANPATH=""
  export INFOPATH=""
  eval $(/usr/libexec/path_helper -s)

  # Skip on a brew-less host (e.g. a fresh Mac) so we keep path_helper's system
  # PATH instead of spewing "no such file" from the eval on every shell.
  if [ -x "$HOMEBREW_PATH/bin/brew" ]; then
    export HOMEBREW_PREFIX=""
    export HOMEBREW_CELLAR=""
    export HOMEBREW_REPOSITORY=""
    eval "$($HOMEBREW_PATH/bin/brew shellenv)"
  fi

  # unprefixed utils
  export PATH="$HOMEBREW_PATH/opt/findutils/libexec/gnubin:$PATH"
  export PATH="$HOMEBREW_PATH/opt/grep/libexec/gnubin:$PATH"
  export PATH="$HOMEBREW_PATH/opt/gnu-tar/libexec/gnubin:$PATH"
  export PATH="$HOMEBREW_PATH/opt/curl/bin:$PATH"
  export PATH="$HOMEBREW_PATH/opt/postgresql@12/bin:$PATH"
  export PATH="$HOMEBREW_PATH/opt/dotnet@8/bin:$PATH"
  export PATH="$HOME/.platformio/penv/bin:$PATH"

  # Gopath
  export GOPATH=$HOME/.gopath
  export PATH=$GOPATH/bin:$PATH

  # LM Studio CLI (lms)
  export PATH="$PATH:$HOME/.lmstudio/bin"

  [ -f "$HOMEBREW_PATH/share/google-cloud-sdk/path.zsh.inc" ] && source "$HOMEBREW_PATH/share/google-cloud-sdk/path.zsh.inc"

  # Load the mac-only language pins (~/.config/mise/config.mac.toml). The fleet
  # leaves MISE_ENV unset, so a bare `mise install` there sees only the
  # cross-platform CLI tools in config.toml — never the source-compiled ruby.
  export MISE_ENV=mac

  # On macOS, /etc/zprofile reorders the path by executing path_helper. The following lines, coupled with code in ~/.zprofile,
  # ensure that the PATH we set in this file take precedence
  typeset -U path
  path_prepend=($path)

fi

# editor
export EDITOR=vim

# fzf
export PATH="$HOME/.zsh/fzf/bin:$PATH"

# local binaries
export PATH="$HOME/.local/bin:$PATH"

# dotfiles bare-repo wrapper — a function (not a .zshrc alias) so it resolves in
# non-interactive shells and scripts too; aliases are only expanded interactively.
dotfiles() {
  /usr/bin/env git -C "$HOME" --git-dir="$HOME/.dotfiles" --work-tree="$HOME" "$@"
}

# Machine-local overrides (untracked, not in the dotfiles repo)
[ -f ~/.zshenv.local ] && source ~/.zshenv.local
