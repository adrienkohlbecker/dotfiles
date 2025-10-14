# .zprofile is loaded after .zshenv for login shells (the shell you get when you first log in). It’s not loaded again when you open more terminals on the machine. It’s also not loaded by remote commands run over ssh (usually).

# Restore path set by ~/.zshenv after executing /etc/zprofile
if [[ -v path_prepend ]]; then
  path=($path_prepend $path)
fi

# Start gpg-agent if not running
gpg-connect-agent /bye
