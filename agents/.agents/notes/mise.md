# mise tooling

## Config split: cross-platform CLI vs language runtimes

The dotfiles' mise config is the single source of truth for tool versions:
- Global `~/.config/mise/config.toml` — cross-platform CLI tools (fd, bat, zoxide, atuin, delta, eza, …). Installed everywhere, including the Linux fleet via a bare non-interactive `mise install`.
- `~/.config/mise/config.mac.toml` — language runtimes (python, ruby, node, go) and mac-only tools, loaded only via `MISE_ENV=mac` (set in `.zshenv`'s Darwin block).

Language runtimes must **not** install on Linux servers: ruby compiles from source via ruby-build and the fleet lacks the build deps; dev-time pins belong on the workstation. So a fleet `mise install` runs without `MISE_ENV` and sees only the CLI tools. New fleet-wide tooling → add to the global `config.toml`; anything that compiles or is dev-only → `config.mac.toml`. Don't duplicate a hardcoded tool list anywhere — let `mise install` read the config.

## eza has no macOS release binary

eza (`eza-community/eza`) publishes only Linux + Windows release binaries — no `*-apple-darwin` asset. Every GitHub-asset mise backend (`aqua:`, `ubi:`, `github:eza-community/eza`) FAILS on macOS ("could not find a release asset for this OS (macos)").

Use `asdf:mise-plugins/mise-eza` instead — its install script gets prebuilt binaries on both platforms (Linux from eza's release, macOS from `cargo-bins/cargo-quickinstall`, no local compile). Pin the explicit `asdf:` backend in config, not the short name `eza`, so resolution can't drift to the darwin-broken aqua backend. Caveat: unlike aqua it does not verify a checksum (plain curl) — accepted pragmatic gap. The other CLI tools have cross-platform aqua entries (prebuilt + checksum/attestation verified).
