#!/usr/bin/env python3
"""Helper for csearch (~/.zsh/claude-search.zsh).

list-all                  Walk ~/.claude/projects/ and emit one tab-separated
                          row per non-subagent transcript, newest first:
                            filepath \t cwd \t display
                          `display` is pre-rendered with ANSI colors and
                          fixed-width columns for fzf.

list-stdin                Same row format, but reads newline-delimited
                          filepaths from stdin (used after `rg -l` upstream).

preview <file> [<query>]  Render the transcript with optional keyword
                          highlight. With a non-empty query, emit ONLY the
                          turns whose text matches the query (with highlight).
                          Empty query = full transcript, no highlight.

Schema reference (Claude Code session JSONL):
  type        'user' | 'assistant' | 'summary' | ...
  message     { role, content }; content is str | [block, ...]
  cwd         working directory at session start
  entrypoint  'cli' | 'claude-vscode' | 'sdk-cli' (programmatic; excluded)
  isSidechain bool; pure-True sessions are subagent traces (excluded)
"""
from __future__ import annotations

import glob
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path


PROJECTS_DIR = Path.home() / ".claude" / "projects"
CACHE_DIR = Path.home() / ".cache" / "claude-search"
# Bump when the cache row format or filter logic changes — older entries
# get ignored automatically.
CACHE_VERSION = 3

MAX_LINES_PER_FILE = 200  # cwd / entrypoint / first_user usually within ~10

# Display column widths. Tweak to taste — fzf will further truncate the
# display column if the terminal is narrow.
CWD_WIDTH = 26
RELTIME_WIDTH = 4
SUMMARY_MAX = 240

# ANSI colors. Kept short — fzf renders them via --ansi.
DIM = "\x1b[2m"
RED = "\x1b[31m"
BOLD = "\x1b[1m"
CYAN = "\x1b[36m"
YELL = "\x1b[33m"
BLUE = "\x1b[34m"
RST = "\x1b[0m"


def render_content(content) -> str:
    """Flatten message.content (str or list-of-blocks) to plain text."""
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return str(content)
    parts: list[str] = []
    for block in content:
        if not isinstance(block, dict):
            parts.append(str(block))
            continue
        t = block.get("type")
        if t == "text":
            parts.append(block.get("text", ""))
        elif t == "tool_use":
            parts.append(f"[tool_use: {block.get('name', '?')}]")
        elif t == "tool_result":
            parts.append(f"[tool_result] {render_content(block.get('content', ''))}")
        elif t == "thinking":
            parts.append(f"[thinking] {block.get('thinking', '')}")
        else:
            parts.append(f"[{t or '?'}]")
    return "\n".join(parts)


def reltime(mtime: float) -> str:
    diff = max(0, time.time() - mtime)
    if diff < 60:
        return f"{int(diff)}s"
    if diff < 3600:
        return f"{int(diff / 60)}m"
    if diff < 86400:
        return f"{int(diff / 3600)}h"
    return f"{int(diff / 86400)}d"


def collapse_home(path: str) -> str:
    home = str(Path.home())
    return "~" + path[len(home):] if path.startswith(home) else path


def truncate_left(s: str, width: int) -> str:
    """`/very/long/path` -> `…ong/path` so the distinctive tail stays."""
    if len(s) <= width:
        return s.ljust(width)
    return "…" + s[-(width - 1):]


_WS = re.compile(r"\s+")
_CMD_NAME = re.compile(r"<command-name>([^<]*)</command-name>")
_CMD_ARGS = re.compile(r"<command-args>([^<]*)</command-args>")
_WRAPPER_PREFIXES = (
    "<ide_opened_file>",
    "<local-command-caveat>",
    "<system-reminder>",
    "[tool_result]",
)


def normalize_first_user(text: str) -> str | None:
    """Strip Claude Code wrapper markup from a candidate first-user prompt.

    Returns the cleaned text, or None if this turn is purely wrapper noise
    (caller should try the next user message)."""
    text = text.strip()
    if not text:
        return None
    # Slash-command invocation: `<command-name>`, `<command-message>`, and
    # `<command-args>` appear in any order. Extract name+args regardless.
    name_m = _CMD_NAME.search(text)
    if name_m:
        name = name_m.group(1).strip().lstrip("/")
        args_m = _CMD_ARGS.search(text)
        args = (args_m.group(1).strip() if args_m else "")
        return f"/{name} {args}".strip() if name else None
    if text.startswith(_WRAPPER_PREFIXES):
        return None
    return text


def _scan_file(path: Path, mtime: float) -> tuple[str, str] | None:
    """Return (cwd, summary) for the transcript, or None to exclude.

    `summary` is the first real user prompt (wrappers stripped). Reads up
    to MAX_LINES_PER_FILE records — enough to capture metadata and a
    couple of user turns even when the session opens with wrapper noise.
    """
    cwd = ""
    summary = ""
    entrypoint = ""
    sidechain_states: set[bool] = set()

    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            for i, line in enumerate(fh):
                if i >= MAX_LINES_PER_FILE:
                    break
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if not cwd and isinstance(rec.get("cwd"), str):
                    cwd = rec["cwd"]
                if not entrypoint and isinstance(rec.get("entrypoint"), str):
                    entrypoint = rec["entrypoint"]
                if isinstance(rec.get("isSidechain"), bool):
                    sidechain_states.add(rec["isSidechain"])
                if not summary and rec.get("type") == "user":
                    msg = rec.get("message")
                    if isinstance(msg, dict):
                        text = render_content(msg.get("content", ""))
                        text = _WS.sub(" ", text)
                        cleaned = normalize_first_user(text)
                        if cleaned:
                            summary = cleaned
                if cwd and entrypoint and summary:
                    break
    except OSError:
        return None

    if entrypoint == "sdk-cli":
        return None
    if sidechain_states == {True}:
        return None
    if cwd.startswith(("/private/tmp", "/tmp", "/private/var/folders", "/var/folders")):
        return None
    if not cwd or not summary:
        # Likely a synthetic / aborted session — skip rather than show noise.
        return None

    return (cwd, summary[:SUMMARY_MAX])


def _format_row(path: Path, mtime: float, cwd: str, summary: str) -> str:
    rt = reltime(mtime).rjust(RELTIME_WIDTH)
    cwd_disp = collapse_home(cwd)
    cwd_disp = truncate_left(cwd_disp, CWD_WIDTH)
    summary_one_line = summary.replace("\t", " ").replace("\n", " ")
    display = (
        f"{DIM}{rt}{RST}  {CYAN}{cwd_disp}{RST}  {summary_one_line}"
    )
    # Internal columns first (filepath, cwd), then the display column.
    return f"{path}\t{cwd}\t{display}"


def _cache_path_for(jsonl_path: str) -> Path:
    h = hashlib.sha1(jsonl_path.encode("utf-8")).hexdigest()
    return CACHE_DIR / f"v{CACHE_VERSION}_{h}.row"


def _emit_rows(paths: list[str]) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    files_with_mt = []
    for p in paths:
        try:
            files_with_mt.append((os.path.getmtime(p), p))
        except OSError:
            continue
    files_with_mt.sort(reverse=True)

    for mtime, p in files_with_mt:
        cache_file = _cache_path_for(p)
        cached: str | None = None
        try:
            if cache_file.stat().st_mtime >= mtime:
                cached = cache_file.read_text(encoding="utf-8") or None
                if cached == "__EXCLUDED__":
                    continue
        except OSError:
            pass

        if cached is None:
            scan = _scan_file(Path(p), mtime)
            if scan is None:
                try:
                    cache_file.write_text("__EXCLUDED__", encoding="utf-8")
                    os.utime(cache_file, (mtime, mtime))
                except OSError:
                    pass
                continue
            cwd, summary = scan
            # Cache the raw (cwd, summary); regenerate the row at print
            # time so reltime stays fresh on subsequent runs.
            try:
                cache_file.write_text(
                    f"{cwd}\t{summary}", encoding="utf-8"
                )
                os.utime(cache_file, (mtime, mtime))
            except OSError:
                pass
            row = _format_row(Path(p), mtime, cwd, summary)
        else:
            parts = cached.split("\t", 1)
            if len(parts) != 2:
                continue  # malformed cache entry, ignore
            cwd, summary = parts
            row = _format_row(Path(p), mtime, cwd, summary)

        print(row)


def list_all() -> None:
    _emit_rows(glob.glob(str(PROJECTS_DIR / "*" / "*.jsonl")))


def list_stdin() -> None:
    paths = [ln.strip() for ln in sys.stdin if ln.strip()]
    _emit_rows(paths)


def preview(file: str, keyword: str = "") -> None:
    pat = re.compile(re.escape(keyword), re.IGNORECASE) if keyword else None

    def hl(s: str) -> str:
        return pat.sub(lambda m: f"{RED}{BOLD}{m.group(0)}{RST}", s) if pat else s

    try:
        fh = open(file, encoding="utf-8", errors="replace")
    except OSError as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(1)

    emitted = 0
    with fh:
        for line in fh:
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            t = rec.get("type")
            if t not in ("user", "assistant"):
                continue
            msg = rec.get("message")
            content = msg.get("content", "") if isinstance(msg, dict) else ""
            text = render_content(content).strip()
            if not text:
                continue
            if pat and not pat.search(text):
                continue
            role = f"{CYAN}user{RST}" if t == "user" else f"{YELL}claude{RST}"
            ts = rec.get("timestamp", "")[:19]
            print(f"{DIM}── {ts}{RST}  {role}")
            for ln in text.split("\n"):
                print(hl(ln))
            print()
            emitted += 1

    if pat and emitted == 0:
        print(f"{DIM}(no turns match {keyword!r}){RST}")


def main() -> int:
    args = sys.argv[1:]
    if not args:
        print(__doc__, file=sys.stderr)
        return 1
    cmd, rest = args[0], args[1:]
    if cmd == "list-all":
        list_all()
        return 0
    if cmd == "list-stdin":
        list_stdin()
        return 0
    if cmd == "preview":
        if not rest:
            print("preview: expected <file> [<query>]", file=sys.stderr)
            return 1
        preview(rest[0], rest[1] if len(rest) > 1 else "")
        return 0
    print(f"unknown command: {cmd}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except BrokenPipeError:
        try:
            sys.stdout.close()
        except OSError:
            pass
        sys.exit(0)
