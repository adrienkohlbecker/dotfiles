#!/usr/bin/env python3
"""Helper for csearch (~/.zsh/claude-search.zsh).

refresh                   Bring the index up to date: reparse only transcripts
                          whose mtime or size changed, drop those that are gone.

list-all                  One tab-separated row per session, newest first:
                            agent \t session_id \t filepath \t resume_dir \t display
                          `display` is pre-rendered with ANSI colors for fzf.
                          `resume_dir` is empty when no known directory survives.

search <query>            Same row format, ranked by relevance over the
                          conversation PROSE (user/assistant message text only,
                          NOT tool output, thinking, or injected context — those
                          make common words match everything). Rows order by
                          (distinct terms matched, terms in title, prose hits,
                          most recently active).
                          Terms are case-insensitive substrings; any term matches.

preview <file> [<query>]  Render a transcript's prose straight from the file. A
                          non-empty query keeps only turns containing any term,
                          each highlighted.

The index is a rebuildable SQLite cache (~/.cache/csearch/index.sqlite3). A full
scan reads gigabytes of tool output to find megabytes of prose, too slow to rerun
on each keystroke; the cached prose answers a query in a fraction of a second.

Recency comes from the last turn's timestamp, not the file's mtime: Claude Code
appends metadata to old transcripts and rewrites them in bulk, so most mtimes are
far newer than the conversation. mtime only decides what needs reparsing.

Claude Code schema (~/.claude/projects/<slug>/<session_id>.jsonl):
  type          'user' | 'assistant' | 'attachment' | 'custom-title' | ...
  message       { role, content }; content is str | [block, ...]
  customTitle   on 'custom-title': name the operator gave the session
  agentName     on 'agent-name': session name when no custom-title was written
  aiTitle       on 'ai-title': model-generated title, rewritten as it grows
  attachment    { type: 'queued_command', commandMode: 'prompt', prompt } is a
                prompt typed mid-turn; it has no matching 'user' record
  relocatedCwd  on 'relocated': directory the session now belongs to
  worktreeSession  on 'worktree-state': { originalCwd, worktreePath, ... }
  isMeta, isCompactSummary  user records holding injected text, not prose

Codex schema (~/.codex/{sessions,archived_sessions}/**/rollout-*.jsonl):
  session_meta  payload { id, cwd, originator, source }; source is an object
                on subagent threads. The first one is this thread's, later ones
                come from a parent it was forked from.
  event_msg     payload { type: 'item_completed', item: { type, content } } with
                item.type 'UserMessage' | 'AgentMessage'. response_item messages
                also hold injected AGENTS.md and environment context, so skip them.
  ~/.codex/session_index.jsonl  { id, thread_name }, latest line wins
"""
from __future__ import annotations

import datetime
import glob
import json
import os
import re
import sqlite3
import sys
import time
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

INDEX_VERSION = 1

# Commit interval while indexing, so an interrupted first build keeps its progress.
COMMIT_EVERY = 50
# Below this many stale transcripts a refresh is too quick to be worth announcing.
ANNOUNCE_MIN = 20

# Display column widths. fzf further truncates the display column if narrow.
PROJECT_WIDTH = 26
RELTIME_WIDTH = 4
TITLE_MAX = 240

# ANSI colors. Kept short — fzf renders them via --ansi.
DIM = "\x1b[2m"
RED = "\x1b[31m"
BOLD = "\x1b[1m"
CYAN = "\x1b[36m"
YELL = "\x1b[33m"
RST = "\x1b[0m"

_WS = re.compile(r"\s+")
# Strip C0+C1 control bytes (keep \t and \n) so transcript-derived text can't
# inject terminal escapes into the fzf list/preview. The C1 range (0x80-0x9f)
# covers the 8-bit CSI introducer 0x9b a terminal in 8-bit mode would act on.
_CTRL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]")
_CMD_NAME = re.compile(r"<command-name>([^<]*)</command-name>")
_CMD_ARGS = re.compile(r"<command-args>(.*?)</command-args>", re.DOTALL)
# Context the harness injects into user messages, around or instead of the text
# the operator typed. Pasted content stays: it is something they chose to send.
_INJECTED = re.compile(
    r"<(system-reminder|local-command-caveat|local-command-stdout|local-command-stderr"
    r"|ide_opened_file|ide_selection|task-notification|side-sessions-event"
    r"|ci-monitor-event|environment_context|recommended_plugins|skill|turn_aborted"
    r"|subagent_notification|bash-stdout|bash-stderr)\b[^>]*>.*?</\1>",
    re.DOTALL,
)
_BASH_INPUT = re.compile(r"<bash-input>(.*?)</bash-input>", re.DOTALL)
_NOT_SLUG = re.compile(r"[^A-Za-z0-9]")
_WORKTREE = re.compile(r"/(?:\.claude/worktrees|\.worktrees)/[^/]+")

# Byte prefilters that skip JSON-parsing the bulk of a transcript. Quotes inside
# a JSON string are escaped, so these unescaped key/value spellings can't match
# text in a message: only a record's own structure.
_CLAUDE_RECORDS = tuple(
    b'"type":"%s"' % kind
    for kind in (
        b"user",
        b"assistant",
        b"queued_command",
        b"custom-title",
        b"agent-name",
        b"ai-title",
        b"relocated",
        b"worktree-state",
    )
)
_CLAUDE_TOOL_RESULTS = (b'"toolUseResult":', b'"type":"tool_result"')
_CODEX_RECORDS = (b'"session_meta"', b'"type":"UserMessage"', b'"type":"AgentMessage"')

# First prompts of programmatic `claude -p` runs (review and commit-message
# tooling). Remote Control sessions share their 'sdk-cli' entrypoint but are real
# conversations, so a prompt that doesn't match stays visible.
_AUTOMATION_PROMPTS = ("You are ", "Output ONLY", "A git diff")

_COLUMNS = "agent, session_id, path, active, project, dirs, title"


@dataclass
class Turn:
    role: str  # 'user' | 'assistant'
    text: str
    timestamp: str = ""


@dataclass
class Transcript:
    agent: str  # 'claude' | 'codex'
    session_id: str
    title: str = ""
    project: str = ""
    dirs: list[str] = field(default_factory=list)  # resume candidates, best first
    hidden: bool = False
    turns: list[Turn] = field(default_factory=list)


def fold(text: str) -> str:
    """Normalize for case-insensitive matching, including non-ASCII ('Été')."""
    return unicodedata.normalize("NFC", text).casefold()


def _safe(text: str) -> str:
    """Replace lone surrogates (valid in JSON, not in UTF-8) so SQLite accepts it."""
    return text.encode("utf-8", "replace").decode("utf-8")


def _one_line(text: str) -> str:
    return _CTRL.sub("", _WS.sub(" ", text)).strip()


def _str(mapping: dict, key: str) -> str:
    value = mapping.get(key)
    return _safe(value) if isinstance(value, str) else ""


def _block_text(content) -> str:
    """Text blocks of a message's content (str or list-of-blocks). Tool calls and
    thinking are dropped: they carry incidental keywords, not the topic. Codex
    spells the block type 'Text' on agent messages and 'text' on user ones."""
    if isinstance(content, str):
        return _safe(content)
    if not isinstance(content, list):
        return ""
    return "\n".join(
        _str(block, "text")
        for block in content
        if isinstance(block, dict) and block.get("type") in ("text", "Text")
    )


def clean_user_text(text: str) -> str:
    """Reduce a user message to what the operator typed: a slash-command wrapper
    becomes `/name args`, a shell escape `!cmd`, injected context blocks and
    interrupt markers go. Empty if nothing remains."""
    name = _CMD_NAME.search(text)
    if name:
        args = _CMD_ARGS.search(text)
        return f"/{name.group(1).strip().lstrip('/')} {args.group(1).strip() if args else ''}".strip()
    if text.startswith("[Request interrupted"):
        return ""
    return _BASH_INPUT.sub(r"!\1", _INJECTED.sub("", text)).strip()


def last_active(turns: list[Turn], fallback: float) -> float:
    """Epoch seconds of the newest parseable turn timestamp, else `fallback`."""
    stamps = []
    for turn in turns:
        try:
            # fromisoformat only accepts a trailing 'Z' from Python 3.11 on.
            stamps.append(datetime.datetime.fromisoformat(turn.timestamp.replace("Z", "+00:00")))
        except ValueError:
            continue  # absent or malformed: the other turns still date the session
    # A naive stamp would compare unequal to aware ones and is not what either
    # agent writes, so only timezone-aware stamps count.
    aware = [stamp.timestamp() for stamp in stamps if stamp.tzinfo]
    return max(aware, default=fallback)


def _strip_worktree(path: str) -> str:
    """`~/repo/.worktrees/foo/sub` -> `~/repo/sub`: the checkout it was cut from."""
    return _WORKTREE.sub("", path, count=1)


def _unique(items: list[str]) -> list[str]:
    return list(dict.fromkeys(item for item in items if item))


def _records(path: str, wanted: tuple[bytes, ...], skipped: tuple[bytes, ...] = ()):
    with open(path, "rb") as fh:
        for line in fh:
            if not any(m in line for m in wanted) or any(m in line for m in skipped):
                continue
            try:
                rec = json.loads(line)
            except ValueError:
                # The live session's last line may still be half written.
                continue
            if isinstance(rec, dict):
                yield rec


def parse_claude(path: str) -> Transcript:
    """Parse a Claude Code transcript. Raises OSError if it can't be read."""
    transcript = Transcript("claude", Path(path).stem)
    slug = Path(path).parent.name
    titles = {"custom-title": "", "agent-name": "", "ai-title": ""}
    title_fields = {"custom-title": "customTitle", "agent-name": "agentName", "ai-title": "aiTitle"}
    cwds: list[str] = []
    relocated = original = entrypoint = prompt = command = ""
    main_thread = sidechain = False

    for rec in _records(path, _CLAUDE_RECORDS, _CLAUDE_TOOL_RESULTS):
        kind = rec.get("type")
        if kind in titles:
            titles[kind] = _str(rec, title_fields[kind]).strip() or titles[kind]
            continue
        if kind == "relocated":
            relocated = _str(rec, "relocatedCwd") or relocated
            continue
        if kind == "worktree-state":
            worktree = rec.get("worktreeSession")
            if isinstance(worktree, dict):
                original = _str(worktree, "originalCwd") or original
            continue

        cwd = _str(rec, "cwd")
        if cwd and cwd not in cwds:
            cwds.append(cwd)
        entrypoint = entrypoint or _str(rec, "entrypoint")
        if rec.get("isSidechain") is True:
            sidechain = True
            continue
        if isinstance(rec.get("isSidechain"), bool):
            main_thread = True
        if rec.get("isMeta") or rec.get("isCompactSummary"):
            continue

        text = ""
        role = "user"
        if kind == "user":
            message = rec.get("message")
            content = message.get("content") if isinstance(message, dict) else None
            text = clean_user_text(_block_text(content))
        elif kind == "assistant":
            message = rec.get("message")
            content = message.get("content") if isinstance(message, dict) else None
            text = _block_text(content).strip()
            role = "assistant"
        elif kind == "attachment":
            attachment = rec.get("attachment")
            if isinstance(attachment, dict) and attachment.get("commandMode") == "prompt":
                text = clean_user_text(_block_text(attachment.get("prompt")))
        if not text:
            continue
        if role == "user":
            if text.startswith(("/", "!")):
                command = command or text
            else:
                prompt = prompt or text
        transcript.turns.append(Turn(role, text, _str(rec, "timestamp")))

    # The transcript's directory is named after the launch directory, which is
    # not always the first cwd recorded: a session can enter a worktree first.
    launch = next((c for c in cwds if _NOT_SLUG.sub("-", c) == slug), cwds[0] if cwds else "")
    transcript.dirs = _unique(
        [relocated, launch, cwds[-1] if cwds else "", original, _strip_worktree(launch)]
    )
    transcript.project = _strip_worktree(original or launch)
    first_prompt = prompt or command
    transcript.title = _one_line(
        titles["custom-title"] or titles["agent-name"] or titles["ai-title"] or first_prompt
    )[:TITLE_MAX]
    transcript.hidden = (
        not launch
        or not transcript.title
        or (sidechain and not main_thread)
        or (entrypoint == "sdk-cli" and first_prompt.startswith(_AUTOMATION_PROMPTS))
    )
    return transcript


def parse_codex(path: str, titles: dict[str, str]) -> Transcript:
    """Parse a Codex rollout. Raises OSError if it can't be read."""
    transcript = Transcript("codex", "")
    cwd = ""
    prompt = ""
    interactive = False

    for rec in _records(path, _CODEX_RECORDS):
        payload = rec.get("payload")
        if not isinstance(payload, dict):
            continue
        if rec.get("type") == "session_meta":
            if not transcript.session_id:
                transcript.session_id = _str(payload, "id")
                cwd = _str(payload, "cwd")
                source = payload.get("source")
                interactive = (
                    isinstance(source, str)
                    and source != "exec"
                    and payload.get("originator") != "codex_exec"
                )
            continue
        if rec.get("type") != "event_msg" or payload.get("type") != "item_completed":
            continue
        item = payload.get("item")
        if not isinstance(item, dict):
            continue
        if item.get("type") == "UserMessage":
            text = clean_user_text(_block_text(item.get("content")))
            role = "user"
            prompt = prompt or text
        elif item.get("type") == "AgentMessage":
            text = _block_text(item.get("content")).strip()
            role = "assistant"
        else:
            continue
        if text:
            transcript.turns.append(Turn(role, text, _str(rec, "timestamp")))

    transcript.dirs = _unique([cwd, _strip_worktree(cwd)])
    transcript.project = _strip_worktree(cwd)
    transcript.title = _one_line(titles.get(transcript.session_id) or prompt)[:TITLE_MAX]
    transcript.hidden = not (interactive and cwd and transcript.session_id and transcript.title)
    return transcript


def codex_titles() -> dict[str, str]:
    """Codex's own thread names, kept outside the rollouts: renaming a thread
    doesn't touch its rollout, so these are applied at query time, not indexed."""
    titles: dict[str, str] = {}
    try:
        fh = open(Path.home() / ".codex" / "session_index.jsonl", encoding="utf-8", errors="replace")
    except OSError:
        return titles
    with fh:
        for line in fh:
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if isinstance(rec, dict) and isinstance(rec.get("id"), str):
                titles[rec["id"]] = _str(rec, "thread_name") or titles.get(rec["id"], "")
    return titles


def _transcript_paths() -> dict[str, str]:
    """Every top-level transcript, as {path: agent}. Claude subagent traces live
    one level deeper (<session>/subagents/) and stay out of this glob."""
    home = Path.home()
    paths = {p: "claude" for p in glob.glob(str(home / ".claude" / "projects" / "*" / "*.jsonl"))}
    for store in ("sessions", "archived_sessions"):
        pattern = str(home / ".codex" / store / "**" / "rollout-*.jsonl")
        paths.update((p, "codex") for p in glob.glob(pattern, recursive=True))
    return paths


def _parse(path: str, agent: str, titles: dict[str, str]) -> Transcript:
    return parse_codex(path, titles) if agent == "codex" else parse_claude(path)


def open_index() -> sqlite3.Connection:
    cache = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "csearch"
    cache.mkdir(parents=True, exist_ok=True)
    path = cache / "index.sqlite3"
    try:
        return _connect(path)
    except sqlite3.DatabaseError:
        # A corrupt file holds nothing that can't be rebuilt from the transcripts.
        path.unlink()
        return _connect(path)


def _connect(path: Path) -> sqlite3.Connection:
    db = sqlite3.connect(path, timeout=30)
    if db.execute("PRAGMA user_version").fetchone()[0] != INDEX_VERSION:
        db.executescript(
            f"""
            DROP TABLE IF EXISTS sessions;
            CREATE TABLE sessions (
                path TEXT PRIMARY KEY,
                mtime_ns INTEGER NOT NULL,
                size INTEGER NOT NULL,
                active REAL NOT NULL,
                agent TEXT NOT NULL,
                session_id TEXT NOT NULL,
                project TEXT NOT NULL,
                dirs TEXT NOT NULL,
                title TEXT NOT NULL,
                hidden INTEGER NOT NULL,
                prose TEXT NOT NULL
            );
            PRAGMA user_version = {INDEX_VERSION};
            """
        )
    # WAL lets a picker in another terminal keep reading during a refresh.
    db.execute("PRAGMA journal_mode = WAL")
    return db


def refresh(db: sqlite3.Connection) -> None:
    """Sync the index with the transcripts on disk, parsing only what changed."""
    known = {row[0]: row[1:] for row in db.execute("SELECT path, mtime_ns, size FROM sessions")}
    paths = _transcript_paths()
    stale: list[tuple[str, str, int, int]] = []
    for path, agent in paths.items():
        try:
            stat = os.stat(path)
        except OSError:
            continue  # deleted since the glob; the next refresh drops its row
        if known.get(path) != (stat.st_mtime_ns, stat.st_size):
            stale.append((path, agent, stat.st_mtime_ns, stat.st_size))

    db.executemany("DELETE FROM sessions WHERE path = ?", [(p,) for p in known if p not in paths])
    if len(stale) >= ANNOUNCE_MIN:
        print(f"csearch: indexing {len(stale)} transcripts…", file=sys.stderr)
    titles = codex_titles()
    for count, (path, agent, mtime_ns, size) in enumerate(stale, 1):
        try:
            transcript = _parse(path, agent, titles)
        except OSError:
            continue  # deleted or unreadable mid-refresh; retried on the next one
        hidden = transcript.hidden
        prose = "" if hidden else fold("\n".join(turn.text for turn in transcript.turns))
        db.execute(
            "INSERT OR REPLACE INTO sessions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                path,
                mtime_ns,
                size,
                last_active(transcript.turns, mtime_ns / 1e9),
                agent,
                transcript.session_id,
                transcript.project,
                json.dumps(transcript.dirs),
                transcript.title,
                int(hidden),
                prose,
            ),
        )
        if count % COMMIT_EVERY == 0:
            db.commit()
    db.commit()


def reltime(then: float, now: float) -> str:
    diff = max(0, now - then)
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


def truncate_left(text: str, width: int) -> str:
    """`/very/long/path` -> `…ong/path` so the distinctive tail stays."""
    if len(text) <= width:
        return text.ljust(width)
    return "…" + text[-(width - 1):]


def _title(row, titles: dict[str, str]) -> str:
    agent, session_id, _, _, _, _, title = row
    named = titles.get(session_id) if agent == "codex" else None
    return _one_line(named)[:TITLE_MAX] if named else title


def _resume_dir(dirs: list[str]) -> str:
    return next((d for d in dirs if os.path.isdir(d)), "")


def format_row(row, titles: dict[str, str], now: float) -> str:
    agent, session_id, path, active, project, dirs, _ = row
    age = reltime(active, now).rjust(RELTIME_WIDTH)
    badge = f"{YELL}cx{RST}" if agent == "codex" else f"{DIM}cc{RST}"
    place = truncate_left(collapse_home(_one_line(project)), PROJECT_WIDTH)
    # Everything but path (from the filesystem) is transcript-controlled: a tab or
    # newline would split the row, a raw escape would render under fzf --ansi.
    display = f"{DIM}{age}{RST} {badge} {CYAN}{place}{RST}  {_title(row, titles)}"
    resume_dir = _one_line(_resume_dir(json.loads(dirs)))
    return "\t".join((agent, _one_line(session_id), path, resume_dir, display))


def list_all(db: sqlite3.Connection, now: float) -> None:
    titles = codex_titles()
    for row in db.execute(f"SELECT {_COLUMNS} FROM sessions WHERE hidden = 0 ORDER BY active DESC"):
        print(format_row(row, titles, now))


def search(db: sqlite3.Connection, query: str, now: float) -> None:
    """Rank visible sessions by (distinct terms matched, terms in the title, prose
    hits, last activity): matching every term beats matching fewer, a session named after
    the terms beats one that mentions them, then more mentions, then the newest."""
    terms = [fold(term) for term in query.split()]
    if not terms:
        list_all(db, now)
        return
    titles = codex_titles()
    ranked = []
    for *row, prose in db.execute(f"SELECT {_COLUMNS}, prose FROM sessions WHERE hidden = 0"):
        title = fold(_title(row, titles))
        title_hits = [term in title for term in terms]
        prose_hits = [prose.count(term) for term in terms]
        distinct = sum(1 for t, p in zip(title_hits, prose_hits) if t or p)
        if distinct:
            ranked.append((distinct, sum(title_hits), sum(prose_hits), row[3], row))
    ranked.sort(key=lambda entry: entry[:4], reverse=True)
    for *_, row in ranked:
        print(format_row(row, titles, now))


def preview(path: str, query: str = "") -> None:
    agent = "codex" if Path(path).name.startswith("rollout-") else "claude"
    titles = codex_titles()
    transcript = _parse(path, agent, titles)
    terms = query.split()
    folded = [fold(term) for term in terms]
    # One alternation, longest first: substituting term by term would let a later
    # term match inside the escape codes the earlier ones inserted.
    pattern = (
        re.compile(
            "|".join(re.escape(t) for t in sorted(terms, key=len, reverse=True)), re.IGNORECASE
        )
        if terms
        else None
    )

    print(f"{BOLD}{transcript.title}{RST}")
    place = _resume_dir(transcript.dirs) or "(no directory left)"
    print(f"{DIM}{agent} {_one_line(transcript.session_id)} · {_one_line(collapse_home(place))}{RST}")
    print()

    emitted = 0
    for turn in transcript.turns:
        if folded:
            text = fold(turn.text)
            if not any(term in text for term in folded):
                continue
        role = f"{CYAN}user{RST}" if turn.role == "user" else f"{YELL}{agent}{RST}"
        print(f"{DIM}── {turn.timestamp[:19]}{RST}  {role}")
        for line in turn.text.split("\n"):
            line = _CTRL.sub("", line)
            print(pattern.sub(lambda m: f"{RED}{BOLD}{m.group(0)}{RST}", line) if pattern else line)
        print()
        emitted += 1
    if folded and emitted == 0:
        print(f"{DIM}(no turns match {query!r}; it may only be in the title){RST}")


def main() -> int:
    args = sys.argv[1:]
    if not args:
        print(__doc__, file=sys.stderr)
        return 1
    # A non-UTF-8 locale or a lone surrogate in a query must not abort the listing.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    cmd, rest = args[0], args[1:]
    if cmd == "refresh":
        refresh(open_index())
        return 0
    if cmd == "list-all":
        list_all(open_index(), time.time())
        return 0
    if cmd == "search":
        search(open_index(), rest[0] if rest else "", time.time())
        return 0
    if cmd == "preview":
        if not rest:
            print("preview: expected <file> [<query>]", file=sys.stderr)
            return 1
        try:
            preview(rest[0], rest[1] if len(rest) > 1 else "")
        except OSError as e:
            print(f"error: {e}", file=sys.stderr)
            return 1
        return 0
    print(f"unknown command: {cmd}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except BrokenPipeError:
        # fzf closed the pipe: the query changed or the picker exited.
        try:
            sys.stdout.close()
        except OSError:
            pass
        sys.exit(0)
