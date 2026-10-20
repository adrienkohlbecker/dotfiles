#!/usr/bin/env bash
# Claude Code PostToolUse hook for Bash: the agent shell's `grep` is a function
# running ugrep with --ignore-files, so a recursive grep silently skips
# gitignored trees (private notes clones, vendored config). When a recursive
# grep runs in a repo with such trees, name them next to the result.
set -euo pipefail

input=$(cat)
cmd=$(jq -r '.tool_input.command // empty' <<<"$input")
cwd=$(jq -r '.cwd // empty' <<<"$input")

# `command grep` is the real grep and already searches ignored trees.
cmd=${cmd//command grep/}
recursive='(^|[^[:alnum:]_.-])grep[^|;&]*[[:space:]](-[[:alpha:]]*[rR][[:alpha:]]*|--recursive|--dereference-recursive)([[:space:]]|$)'
[[ $cmd =~ $recursive ]] || exit 0
[[ $cmd != *--no-ignore-files* ]] || exit 0
[ -d "$cwd" ] || exit 0

# Top-level ignored directories, skipping hidden ones and caches that nobody
# searches on purpose. Sorted output lists a parent before its children.
skipped=$(git -C "$cwd" ls-files --others --ignored --exclude-standard --directory --no-empty-directory 2>/dev/null |
  awk '/^\./ || /(^|\/)(__pycache__|node_modules|\.[^\/]*)\/?$/ {next}
    /\/$/ || system("test -d \"" $0 "\"") == 0 {
      for (i = 1; i <= n; i++) if (index($0, kept[i]) == 1) next
      kept[++n] = $0; sub(/\/$/, ""); print
    }' |
  head -n 8 | paste -sd, - | sed 's/,/, /g') || exit 0
[ -n "$skipped" ] || exit 0

msg="Note: grep here is ugrep with --ignore-files, so this recursive search skipped gitignored paths under $cwd: $skipped. If the answer could live there, rerun with \`command grep -r\` or pass the directory explicitly."
jq -n --arg ctx "$msg" '{hookSpecificOutput: {hookEventName: "PostToolUse", additionalContext: $ctx}}'
