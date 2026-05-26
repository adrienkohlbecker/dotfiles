#!/usr/bin/env python3
"""Helper for csearch (~/.zsh/claude-search.zsh).

list-all                  Walk ~/.claude/projects/ and emit one tab-separated
                          row per non-subagent transcript, newest first:
                            filepath \t cwd \t display
                          `display` is pre-rendered with ANSI colors and
                          fixed-width columns for fzf.

search <query>            Same row format, but only transcripts containing
                          every whitespace-separated term in <query> somewhere
                          (file-level AND via chained `rg -F` scans).

preview <file> [<query>]  Render the transcript with optional term highlight.
                          With a non-empty query, emit ONLY the turns whose
                          text contains any term (each highlighted). Empty query
                          = full transcript, no highlight.

Schema reference (Claude Code session JSONL):
  type        'user' | 'assistant' | 'summary' | ...
  message     { role, content }; content is str | [block, ...]
  cwd         working directory at session start
  entrypoint  'cli' | 'claude-vscode' | 'sdk-cli' (programmatic; excluded)
  isSidechain bool; pure-True sessions are subagent traces (excluded)
"""
from __future__ import annotations

import glob
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path


PROJECTS_DIR = Path.home() / ".claude" / "projects"

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
# Strip C0+C1 control bytes (keep \t and \n) so transcript-derived text can't
# inject terminal escapes into the fzf list/preview. The C1 range (0x80-0x9f)
# covers the 8-bit CSI introducer 0x9b a terminal in 8-bit mode would act on.
_CTRL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]")
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
    # cwd is transcript-controlled: strip control bytes and collapse tab/newline
    # before it reaches column 2 (a newline would split the row) or the colored
    # display (a raw escape would render under fzf --ansi). path comes from the
    # filesystem, so it needs no scrub.
    cwd = _CTRL.sub("", cwd.replace("\t", " ").replace("\n", " "))
    cwd_disp = truncate_left(collapse_home(cwd), CWD_WIDTH)
    summary_one_line = _CTRL.sub("", summary.replace("\t", " ").replace("\n", " "))
    display = (
        f"{DIM}{rt}{RST}  {CYAN}{cwd_disp}{RST}  {summary_one_line}"
    )
    # Internal columns first (filepath, cwd), then the display column.
    return f"{path}\t{cwd}\t{display}"


def _emit_rows(paths: list[str]) -> None:
    files_with_mt = []
    for p in paths:
        try:
            files_with_mt.append((os.path.getmtime(p), p))
        except OSError:
            continue
    files_with_mt.sort(reverse=True)

    for mtime, p in files_with_mt:
        scan = _scan_file(Path(p), mtime)
        if scan is None:
            continue
        cwd, summary = scan
        print(_format_row(Path(p), mtime, cwd, summary))


def list_all() -> None:
    _emit_rows(glob.glob(str(PROJECTS_DIR / "*" / "*.jsonl")))


def _rg_files(args: list[str]) -> list[str] | None:
    """`rg -l --null -i -F <args>` → matching paths, or None on rg failure.

    `--null` separates paths with NUL so a newline in a (transcript-derived)
    path can't split a row. rc 1 with empty output is "no matches" (empty list);
    rc >= 2 with a stderr message is a real failure.
    """
    try:
        proc = subprocess.run(
            ["rg", "-l", "--null", "-i", "-F", *args],
            capture_output=True, text=True, check=False,
        )
    except FileNotFoundError:
        print("csearch: ripgrep (rg) not found on PATH", file=sys.stderr)
        return None
    if proc.returncode >= 2 and proc.stderr.strip():
        print(f"csearch: rg: {proc.stderr.strip()}", file=sys.stderr)
        return None
    return [p for p in proc.stdout.split("\0") if p]


def search(query: str) -> None:
    """Filtered list: transcripts containing ALL whitespace-separated terms.

    File-level AND via chained ripgrep `-F` scans: a transcript matches when
    every term appears somewhere in it (not necessarily the same turn). `-F`
    is memchr-fast even on the multi-kilobyte single lines JSONL records produce
    — a PCRE2 lookahead chain is pathologically slow there. Each pass narrows
    the file set the next term searches.
    """
    terms = query.split()
    if not terms:
        list_all()
        return
    # First term scans the whole projects tree; subsequent terms scan only the
    # surviving file list (a few thousand uuid-named paths, well under ARG_MAX).
    files = _rg_files(["-g", "*.jsonl", "--", terms[0], str(PROJECTS_DIR)])
    if files is None:
        return
    for term in terms[1:]:
        if not files:
            break
        files = _rg_files(["--", term, *files])
        if files is None:
            return
    _emit_rows(files)


def preview(file: str, query: str = "") -> None:
    # search() matches transcripts containing every term *somewhere* (file-level
    # AND), so show every turn matching ANY term, each highlighted — that
    # surfaces each term's context and never renders an empty preview for a
    # transcript the list matched.
    terms = query.split()
    pats = [re.compile(re.escape(t), re.IGNORECASE) for t in terms]

    def hl(s: str) -> str:
        for p in pats:
            s = p.sub(lambda m: f"{RED}{BOLD}{m.group(0)}{RST}", s)
        return s

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
            if pats and not any(p.search(text) for p in pats):
                continue
            role = f"{CYAN}user{RST}" if t == "user" else f"{YELL}claude{RST}"
            ts = rec.get("timestamp", "")[:19]
            print(f"{DIM}── {ts}{RST}  {role}")
            for ln in text.split("\n"):
                print(hl(_CTRL.sub("", ln)))
            print()
            emitted += 1

    if pats and emitted == 0:
        print(f"{DIM}(no turns match {query!r}){RST}")


def main() -> int:
    args = sys.argv[1:]
    if not args:
        print(__doc__, file=sys.stderr)
        return 1
    cmd, rest = args[0], args[1:]
    if cmd == "list-all":
        list_all()
        return 0
    if cmd == "search":
        search(rest[0] if rest else "")
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
