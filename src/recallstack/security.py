"""Security helpers for repository ingestion."""

from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import urlparse

ALLOWED_GIT_HOSTS = {"github.com", "gitlab.com", "bitbucket.org"}
_HTTPS_RE = re.compile(r"^https://", re.IGNORECASE)

# common secrets / junk that must never leave the sandbox
BLOCKED_NAME_PATTERNS = (
    re.compile(r"^\.env(\.|$)"),
    re.compile(r".*\.(pem|key|p12|pfx|crt|cer)$", re.I),
    re.compile(r"^(id_rsa|id_dsa|id_ecdsa|id_ed25519)$"),
    re.compile(r".*secret.*", re.I),
    re.compile(r".*credential.*", re.I),
)


class SecurityError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def validate_git_url(url: str) -> str:
    """Only allow https Git URLs to known hosts. Reject ssh/file/custom schemes."""
    raw = (url or "").strip()
    if not raw:
        raise SecurityError("invalid_git_url", "Git URL is empty")

    lower = raw.lower()
    if lower.startswith(("file://", "ssh://", "git@", "git://")):
        raise SecurityError("forbidden_scheme", "Only https Git URLs are allowed")

    if not _HTTPS_RE.match(raw):
        # bare github.com/owner/repo is ok after normalize
        if "://" in raw:
            raise SecurityError("forbidden_scheme", "Only https Git URLs are allowed")
        raw = "https://" + raw.lstrip("/")

    parsed = urlparse(raw)
    if parsed.scheme.lower() != "https":
        raise SecurityError("forbidden_scheme", "Only https Git URLs are allowed")
    host = (parsed.hostname or "").lower()
    if host not in ALLOWED_GIT_HOSTS:
        raise SecurityError("forbidden_host", f"Host not allowed: {host or 'unknown'}")
    path_parts = [p for p in parsed.path.split("/") if p]
    if len(path_parts) < 2:
        raise SecurityError("invalid_git_url", "Git URL must include owner and repo")
    return f"https://{host}/{path_parts[0]}/{path_parts[1].removesuffix('.git')}.git"


def validate_local_path(path: str, *, allow_root: Path | None = None) -> Path:
    """Resolve local path and ensure it stays inside allowed roots."""
    if not path or not str(path).strip():
        raise SecurityError("invalid_local_path", "Local path is empty")
    if str(path).lower().startswith("file:"):
        raise SecurityError("forbidden_scheme", "file:// paths are not allowed")

    resolved = Path(path).expanduser().resolve()
    if not resolved.exists() or not resolved.is_dir():
        raise SecurityError("path_not_found", f"Directory not found: {resolved.name}")

    # prevent reading outside an optional sandbox root
    if allow_root is not None:
        root = allow_root.resolve()
        try:
            resolved.relative_to(root)
        except ValueError as exc:
            raise SecurityError(
                "path_escape", "Local path escapes allowed root"
            ) from exc

    return resolved


def is_blocked_filename(name: str) -> bool:
    base = Path(name).name
    return any(p.search(base) for p in BLOCKED_NAME_PATTERNS)


def normalize_repo_path(path: str) -> str:
    """Canonical repo-relative form: forward slashes, no leading ``./`` or ``/``.

    ``lstrip("./")`` is not usable here — it strips a *character set*, so it
    eats the leading dot of ``.env.example`` and ``.github/workflows/ci.yml``
    and yields a path that no longer exists on disk.
    """
    text = str(path).replace("\\", "/")
    while text.startswith("./"):
        text = text[2:]
    return text.lstrip("/")


def filter_source_references(
    refs: list[dict],
    valid_paths: set[str],
) -> list[dict]:
    """Drop references that do not exist in the scanned file set.

    Both sides are normalised first. Ingestion on Windows yields
    ``src\\pkg\\mod.py`` while references arrive as ``src/pkg/mod.py``, and
    comparing the two forms directly drops every reference below the repository
    root — leaving concepts anchored only to top-level files.
    """
    allowed = {normalize_repo_path(p) for p in valid_paths}
    cleaned: list[dict] = []
    for ref in refs:
        path = normalize_repo_path(ref.get("path", ""))
        if not path or path not in allowed:
            continue
        if is_blocked_filename(path):
            continue
        item = dict(ref)
        item["path"] = path
        cleaned.append(item)
    return cleaned
