"""Regression tests for the csearch helper (zsh/.zsh/claude-search.py).

Each test builds a throwaway $HOME and drives the helper as csearch does, through
its command line. Run with `mise run test`.
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HELPER = Path(__file__).parent / "zsh" / ".zsh" / "claude-search.py"
ANSI = re.compile(r"\x1b\[[0-9;]*m")


def jsonl_line(record):
    # Compact separators and raw non-ASCII, as both agents write them.
    return json.dumps(record, separators=(",", ":"), ensure_ascii=False) + "\n"


def user(text, cwd="/gone", **extra):
    return {"type": "user", "cwd": cwd, "isSidechain": False, "message": {"role": "user", "content": text}, **extra}


def assistant(text, cwd="/gone"):
    content = [{"type": "text", "text": text}]
    return {"type": "assistant", "cwd": cwd, "isSidechain": False, "message": {"role": "assistant", "content": content}}


def codex_item(kind, text):
    block_type = "Text" if kind == "AgentMessage" else "text"
    item = {"type": kind, "content": [{"type": block_type, "text": text}]}
    return {"type": "event_msg", "timestamp": "2026-11-01T10:00:00", "payload": {"type": "item_completed", "item": item}}


def codex_meta(session_id, cwd="/gone", source="cli", originator="codex-tui"):
    payload = {"id": session_id, "cwd": cwd, "source": source, "originator": originator}
    return {"type": "session_meta", "payload": payload}


class CsearchTestCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.home = Path(tmp.name).resolve()

    def write_claude(self, session_id, records, slug="-gone"):
        path = self.home / ".claude" / "projects" / slug / f"{session_id}.jsonl"
        return self.write_jsonl(path, records)

    def write_codex(self, session_id, records, store="sessions"):
        path = self.home / ".codex" / store / "2026" / f"rollout-2026-11-01-{session_id}.jsonl"
        return self.write_jsonl(path, records)

    def write_jsonl(self, path, records):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(jsonl_line(r) for r in records), encoding="utf-8")
        return path

    def helper(self, *args):
        env = {**os.environ, "HOME": str(self.home), "XDG_CACHE_HOME": str(self.home / ".cache")}
        proc = subprocess.run(
            [sys.executable, "-B", str(HELPER), *args],
            env=env, capture_output=True, encoding="utf-8", timeout=30, check=True,
        )
        return proc.stdout

    def rows(self, *args):
        self.helper("refresh")
        rows = []
        for line in self.helper(*(args or ("list-all",))).splitlines():
            fields = line.split("\t")
            self.assertEqual(len(fields), 5, line)
            agent, session_id, path, resume_dir, display = fields
            rows.append({"agent": agent, "id": session_id, "path": path, "dir": resume_dir,
                         "display": ANSI.sub("", display)})
        return rows

    def ids(self, *args):
        return [row["id"] for row in self.rows(*args)]


class TitleTest(CsearchTestCase):
    def display(self, records):
        self.write_claude("s", records)
        return self.rows()[0]["display"]

    def test_custom_title_beats_ai_title_and_prompt(self):
        display = self.display([
            user("first prompt"),
            {"type": "ai-title", "aiTitle": "generated"},
            {"type": "custom-title", "customTitle": "renamed"},
            {"type": "ai-title", "aiTitle": "generated later"},
        ])
        self.assertTrue(display.endswith("renamed"), display)

    def test_title_written_deep_into_a_long_session_is_used(self):
        filler = [assistant(f"step {i}") for i in range(1000)]
        display = self.display([user("first prompt"), *filler, {"type": "ai-title", "aiTitle": "late"}])
        self.assertTrue(display.endswith("late"), display)

    def test_prompt_after_injected_context_becomes_the_title(self):
        text = "<system-reminder>\ninjected\n</system-reminder>\nreal question"
        self.assertTrue(self.display([user(text)]).endswith("real question"))

    def test_real_prompt_beats_a_leading_slash_command(self):
        command = "<command-name>/clear</command-name><command-args></command-args>"
        self.assertTrue(self.display([user(command), user("real question")]).endswith("real question"))

    def test_interrupt_markers_and_shell_escapes_do_not_become_the_title(self):
        records = [user("[Request interrupted by user]"), user("<bash-input>ls</bash-input>"), user("real question")]
        self.assertTrue(self.display(records).endswith("real question"))

    def test_shell_escape_is_readable_when_nothing_else_was_typed(self):
        output = self.display([user("<bash-input>ls</bash-input><bash-stdout>noise</bash-stdout>")])
        self.assertTrue(output.endswith("!ls"), output)

    def test_control_bytes_and_tabs_cannot_break_the_row(self):
        display = self.display([{"type": "ai-title", "aiTitle": "a\tb\nc\x1b[31md"}, user("x", cwd="/gone\tdir\x1b[1m")])
        self.assertTrue(display.endswith("a b c[31md"), display)


class VisibilityTest(CsearchTestCase):
    def test_remote_control_sessions_are_listed_but_automation_is_not(self):
        self.write_claude("rc", [{**user("why is the purifier offline?"), "entrypoint": "sdk-cli"}])
        self.write_claude("review", [{**user("You are an expert code reviewer"), "entrypoint": "sdk-cli"}])
        self.assertEqual(self.ids(), ["rc"])

    def test_desktop_and_tempdir_sessions_are_listed(self):
        self.write_claude("desktop", [{**user("hello"), "entrypoint": "claude-desktop"}])
        self.write_claude("scratch", [user("hello", cwd="/private/tmp/scratch")], slug="-private-tmp-scratch")
        self.assertCountEqual(self.ids(), ["desktop", "scratch"])

    def test_sidechain_only_and_empty_transcripts_are_not_listed(self):
        self.write_claude("side", [{**user("delegated"), "isSidechain": True}])
        self.write_claude("empty", [])
        self.assertEqual(self.ids(), [])


class SearchTest(CsearchTestCase):
    def test_prose_is_searched_but_not_tool_output_or_injected_text(self):
        self.write_claude("prose", [user("about zebra")])
        tool_result = {**user([{"type": "tool_result", "content": "zebra"}]), "toolUseResult": "zebra"}
        self.write_claude("tool", [user("other"), tool_result])
        self.write_claude("meta", [user("other"), user("zebra skill body", isMeta=True)])
        self.write_claude("compact", [user("other"), user("zebra summary", isCompactSummary=True)])
        self.write_claude("reminder", [user("other <system-reminder>zebra</system-reminder>")])
        self.assertEqual(self.ids("search", "zebra"), ["prose"])

    def test_prompt_queued_mid_turn_is_searched(self):
        queued = {"type": "attachment", "attachment": {"type": "queued_command", "commandMode": "prompt", "prompt": "zebra"}}
        notification = {"type": "attachment", "attachment": {"type": "queued_command", "commandMode": "task-notification", "prompt": "okapi"}}
        self.write_claude("s", [user("other"), queued, notification])
        self.assertEqual(self.ids("search", "zebra"), ["s"])
        self.assertEqual(self.ids("search", "okapi"), [])

    def test_prose_naming_noise_markers_is_still_searched(self):
        self.write_claude("s", [user("zebra toolUseResult file-history-snapshot")])
        self.assertEqual(self.ids("search", "zebra"), ["s"])

    def test_matching_is_case_insensitive_beyond_ascii(self):
        self.write_claude("s", [user("Été chaud")])
        self.assertEqual(self.ids("search", "été"), ["s"])
        self.assertEqual(self.ids("search", "ÉTÉ"), ["s"])

    def test_term_with_json_escaped_characters_matches(self):
        self.write_claude("s", [user('say "hello" to C:\\temp')])
        self.assertEqual(self.ids("search", '"hello"'), ["s"])
        self.assertEqual(self.ids("search", "C:\\temp"), ["s"])

    def test_ranking_prefers_all_terms_then_title_then_mentions(self):
        self.write_claude("one_term", [{"type": "ai-title", "aiTitle": "other"}, user("zebra zebra zebra zebra")])
        self.write_claude("both_terms", [{"type": "ai-title", "aiTitle": "other"}, user("zebra okapi")])
        self.write_claude("titled", [{"type": "ai-title", "aiTitle": "zebra okapi"}, user("zebra okapi")])
        self.write_claude("mentions", [{"type": "ai-title", "aiTitle": "other"}, user("zebra okapi zebra okapi")])
        self.assertEqual(self.ids("search", "zebra okapi"), ["titled", "mentions", "both_terms", "one_term"])

    def test_sessions_without_timestamps_order_by_mtime(self):
        old = self.write_claude("old", [user("x")])
        new = self.write_claude("new", [user("x")])
        os.utime(old, (1_000_000, 1_000_000))
        os.utime(new, (2_000_000, 2_000_000))
        self.assertEqual(self.ids("search", ""), ["new", "old"])

    def test_order_and_age_follow_the_last_turn_not_a_touched_mtime(self):
        old = self.write_claude("old", [user("x", timestamp="2020-01-01T00:00:00.000Z")])
        new = self.write_claude("new", [user("x", timestamp="2026-11-01T00:00:00.000Z")])
        os.utime(old, (2_000_000_000, 2_000_000_000))
        os.utime(new, (1_000_000_000, 1_000_000_000))
        rows = self.rows()
        self.assertEqual([row["id"] for row in rows], ["new", "old"])
        age = int(rows[1]["display"].split("d")[0])
        self.assertGreater(age, 2000)

    def test_equal_relevance_breaks_ties_on_last_turn(self):
        title = {"type": "ai-title", "aiTitle": "other"}
        self.write_claude("old", [title, user("zebra", timestamp="2020-01-01T00:00:00.000Z")])
        self.write_claude("new", [title, user("zebra", timestamp="2026-11-01T00:00:00.000Z")])
        self.assertEqual(self.ids("search", "zebra"), ["new", "old"])

    def test_lone_surrogate_in_a_transcript_does_not_break_indexing(self):
        path = self.home / ".claude" / "projects" / "-gone" / "s.jsonl"
        path.parent.mkdir(parents=True)
        path.write_text('{"type":"user","cwd":"/gone","message":{"content":"zebra \\ud83d end"}}\n')
        self.assertEqual(self.ids("search", "zebra"), ["s"])

    def test_half_written_last_line_is_ignored(self):
        path = self.write_claude("s", [user("zebra")])
        with path.open("a") as fh:
            fh.write('{"type":"user","message":{"content":"tru')
        self.assertEqual(self.ids("search", "zebra"), ["s"])


class ResumeDirTest(CsearchTestCase):
    def directory(self, name):
        path = self.home / name
        path.mkdir(parents=True)
        return str(path)

    def slug(self, path):
        return re.sub(r"[^A-Za-z0-9]", "-", path)

    def test_uses_the_directory_the_transcript_is_filed_under(self):
        repo = self.directory("repo")
        worktree = self.directory("repo/.worktrees/feature")
        self.write_claude("s", [user("x", cwd=worktree), user("y", cwd=repo)], slug=self.slug(repo))
        self.assertEqual(self.rows()[0]["dir"], repo)

    def test_relocated_session_uses_its_new_directory(self):
        repo = self.directory("repo")
        self.write_claude("s", [user("x", cwd=str(self.home / "gone")), {"type": "relocated", "relocatedCwd": repo}])
        self.assertEqual(self.rows()[0]["dir"], repo)

    def test_deleted_worktree_falls_back_to_recorded_checkout(self):
        repo = self.directory("repo")
        worktree = str(self.home / "elsewhere" / "feature")
        state = {"type": "worktree-state", "worktreeSession": {"originalCwd": repo, "worktreePath": worktree}}
        self.write_claude("s", [user("x", cwd=worktree), state])
        row = self.rows()[0]
        self.assertEqual(row["dir"], repo)
        self.assertIn("repo", row["display"])

    def test_deleted_worktree_falls_back_to_checkout_in_its_path(self):
        repo = self.directory("repo")
        self.write_claude("s", [user("x", cwd=f"{repo}/.claude/worktrees/feature")])
        self.assertEqual(self.rows()[0]["dir"], repo)

    def test_no_surviving_directory_leaves_the_field_empty(self):
        self.write_claude("s", [user("x", cwd=str(self.home / "gone"))])
        self.assertEqual(self.rows()[0]["dir"], "")


class CodexTest(CsearchTestCase):
    def test_interactive_threads_are_listed_with_their_resume_id(self):
        cwd = str(self.home)
        self.write_codex("a", [codex_meta("thread-a", cwd), codex_item("UserMessage", "about zebra")])
        self.write_codex("b", [codex_meta("thread-b", cwd, source="vscode"), codex_item("UserMessage", "x")], store="archived_sessions")
        rows = {row["id"]: row for row in self.rows()}
        self.assertEqual(sorted(rows), ["thread-a", "thread-b"])
        self.assertEqual(rows["thread-a"]["agent"], "codex")
        self.assertEqual(rows["thread-a"]["dir"], cwd)
        self.assertEqual(self.ids("search", "zebra"), ["thread-a"])

    def test_agent_replies_are_searched(self):
        self.write_codex("a", [codex_meta("a"), codex_item("UserMessage", "x"), codex_item("AgentMessage", "about zebra")])
        self.assertEqual(self.ids("search", "zebra"), ["a"])

    def test_subagent_and_exec_threads_are_not_listed(self):
        prompt = codex_item("UserMessage", "x")
        self.write_codex("sub", [codex_meta("sub", source={"subagent": {"thread_spawn": {}}}), prompt])
        self.write_codex("exec", [codex_meta("exec", source="exec", originator="codex_exec"), prompt])
        self.assertEqual(self.ids(), [])

    def test_first_session_meta_wins_over_a_forked_parents(self):
        self.write_codex("fork", [codex_meta("child"), codex_meta("parent"), codex_item("UserMessage", "x")])
        self.assertEqual(self.ids(), ["child"])

    def test_thread_name_is_the_title_and_tracks_renames_without_a_new_rollout(self):
        self.write_codex("a", [codex_meta("thread-a"), codex_item("UserMessage", "first prompt")])
        self.assertTrue(self.rows()[0]["display"].endswith("first prompt"))
        index = self.home / ".codex" / "session_index.jsonl"
        index.write_text('{"id":"thread-a","thread_name":"old"}\n{"id":"thread-a","thread_name":"renamed"}\n')
        self.assertTrue(self.rows()[0]["display"].endswith("renamed"))

    def test_only_message_items_are_searched(self):
        command = {"type": "event_msg", "payload": {"type": "item_completed", "item": {"type": "CommandExecution", "output": "zebra"}}}
        injected = {"type": "response_item", "payload": {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "zebra"}]}}
        self.write_codex("a", [codex_meta("a"), codex_item("UserMessage", "x"), command, injected])
        self.assertEqual(self.ids("search", "zebra"), [])

    def test_order_follows_the_last_message(self):
        def stamped(stamp):
            return {**codex_item("UserMessage", "x"), "timestamp": stamp}
        self.write_codex("old", [codex_meta("old"), stamped("2020-01-01T00:00:00Z")])
        self.write_codex("new", [codex_meta("new"), stamped("2026-11-01T00:00:00Z")])
        self.assertEqual(self.ids(), ["new", "old"])

    def test_preview_renders_codex_turns(self):
        path = self.write_codex("a", [codex_meta("a"), codex_item("UserMessage", "hi"), codex_item("AgentMessage", "hello")])
        output = ANSI.sub("", self.helper("preview", str(path)))
        self.assertIn("user\nhi\n", output)
        self.assertIn("codex\nhello\n", output)


class RefreshTest(CsearchTestCase):
    def test_changed_file_is_reparsed_and_deleted_file_dropped(self):
        path = self.write_claude("s", [user("zebra")])
        gone = self.write_claude("gone", [user("zebra")])
        self.assertCountEqual(self.ids("search", "zebra"), ["s", "gone"])
        path.write_text(jsonl_line(user("okapi and more text")))
        gone.unlink()
        self.assertEqual(self.ids("search", "zebra"), [])
        self.assertEqual(self.ids("search", "okapi"), ["s"])

    def test_unchanged_file_is_not_reparsed(self):
        path = self.write_claude("s", [user("zebra")])
        self.helper("refresh")
        stat = path.stat()
        same_size = jsonl_line(user("okapi")).rstrip("\n").ljust(stat.st_size - 1) + "\n"
        path.write_text(same_size)
        self.assertEqual(path.stat().st_size, stat.st_size)
        os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns))
        self.assertEqual(self.ids("search", "zebra"), ["s"])

    def test_corrupt_index_is_rebuilt(self):
        self.write_claude("s", [user("zebra")])
        self.helper("refresh")
        index = self.home / ".cache" / "csearch" / "index.sqlite3"
        for sibling in index.parent.glob("index.sqlite3-*"):
            sibling.unlink()
        index.write_bytes(b"not a database" * 100)
        self.assertEqual(self.ids("search", "zebra"), ["s"])


class PreviewTest(CsearchTestCase):
    def test_query_keeps_only_matching_turns(self):
        path = self.write_claude("s", [user("about zebra"), assistant("unrelated reply")])
        output = self.helper("preview", str(path), "ZEBRA")
        self.assertIn("zebra", ANSI.sub("", output))
        self.assertNotIn("unrelated", output)

    def test_every_listed_match_has_a_turn_to_show(self):
        tool_result = {**user([{"type": "tool_result", "content": "zebra"}]), "toolUseResult": "zebra"}
        path = self.write_claude("s", [user("about zebra"), tool_result])
        output = ANSI.sub("", self.helper("preview", str(path), "zebra"))
        self.assertEqual(output.count("── "), 1)

    def test_highlighting_does_not_corrupt_its_own_escape_codes(self):
        path = self.write_claude("s", [{"type": "ai-title", "aiTitle": "other"}, user("alpha m 31 here")])
        output = self.helper("preview", str(path), "alpha m 31")
        self.assertIn("\x1b[31m\x1b[1malpha\x1b[0m", output)
        self.assertEqual(ANSI.sub("", output).count("alpha m 31 here"), 1)

    def test_transcript_cannot_inject_terminal_escapes(self):
        path = self.write_claude("s", [user("safe\x1b]0;evil\x07 text\x9b31m")])
        self.assertNotIn("\x1b]", self.helper("preview", str(path)))
        self.assertNotIn("\x9b", self.helper("preview", str(path)))

    def test_missing_transcript_fails_with_a_message(self):
        env = {**os.environ, "HOME": str(self.home)}
        proc = subprocess.run(
            [sys.executable, "-B", str(HELPER), "preview", str(self.home / "nope.jsonl")],
            env=env, capture_output=True, encoding="utf-8", timeout=30, check=False,
        )
        self.assertEqual(proc.returncode, 1)
        self.assertIn("error:", proc.stderr)


if __name__ == "__main__":
    unittest.main()
