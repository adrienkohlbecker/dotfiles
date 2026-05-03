#!/bin/sh
input=$(cat)
current_dir=$(echo "$input" | jq -r '.workspace.current_dir')
model_name=$(echo "$input" | jq -r '.model.display_name')
remaining=$(echo "$input" | jq -r '.context_window.remaining_percentage // empty')

# Output style (empty when default or not set)
output_style=$(echo "$input" | jq -r '.output_style.name // empty')
[ "$output_style" = "default" ] && output_style=""

# Context warning: flag when current API response exceeds 200k tokens
ctx_warning=$(echo "$input" | jq -r 'if .exceeds_200k_tokens then "1" else "" end')

# Optional context indicators (rendered only when set)
session_name=$(echo "$input" | jq -r '.session_name // empty')
agent_name=$(echo "$input" | jq -r '.agent.name // empty')
worktree_name=$(echo "$input" | jq -r '.worktree.name // empty')
worktree_branch=$(echo "$input" | jq -r '.worktree.branch // empty')

# Rate limit fields (Claude.ai subscribers only; empty when not available)
rl_5h=$(echo "$input" | jq -r '.rate_limits.five_hour.used_percentage // empty')
rl_7d=$(echo "$input" | jq -r '.rate_limits.seven_day.used_percentage // empty')
rl_5h_reset=$(echo "$input" | jq -r '.rate_limits.five_hour.resets_at // empty')
rl_7d_reset=$(echo "$input" | jq -r '.rate_limits.seven_day.resets_at // empty')

dir_name=$(basename "$current_dir")

# --- git section (pure-style, cheap operations only) ---
git_info=""
if git -C "$current_dir" rev-parse --git-dir > /dev/null 2>&1; then
  # Branch name; falls back to tag name, then short SHA for detached HEAD
  branch=$(git -C "$current_dir" symbolic-ref --short HEAD 2>/dev/null)
  if [ -z "$branch" ]; then
    branch=$(git -C "$current_dir" describe --tags --exact-match HEAD 2>/dev/null)
    if [ -z "$branch" ]; then
      branch=$(git -C "$current_dir" rev-parse --short HEAD 2>/dev/null)
      [ -n "$branch" ] && branch="($branch)"  # detached indicator, pure style
    else
      branch="($branch)"  # on a tag
    fi
  fi

  # Dirty indicator: staged or unstaged changes (index + worktree, excludes untracked)
  dirty=""
  if ! git -C "$current_dir" diff --quiet 2>/dev/null || \
     ! git -C "$current_dir" diff --cached --quiet 2>/dev/null; then
    dirty="*"
  fi

  # Ahead / behind upstream
  arrows=""
  upstream=$(git -C "$current_dir" rev-parse --abbrev-ref '@{upstream}' 2>/dev/null)
  if [ -n "$upstream" ]; then
    ahead=$(git -C "$current_dir" rev-list --count '@{upstream}..HEAD' 2>/dev/null)
    behind=$(git -C "$current_dir" rev-list --count 'HEAD..@{upstream}' 2>/dev/null)
    [ "${ahead:-0}" -gt 0 ] 2>/dev/null && arrows="${arrows}⇡${ahead}"
    [ "${behind:-0}" -gt 0 ] 2>/dev/null && arrows="${arrows}⇣${behind}"
  fi

  # Assemble: branch + dirty run together, arrows separated by space
  git_part="${branch}${dirty}"
  [ -n "$arrows" ] && git_part="${git_part} ${arrows}"
  # dim grey, matching pure's muted branch colour
  git_info=$(printf '\033[2m%s\033[0m' "$git_part")
fi

# --- rate limit section ---
# Builds a compact "5h:NN% 7d:NN%" string; each part omitted when not present.
# Uses "remaining" framing (100 - used) so the number stays intuitive alongside ctx%.
# Color thresholds per field: >50% remaining = dim, 20-50% = yellow, <20% = red.
_rl_color() {
  pct=$1  # remaining percentage
  if [ "$pct" -lt 20 ] 2>/dev/null; then
    printf '\033[31m'   # red
  elif [ "$pct" -lt 50 ] 2>/dev/null; then
    printf '\033[33m'   # yellow
  else
    printf '\033[2m'    # dim
  fi
}
rate_info=""
if [ -n "$rl_5h" ]; then
  rem_5h=$(printf '%.0f' "$(echo "$rl_5h" | awk '{print 100 - $1}')")
  reset_5h=""
  if [ -n "$rl_5h_reset" ]; then
    t=$(date -r "$rl_5h_reset" '+%H:%M' 2>/dev/null)
    [ -n "$t" ] && reset_5h="↻${t}"
  fi
  rate_info="${rate_info}$(_rl_color "$rem_5h")5h:${rem_5h}%${reset_5h}\033[0m"
fi
if [ -n "$rl_7d" ]; then
  rem_7d=$(printf '%.0f' "$(echo "$rl_7d" | awk '{print 100 - $1}')")
  reset_7d=""
  if [ -n "$rl_7d_reset" ]; then
    # Same-day -> HH:MM; otherwise "Day HH:MM" (7d window can be days away)
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
  rate_info="${rate_info}$(_rl_color "$rem_7d")7d:${rem_7d}%${reset_7d}\033[0m"
fi

# --- assemble status line ---
# order: dir  git  [worktree]  model  [agent]  [session]  [style]  ctx  usage
line=$(printf '\033[2m%s\033[0m' "$dir_name")
[ -n "$git_info" ] && line="${line}  ${git_info}"
if [ -n "$worktree_name" ]; then
  wt_label="${worktree_name}"
  [ -n "$worktree_branch" ] && wt_label="${worktree_name}:${worktree_branch}"
  line="${line}  $(printf '\033[35m⎇ %s\033[0m' "$wt_label")"
fi
line="${line}  \033[36m${model_name}\033[0m"
[ -n "$agent_name" ] && line="${line}  $(printf '\033[35m@%s\033[0m' "$agent_name")"
[ -n "$session_name" ] && line="${line}  $(printf '\033[2m{%s}\033[0m' "$session_name")"
if [ -n "$output_style" ]; then
  line="${line}  $(printf '\033[2m[%s]\033[0m' "$output_style")"
fi
if [ -n "$remaining" ]; then
  if [ -n "$ctx_warning" ]; then
    # Red when context exceeds 200k tokens
    line="${line}  $(printf '\033[31mctx:%s%%\033[0m' "$(printf '%.0f' "$remaining")")"
  else
    line="${line}  $(printf '\033[2mctx:%s%%\033[0m' "$(printf '%.0f' "$remaining")")"
  fi
fi
if [ -n "$rate_info" ]; then
  line="${line}  ${rate_info}"
fi
printf '%b' "$line"
