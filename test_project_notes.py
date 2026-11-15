"""Regression tests for `project_notes lint`'s forge link check (bin/.local/bin/project_notes).

Each test builds a throwaway notes repository and code repository whose remotes
point at a made-up forge, then runs the CLI against them. The forge is never
contacted: links verify against the local clones only. Run with `mise run test`.
"""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

CLI = Path(__file__).parent / "bin" / ".local" / "bin" / "project_notes"
FORGE = "https://forge.example/owner"


class ForgeLinkTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name).resolve()
        # A stub linter keeps markdownlint (and its shared config) out of the result.
        stubs = root / "bin"
        stubs.mkdir()
        (stubs / "markdownlint-cli2").write_text("#!/bin/sh\nexit 0\n")
        (stubs / "markdownlint-cli2").chmod(0o755)
        git_dir = os.path.dirname(shutil.which("git"))
        # A throwaway HOME keeps the operator's global git config and hooks out.
        self.env = {
            "HOME": str(root),
            "PATH": f"{stubs}:{git_dir}:/usr/bin:/bin",
            "PROJECT_NOTES_ROOT": str(root / "vault"),
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_AUTHOR_NAME": "Test",
            "GIT_AUTHOR_EMAIL": "test@example.com",
            "GIT_COMMITTER_NAME": "Test",
            "GIT_COMMITTER_EMAIL": "test@example.com",
        }
        self.root = root
        self.code, self.notes = self.init_project("proj")

    def init_project(self, name):
        code, notes = self.root / "code" / name, self.root / "vault" / name
        self.init_repo(code, f"{FORGE}/{name}.git")
        self.init_repo(notes, f"ssh://git@forge.example:2222/owner/{name}_notes.git")
        self.git(notes, "config", "projectnotes.coderepo", str(code))
        return code, notes

    def git(self, repo, *args):
        result = subprocess.run(["git", *args], cwd=repo, env=self.env, capture_output=True, text=True, check=True)
        return result.stdout.strip()

    def init_repo(self, repo, remote):
        repo.mkdir(parents=True)
        self.git(repo, "init", "-q", "-b", "main")
        self.git(repo, "remote", "add", "origin", remote)

    def commit(self, repo, files, message="Change"):
        for name, text in files.items():
            path = repo / name
            if text is None:
                path.unlink()
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
        self.git(repo, "add", "-A")
        self.git(repo, "commit", "-q", "-m", message)
        return self.git(repo, "rev-parse", "HEAD")

    def lint(self, *links):
        body = "".join(f"- [link]({url})\n" for url in links)
        (self.notes / "note.md").write_text(f"---\nstatus: reference\ncreated_at: 2026-11-15\n---\n\n# Note\n\n{body}")
        return subprocess.run(
            [sys.executable, str(CLI), "lint", "--repo", str(self.notes)],
            env=self.env,
            capture_output=True,
            text=True,
            timeout=60,
        )

    def assert_ok(self, result):
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("proj: ok", result.stdout)

    def assert_broken(self, result, *urls):
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertEqual(result.stdout.splitlines(), [f"note.md: broken link: {url}" for url in urls])

    def test_gitea_branch_link_checks_the_code_repository(self):
        self.commit(self.code, {"src/app.py": "", "docs/my file.md": ""})
        ok = [
            f"{FORGE}/proj/src/branch/main/src/app.py",
            f"{FORGE}/proj/src/branch/main/src/app.py#L12",
            f"{FORGE}/proj/src/branch/main/docs/my%20file.md",
            f"{FORGE}/proj/src/branch/main/src",
            f"{FORGE}/proj/src/branch/main/",
        ]
        self.assert_ok(self.lint(*ok))
        missing = f"{FORGE}/proj/src/branch/main/src/gone.py"
        self.assert_broken(self.lint(*ok, missing), missing)

    def test_branch_checks_the_committed_ref_not_the_working_tree(self):
        self.commit(self.code, {"README.md": ""})
        (self.code / "draft.py").write_text("")
        link = f"{FORGE}/proj/src/branch/main/draft.py"
        self.assert_broken(self.lint(link), link)

    def test_branch_found_only_on_its_remote_tracking_ref(self):
        self.commit(self.code, {"README.md": ""})
        sha = self.commit(self.code, {"merged.py": ""})
        self.git(self.code, "update-ref", "refs/remotes/origin/release/v2", sha)
        self.git(self.code, "reset", "-q", "--hard", "HEAD~1")
        self.assert_ok(self.lint(f"{FORGE}/proj/src/branch/release/v2/merged.py"))

    def test_remote_tracking_ref_counts_when_local_branch_lags(self):
        self.commit(self.code, {"old.py": ""})
        ahead = self.commit(self.code, {"new.py": ""})
        self.git(self.code, "update-ref", "refs/remotes/origin/main", ahead)
        self.git(self.code, "reset", "-q", "--hard", "HEAD~1")
        self.assert_ok(self.lint(f"{FORGE}/proj/src/branch/main/new.py"))

    def test_unpushed_commit_link_to_a_file_deleted_from_the_notes(self):
        sha = self.commit(self.notes, {"old_note.md": "---\nstatus: completed\ncreated_at: 2026-11-15\n---\n"})
        self.commit(self.notes, {"old_note.md": None})
        kept = f"https://forge.example/owner/proj_notes/src/commit/{sha}/old_note.md"
        wrong = f"https://forge.example/owner/proj_notes/src/commit/{sha}/other.md"
        self.assert_ok(self.lint(kept))
        self.assert_broken(self.lint(kept, wrong), wrong)

    def test_tag_link(self):
        self.commit(self.code, {"tagged.py": ""})
        self.git(self.code, "tag", "v1.0")
        self.assert_ok(self.lint(f"{FORGE}/proj/src/tag/v1.0/tagged.py"))
        missing = f"{FORGE}/proj/src/tag/v1.0/untagged.py"
        self.assert_broken(self.lint(missing), missing)

    def test_github_and_gitlab_forms(self):
        sha = self.commit(self.code, {"lib/mod.py": ""})
        self.git(self.code, "branch", "feature/x")
        ok = [
            f"{FORGE}/proj/blob/main/lib/mod.py",
            f"{FORGE}/proj/tree/feature/x/lib",
            f"{FORGE}/proj/-/blob/{sha[:12]}/lib/mod.py?ref_type=heads",
            "https://Forge.Example/Owner/Proj/blob/main/lib/mod.py",
        ]
        self.assert_ok(self.lint(*ok))
        missing = f"{FORGE}/proj/-/blob/main/lib/gone.py"
        self.assert_broken(self.lint(*ok, missing), missing)

    def test_link_into_another_projects_code(self):
        other_code, _ = self.init_project("other")
        self.commit(other_code, {"shared.py": ""})
        self.assert_ok(self.lint(f"{FORGE}/other/src/branch/main/shared.py"))
        missing = f"{FORGE}/other/src/branch/main/gone.py"
        self.assert_broken(self.lint(missing), missing)

    def test_third_party_repository_is_skipped_silently(self):
        result = self.lint("https://forge.example/someone/else/src/branch/main/x.py")
        self.assert_ok(result)
        self.assertEqual(result.stderr, "")

    def test_unknown_ref_is_only_noted(self):
        self.commit(self.code, {"README.md": ""})
        result = self.lint(
            f"{FORGE}/proj/src/branch/unfetched/x.py",
            f"{FORGE}/proj/src/commit/{'0' * 40}/x.py",
        )
        self.assert_ok(result)
        self.assertIn("ref not in", result.stderr)
        self.assertIn("src/branch/unfetched/x.py", result.stderr)
        self.assertIn(f"src/commit/{'0' * 40}/x.py", result.stderr)

    def test_relative_links_still_checked(self):
        self.commit(self.code, {"README.md": ""})
        (self.notes / "other.md").write_text("---\nstatus: reference\ncreated_at: 2026-11-15\n---\n")
        self.assert_ok(self.lint("other.md#section"))
        self.assert_broken(self.lint("missing.md"), "missing.md")


if __name__ == "__main__":
    unittest.main()
