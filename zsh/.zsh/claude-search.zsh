# csearch — fzf browser over Claude Code and Codex session transcripts.
#
# Usage:  csearch [terms…]
#
# Empty query lists every session, newest first: CLI, desktop, VS Code, Remote
# Control and Codex alike (subagent traces and programmatic runs excluded). As you
# type, fzf reloads the list ranked by relevance over the conversation PROSE — the
# prompts and replies, NOT tool output or injected context, which would otherwise
# make common words match nearly every transcript. The preview pane renders the
# selected conversation, showing turns matching any term (or all of them when the
# query is empty). Enter resumes the session from the first directory of it that
# still exists: its own, or the checkout a deleted worktree was cut from.
#
# Row layout:
#   col 1  agent (hidden — claude | codex, picks the resume command)
#   col 2  session id (hidden — resume target)
#   col 3  filepath (hidden — preview input)
#   col 4  resume directory (hidden — empty when none survives)
#   col 5  display string (colored reltime / agent / project / title)
#
# Requires: fzf, python3 (stdlib only). Paired helper at ~/.zsh/claude-search.py,
# which keeps its index in ~/.cache/csearch/.

typeset -g _CLAUDE_SEARCH_HELPER=${0:A:h}/claude-search.py

csearch() {
  emulate -L zsh
  setopt localoptions pipefail no_aliases 2>/dev/null

  local helper="$_CLAUDE_SEARCH_HELPER"
  # Sync once per launch, so reloads only read the index and stay fast. {q} is
  # fzf's current query, passed as one shell-quoted arg the helper splits into
  # terms.
  "$helper" refresh || return
  local reload="if [ -z {q} ]; then \"$helper\" list-all; else \"$helper\" search {q}; fi || :"

  local picked
  picked=$(
    : | fzf \
          --with-shell 'sh -c' \
          --ansi \
          --disabled \
          --no-sort \
          --query="$*" \
          --delimiter=$'\t' \
          --with-nth=5 \
          --bind "start:reload-sync:$reload" \
          --bind "change:reload(sleep 0.05; $reload)" \
          --preview="\"$helper\" preview {3} {q}" \
          --preview-window='right:55%:wrap:follow:~2' \
          --header='claude & codex sessions — type terms to rank by relevance (prose, not tool output)' \
          --header-first \
          --prompt='› ' \
          --pointer='▶' \
          --color='header:italic:dim,prompt:cyan,pointer:cyan,info:dim' \
          --no-multi
  )
  [[ -z "$picked" ]] && return 0

  # picked = "<agent>\t<id>\t<filepath>\t<dir>\t<display>"; split on tab in-shell
  # rather than forking a `cut` per field. (@) keeps an empty <dir> in its slot.
  local -a fields resume
  fields=("${(@ps:\t:)picked}")
  local agent=$fields[1]
  local session_id=$fields[2]
  local dir=$fields[4]

  case $agent in
    codex) resume=(codex resume "$session_id") ;;
    *) resume=(claude --resume "$session_id") ;;
  esac

  if [[ -d "$dir" ]]; then
    (cd "$dir" && "${resume[@]}")
  else
    print -u2 "csearch: no directory left for this session, resuming from $PWD"
    "${resume[@]}"
  fi
}
