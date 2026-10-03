import os
import subprocess

import pytest

from helm4_ready.cli import main

GIT = ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid"]


def git(cwd, *a):
    subprocess.run([*GIT, *a], cwd=cwd, check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path):
    git(tmp_path, "init", "-q", "-b", "main")
    (tmp_path / "Makefile").write_text("old:\n\thelm list -a\n")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-q", "-m", "base")
    return tmp_path


def test_existing_findings_are_not_new(repo, capsys):
    assert main([str(repo), "--base", "HEAD", "--today", "2026-10-03"]) == 0
    assert "introduced since HEAD" in capsys.readouterr().out


def test_new_finding_fails_and_old_one_stays_hidden(repo, capsys):
    with open(repo / "Makefile", "a") as fh:
        fh.write("new:\n\thelm status a --show-desc\n")
    git(repo, "commit", "-q", "-am", "pr")
    rc = main([str(repo), "--base", "HEAD~1", "--today", "2026-10-03", "-f", "json"])
    out = capsys.readouterr().out
    assert rc == 1 and "--show-desc" in out and "list -a" not in out


def test_moved_line_is_not_new(repo, capsys):
    (repo / "Makefile").write_text("\n\n# comment\nold:\n\thelm list -a\n")
    git(repo, "commit", "-q", "-am", "move")
    assert main([str(repo), "--base", "HEAD~1", "--today", "2026-10-03"]) == 0


def test_unknown_base_is_a_usage_error(repo, capsys):
    assert main([str(repo), "--base", "no-such-rev"]) == 2
