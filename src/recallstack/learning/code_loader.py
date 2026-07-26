"""Safely load source snippets for hints and evidence UI (local repos only)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from recallstack.security import (
    is_blocked_filename,
    normalize_repo_path,
    validate_local_path,
)


def resolve_local_repo_root(source_location: str) -> Path | None:
    """Return resolved local root or None when not available."""
    try:
        return validate_local_path(source_location)
    except Exception:  # noqa: BLE001 — treat any security/path error as unavailable
        return None


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
