from __future__ import annotations

from types import SimpleNamespace

import pytest

import benchmarks.run_task037_extra_h2b as runner


def test_light_source_uses_posix_spawn_eligible_git_calls(monkeypatch):
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        if command[-1] == "HEAD":
            return SimpleNamespace(stdout="a" * 40 + "\n")
        return SimpleNamespace(stdout=" M tracked.py\n?? raw.json\n")

    monkeypatch.setattr(runner.shutil, "which", lambda _name: "/usr/bin/git")
    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    identity = runner._light_source()

    assert identity["source_commit_full_sha"] == "a" * 40
    assert identity["tracked_source_dirty"] is True
    assert identity["nonignored_untracked_paths"] == ["raw.json"]
    assert len(calls) == 2
    assert all(command[0] == "/usr/bin/git" for command, _kwargs in calls)
    assert all(kwargs["close_fds"] is False for _command, kwargs in calls)


def test_light_source_missing_git_fails_closed(monkeypatch):
    monkeypatch.setattr(runner.shutil, "which", lambda _name: None)
    with pytest.raises(FileNotFoundError, match="git executable"):
        runner._light_source()
