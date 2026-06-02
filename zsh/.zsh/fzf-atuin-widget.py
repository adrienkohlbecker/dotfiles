#!/usr/bin/env -S uv run --script --quiet
# /// script
# requires-python = ">=3.10"
# dependencies = ["tree-sitter", "tree-sitter-bash"]
# ///
"""fzf-atuin helper. Invoked from fzf-atuin-widget.zsh.

Modes:
  fzf-atuin-widget.py <session-preload|workspace|host>
      Emit a NUL-free, one-row-per-command, tree-sitter-bash-highlighted list
      to stdout. \\n in source commands is encoded as ↵ so multi-line commands
      stay on one fzf row; the widget decodes back when assigning $LBUFFER.

  fzf-atuin-widget.py cycle
      Read $FZF_GHOST, emit the fzf action chain to advance one step in the
      session-preload → workspace → host cycle.

Highlighting is done on the fly (no cache): tree-sitter-bash parses the whole
distinct command set in a couple of ms — fast enough that the sidecar sqlite
cache an earlier bat-based version needed (bat paid a process spawn per command)
is gone, along with its on-disk footprint and coupling to atuin's internals.

Why uv-script-with-inline-deps instead of plain `python3`: $PATH's python3
depends on which venv is active for the user's cwd at Ctrl-R time, and most of
them don't have tree-sitter / tree-sitter-bash. `uv run --script` resolves+caches
the dep set independent of any ambient venv, so the widget works everywhere.
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

# Colors follow the Dracula palette. The Dracula zsh-syntax-highlighting theme
# leaves some tokens at foreground (#F8F8F2) that tree-sitter can reliably
# distinguish — redirections, assignments, $var inside strings, substitution
# delimiters — so the popup colors those more richly than the live prompt.
# 16-color SGR where the Dracula terminal palette maps correctly; truecolor for
# Dracula orange (no 16-color equivalent).
_RESET = "\033[0m"
_GREEN = "\033[32m"                   # commands / functions / aliases
_CYAN = "\033[36m"                    # reserved words / builtins
_ORANGE = "\033[38;2;255;184;108m"    # options (-x / --long)
_MAGENTA = "\033[35m"                 # separators / redirections / subst delimiters
_YELLOW = "\033[33m"                  # quoted strings
_PURPLE = "\033[34m"                  # assignments / $var in strings (Dracula #BD93F9)
_GREY = "\033[90m"                    # comments

# Reserved words (→ cyan). Keyword literals only — `{`, `}`, `[[`, `]]` are
# skipped because `{`/`}` also delimit ${…} expansions.
_RESERVED = frozenset({
    "if", "then", "else", "elif", "fi", "for", "while", "until",
    "do", "done", "case", "esac", "in", "function", "select", "time", "coproc",
})
_SEPARATORS = frozenset({"|", "||", "&&", "&", ";", ";;", "|&"})
_REDIRECT = frozenset({
    ">", "<", ">>", "<<", "<<-", "<<<", ">&", "<&", "&>", "&>>", ">|",
})
_SUBST_OPEN = frozenset({"$(", "`", "<(", ">("})
_SUBST_NODES = frozenset({"command_substitution", "process_substitution"})
_STRING_NODES = frozenset({"string", "raw_string", "ansi_c_string"})
_EXPANSION_NODES = frozenset({"expansion", "simple_expansion"})


def _token_color(node):
    """SGR code for a tree-sitter-bash leaf using the Dracula palette.

    Matches the Dracula z-sy-h theme for tokens it colors, and adds richer
    highlighting for tokens the theme leaves at foreground but tree-sitter can
    reliably distinguish: redirections, assignments, $var inside strings, and
    substitution delimiters.
    """
    t = node.type
    parent = node.parent
    pt = parent.type if parent is not None else ""
    if t == "comment":
        return _GREY
    if pt == "command_name":
        return _GREEN
    if t in _RESERVED:
        return _CYAN
    if t in _SUBST_OPEN or (t in (")", "`") and pt in _SUBST_NODES):
        return _MAGENTA
    if t in _SEPARATORS or t in _REDIRECT:
        return _MAGENTA
    in_string = t in _STRING_NODES
    in_expansion = in_assign = False
    anc = parent
    while anc is not None:
        at = anc.type
        if at == "variable_assignment":
            in_assign = True
        elif at in _STRING_NODES:
            in_string = True
        elif at in _EXPANSION_NODES:
            in_expansion = True
        anc = anc.parent
    if in_assign:
        return _PURPLE
    if in_string:
        return _PURPLE if in_expansion else _YELLOW
    if t == "word" and node.text[:1] == b"-":
        return _ORANGE
    return None


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

    # tree-sitter-bash is imported here (not at module top) so the `cycle` path
    # — invoked on every Ctrl-O — doesn't pay the parser import. If it can't be
    # imported, fall back to plain rows so Ctrl-R still works (just uncolored)
    # instead of failing the whole list. (A uv dependency-resolution failure
    # happens before Python starts, so it can't be caught here.)
    try:
        import tree_sitter_bash as ts_bash
        from tree_sitter import Language, Parser

        parser = Parser(Language(ts_bash.language()))

        def render(cmd: str) -> str:
            # Parse the raw text (real newlines) so the grammar sees the true
            # line structure, then encode \n as ↵ in the output so a multi-line
            # command stays one fzf row. Walk leaves left-to-right, emitting the
            # whitespace gaps between them verbatim and each leaf wrapped in its
            # role color; `cursor` (a byte offset) tracks how far we've emitted.
            data = cmd.encode("utf-8")
            leaves: list = []

            def collect(node) -> None:
                if node.child_count == 0:
                    leaves.append(node)
                    return
                for child in node.children:
                    collect(child)

            collect(parser.parse(data).root_node)

            parts: list[str] = []
            cursor = 0
            for leaf in leaves:
                start, end = leaf.start_byte, leaf.end_byte
                if end <= cursor:
                    continue  # zero-width / overlapping node (e.g. inside ERROR)
                if start > cursor:
                    parts.append(data[cursor:start].decode("utf-8", "replace"))
                text = data[start:end].decode("utf-8", "replace")
                color = _token_color(leaf)
                parts.append(color + text + _RESET if color else text)
                cursor = end
            if cursor < len(data):
                parts.append(data[cursor:].decode("utf-8", "replace"))
            return "".join(parts).replace("\n", "↵")
    except ImportError:
        def render(cmd: str) -> str:
            return cmd.replace("\n", "↵")

    # --cmd-only -r does NOT dedup non-interactively (verified: it returns
    # repeats), so the widget still dedups commands itself. Dedup on the raw
    # text; render() applies the ↵ encoding.
    seen: set[str] = set()
    out = sys.stdout.buffer
    for rec in proc.stdout.split(b"\0"):
        raw = _CTRL.sub("", rec.decode("utf-8", errors="replace"))
        if not raw.strip():
            continue
        if raw in seen:
            continue
        seen.add(raw)
        out.write(render(raw).encode("utf-8"))
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
