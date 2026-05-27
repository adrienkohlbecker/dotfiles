# Atuin-backed Ctrl-R history widget. Source from .zshrc *after* ~/.fzf.zsh
# (which defines __fzfcmd, reused below).
#
# Requires fzf ≥ 0.61 (transform, --ghost, change-ghost) and `uv` on PATH — the
# helper is a uv-run script that pulls pygments for highlighting (see its header
# for why uv rather than the ambient python3).
#
# Filter cycle: session-preload → workspace → host → session-preload …
# Ctrl-O fires a `transform` action that reads $FZF_GHOST to find the current
# mode, picks the next one, and emits `reload(...)+change-ghost(...)`. fzf
# stays alive throughout — no relaunch, no flicker.
#
# Helper at fzf-atuin-widget.py (paired with this file) does the work:
#   helper <mode>   → emit colored history list
#   helper cycle    → emit Ctrl-O transition action chain
# It can't be a zsh function: fzf spawns child sh processes for reload/
# transform actions which don't see the parent zsh's function table.
#
# Highlighting is computed on the fly per invocation — no cache (atuin returns
# in tens of ms and pygments highlights the set in about the same; see the
# helper header for the rationale).

# Capture the helper path at source time; ${0:A:h} resolves the directory
# of the sourced .zsh file (inside the function, $0 would mean the function
# name instead).
typeset -g _FZF_ATUIN_HELPER=${0:A:h}/fzf-atuin-widget.py

fzf-atuin-history-widget() {
  local selected
  setopt localoptions noglobsubst noposixbuiltins pipefail no_aliases 2> /dev/null
  # fzf reads $FZF_DEFAULT_OPTS itself, so we don't need to embed it. CLI args
  # for everything else; $FZF_CTRL_R_OPTS appended last so user overrides win.
  selected=$(
    "$_FZF_ATUIN_HELPER" session-preload | $(__fzfcmd) \
      --with-shell 'sh -c' \
      --height "${FZF_TMUX_HEIGHT:-40%}" \
      --scheme=history \
      --ansi \
      --bind=ctrl-r:toggle-sort,ctrl-z:ignore \
      --query="$LBUFFER" \
      +m \
      --info=inline-right \
      --ghost="filter: session-preload    Ctrl-O: cycle    Ctrl-R: toggle sort" \
      --bind="ctrl-o:transform($_FZF_ATUIN_HELPER cycle)" \
      ${=FZF_CTRL_R_OPTS:-}
  )
  local ret=$?
  if [ -n "$selected" ]; then
    LBUFFER=${selected//↵/$'\n'}
  fi
  zle reset-prompt
  return $ret
}

zle     -N             fzf-atuin-history-widget
bindkey -M emacs '^R'  fzf-atuin-history-widget
bindkey -M vicmd '^R'  fzf-atuin-history-widget
bindkey -M viins '^R'  fzf-atuin-history-widget
