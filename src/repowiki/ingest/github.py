"""Clone a remote git repository and ingest it.

Public HTTPS ``--depth 1`` clone. Optional token from the environment
(``REPOWIKI_GITHUB_TOKEN``, ``GITHUB_TOKEN``, or ``GH_TOKEN``) — never commit
it, never log it. LFS objects and submodules are not fetched.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

from repowiki.core.models import ProjectContext
from repowiki.ingest.local import ingest_local

logger = logging.getLogger(__name__)

_CLONE_DIR = Path.home() / ".repowiki" / "repos"
_CLONE_TIMEOUT = 120  # seconds
_MAX_REPO_SIZE_MB = 500
_DEFAULT_CACHE_TTL = 24 * 60 * 60
_TOKEN_ENV = ("REPOWIKI_GITHUB_TOKEN", "GITHUB_TOKEN", "GH_TOKEN")

# matches github/gitlab/bitbucket URLs in various formats
_GIT_URL_RE = re.compile(
    r"(?:https?://)?(?:www\.)?"
    r"(github\.com|gitlab\.com|bitbucket\.org)"
    r"/([^/\s]+)/([^/\s#?.]+)"
)


class GitIngestError(RuntimeError):
    """Clone/ingest failed with a code the API can map to a non-500 response."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def parse_git_url(url: str) -> tuple[str, str, str] | None:
    """extract (host, owner, repo) from a git URL. returns None if not recognized."""
    url = url.strip().rstrip("/")
    # strip trailing .git
    if url.endswith(".git"):
        url = url[:-4]

    m = _GIT_URL_RE.search(url)
    if not m:
        return None
    return m.group(1), m.group(2), m.group(3)


def github_token() -> str:
    """Optional clone token from the environment. Empty for public HTTPS."""
    for key in _TOKEN_ENV:
        val = (os.getenv(key) or "").strip()
        if val:
            return val
    return ""


def _redact(text: str, token: str = "") -> str:
    token = token or github_token()
    if token and token in text:
        return text.replace(token, "***")
    return text


def _clone_url(url: str) -> str:
    """normalize a URL to a proper git clone URL (no credentials)."""
    parsed = parse_git_url(url)
    if not parsed:
        return url  # let git figure it out
    host, owner, repo = parsed
    return f"https://{host}/{owner}/{repo}.git"


def _authenticated_clone_url(url: str, token: str) -> str:
    public = _clone_url(url)
    if not token:
        return public
    parsed = parse_git_url(url)
    if not parsed:
        return public
    host, owner, repo = parsed
    if host != "github.com":
        return public
    return f"https://x-access-token:{token}@{host}/{owner}/{repo}.git"


def cached_clone_path(url: str) -> Path | None:
    """Return the on-disk clone cache for a git URL, if it already exists."""
    parsed = parse_git_url(url)
    if not parsed:
        return None
    host, owner, repo = parsed
    dest = _CLONE_DIR / host / owner / repo
    return dest if dest.is_dir() else None


def _cache_ttl() -> int:
    raw = (os.getenv("REPOWIKI_CLONE_CACHE_TTL") or "").strip()
    if raw.isdigit():
        return int(raw)
    return _DEFAULT_CACHE_TTL


def _cache_is_usable(dest: Path) -> bool:
    return dest.is_dir() and (dest / ".git").exists()


def _cache_is_fresh(dest: Path) -> bool:
    if not _cache_is_usable(dest):
        return False
    try:
        age = time.time() - (dest / ".git").stat().st_mtime
    except OSError:
        return False
    return age < _cache_ttl()


def _classify_clone_stderr(stderr: str) -> tuple[str, str]:
    low = stderr.lower()
    if any(
        tok in low
        for tok in (
            "authentication failed",
            "could not read username",
            "invalid username or token",
            "bad credentials",
        )
    ):
        return (
            "auth_required",
            "GitHub rejected the clone (authentication failed). "
            "For a private repo, set REPOWIKI_GITHUB_TOKEN or GITHUB_TOKEN. "
            "Public repos clone over HTTPS without a token. "
            "LFS files and submodules are not fetched.",
        )
    if "repository not found" in low or (
        "fatal: repository" in low and "not found" in low
    ):
        return (
            "private_or_not_found",
            "GitHub returned not found. The URL may be wrong, or the repo is private. "
            "Private repos need REPOWIKI_GITHUB_TOKEN or GITHUB_TOKEN. "
            "Public shallow clones work without a token. "
            "LFS files and submodules are not fetched.",
        )
    if "403" in low or "permission denied" in low or "access denied" in low:
        return (
            "auth_required",
            "GitHub denied access to this repository. "
            "If it is private, set REPOWIKI_GITHUB_TOKEN or GITHUB_TOKEN. "
            "Public repos do not need a token. LFS files and submodules are not fetched.",
        )
    snippet = _redact(stderr.strip() or "git clone failed")[:240]
    return (
        "clone_failed",
        f"Clone failed: {snippet}. "
        "This path is a public HTTPS --depth 1 clone (120s). "
        "LFS files and submodules are not fetched.",
    )


def _run_git(args: list[str], *, timeout: int, token: str) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            args,
            timeout=timeout,
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.TimeoutExpired as exc:
        raise GitIngestError(
            "clone_timeout",
            f"Clone timed out after {_CLONE_TIMEOUT}s. "
            "The repo may be too large for a shallow clone — import a local path instead. "
            "If it is private, set REPOWIKI_GITHUB_TOKEN or GITHUB_TOKEN. "
            "LFS files and submodules are not fetched.",
        ) from exc
    except subprocess.CalledProcessError as exc:
        stderr = _redact(exc.stderr or "", token)
        code, message = _classify_clone_stderr(stderr)
        raise GitIngestError(code, message) from exc


def _refresh_cache(dest: Path, token: str) -> bool:
    """Fast-forward a stale shallow clone. False means caller should reclone."""
    try:
        _run_git(
            ["git", "-C", str(dest), "fetch", "--depth", "1", "origin"],
            timeout=_CLONE_TIMEOUT,
            token=token,
        )
        _run_git(
            ["git", "-C", str(dest), "reset", "--hard", "FETCH_HEAD"],
            timeout=30,
            token=token,
        )
        return True
    except GitIngestError:
        logger.info("stale clone refresh failed; will reclone %s", dest)
        return False


def ingest_github(
    url: str,
    max_file_size: int = 200 * 1024,
    max_files: int = 1000,
    force_reclone: bool = False,
) -> ProjectContext:
    """shallow-clone a git repo and return a ProjectContext."""
    parsed = parse_git_url(url)
    if not parsed:
        raise GitIngestError("invalid_url", f"Can't parse git URL: {url}")

    host, owner, repo = parsed
    dest = _CLONE_DIR / host / owner / repo
    token = github_token()
    public_url = _clone_url(url)

    if dest.exists() and not _cache_is_usable(dest):
        shutil.rmtree(dest)

    if dest.exists() and not force_reclone:
        if _cache_is_fresh(dest):
            logger.info("Using cached clone: %s", dest)
            return ingest_local(dest, max_file_size=max_file_size, max_files=max_files)
        logger.info("Refreshing stale clone cache: %s", dest)
        if _refresh_cache(dest, token):
            return ingest_local(dest, max_file_size=max_file_size, max_files=max_files)
        shutil.rmtree(dest)
    elif dest.exists() and force_reclone:
        shutil.rmtree(dest)

    dest.parent.mkdir(parents=True, exist_ok=True)
    clone_url = _authenticated_clone_url(url, token)
    logger.info("Cloning %s -> %s", public_url, dest)

    try:
        _run_git(
            ["git", "clone", "--depth", "1", "--single-branch", clone_url, str(dest)],
            timeout=_CLONE_TIMEOUT,
            token=token,
        )
    except GitIngestError:
        if dest.exists():
            shutil.rmtree(dest)
        raise

    # check repo size
    total_mb = sum(f.stat().st_size for f in dest.rglob("*") if f.is_file()) / (1024 * 1024)
    if total_mb > _MAX_REPO_SIZE_MB:
        shutil.rmtree(dest)
        raise GitIngestError(
            "repo_too_large",
            f"Repo too large ({total_mb:.0f} MB > {_MAX_REPO_SIZE_MB} MB). "
            "Import a local checkout, or clone a smaller slice. "
            "LFS files and submodules are not fetched.",
        )

    return ingest_local(dest, max_file_size=max_file_size, max_files=max_files)
