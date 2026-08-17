"""Lazy first-principles teaching notes for SourcePeek.

Overlay only — never writes comments into the scanned repo. Generated on first
peek, cached by ``(repo_version_id, path, start_line, content_hash)``.

Analyze stays on ``REPOWIKI_MODEL`` (Jake: deepseek-v4-flash). This small call
uses ``REPOWIKI_ANNOTATE_MODEL`` (default ``openai/deepseek-v4-flash``, same as
analyze). Optional ``REPOWIKI_ANNOTATE_API_KEY`` / ``REPOWIKI_ANNOTATE_API_BASE``
fall back to the existing key and base. Thinking is disabled (same as
structured wiki JSON).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
from pathlib import Path
from typing import Any

from recallstack.learning.learning_contract import pass_gate, path_principles

logger = logging.getLogger(__name__)

# Non-flash sibling. Do not invent ids that are not on the hub.
DEFAULT_ANNOTATE_MODEL = "openai/deepseek-v4-flash"
MAX_NOTES = 3
MAX_NOTE_CHARS = 120
MAX_TOKENS = 280
ANNOTATE_TIMEOUT_SECONDS = 12.0
_CACHE_DIR = Path("data") / "peek_annotations"

_SYNTAX_NARRATION_RE = re.compile(
    r"(这是一个|这是函数|这是结构体|这是变量|这是类型|"
    r"this (is|defines) (a )?(function|struct|variable|type)|"
    r"语法|syntax narration|docstring)",
    re.I,
)

ANNOTATE_SYSTEM = (
    "你是源码手册助教。"
    "只标出证明不变量的行：状态怎么变、谁调用谁、失败时怎样。"
    "不要讲语法，不要复述标识符，不要写 docstring，不要把注释写进仓库。"
    "对读者用「你」，中文手册口吻。不要写「你负责」「并签字」「过关」。"
    "没有承重行就返回空数组。"
    "行号必须出现在给定片段里，禁止发明片段外的行。"
)


def snippet_content_hash(snippet: str) -> str:
    return hashlib.sha256((snippet or "").encode("utf-8")).hexdigest()[:16]


def annotation_cache_key(
    version_id: str,
    path: str,
    start_line: int,
    content_hash: str,
) -> str:
    raw = f"{version_id}\0{path}\0{int(start_line)}\0{content_hash}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _cache_path(key: str) -> Path:
    return _CACHE_DIR / f"{key}.json"


def load_cached_annotations(key: str) -> list[dict[str, Any]] | None:
    path = _cache_path(key)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    notes = data.get("notes") if isinstance(data, dict) else data
    if not isinstance(notes, list):
        return None
    return [item for item in notes if isinstance(item, dict)]


def save_cached_annotations(key: str, notes: list[dict[str, Any]]) -> None:
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    _cache_path(key).write_text(
        json.dumps({"notes": notes}, ensure_ascii=False),
        encoding="utf-8",
    )


def build_annotate_messages(
    *,
    path: str,
    start_line: int,
    end_line: int,
    snippet: str,
    principles: str = "",
    pass_gate_text: str = "",
) -> list[dict[str, str]]:
    numbered: list[str] = []
    for offset, raw in enumerate((snippet or "").splitlines()):
        numbered.append(f"{start_line + offset}|{raw}")
    body = [
        f"文件：{path}",
        f"行：{start_line}-{end_line}",
        "",
        "原理：",
        (principles or "").strip() or "（无）",
        "",
        "核对：",
        (pass_gate_text or "").strip() or "（无）",
        "",
        "片段（行号|源码）：",
        "\n".join(numbered) if numbered else "（空）",
        "",
        "输出 JSON 对象：{\"notes\":[{\"line\":791,\"note\":\"这一行保证…\"}]}。"
        f"最多 {MAX_NOTES} 条。note 用中文、对你说这一行保证了什么。"
        "只标承重行。不要语法叙述。没有就 {\"notes\":[]}。",
    ]
    return [
        {"role": "system", "content": ANNOTATE_SYSTEM},
        {"role": "user", "content": "\n".join(body)},
    ]


def _step_context(slug: str) -> tuple[str, str]:
    if not slug:
        return "", ""
    concept = type("C", (), {"slug": slug, "title": slug})()
    return path_principles(concept), pass_gate(concept)


def sanitize_notes(
    raw: Any,
    *,
    path: str,
    start_line: int,
    end_line: int,
) -> list[dict[str, Any]]:
    if isinstance(raw, dict):
        items = raw.get("notes")
        if items is None and {"line", "note"} <= set(raw):
            items = [raw]
    else:
        items = raw
    if not isinstance(items, list):
        return []
    out: list[dict[str, Any]] = []
    seen: set[int] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        try:
            line = int(item.get("line"))
        except (TypeError, ValueError):
            continue
        if line < start_line or line > end_line or line in seen:
            continue
        note = str(item.get("note") or "").strip()
        if not note or _SYNTAX_NARRATION_RE.search(note):
            continue
        if len(note) > MAX_NOTE_CHARS:
            note = note[: MAX_NOTE_CHARS - 1].rstrip() + "…"
        seen.add(line)
        out.append({"path": path, "line": line, "note": note})
        if len(out) >= MAX_NOTES:
            break
    return out


def parse_model_notes(text: str, *, path: str, start_line: int, end_line: int) -> list[dict[str, Any]]:
    from recallstack.llm.structured import extract_json_text

    blob = extract_json_text(text or "")
    if not blob:
        return []
    try:
        data = json.loads(blob)
    except json.JSONDecodeError:
        return []
    return sanitize_notes(data, path=path, start_line=start_line, end_line=end_line)


def annotate_model_id() -> str:
    return (os.getenv("REPOWIKI_ANNOTATE_MODEL") or "").strip() or DEFAULT_ANNOTATE_MODEL


def build_annotate_llm():
    """Stronger-model client for peek notes, or None when no key."""
    try:
        from repowiki.config import Config as RepoWikiConfig
        from repowiki.llm.client import LLMClient
    except Exception:  # noqa: BLE001
        return None
    rw = RepoWikiConfig.load()
    key = (os.getenv("REPOWIKI_ANNOTATE_API_KEY") or "").strip() or rw.api_key
    base = (os.getenv("REPOWIKI_ANNOTATE_API_BASE") or "").strip() or rw.api_base
    if not key:
        return None
    return LLMClient(model=annotate_model_id(), api_key=key, api_base=base or "")


async def annotations_for_snippet(
    *,
    version_id: str,
    path: str,
    start_line: int,
    end_line: int,
    snippet: str,
    slug: str = "",
    llm: Any | None = None,
) -> list[dict[str, Any]]:
    """Return 0–3 overlay notes. Fail soft: never raise into the peek."""
    if not (snippet or "").strip():
        return []
    digest = snippet_content_hash(snippet)
    key = annotation_cache_key(version_id, path, start_line, digest)
    cached = load_cached_annotations(key)
    if cached is not None:
        return sanitize_notes(cached, path=path, start_line=start_line, end_line=end_line)

    client = llm if llm is not None else build_annotate_llm()
    if client is None:
        return []

    principles, gate = _step_context(slug)
    messages = build_annotate_messages(
        path=path,
        start_line=start_line,
        end_line=end_line,
        snippet=snippet,
        principles=principles,
        pass_gate_text=gate,
    )
    try:
        raw = await asyncio.wait_for(
            client.complete(
                messages,
                temperature=0.15,
                max_tokens=MAX_TOKENS,
                response_format={"type": "json_object"},
                timeout=ANNOTATE_TIMEOUT_SECONDS,
            ),
            timeout=ANNOTATE_TIMEOUT_SECONDS + 2,
        )
    except Exception as exc:  # noqa: BLE001
        logger.info("peek annotate failed soft: %s", type(exc).__name__)
        return []
    if isinstance(raw, str) and raw.startswith("[LLM Error:"):
        logger.info("peek annotate LLM error (soft)")
        return []
    notes = parse_model_notes(raw, path=path, start_line=start_line, end_line=end_line)
    try:
        save_cached_annotations(key, notes)
    except OSError:
        logger.debug("peek annotate cache write skipped")
    return notes


def prefetch_annotations_sync(
    *,
    version_id: str,
    path: str,
    start_line: int,
    end_line: int,
    snippet: str,
    slug: str = "",
) -> None:
    """Warm the cache after learning-path GET. Never raises."""
    try:
        asyncio.run(
            annotations_for_snippet(
                version_id=version_id,
                path=path,
                start_line=start_line,
                end_line=end_line,
                snippet=snippet,
                slug=slug,
            )
        )
    except Exception:  # noqa: BLE001
        logger.debug("peek annotate prefetch skipped")


_CHIP_LOC_RE = re.compile(
    r"^((?:[A-Za-z0-9_.@-]+/)*[A-Za-z0-9_.@-]+\.[A-Za-z0-9]+)(?::(\d+)(?:-\d+)?)?"
)


def parse_evidence_chip(chip: str) -> tuple[str, int] | None:
    loc = (chip or "").strip().strip("`")
    if not loc:
        return None
    loc = loc.split()[0]
    match = _CHIP_LOC_RE.match(loc)
    if not match:
        return None
    return match.group(1), int(match.group(2) or 1)


