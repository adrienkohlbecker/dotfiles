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
  # Strip control chars from strings; pass numbers (e.g. epoch resets_at) through
  # untouched — gsub errors on a non-string, and jq -r stringifies it anyway.
  def clean: if type == "string" then gsub("[[:cntrl:]]"; "") else . end;
  # One copy of the round/coerce rule: ctx is "remaining", the rate windows are
  # "100 − used". A non-number yields "" and is skipped downstream.
  def numpct(x): if (x | type) == "number" then (x | round) else "" end;
  def rempct(x): if (x | type) == "number" then ((100 - x) | round) else "" end;
  (.workspace.current_dir // "" | clean),
  (.model.display_name // "" | clean),
  numpct(.context_window.remaining_percentage),
  (.output_style.name // "" | if . == "default" then "" else . end | clean),
  (if .exceeds_200k_tokens then "1" else "" end),
  (.session_name // "" | clean),
  (.agent.name // "" | clean),
  (.worktree.name // "" | clean),
  (.worktree.branch // "" | clean),
  (.workspace.git_worktree // "" | clean),
  rempct(.rate_limits.five_hour.used_percentage),
  rempct(.rate_limits.seven_day.used_percentage),
  (.rate_limits.five_hour.resets_at // "" | clean),
  (.rate_limits.seven_day.resets_at // "" | clean),
  (.session_id // "" | clean),
  (.effort.level // "" | clean)
')
EOF

# Colors as real ESC bytes (built once) so the final emit can be printf '%s' —
# never '%b'. A field value containing a literal "\033[..." must be printed
# verbatim, not interpreted into control sequences (terminal-injection guard).
esc=$(printf '\033')
dim="${esc}[2m"; red="${esc}[31m"; yel="${esc}[33m"; grn="${esc}[32m"; cyan="${esc}[36m"; mag="${esc}[35m"; bold="${esc}[1m"; rst="${esc}[0m"

# Clamp a label to the line's one-row budget. ${#1} is an upper bound on the
# character count (bytes >= chars), so a label within budget by that measure is
# within it by characters too — the common short-label case forks nothing. When
# it might overflow, awk decides and slices on character boundaries (its length
# and substr share a unit, char-based in a UTF-8 locale), so a multibyte label
# is never cut mid-codepoint the way `cut -c` would under LC_ALL=C.
_trunc() {
  if [ "${#1}" -gt "$2" ]; then
    printf '%s' "$1" | awk -v n="$2" '{ if (length($0) > n) printf "%s…", substr($0, 1, n); else printf "%s", $0 }'
  else
    printf '%s' "$1"
  fi
}

# Per-field truncation budget, scaled to the terminal width Claude Code exports
# in COLUMNS (≈ a quarter of the line per field). Falls back to 24 when COLUMNS
# is absent (older clients — it can't be probed, since our stdout is captured,
# not a tty) or non-numeric. Clamped so a narrow window still shows something
# and a very wide one doesn't let a single field sprawl across the line.
fw=24
if [ -n "${COLUMNS:-}" ] && [ "$COLUMNS" -gt 0 ] 2>/dev/null; then
  fw=$((COLUMNS / 4))
  [ "$fw" -lt 10 ] && fw=10
  [ "$fw" -gt 40 ] && fw=40
fi

dir_name=${current_dir##*/}
[ -z "$dir_name" ] && dir_name=$current_dir   # current_dir is "/" (or empty)
dir_name=$(_trunc "$dir_name" $fw)

# --- git section ---
# Read-only git, hardened against a hostile repo: a planted .git/config could
# point core.fsmonitor/pager at an arbitrary program that would then run on
# every refresh. OPTIONAL_LOCKS=0 also keeps `status` from touching the index,
# so its mtime stays meaningful for the cache-freshness check below.
_git() { GIT_OPTIONAL_LOCKS=0 git -C "$current_dir" -c core.fsmonitor=false -c core.pager=cat "$@"; }

# Epoch mtime of a file, portable across BSD (`stat -f`) and GNU (`stat -c`).
_mtime() { stat -f %m "$1" 2>/dev/null || stat -c %Y "$1" 2>/dev/null; }

git_info=""
branch=""
now=$(date +%s)

# Resolve the repo once (single fork): the work-tree gate AND the git dir. The
# gate guards against bare repos / `.git` dirs, where porcelain v2 still prints
# `# branch.head` and would render a phantom branch for a location with no work
# tree. Outside any repo rev-parse exits non-zero and prints nothing.
inwork=""
gitdir=""
if [ -n "$current_dir" ]; then
  gitmeta=$(_git rev-parse --is-inside-work-tree --absolute-git-dir 2>/dev/null)
  if [ -n "$gitmeta" ]; then
    {
      IFS= read -r inwork
      IFS= read -r gitdir
    } <<EOF_META
$gitmeta
EOF_META
  fi
fi

if [ "$inwork" = "true" ]; then
  # Cache the rendered git segment per (session, dir) in a private 0700 dir —
  # never the shared /tmp root, where a predictable name invites a symlink or a
  # planted file that the cache read would emit to the terminal verbatim. The
  # two key parts are newline-joined (clean strips newlines from both) so the
  # key can't collide across a split like ("ab","cd") vs ("a","bcd").
  cache_file=""
  if [ -n "$session_id" ]; then
    cache_dir="${TMPDIR:-/tmp}/claude-statusline-$(id -u)"
    if mkdir -p "$cache_dir" 2>/dev/null && chmod 700 "$cache_dir" 2>/dev/null; then
      key=$(printf '%s\n%s' "$session_id" "$current_dir" | cksum | cut -d' ' -f1)
      cache_file="${cache_dir}/git-${key}"
    fi
  fi

  # Fresh when the cache is newer than HEAD/index (so a commit or a stage drops
  # it at once) AND under a 5s ceiling — the backstop for state mtime can't see,
  # i.e. a plain unstaged edit to a tracked file. Refuse a symlink: the content
  # reaches the terminal unfiltered.
  cached=""
  if [ -n "$cache_file" ] && [ -f "$cache_file" ] && [ ! -h "$cache_file" ]; then
    cmt=$(_mtime "$cache_file")
    if [ -n "$cmt" ] && [ "$((now - cmt))" -lt 5 ]; then
      newest=$(_mtime "$gitdir/HEAD"); newest=${newest:-0}
      imt=$(_mtime "$gitdir/index")
      [ "${imt:-0}" -gt "$newest" ] 2>/dev/null && newest=$imt
      if [ "$cmt" -ge "$newest" ] 2>/dev/null; then
        cached=1
        git_info=$(cat "$cache_file")
      fi
    fi
  fi

  if [ -z "$cached" ]; then
    gitout=$(_git status --porcelain=v2 --branch 2>/dev/null)

    # One awk pass over the porcelain buffer for all three derived fields:
    #   branch — `# branch.head <name>` (or literally "(detached)", which v2
    #            can't expand)
    #   ab     — `# branch.ab +A -B`, present only with an upstream
    #   state  — `u` (unmerged) and/or `d` (tracked 1/2 changes); untracked (?)
    #            is intentionally not counted
    gitparse=$(printf '%s\n' "$gitout" | awk '
      /^# branch.head / { head = $3 }
      /^# branch.ab / { ab = $3" "$4 }
      /^u /{ u = 1 } /^[12] /{ d = 1 }
      END { print head; print ab; print (u ? "u" : "") (d ? "d" : "") }
    ')
    {
      IFS= read -r branch
      IFS= read -r ab
      IFS= read -r state
    } <<EOF_PARSE
$gitparse
EOF_PARSE

    # A detached HEAD is a non-standard state, so it renders yellow (vs dim).
    branch_color=$dim
    if [ "$branch" = "(detached)" ]; then
      # One describe: --tags shows an exact tag if HEAD is on one, --always
      # falls back to the abbreviated SHA otherwise.
      b=$(_git describe --tags --always --abbrev=7 HEAD 2>/dev/null)
      branch="($b)"
      branch_color=$yel
    fi
    # Strip control chars before this hostile-repo-derived value reaches the
    # terminal via the verbatim printf '%s' below. git's ref-format rules forbid
    # them in a branch/tag name, but a hand-planted ref/packed-refs can smuggle
    # an ESC past those create-time checks — same guard the session fields get
    # through `clean`.
    branch=$(printf '%s' "$branch" | tr -d '[:cntrl:]')
    branch=$(_trunc "$branch" $fw)

    # Conflicts outrank plain dirt: a red ✗ vs a yellow * for a plain dirty tree.
    marker=""
    case $state in
      *u*) marker="${red}✗${rst}" ;;
      *d*) marker="${yel}*${rst}" ;;
    esac

    # A git operation in progress (rebase/merge/...) is the loudest non-standard
    # state: flag it in bold red. porcelain v2 doesn't report it, so probe the
    # well-known sentinel paths under the git dir; for a rebase, append the
    # step/total progress (the most useful thing to see mid-operation).
    op=""
    if [ -d "$gitdir/rebase-merge" ]; then
      op="rebase"
      n=$(cat "$gitdir/rebase-merge/msgnum" 2>/dev/null)
      t=$(cat "$gitdir/rebase-merge/end" 2>/dev/null)
      [ -n "$n" ] && [ -n "$t" ] && op="rebase ${n}/${t}"
    elif [ -d "$gitdir/rebase-apply" ]; then
      op="rebase"
      n=$(cat "$gitdir/rebase-apply/next" 2>/dev/null)
      t=$(cat "$gitdir/rebase-apply/last" 2>/dev/null)
      [ -n "$n" ] && [ -n "$t" ] && op="rebase ${n}/${t}"
    elif [ -f "$gitdir/MERGE_HEAD" ]; then op="merge"
    elif [ -f "$gitdir/CHERRY_PICK_HEAD" ]; then op="cherry-pick"
    elif [ -f "$gitdir/REVERT_HEAD" ]; then op="revert"
    elif [ -f "$gitdir/BISECT_LOG" ]; then op="bisect"
    fi

    # Ahead/behind from `# branch.ab +A -B`: unpushed green, unpulled yellow.
    arrows=""
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

    # Atomic publish: write a temp then rename, so a concurrent refresh never
    # reads a half-written (colour-truncated) segment.
    if [ -n "$cache_file" ] && [ -n "$git_info" ]; then
      tmp="${cache_file}.$$"
      printf '%s' "$git_info" >"$tmp" 2>/dev/null && mv -f "$tmp" "$cache_file" 2>/dev/null
    fi
  fi
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
    # then drop the weekday prefix when it resets today. LC_TIME=C keeps the
    # weekday stable English ("Thu") on the French fleet, not "jeu."; the
    # %Y%m%d "is it today" compare below is locale-agnostic (digits only).
    parts=$(export LC_TIME=C; _epoch_date "$rl_7d_reset" '+%Y%m%d|%a %H:%M')
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

# --- deduplication helpers ---
# Determine the effective worktree label BEFORE deciding whether to print the
# dir, so we can suppress tokens already shown elsewhere.
#
# Priority: --worktree session fields (name + branch) > workspace.git_worktree.
# The ⎇ label is omitted when every colon-separated token it would display is
# already contained in either dir_name or the plain-text git branch — the
# common case where the worktree name, branch, and directory basename are all
# the same string (e.g. "zbm-recovery" appearing four times).
wt_label=""
if [ -n "$worktree_name" ] || [ -n "$worktree_branch" ]; then
  wt_label="$worktree_name"
  if [ -n "$worktree_branch" ]; then
    if [ -n "$wt_label" ]; then
      wt_label="${wt_label}:${worktree_branch}"
    else
      wt_label="$worktree_branch"
    fi
  fi
elif [ -n "$ws_git_worktree" ]; then
  wt_label="$ws_git_worktree"
fi

# Returns 0 (true) when every colon-separated token in $1 is a substring of
# either $2 or $3.
_all_tokens_seen() {
  _label="$1"; _ref1="$2"; _ref2="$3"
  _rest="$_label"
  while [ -n "$_rest" ]; do
    _tok="${_rest%%:*}"
    # Advance: if no ':' left, both sides equal — clear rest to end the loop.
    if [ "$_rest" = "$_tok" ]; then _rest=""; else _rest="${_rest#*:}"; fi
    [ -z "$_tok" ] && continue
    # Token must appear as a substring in at least one reference string.
    case "$_ref1" in *"$_tok"*) continue ;; esac
    case "$_ref2" in *"$_tok"*) continue ;; esac
    return 1   # found a token not seen in either reference
  done
  return 0
}

# Plain-text branch for duplicate checks (strip ANSI escape sequences).
branch_plain=$(printf '%s' "$branch" | sed 's/'"${esc}"'\[[0-9;]*m//g')

# Suppress ⎇ when all its tokens are already visible in dir_name or branch.
show_wt=1
if [ -n "$wt_label" ] && _all_tokens_seen "$wt_label" "$dir_name" "$branch_plain"; then
  show_wt=0
fi

# Suppress dir_name when it exactly matches the git branch AND we are inside a
# named worktree — the branch already appears via git_info, so the dir adds
# nothing new.
show_dir=1
in_worktree=0
if [ -n "$worktree_name" ] || [ -n "$worktree_branch" ] || [ -n "$ws_git_worktree" ]; then
  in_worktree=1
fi
if [ "$in_worktree" = "1" ] && [ "$dir_name" = "$branch_plain" ]; then
  show_dir=0
fi

# --- assemble: [dir]  git  [⎇ worktree]  model[ effort]  [agent]  [session]  [style]  ctx  usage ---
line=""
if [ "$show_dir" = "1" ]; then
  line="${dim}${dir_name}${rst}"
fi
if [ -n "$git_info" ]; then
  if [ -n "$line" ]; then line="${line}  ${git_info}"; else line="$git_info"; fi
fi

wt_label=$(_trunc "$wt_label" $fw)
if [ -n "$wt_label" ] && [ "$show_wt" = "1" ]; then
  line="${line}  ${mag}⎇ ${wt_label}${rst}"
fi

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
[ -n "$agent_name" ] && line="${line}  ${mag}@$(_trunc "$agent_name" $fw)${rst}"
[ -n "$session_name" ] && line="${line}  ${dim}{$(_trunc "$session_name" $fw)}${rst}"
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
