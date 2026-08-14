"""GitHub clone: token, cache refresh, actionable errors. No network."""

from __future__ import annotations

import subprocess
import time
from pathlib import Path

import pytest

from repowiki.ingest import github as gh


def test_public_clone_url_has_no_token():
    assert (
        gh._authenticated_clone_url("https://github.com/acme/demo", "")
        == "https://github.com/acme/demo.git"
    )


def test_token_is_injected_but_redacted_from_errors(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_secret_value_do_not_leak")
    url = gh._authenticated_clone_url("https://github.com/acme/demo", gh.github_token())
    assert "ghp_secret_value_do_not_leak" in url
    assert "x-access-token" in url
    redacted = gh._redact(
        "fatal: Authentication failed for 'https://x-access-token:ghp_secret_value_do_not_leak@github.com/acme/demo.git'",
        "ghp_secret_value_do_not_leak",
    )
    assert "ghp_secret_value_do_not_leak" not in redacted
    assert "***" in redacted


def test_timeout_error_is_actionable():
    with pytest.raises(gh.GitIngestError) as caught:
        raise gh.GitIngestError(
            "clone_timeout",
            f"Clone timed out after {gh._CLONE_TIMEOUT}s. "
            "The repo may be too large for a shallow clone — import a local path instead. "
            "If it is private, set REPOWIKI_GITHUB_TOKEN or GITHUB_TOKEN. "
            "LFS files and submodules are not fetched.",
        )
    assert caught.value.code == "clone_timeout"
    assert "120" in caught.value.message
    assert "GITHUB_TOKEN" in caught.value.message


def test_run_git_timeout_maps_to_ingest_error(monkeypatch):
    def boom(*_a, **_k):
        raise subprocess.TimeoutExpired(cmd=["git"], timeout=120)

    monkeypatch.setattr(gh.subprocess, "run", boom)
    with pytest.raises(gh.GitIngestError) as caught:
        gh._run_git(["git", "clone", "https://github.com/acme/demo.git", "/tmp/x"], timeout=120, token="")
    assert caught.value.code == "clone_timeout"
    assert "120" in caught.value.message
    assert "local path" in caught.value.message.lower() or "GITHUB_TOKEN" in caught.value.message


def test_run_git_auth_failure_is_actionable(monkeypatch):
    def boom(*_a, **_k):
        raise subprocess.CalledProcessError(
            128,
            ["git", "clone"],
            stderr="fatal: Authentication failed for 'https://github.com/acme/private.git'",
        )

    monkeypatch.setattr(gh.subprocess, "run", boom)
    with pytest.raises(gh.GitIngestError) as caught:
        gh._run_git(["git", "clone", "x"], timeout=120, token="")
    assert caught.value.code == "auth_required"
    assert "GITHUB_TOKEN" in caught.value.message
    assert "private" in caught.value.message.lower()


def test_run_git_not_found_mentions_private_and_token(monkeypatch):
    def boom(*_a, **_k):
        raise subprocess.CalledProcessError(
            128,
            ["git", "clone"],
            stderr="fatal: repository 'https://github.com/acme/missing.git' not found",
        )

    monkeypatch.setattr(gh.subprocess, "run", boom)
    with pytest.raises(gh.GitIngestError) as caught:
        gh._run_git(["git", "clone", "x"], timeout=120, token="")
    assert caught.value.code == "private_or_not_found"
    assert "GITHUB_TOKEN" in caught.value.message
    assert "LFS" in caught.value.message


def test_fresh_cache_skips_clone(monkeypatch, tmp_path: Path):
    dest = tmp_path / "github.com" / "acme" / "demo"
    dest.mkdir(parents=True)
    (dest / ".git").mkdir()
    (dest / "README.md").write_text("# demo\n", encoding="utf-8")
    monkeypatch.setattr(gh, "_CLONE_DIR", tmp_path)

    def no_git(*_a, **_k):
        raise AssertionError("fresh cache must not call git")

    monkeypatch.setattr(gh.subprocess, "run", no_git)
    project = gh.ingest_github("https://github.com/acme/demo")
    assert project.files


def test_stale_cache_refreshes(monkeypatch, tmp_path: Path):
    dest = tmp_path / "github.com" / "acme" / "demo"
    dest.mkdir(parents=True)
    git_dir = dest / ".git"
    git_dir.mkdir()
    (dest / "README.md").write_text("# demo\n", encoding="utf-8")
    old = time.time() - (gh._DEFAULT_CACHE_TTL + 10)
    # pathlib Path.stat is used on .git
    import os

    os.utime(git_dir, (old, old))
    monkeypatch.setattr(gh, "_CLONE_DIR", tmp_path)
    calls: list[list[str]] = []

    def fake_run(args, **kwargs):
        calls.append(list(args))
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    monkeypatch.setattr(gh.subprocess, "run", fake_run)
    project = gh.ingest_github("https://github.com/acme/demo")
    assert project.files
    assert any(args[:3] == ["git", "-C", str(dest)] and "fetch" in args for args in calls)
    assert any("reset" in args for args in calls)
    assert not any("clone" in args for args in calls)
