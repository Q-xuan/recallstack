"""Load source snippets for the wiki peek and learning hints.

Prefers scanned file text persisted at analyze time so GitHub/cloned
repos can still expand citations. Falls back to the local working copy
or the GitHub clone cache. Secrets are never served.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from recallstack.learning.i18n import t
from recallstack.security import (
    is_blocked_filename,
    normalize_repo_path,
    validate_local_path,
)

logger = logging.getLogger(__name__)

_VERSION_FILES_DIR = Path("data") / "version_files"


def _package_repo_root() -> Path:
    # src/recallstack/learning/code_loader.py → checkout root
    return Path(__file__).resolve().parents[3]


def version_file_lookup_paths(version_id: str) -> list[Path]:
    """CWD, RECALLSTACK_DATA_DIR, then the checkout's data/version_files."""
    name = f"{str(version_id).strip()}.json"
    if name == ".json":
        return []
    seen: set[str] = set()
    out: list[Path] = []

    def add(path: Path) -> None:
        key = str(path)
        if key in seen:
            return
        seen.add(key)
        out.append(path)

    data_dir = os.environ.get("RECALLSTACK_DATA_DIR", "").strip()
    if data_dir:
        add(Path(data_dir) / "version_files" / name)
    add(Path("data") / "version_files" / name)
    add(_package_repo_root() / "data" / "version_files" / name)
    return out


def missing_working_copy_message() -> str:
    return t(
        "This file is not in the scanned working copy.",
        "找不到工作副本里的这个文件",
    )


def resolve_local_repo_root(source_location: str) -> Path | None:
    """Return resolved local root or None when not available."""
    try:
        return validate_local_path(source_location)
    except Exception:  # noqa: BLE001 — treat any security/path error as unavailable
        return None


def version_files_path(version_id: str) -> Path:
    return _VERSION_FILES_DIR / f"{str(version_id).strip()}.json"


def save_version_file_texts(version_id: str, files: dict[str, str]) -> None:
    """Persist scanned file texts keyed by repo-relative path."""
    _VERSION_FILES_DIR.mkdir(parents=True, exist_ok=True)
    clean: dict[str, str] = {}
    for raw_path, text in files.items():
        path = normalize_repo_path(raw_path)
        if not path or not text or is_blocked_filename(path):
            continue
        if ".." in path.split("/") or path.startswith("/"):
            continue
        clean[path] = text
    version_files_path(version_id).write_text(
        json.dumps(clean, ensure_ascii=False),
        encoding="utf-8",
    )


def load_version_file_texts(version_id: str) -> dict[str, str]:
    vid = str(version_id or "").strip()
    if not vid:
        return {}
    tried: list[str] = []
    for path in version_file_lookup_paths(vid):
        tried.append(str(path))
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            logger.warning("learning-path: failed to parse scan store %s", path)
            continue
        if not isinstance(data, dict):
            continue
        texts = {
            str(k): str(v)
            for k, v in data.items()
            if isinstance(k, str) and isinstance(v, str)
        }
        logger.debug("learning-path: loaded %d files from %s", len(texts), path)
        return texts
    logger.warning(
        "learning-path: scan store missing for version %s (tried %s)",
        vid,
        tried,
    )
    return {}


def _read_under(root: Path, rel: str) -> str | None:
    if not root.is_dir():
        return None
    root = root.resolve()
    file_path = (root / rel).resolve()
    try:
        file_path.relative_to(root)
    except ValueError:
        return None
    if not file_path.is_file():
        return None
    try:
        return file_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _github_clone_root(source_location: str) -> Path | None:
    try:
        from repowiki.ingest.github import cached_clone_path

        return cached_clone_path(source_location)
    except Exception:  # noqa: BLE001
        logger.debug("github clone lookup failed for %s", source_location, exc_info=True)
        return None


def resolve_file_text(
    *,
    source_type: str,
    source_location: str,
    rel_path: str,
    version_id: str | None = None,
) -> str | None:
    """Return full file text from scan cache, local disk, or github clone cache."""
    rel = normalize_repo_path(rel_path)
    if not rel or ".." in rel.split("/") or rel.startswith("/"):
        return None
    if is_blocked_filename(rel):
        return None

    if version_id:
        cached = load_version_file_texts(version_id).get(rel)
        if cached:
            return cached

    if source_type == "local":
        root = resolve_local_repo_root(source_location)
        if root:
            text = _read_under(root, rel)
            if text is not None:
                return text

    clone = _github_clone_root(source_location)
    if clone:
        return _read_under(clone, rel)
    return None


def slice_lines(text: str, start_line: int | None, end_line: int | None) -> tuple[str, int, int]:
    lines = text.splitlines()
    if not lines:
        return "", 1, 1
    s = max(1, start_line or 1)
    s = min(s, len(lines))
    e = min(len(lines), end_line or (s + 40))
    e = max(e, s)
    snippet = "\n".join(lines[s - 1 : e])
    return snippet, s, e


def load_code_lookup(
    root: Path,
    source_references: list[dict[str, Any]] | None,
    *,
    max_files: int = 6,
    max_bytes: int = 120_000,
) -> dict[str, str]:
    """Map relative repo paths → full file text for referenced sources.

    Paths must stay under ``root``. Secrets / blocked filenames are skipped.
    """
    lookup: dict[str, str] = {}
    if not root or not root.is_dir():
        return lookup

    root = root.resolve()
    seen: list[str] = []
    for ref in source_references or []:
        path = normalize_repo_path(ref.get("path") or "")
        if not path or path in lookup or path in seen:
            continue
        if ".." in path.split("/") or path.startswith("/"):
            continue
        if is_blocked_filename(path):
            continue
        seen.append(path)
        if len(seen) > max_files * 2:
            break
        abs_path = (root / path).resolve()
        try:
            abs_path.relative_to(root)
        except ValueError:
            continue
        if not abs_path.is_file():
            continue
        try:
            if abs_path.stat().st_size > max_bytes:
                continue
            text = abs_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        lookup[path] = text
        if len(lookup) >= max_files:
            break
    return lookup


def snippet_for_ref(
    code_lookup: dict[str, str],
    ref: dict[str, Any],
    *,
    context_lines: int = 2,
    max_lines: int = 12,
) -> str:
    """Extract a short window around start/end lines for one reference."""
    path = str(ref.get("path") or "").replace("\\", "/")
    text = code_lookup.get(path)
    if not text:
        return ""
    lines = text.splitlines()
    if not lines:
        return ""

    start = ref.get("start_line")
    end = ref.get("end_line")
    if start is None:
        # first non-empty lines as fallback
        body = [ln for ln in lines[:max_lines] if ln.strip()]
        return "\n".join(body[:max_lines])

    s = max(1, int(start)) - 1
    e = int(end) if end is not None else s + 1
    s = max(0, s - context_lines)
    e = min(len(lines), max(e, s + 1) + context_lines)
    e = min(e, s + max_lines)
    return "\n".join(lines[s:e])
