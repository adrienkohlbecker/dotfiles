#!/bin/sh
# Claude Code status line. Reads session JSON on stdin, prints one colored line.
# Deliberately NO `set -e`: a statusline must degrade gracefully, never abort —
# a non-numeric field or a missing git repo must not blank the whole line.
input=$(cat)

# Single jq pass: one field per line, fixed order, read positionally below.
# `// ""` keeps every field present so the line count stays stable even when
# a field is absent (one parse, one fork — not one jq per field).
{
  IFS= read -r current_dir
  IFS= read -r model_name
  IFS= read -r remaining
  IFS= read -r output_style
  IFS= read -r ctx_warning
  IFS= read -r session_name
  IFS= read -r agent_name
  IFS= read -r worktree_name
  IFS= read -r worktree_branch
  IFS= read -r ws_git_worktree
  IFS= read -r rl_5h
  IFS= read -r rl_7d
  IFS= read -r rl_5h_reset
  IFS= read -r rl_7d_reset
} <<EOF
$(printf '%s' "$input" | jq -r '
  def clean: gsub("[[:cntrl:]]"; "");
  (.workspace.current_dir // "" | clean),
  (.model.display_name // "" | clean),
  (.context_window.remaining_percentage // ""),
  (.output_style.name // "" | if . == "default" then "" else . end | clean),
  (if .exceeds_200k_tokens then "1" else "" end),
  (.session_name // "" | clean),
  (.agent.name // "" | clean),
  (.worktree.name // "" | clean),
  (.worktree.branch // "" | clean),
  (.workspace.git_worktree // "" | clean),
  (.rate_limits.five_hour.used_percentage // ""),
  (.rate_limits.seven_day.used_percentage // ""),
  (.rate_limits.five_hour.resets_at // ""),
  (.rate_limits.seven_day.resets_at // "")
')
EOF

# Colors as real ESC bytes (built once) so the final emit can be printf '%s' —
# never '%b'. A field value containing a literal "\033[..." must be printed
# verbatim, not interpreted into control sequences (terminal-injection guard).
esc=$(printf '\033')
dim="${esc}[2m"; red="${esc}[31m"; yel="${esc}[33m"; cyan="${esc}[36m"; mag="${esc}[35m"; rst="${esc}[0m"

dir_name=$(basename "$current_dir")

# --- git section: one `git status --porcelain=v2 --branch` instead of ~8 calls ---
git_info=""
gitout=$(git -C "$current_dir" status --porcelain=v2 --branch 2>/dev/null)
if [ -n "$gitout" ]; then
  # `# branch.head <name>` — or literally "(detached)", which v2 can't expand
  branch=$(printf '%s\n' "$gitout" | awk '/^# branch.head / {print $3; exit}')
  if [ "$branch" = "(detached)" ]; then
    b=$(git -C "$current_dir" describe --tags --exact-match HEAD 2>/dev/null) \
      || b=$(git -C "$current_dir" rev-parse --short HEAD 2>/dev/null)
    branch="($b)"
  fi

  # Dirty: any staged/unstaged tracked change (1/2) or unmerged (u). Untracked
  # (?) is excluded, matching the prior diff-based check.
  dirty=""
  printf '%s\n' "$gitout" | grep -q '^[12u] ' && dirty="*"

  # Ahead/behind from `# branch.ab +A -B` (only present when an upstream exists)
  arrows=""
  ab=$(printf '%s\n' "$gitout" | awk '/^# branch.ab / {print $3" "$4; exit}')
  if [ -n "$ab" ]; then
    ahead=${ab%% *}; ahead=${ahead#+}
    behind=${ab##* }; behind=${behind#-}
    [ "${ahead:-0}" -gt 0 ] 2>/dev/null && arrows="${arrows}⇡${ahead}"
    [ "${behind:-0}" -gt 0 ] 2>/dev/null && arrows="${arrows}⇣${behind}"
  fi

  git_part="${branch}${dirty}"
  [ -n "$arrows" ] && git_part="${git_part} ${arrows}"
  git_info="${dim}${git_part}${rst}"
fi

# --- rate limit section ---
# "5h:NN% 7d:NN%" in remaining framing (100 - used). resets_at is Unix epoch
# seconds (per the statusline schema), so date -r is the correct reader.
# Color per field: >50% remaining = dim, 20-50% = yellow, <20% = red.
_rl_color() {
  pct=$1
  if [ "$pct" -lt 20 ] 2>/dev/null; then printf '%s' "$red"
  elif [ "$pct" -lt 50 ] 2>/dev/null; then printf '%s' "$yel"
  else printf '%s' "$dim"; fi
}
rate_info=""
if [ -n "$rl_5h" ]; then
  rem_5h=$(printf '%.0f' "$(echo "$rl_5h" | awk '{print 100 - $1}')")
  reset_5h=""
  if [ -n "$rl_5h_reset" ]; then
    t=$(date -r "$rl_5h_reset" '+%H:%M' 2>/dev/null)
    [ -n "$t" ] && reset_5h="↻${t}"
  fi
  rate_info="${rate_info}$(_rl_color "$rem_5h")5h:${rem_5h}%${reset_5h}${rst}"
fi
if [ -n "$rl_7d" ]; then
  rem_7d=$(printf '%.0f' "$(echo "$rl_7d" | awk '{print 100 - $1}')")
  reset_7d=""
  if [ -n "$rl_7d_reset" ]; then
    # Same-day -> HH:MM; otherwise "Day HH:MM" (7d window can be days out)
    today=$(date '+%Y%m%d')
    reset_day=$(date -r "$rl_7d_reset" '+%Y%m%d' 2>/dev/null)
    if [ "$reset_day" = "$today" ]; then
      t=$(date -r "$rl_7d_reset" '+%H:%M' 2>/dev/null)
    else
      t=$(date -r "$rl_7d_reset" '+%a %H:%M' 2>/dev/null)
    fi
    [ -n "$t" ] && reset_7d="↻${t}"
  fi
  [ -n "$rate_info" ] && rate_info="${rate_info} "
  rate_info="${rate_info}$(_rl_color "$rem_7d")7d:${rem_7d}%${reset_7d}${rst}"
fi

# --- assemble: dir  git  [worktree]  model  [agent]  [session]  [style]  ctx  usage ---
line="${dim}${dir_name}${rst}"
[ -n "$git_info" ] && line="${line}  ${git_info}"

# Worktree: prefer the --worktree-session fields (they carry a branch); fall back
# to workspace.git_worktree, which is populated for any linked git worktree.
wt_label=""
if [ -n "$worktree_name" ]; then
  wt_label="$worktree_name"
  [ -n "$worktree_branch" ] && wt_label="${worktree_name}:${worktree_branch}"
elif [ -n "$ws_git_worktree" ]; then
  wt_label="$ws_git_worktree"
fi
[ -n "$wt_label" ] && line="${line}  ${mag}⎇ ${wt_label}${rst}"

line="${line}  ${cyan}${model_name}${rst}"
[ -n "$agent_name" ] && line="${line}  ${mag}@${agent_name}${rst}"
[ -n "$session_name" ] && line="${line}  ${dim}{${session_name}}${rst}"
[ -n "$output_style" ] && line="${line}  ${dim}[${output_style}]${rst}"
if [ -n "$remaining" ]; then
  rem=$(printf '%.0f' "$remaining")
  if [ -n "$ctx_warning" ]; then
    line="${line}  ${red}ctx:${rem}%${rst}"
  else
    line="${line}  ${dim}ctx:${rem}%${rst}"
  fi
fi
[ -n "$rate_info" ] && line="${line}  ${rate_info}"

printf '%s' "$line"
