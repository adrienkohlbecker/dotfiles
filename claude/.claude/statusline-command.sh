#!/bin/sh
# Claude Code status line. Reads session JSON on stdin, prints one colored line.
# Deliberately NO `set -e`: a statusline must degrade gracefully, never abort —
# a non-numeric field or a missing git repo must not blank the whole line.

# Cap the read: legitimate session JSON is well under 64 KiB, and the script runs
# on every refresh, so an unbounded `cat` would re-buffer a pathological payload
# each keystroke.
input=$(head -c 65536)

# Single jq pass: one field per line, fixed order, read positionally below.
# `// ""` keeps every field present so the line count stays stable even when
# a field is absent (one parse, one fork — not one jq per field). The numeric
# fields are also rounded here (ctx, and 100−used for each rate window) so the
# shell does no float math downstream — a non-number yields "" and is skipped.
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
  IFS= read -r rem_5h
  IFS= read -r rem_7d
  IFS= read -r rl_5h_reset
  IFS= read -r rl_7d_reset
  IFS= read -r session_id
  IFS= read -r effort
} <<EOF
$(printf '%s' "$input" | jq -r '
  def clean: gsub("[[:cntrl:]]"; "");
  (.workspace.current_dir // "" | clean),
  (.model.display_name // "" | clean),
  (if (.context_window.remaining_percentage | type) == "number"
     then (.context_window.remaining_percentage | round) else "" end),
  (.output_style.name // "" | if . == "default" then "" else . end | clean),
  (if .exceeds_200k_tokens then "1" else "" end),
  (.session_name // "" | clean),
  (.agent.name // "" | clean),
  (.worktree.name // "" | clean),
  (.worktree.branch // "" | clean),
  (.workspace.git_worktree // "" | clean),
  (if (.rate_limits.five_hour.used_percentage | type) == "number"
     then ((100 - .rate_limits.five_hour.used_percentage) | round) else "" end),
  (if (.rate_limits.seven_day.used_percentage | type) == "number"
     then ((100 - .rate_limits.seven_day.used_percentage) | round) else "" end),
  (.rate_limits.five_hour.resets_at // ""),
  (.rate_limits.seven_day.resets_at // ""),
  (.session_id // "" | clean),
  (.effort.level // "" | clean)
')
EOF

# Colors as real ESC bytes (built once) so the final emit can be printf '%s' —
# never '%b'. A field value containing a literal "\033[..." must be printed
# verbatim, not interpreted into control sequences (terminal-injection guard).
esc=$(printf '\033')
dim="${esc}[2m"; red="${esc}[31m"; yel="${esc}[33m"; grn="${esc}[32m"; cyan="${esc}[36m"; mag="${esc}[35m"; bold="${esc}[1m"; rst="${esc}[0m"

# Clamp a label to the line's one-row budget. Best-effort (byte-wise via cut),
# guarded on length so the common short-label case forks nothing.
_trunc() {
  if [ "${#1}" -gt "$2" ]; then
    printf '%s…' "$(printf '%s' "$1" | cut -c1-"$2")"
  else
    printf '%s' "$1"
  fi
}

dir_name=${current_dir##*/}
[ -z "$dir_name" ] && dir_name=$current_dir   # current_dir is "/" (or empty)
dir_name=$(_trunc "$dir_name" 24)

# --- git section ---
# One `git status --porcelain=v2 --branch` instead of ~8 calls. git status can
# stall on large/slow repos and this runs on every refresh, so the rendered
# segment is cached per (session, dir) for a few seconds. Keying on the dir too
# means a `cd` mid-session refreshes immediately instead of showing a stale repo.
git_info=""
now=$(date +%s)
cache_file=""
if [ -n "$session_id" ]; then
  key=$(printf '%s' "${session_id}${current_dir}" | cksum | cut -d' ' -f1)
  cache_file="${TMPDIR:-/tmp}/statusline-git-${key}"
fi

cached=""
if [ -n "$cache_file" ] && [ -f "$cache_file" ]; then
  mtime=$(stat -f %m "$cache_file" 2>/dev/null || stat -c %Y "$cache_file" 2>/dev/null)
  if [ -n "$mtime" ] && [ "$((now - mtime))" -lt 5 ]; then
    cached=1
    git_info=$(cat "$cache_file")
  fi
fi

if [ -z "$cached" ]; then
  # Gate on a real work tree: inside a bare repo or a `.git` dir, porcelain v2
  # still prints `# branch.head`, which would render a phantom branch for a
  # location that has no working copy.
  if [ -n "$current_dir" ] \
    && [ "$(git -C "$current_dir" rev-parse --is-inside-work-tree 2>/dev/null)" = "true" ]; then
    gitout=$(git -C "$current_dir" status --porcelain=v2 --branch 2>/dev/null)

    # `# branch.head <name>` — or literally "(detached)", which v2 can't expand.
    # A detached HEAD is a non-standard state, so it renders yellow (vs dim).
    branch_color=$dim
    branch=$(printf '%s\n' "$gitout" | awk '/^# branch.head / {print $3; exit}')
    if [ "$branch" = "(detached)" ]; then
      # One describe: --tags shows an exact tag if HEAD is on one, --always
      # falls back to the abbreviated SHA otherwise.
      b=$(git -C "$current_dir" describe --tags --always --abbrev=7 HEAD 2>/dev/null)
      branch="($b)"
      branch_color=$yel
    fi
    branch=$(_trunc "$branch" 24)

    # Worktree state from the 1/2 (tracked changes) and u (unmerged) entries;
    # untracked (?) is intentionally not counted. Conflicts outrank plain dirt
    # and render a red ✗; a plain dirty tree renders a yellow *.
    state=$(printf '%s\n' "$gitout" | awk '/^u /{u=1} /^[12] /{d=1} END {print (u ? "u" : "") (d ? "d" : "")}')
    marker=""
    case $state in
      *u*) marker="${red}✗${rst}" ;;
      *d*) marker="${yel}*${rst}" ;;
    esac

    # A git operation in progress (rebase/merge/...) is the loudest non-standard
    # state: flag it in bold red. porcelain v2 doesn't report it, so probe the
    # well-known sentinel paths under the git dir.
    op=""
    gitdir=$(git -C "$current_dir" rev-parse --absolute-git-dir 2>/dev/null)
    if [ -n "$gitdir" ]; then
      if [ -d "$gitdir/rebase-merge" ] || [ -d "$gitdir/rebase-apply" ]; then op="rebase"
      elif [ -f "$gitdir/MERGE_HEAD" ]; then op="merge"
      elif [ -f "$gitdir/CHERRY_PICK_HEAD" ]; then op="cherry-pick"
      elif [ -f "$gitdir/REVERT_HEAD" ]; then op="revert"
      elif [ -f "$gitdir/BISECT_LOG" ]; then op="bisect"
      fi
    fi

    # Ahead/behind from `# branch.ab +A -B` (only present when an upstream
    # exists): unpushed commits green, unpulled commits yellow.
    arrows=""
    ab=$(printf '%s\n' "$gitout" | awk '/^# branch.ab / {print $3" "$4; exit}')
    if [ -n "$ab" ]; then
      ahead=${ab%% *}; ahead=${ahead#+}
      behind=${ab##* }; behind=${behind#-}
      [ "${ahead:-0}" -gt 0 ] 2>/dev/null && arrows="${arrows}${grn}⇡${ahead}${rst}"
      [ "${behind:-0}" -gt 0 ] 2>/dev/null && arrows="${arrows}${yel}⇣${behind}${rst}"
    fi

    git_part="${branch_color}${branch}${rst}${marker}"
    [ -n "$op" ] && git_part="${git_part} ${bold}${red}${op}${rst}"
    [ -n "$arrows" ] && git_part="${git_part} ${arrows}"
    git_info="$git_part"
  fi
  [ -n "$cache_file" ] && printf '%s' "$git_info" >"$cache_file" 2>/dev/null
fi

# date(1) reads an epoch with -r on BSD/macOS but with -d @ on GNU coreutils
# (where -r means "reference file's mtime"). Pick the right reader once so the
# reset times work on both the mac and the Linux fleet.
if date -r 0 +%s >/dev/null 2>&1; then
  _epoch_date() { date -r "$1" "$2" 2>/dev/null; }
else
  _epoch_date() { date -d "@$1" "$2" 2>/dev/null; }
fi

# --- rate limit section ---
# "5h:NN% 7d:NN%" in remaining framing (jq already emitted 100 − used, rounded).
# resets_at is Unix epoch seconds (per the statusline schema).
# Color per field: >50% remaining = dim, 20-50% = yellow, <20% = red.
_rl_color() {
  pct=$1
  if [ "$pct" -lt 20 ] 2>/dev/null; then printf '%s' "$red"
  elif [ "$pct" -lt 50 ] 2>/dev/null; then printf '%s' "$yel"
  else printf '%s' "$dim"; fi
}
rate_info=""
if [ -n "$rem_5h" ]; then
  reset_5h=""
  if [ -n "$rl_5h_reset" ]; then
    t=$(_epoch_date "$rl_5h_reset" '+%H:%M')
    [ -n "$t" ] && reset_5h="↻${t}"
  fi
  rate_info="${rate_info}$(_rl_color "$rem_5h")5h:${rem_5h}%${reset_5h}${rst}"
fi
if [ -n "$rem_7d" ]; then
  reset_7d=""
  if [ -n "$rl_7d_reset" ]; then
    # 7d window can land days out: one date call yields "YYYYMMDD|Day HH:MM",
    # then drop the weekday prefix when it resets today.
    parts=$(_epoch_date "$rl_7d_reset" '+%Y%m%d|%a %H:%M')
    if [ -n "$parts" ]; then
      day=${parts%%|*}
      disp=${parts#*|}
      [ "$day" = "$(date '+%Y%m%d')" ] && disp=${disp#* }
      reset_7d="↻${disp}"
    fi
  fi
  [ -n "$rate_info" ] && rate_info="${rate_info} "
  rate_info="${rate_info}$(_rl_color "$rem_7d")7d:${rem_7d}%${reset_7d}${rst}"
fi

# --- assemble: dir  git  [worktree]  model[ effort]  [agent]  [session]  [style]  ctx  usage ---
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
wt_label=$(_trunc "$wt_label" 24)
[ -n "$wt_label" ] && line="${line}  ${mag}⎇ ${wt_label}${rst}"

if [ -n "$model_name" ]; then
  line="${line}  ${cyan}${model_name}${rst}"
  # Effort tier sits tight to the model; higher tiers escalate in color since
  # they are the non-standard, attention-worthy settings.
  if [ -n "$effort" ]; then
    case $effort in
      high|xhigh) effort_color=$yel ;;
      max|ultra) effort_color=$red ;;
      *) effort_color=$dim ;;
    esac
    line="${line} ${effort_color}${effort}${rst}"
  fi
fi
[ -n "$agent_name" ] && line="${line}  ${mag}@$(_trunc "$agent_name" 24)${rst}"
[ -n "$session_name" ] && line="${line}  ${dim}{$(_trunc "$session_name" 24)}${rst}"
[ -n "$output_style" ] && line="${line}  ${yel}[${output_style}]${rst}"
if [ -n "$remaining" ]; then
  if [ -n "$ctx_warning" ]; then
    line="${line}  ${red}ctx:${remaining}%${rst}"
  else
    line="${line}  ${dim}ctx:${remaining}%${rst}"
  fi
fi
[ -n "$rate_info" ] && line="${line}  ${rate_info}"

printf '%s' "$line"
