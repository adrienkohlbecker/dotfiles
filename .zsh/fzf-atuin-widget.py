#!/usr/bin/env -S uv run --script --quiet
# /// script
# requires-python = ">=3.10"
# dependencies = ["pygments"]
# ///
"""fzf-atuin helper. Invoked from fzf-atuin-widget.zsh.

Modes:
  fzf-atuin-widget.py <session|workspace|host>
      Emit a NUL-free, one-row-per-command, pygments-highlighted list to
      stdout. \\n in source commands is encoded as ↵ so multi-line commands
      stay on one fzf row; the widget decodes back when assigning $BUFFER.

  fzf-atuin-widget.py cycle
      Read $FZF_GHOST, emit the fzf action chain to advance one step in the
      session → workspace → host cycle.

Cache: a sidecar sqlite db at ~/.cache/fzf-atuin/highlights.db with a
       single (uuid PRIMARY KEY, text) table. atuin commands are immutable
       per uuid, so cached entries never go stale. Sidecar (vs adding a
       column to atuin's own history.db) keeps us decoupled from atuin's
       schema — an atuin migration can't silently nuke our cache, and our
       writes can't bloat atuin's working set.

Why uv-script-with-inline-deps instead of plain `python3`: $PATH's python3
depends on which venv is active for the user's cwd at Ctrl-R time, and
most of them don't have pygments. `uv run --script` resolves+caches the
dep set independent of any ambient venv, so the widget works everywhere.
"""
import os
import sqlite3
import subprocess
import sys
import traceback

CACHE_DB = os.path.expanduser("~/.cache/fzf-atuin/highlights.db")
SELF = os.path.abspath(__file__)
# SQLite default SQLITE_MAX_VARIABLE_NUMBER is 999 on older builds, 32k on
# macOS system python's bundled sqlite. Stay safely below either.
SQL_CHUNK = 900


def _list_err(short: str, detail: str = "") -> None:
    """build()-path error: write one red row to fzf, detail to stderr, exit 1.

    The fzf row is the only thing the user sees while focused on the popup;
    detail goes to stderr so it surfaces in the terminal once fzf exits.
    """
    sys.stdout.write(f"\033[31m⚠ {short}\033[0m\n")
    if detail:
        sys.stderr.write(detail.rstrip() + "\n")
    sys.exit(1)


def open_cache() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(CACHE_DB), exist_ok=True)
    db = sqlite3.connect(CACHE_DB)
    db.execute("PRAGMA journal_mode=WAL")
    db.execute(
        "CREATE TABLE IF NOT EXISTS highlights ("
        "uuid TEXT PRIMARY KEY, text TEXT NOT NULL)"
    )
    return db


def cycle() -> None:
    # Anything we write here is parsed by fzf as a transform-action chain; a
    # raw traceback would be silently swallowed (or worse, partially parsed).
    # Wrap the whole body so errors become a visible ghost-text update.
    try:
        ghost = os.environ.get("FZF_GHOST", "")
        if "session" in ghost:
            n = "workspace"
        elif "workspace" in ghost:
            n = "host"
        else:
            n = "session"
        sys.stdout.write(
            f"reload({SELF} {n})+change-ghost(filter: {n}    Ctrl-O: cycle    Ctrl-R: toggle sort)"
        )
    except Exception as e:
        sys.stdout.write(
            f"change-ghost(cycle error: {type(e).__name__}: {str(e)[:60]})"
        )
        sys.stderr.write(traceback.format_exc())
        sys.exit(1)


def build(mode: str) -> None:
    try:
        proc = subprocess.run(
            ["atuin", "search", "--filter-mode", mode, "-r",
             "--author", "$all-user",
             "--format", "{uuid}{command}", "--print0"],
            capture_output=True, check=False,
        )
    except FileNotFoundError:
        _list_err("atuin not on PATH")
        return  # unreachable; satisfies static analysers
    # atuin returns exit 1 with empty stderr when a filter has zero matches
    # (empty session, workspace with no history, etc). Treat that as an empty
    # list rather than an error — real failures put a message on stderr.
    if proc.returncode != 0:
        if proc.stderr.strip() == b"":
            return
        lines = proc.stderr.decode(errors="replace").strip().splitlines()
        # atuin's stderr starts with `Error: <msg>` then a blank line and a
        # crate source location. The first line is the actionable bit.
        summary = next((ln for ln in lines if ln.startswith("Error:")), lines[-1])
        _list_err(f"atuin search failed (exit {proc.returncode}): {summary[:80]}",
                  "\n".join(lines))

    order: list[tuple[str, str]] = []
    seen: set[str] = set()
    for rec in proc.stdout.split(b"\0"):
        if len(rec) < 32:
            continue
        uuid = rec[:32].decode("utf-8")
        cmd = rec[32:].decode("utf-8", errors="replace").replace("\n", "↵")
        if cmd in seen:
            continue
        seen.add(cmd)
        order.append((uuid, cmd))

    if not order:
        return

    try:
        db = open_cache()
    except sqlite3.Error as e:
        _list_err(f"sqlite open failed: {CACHE_DB}", str(e))

    cache: dict[str, str | None] = {}
    uuids = [u for u, _ in order]
    try:
        for i in range(0, len(uuids), SQL_CHUNK):
            batch = uuids[i:i + SQL_CHUNK]
            ph = ",".join("?" * len(batch))
            for row_id, hl in db.execute(
                f"SELECT uuid, text FROM highlights WHERE uuid IN ({ph})",
                batch,
            ):
                cache[row_id] = hl
    except sqlite3.Error as e:
        _list_err("sqlite read failed", str(e))

    new = [(u, c) for u, c in order if not cache.get(u)]
    if new:
        # Lazy import: pygments costs ~50ms to load. The warm path (column
        # populated for every uuid in `order`) never needs the highlighter
        # and shouldn't pay that tax.
        from pygments import highlight
        from pygments.formatters import TerminalTrueColorFormatter
        from pygments.lexers import BashLexer
        lexer = BashLexer()
        formatter = TerminalTrueColorFormatter(style="dracula")
        for u, c in new:
            text = highlight(c, lexer, formatter).rstrip("\n")
            cache[u] = text
            db.execute(
                "INSERT OR REPLACE INTO highlights (uuid, text) VALUES (?, ?)",
                (u, text),
            )
        try:
            db.commit()
        except sqlite3.Error as e:
            # Best-effort persist; rows are still in `cache` and renderable.
            # Don't kill the widget over a transient lock.
            sys.stderr.write(f"warning: sqlite commit failed: {e}\n")

    out = sys.stdout.buffer
    for u, _ in order:
        h = cache.get(u)
        if not h:
            continue
        out.write(h.encode("utf-8"))
        out.write(b"\n")


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else ""
    try:
        if arg == "cycle":
            cycle()
        elif arg in ("session", "workspace", "host"):
            build(arg)
        else:
            sys.exit(f"usage: {sys.argv[0]} <session|workspace|host|cycle>")
    except KeyboardInterrupt:
        # Ctrl-C during a slow cold backfill — exit silently with conventional
        # code so the parent shell sees 130.
        sys.exit(130)
    except Exception as e:
        # Last-resort catch for unexpected bugs. cycle/build have already
        # tried to surface known failure modes; anything reaching here is a
        # programmer error. Surface a single human-readable row so the user
        # knows something is wrong, dump the traceback to stderr.
        if arg == "cycle":
            sys.stdout.write(
                f"change-ghost(unexpected {type(e).__name__}: {str(e)[:60]})"
            )
        else:
            sys.stdout.write(
                f"\033[31m⚠ unexpected {type(e).__name__}: {str(e)[:80]}\033[0m\n"
            )
        sys.stderr.write(traceback.format_exc())
        sys.exit(2)
