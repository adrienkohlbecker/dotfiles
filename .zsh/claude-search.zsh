# csearch — live-rg + fzf browser over Claude Code session transcripts.
#
# Usage:  csearch
#
# Empty query lists every transcript under ~/.claude/projects/ (newest first,
# SDK/subagent/tempdir sessions excluded). As you type, fzf reloads the list
# with `rg -l -i -F "{q}"` against the full JSONL content — user prompts,
# assistant turns, tool results, the lot. The preview pane renders the
# selected conversation, showing only turns matching the query (or the
# whole transcript when the query is empty). Enter resumes the session via
# `claude --resume <uuid>` from its original cwd.
#
# Row layout:
#   col 1  filepath (hidden — preview / resume input)
#   col 2  cwd (hidden — resume cd target)
#   col 3  display string (colored reltime / cwd / summary)
#
# Requires: ripgrep, fzf, python3 (stdlib only). Paired helper at
# ~/.zsh/claude-search.py.

typeset -g _CLAUDE_SEARCH_HELPER=${0:A:h}/claude-search.py

csearch() {
  emulate -L zsh
  setopt localoptions pipefail no_aliases 2>/dev/null

  local projects="$HOME/.claude/projects"
  if [[ ! -d "$projects" ]]; then
    print -u2 "csearch: $projects not found"
    return 1
  fi

  local helper="$_CLAUDE_SEARCH_HELPER"
  # Empty query → cached list-all. Non-empty → rg-filter to *.jsonl, then
  # format via the cached list-stdin path. {q} is fzf's current query;
  # rg -F treats it as a literal substring.
  local reload="if [ -z {q} ]; then \"$helper\" list-all; else rg -l -i -F -g '*.jsonl' -- {q} \"$projects\" 2>/dev/null | \"$helper\" list-stdin; fi"

  local picked
  picked=$(
    : | fzf \
          --ansi \
          --disabled \
          --no-sort \
          --delimiter=$'\t' \
          --with-nth=3 \
          --bind "start:reload:$reload" \
          --bind "change:reload(sleep 0.1; $reload)" \
          --preview="$helper preview {1} {q}" \
          --preview-window='right:55%:wrap:follow' \
          --header='claude transcripts — type to filter by full content (rg -F -i)' \
          --header-first \
          --prompt='› ' \
          --pointer='▶' \
          --color='header:italic:dim,prompt:cyan,pointer:cyan,info:dim' \
          --no-multi
  )
  [[ -z "$picked" ]] && return 0

  # picked = "<filepath>\t<cwd>\t<display>"
  local filepath
  filepath=$(print -r -- "$picked" | cut -f1)
  local cwd
  cwd=$(print -r -- "$picked" | cut -f2)
  local uuid="${${filepath:t}:r}"

  if [[ -d "$cwd" ]]; then
    (cd "$cwd" && claude --resume "$uuid")
  else
    print -u2 "csearch: cwd $cwd missing, resuming from $PWD"
    claude --resume "$uuid"
  fi
}
