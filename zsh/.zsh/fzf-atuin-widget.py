#!/usr/bin/env -S uv run --script --quiet
# /// script
# requires-python = ">=3.10"
# dependencies = ["pygments"]
# ///
"""fzf-atuin helper. Invoked from fzf-atuin-widget.zsh.

Modes:
  fzf-atuin-widget.py <session-preload|workspace|host>
      Emit a NUL-free, one-row-per-command, pygments-highlighted list to
      stdout. \\n in source commands is encoded as ↵ so multi-line commands
      stay on one fzf row; the widget decodes back when assigning $LBUFFER.

  fzf-atuin-widget.py cycle
      Read $FZF_GHOST, emit the fzf action chain to advance one step in the
      session-preload → workspace → host cycle.

Highlighting is done on the fly (no cache): atuin returns in ~tens of ms and
pygments highlights the distinct command set in about the same, so a sidecar
sqlite cache wasn't worth its on-disk footprint or its coupling to atuin's
internals.

Why uv-script-with-inline-deps instead of plain `python3`: $PATH's python3
depends on which venv is active for the user's cwd at Ctrl-R time, and
most of them don't have pygments. `uv run --script` resolves+caches the
dep set independent of any ambient venv, so the widget works everywhere.
"""
import os
import re
import subprocess
import sys
import traceback

SELF = os.path.abspath(__file__)
# Strip C0+C1 control bytes (newlines are encoded as ↵ separately) so a recorded
# escape sequence can't inject into the fzf list. The C1 range (0x80-0x9f) covers
# the 8-bit CSI introducer 0x9b a terminal in 8-bit mode would act on.
_CTRL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]")


def _list_err(short: str, detail: str = "") -> None:
    """build()-path error: write one red row to fzf, detail to stderr, exit 1.

    The fzf row is the only thing the user sees while focused on the popup;
    detail goes to stderr so it surfaces in the terminal once fzf exits.
    """
    sys.stdout.write(f"\033[31m⚠ {short}\033[0m\n")
    if detail:
        sys.stderr.write(detail.rstrip() + "\n")
    sys.exit(1)


def cycle() -> None:
    # Anything we write here is parsed by fzf as a transform-action chain; a
    # raw traceback would be silently swallowed (or worse, partially parsed).
    # Wrap the whole body so errors become a visible ghost-text update.
    try:
        ghost = os.environ.get("FZF_GHOST", "")
        if "session-preload" in ghost:
            n = "workspace"
        elif "workspace" in ghost:
            n = "host"
        else:
            n = "session-preload"
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
             "--cmd-only", "--print0"],
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

    # pygments is imported here (not at module top) so the `cycle` path —
    # invoked on every Ctrl-O — doesn't pay the ~50ms highlighter import. If it
    # can't be imported, fall back to plain rows so Ctrl-R still works (just
    # uncolored) instead of failing the whole list. (A uv dependency-resolution
    # failure happens before Python starts, so it can't be caught here.)
    try:
        from pygments import highlight
        from pygments.formatters import TerminalTrueColorFormatter
        from pygments.lexers import BashLexer

        lexer = BashLexer()
        formatter = TerminalTrueColorFormatter(style="dracula")

        def render(cmd: str) -> str:
            return highlight(cmd, lexer, formatter).rstrip("\n")
    except ImportError:
        def render(cmd: str) -> str:
            return cmd

    # --cmd-only -r does NOT dedup non-interactively (verified: it returns
    # repeats), so the widget still dedups commands itself.
    seen: set[str] = set()
    out = sys.stdout.buffer
    for rec in proc.stdout.split(b"\0"):
        raw = _CTRL.sub("", rec.decode("utf-8", errors="replace"))
        if not raw.strip():
            continue
        cmd = raw.replace("\n", "↵")
        if cmd in seen:
            continue
        seen.add(cmd)
        out.write(render(cmd).encode("utf-8"))
        out.write(b"\n")


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else ""
    try:
        if arg == "cycle":
            cycle()
        elif arg in ("session-preload", "workspace", "host"):
            build(arg)
        else:
            sys.exit(f"usage: {sys.argv[0]} <session-preload|workspace|host|cycle>")
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
