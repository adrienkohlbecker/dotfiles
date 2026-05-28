# csearch — live-rg + fzf browser over Claude Code session transcripts.
#
# Usage:  csearch
#
# Empty query lists every transcript under ~/.claude/projects/ (newest first,
# SDK/subagent/tempdir sessions excluded). As you type, fzf reloads the list,
# ranked by relevance over the conversation PROSE — the user prompts and
# assistant replies, NOT tool output, pasted files, or system records, which
# would otherwise make common words match nearly every transcript. An `rg -F`
# union scan narrows candidates, then each is scored by per-term occurrence
# count in its prose; rows order by (distinct terms matched, total occurrences,
# recency), so the sessions actually *about* your terms rise to the top. The
# preview pane renders the selected conversation, showing turns matching any
# term (or the whole transcript when the query is empty). Enter resumes the
# session via `claude --resume <uuid>` from its original cwd.
#
# Row layout:
#   col 1  filepath (hidden — preview / resume input)
#   col 2  cwd (hidden — resume cd target)
#   col 3  display string (colored reltime / cwd / title — ai-title, else
#          first user prompt)
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
  # Empty query → list every transcript. Non-empty → the helper's `search`
  # narrows to transcripts containing all of {q}'s terms somewhere (chained
  # rg -F). Each reload is a fresh scan — there is no cache. {q} is fzf's
  # current query, passed as one shell-quoted arg the helper splits into terms.
  local reload="if [ -z {q} ]; then \"$helper\" list-all; else \"$helper\" search {q}; fi || :"

  local picked
  picked=$(
    : | fzf \
          --with-shell 'sh -c' \
          --ansi \
          --disabled \
          --no-sort \
          --delimiter=$'\t' \
          --with-nth=3 \
          --bind "start:reload-sync:$reload" \
          --bind "change:reload(sleep 0.2; $reload)" \
          --preview="\"$helper\" preview {1} {q}" \
          --preview-window='right:55%:wrap:follow' \
          --header='claude transcripts — type terms to rank by relevance (prose, not tool output)' \
          --header-first \
          --prompt='› ' \
          --pointer='▶' \
          --color='header:italic:dim,prompt:cyan,pointer:cyan,info:dim' \
          --no-multi
  )
  [[ -z "$picked" ]] && return 0

  # picked = "<filepath>\t<cwd>\t<display>"; split on tab in-shell rather than
  # forking two `cut` subshells per selection.
  local -a fields
  fields=("${(@ps:\t:)picked}")
  local filepath=$fields[1]
  local cwd=$fields[2]
  local uuid="${${filepath:t}:r}"

  if [[ -d "$cwd" ]]; then
    (cd "$cwd" && claude --resume "$uuid")
  else
    print -u2 "csearch: cwd $cwd missing, resuming from $PWD"
    claude --resume "$uuid"
  fi
}
