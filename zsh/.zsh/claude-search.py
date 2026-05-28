#!/usr/bin/env python3
"""Helper for csearch (~/.zsh/claude-search.zsh).

list-all                  Walk ~/.claude/projects/ and emit one tab-separated
                          row per non-subagent transcript, newest first:
                            filepath \t cwd \t display
                          `display` is pre-rendered with ANSI colors and
                          fixed-width columns for fzf.

search <query>            Same row format, ranked by relevance over the
                          conversation PROSE (user/assistant message text only,
                          NOT tool output or pasted files — those make common
                          words match everything). An `rg -F` union scan narrows
                          candidates, then each is scored by per-term occurrence
                          counts in its prose. Rows order by (distinct terms
                          matched desc, total occurrences desc, newest first):
                          multi-term and frequently-discussed matches float up;
                          a term seen only in tool output scores zero and drops.

preview <file> [<query>]  Render the transcript with optional term highlight.
                          With a non-empty query, emit ONLY the turns whose
                          text contains any term (each highlighted). Empty query
                          = full transcript, no highlight.

Schema reference (Claude Code session JSONL):
  type        'user' | 'assistant' | 'ai-title' | ...
  message     { role, content }; content is str | [block, ...]
  aiTitle     on type=='ai-title': model-generated session title, refined as
              the conversation grows (the picker's display title). Preferred
              over the first user prompt, which is often just '/clear'.
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

# cwd / entrypoint / first_user land within ~10 lines; the first ai-title
# record lands by ~line 285 in the wild, so 300 captures a title for every
# session that has one. The scan early-exits once all fields are filled, so
# this cap only bounds the rare title-less session.
MAX_LINES_PER_FILE = 300

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

# Cheap substring prefilter for the scan window: only JSON-parse lines that can
# carry a field _scan_file cares about. The assistant/tool/attachment records
# that make up the bulk of a transcript are skipped without parsing, which is
# what keeps list-all fast over hundreds of multi-thousand-line files.
_SCAN_MARKERS = (
    "ai-title",
    '"cwd"',
    "entrypoint",
    '"type":"user"',
    '"type": "user"',
    "isSidechain",
)

# Lines carrying pasted files / tool output / snapshots / system records rather
# than conversation prose. search() skips these before scoring so a common word
# in command output or a pasted file can't inflate a transcript's relevance.
# Only definitively non-prose carriers are listed: a real user/assistant turn
# never contains these substrings, so skipping the whole line can't drop prose.
# Bytes, because the scoring pass reads files in binary for speed.
_NOISE_MARKERS = (
    b'"tool_result"',
    b"toolUseResult",
    b'"type":"attachment"',
    b'"type": "attachment"',
    b"file-history-snapshot",
    b'"type":"system"',
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
    """Return (cwd, title) for the transcript, or None to exclude.

    `title` is the model-generated ai-title (the picker's own display title),
    falling back to the first real user prompt (wrappers stripped) when the
    session predates that feature or has none yet — without the fallback most
    rows would read '/clear', since that is the first user turn after a resume.

    Reads up to MAX_LINES_PER_FILE records, early-exiting once every field is
    filled; a cheap substring prefilter (_SCAN_MARKERS) skips JSON-parsing the
    assistant/tool/attachment bulk.
    """
    cwd = ""
    ai_title = ""
    summary = ""
    entrypoint = ""
    sidechain_states: set[bool] = set()

    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            for i, line in enumerate(fh):
                if i >= MAX_LINES_PER_FILE:
                    break
                if not any(m in line for m in _SCAN_MARKERS):
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                # ai-title is rewritten as the session grows; keep the latest
                # one within the window.
                if rec.get("type") == "ai-title" and isinstance(rec.get("aiTitle"), str):
                    ai_title = rec["aiTitle"].strip()
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
                if cwd and entrypoint and ai_title and summary:
                    break
    except OSError:
        return None

    if entrypoint == "sdk-cli":
        return None
    if sidechain_states == {True}:
        return None
    if cwd.startswith(("/private/tmp", "/tmp", "/private/var/folders", "/var/folders")):
        return None
    title = ai_title or summary
    if not cwd or not title:
        # Likely a synthetic / aborted session — skip rather than show noise.
        return None

    return (cwd, title[:SUMMARY_MAX])


def _format_row(path: Path, mtime: float, cwd: str, title: str) -> str:
    rt = reltime(mtime).rjust(RELTIME_WIDTH)
    # cwd is transcript-controlled: strip control bytes and collapse tab/newline
    # before it reaches column 2 (a newline would split the row) or the colored
    # display (a raw escape would render under fzf --ansi). path comes from the
    # filesystem, so it needs no scrub.
    cwd = _CTRL.sub("", cwd.replace("\t", " ").replace("\n", " "))
    cwd_disp = truncate_left(collapse_home(cwd), CWD_WIDTH)
    # title is transcript-controlled (ai-title or user prompt) — same scrub.
    title_one_line = _CTRL.sub("", title.replace("\t", " ").replace("\n", " "))
    display = (
        f"{DIM}{rt}{RST}  {CYAN}{cwd_disp}{RST}  {title_one_line}"
    )
    # Internal columns first (filepath, cwd), then the display column.
    return f"{path}\t{cwd}\t{display}"


def _with_mtime(paths) -> list[tuple[float, str]]:
    out: list[tuple[float, str]] = []
    for p in paths:
        try:
            out.append((os.path.getmtime(p), p))
        except OSError:
            continue
    return out


def _emit_rows(ordered: list[tuple[float, str]]) -> None:
    """Emit one row per (mtime, path), preserving the given order (fzf runs
    with --no-sort, so emission order is display order)."""
    for mtime, p in ordered:
        scan = _scan_file(Path(p), mtime)
        if scan is None:
            continue
        cwd, title = scan
        print(_format_row(Path(p), mtime, cwd, title))


def list_all() -> None:
    rows = _with_mtime(glob.glob(str(PROJECTS_DIR / "*" / "*.jsonl")))
    rows.sort(reverse=True)  # newest first
    _emit_rows(rows)


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


def _prose_text(rec) -> str:
    """User/assistant message text only — excludes tool_use/tool_result and
    thinking blocks, which carry incidental keyword noise rather than the
    conversation's topic."""
    if rec.get("type") not in ("user", "assistant"):
        return ""
    msg = rec.get("message")
    if not isinstance(msg, dict):
        return ""
    content = msg.get("content", "")
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    return "\n".join(
        b.get("text", "")
        for b in content
        if isinstance(b, dict) and b.get("type") == "text"
    )


def _prose_term_counts(path: str, terms_lc: list[bytes]) -> list[int]:
    """Per-term case-insensitive occurrence count within the transcript's prose.

    Reads bytes and skips noise-carrier lines (_NOISE_MARKERS) cheaply, then
    JSON-parses only the survivors that contain a term and counts within their
    text blocks. The byte skip + substring prefilter keep this off the hot path
    for the bulk of a transcript (tool output), so a full corpus scan stays a
    couple of seconds even though every candidate file is read end to end.
    """
    counts = [0] * len(terms_lc)
    try:
        with open(path, "rb") as fh:
            for line in fh:
                if any(n in line for n in _NOISE_MARKERS):
                    continue
                low = line.lower()
                if not any(t in low for t in terms_lc):
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                text = _prose_text(rec).lower().encode()
                if not text:
                    continue
                for i, t in enumerate(terms_lc):
                    counts[i] += text.count(t)
    except OSError:
        pass
    return counts


def search(query: str) -> None:
    """Relevance-ranked list scored on conversation PROSE, not full content.

    Why prose-only: ripgrep over raw JSONL matches a term *anywhere* — command
    output, pasted file contents, system records — so common words ('swap',
    'ecc', ...) match nearly every transcript and the ranking collapses to plain
    recency. Scoring only user/assistant message text restores the signal: a
    session genuinely *about* a topic mentions it repeatedly in prose; one that
    merely ran a command whose output contained the word does not.

    Pipeline: an `rg -F` union scan (any term, full content) cheaply narrows the
    candidates — a term absent from the whole file is absent from its prose too,
    so this never drops a real match — restricted to the same top-level
    transcript set list_all() shows. Each candidate is then prose-scored in
    Python and ranked by (distinct terms matched desc, total prose occurrences
    desc, mtime desc): matching every term beats matching fewer, more mentions
    beats fewer, ties break to the most recent.
    """
    terms = query.split()
    if not terms:
        list_all()
        return
    universe = set(glob.glob(str(PROJECTS_DIR / "*" / "*.jsonl")))
    candidates: set[str] = set()
    for term in terms:
        hits = _rg_files(["-g", "*.jsonl", "--", term, str(PROJECTS_DIR)])
        if hits is None:
            return
        candidates.update(hits)
    candidates &= universe
    if not candidates:
        return
    terms_lc = [t.lower().encode() for t in terms]
    ranked: list[tuple[int, int, float, str]] = []
    for path in candidates:
        counts = _prose_term_counts(path, terms_lc)
        distinct = sum(1 for c in counts if c)
        if not distinct:
            continue
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            continue
        ranked.append((distinct, sum(counts), mtime, path))
    ranked.sort(reverse=True)  # distinct desc, total desc, mtime desc
    _emit_rows([(mtime, path) for _, _, mtime, path in ranked])


def preview(file: str, query: str = "") -> None:
    # search() ranks transcripts containing ANY term (scored by term count), so
    # show every turn matching ANY term, each highlighted — that surfaces each
    # present term's context and never renders an empty preview for a transcript
    # the list matched.
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
