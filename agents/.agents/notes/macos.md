# macOS workstation

## Terminal: Ghostty + terminfo gap

The operator's terminal is **Ghostty**, so interactive SSH sessions carry `TERM=xterm-ghostty`. Freshly-provisioned hosts (new VPS, mesh nodes) don't ship the `xterm-ghostty` terminfo entry; without it zsh's `zle` line editor misrenders (doubled characters, runaway redraw), made worse by zsh-syntax-highlighting's per-keystroke redraw.

When the operator reports garbled/doubled input over SSH to a new host, check `infocmp xterm-ghostty` on the host first.
- Per-host fix: `infocmp -x xterm-ghostty | ssh <host> -- tic -x -` (installs to `~/.terminfo`).
- Band-aid: `TERM=xterm-256color ssh <host>` (works, no garble).
- Hosts lacking `tic`/`infocmp` (e.g. a Synology NAS) can't self-install: compile locally (`tic -x -o <dir>`), stream the compiled file to `~/.terminfo/x/xterm-ghostty` (`ssh host 'cat > …'` when scp lacks sftp), **and** `ghostty +ssh-cache --add=<user>@<host>` — otherwise Ghostty re-probes, fails, and ignores the file.

Ghostty's `shell-integration-features` includes `ssh-terminfo`, which wraps `ssh` and tries `infocmp xterm-ghostty && exit 0; command -v tic || exit 1; tic -x -` on connect; it only sends `TERM=xterm-ghostty` when that succeeds or the host is in Ghostty's ssh-cache, else falls back to `xterm-256color`.

## `com.apple.provenance` breaks xattr-preserving copies

On macOS Sequoia the kernel stamps an **unremovable** `com.apple.provenance` xattr on essentially every file (`xattr -c` doesn't stick; even `cp -X` re-stamps). A podman-machine container build that bind-mounts host files via virtiofs sees this xattr, and any copy preserving xattrs (`cp --preserve=xattr`, `cp -a`) fails with `setting attributes … Operation not supported` — `com.apple.*` isn't a valid Linux xattr namespace. A second independent trigger: the podman-machine overlay mounts with a fixed SELinux `context=`, so the destination also rejects `setxattr(security.selinux)` (and `--security-opt label=disable` does *not* remove the `context=` mount).

**General lesson:** on Mac + podman, prefer copy mechanisms that DON'T preserve xattrs (`cp` default, `rsync` without `-X`, `tar`) over `cp -a` / `--preserve=xattr`. Tools with their own xattr-preserving copy may expose an opt-out (e.g. dracut honours `DRACUT_NO_XATTR=1`). Linux/CI never hit either trigger.
