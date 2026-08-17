"""Content language for generated learning/wiki text.

Aligned with RepoWiki:

- Codes: ``en`` / ``zh`` / ``ja`` / ``ko`` (see ``repowiki.llm.prompts._lang_instruction``)
- Source of truth: ``REPOWIKI_LANG`` (and persisted ``~/.repowiki/config.json`` language)
- Optional override: ``RECALLSTACK_CONTENT_LANG``

Deterministic templates use ``t(en, zh=..., ja=..., ko=...)``.
Missing translations fall back to English (same spirit as RepoWiki defaults).
"""

from __future__ import annotations

import os
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator, Literal

ContentLang = Literal["en", "zh", "ja", "ko"]
SUPPORTED_LANGS: tuple[ContentLang, ...] = ("en", "zh", "ja", "ko")

# Keep in sync with repowiki.llm.prompts._lang_instruction
_LANG_INSTRUCTIONS: dict[str, str] = {
    "en": (
        "Write handbook English. Do not write 'You own this step', 'sign off', "
        "or 'Restating the heading does not pass'."
    ),
    "zh": (
        "请用手册体简体中文撰写。直接陈述，不要讲义腔或作业单口吻。"
        "禁止「你负责」「并签字」「过关」「复述标题不算过关」「北极星」"
        "「缺了它哪条能力会断」「用户能察觉的行为会坏」。"
        "ACP、`PtyHandle`、`start_turn` 等 identifier 留英文。"
    ),
    "ja": "日本語で回答してください。",
    "ko": "한국어로 답변해주세요.",
}


def normalize_lang(raw: str | None) -> ContentLang:
    """Normalize free-form language tags to RepoWiki's four codes."""
    code = (raw or "en").strip().lower().replace("_", "-")
    if not code:
        return "en"
    primary = code.split("-", 1)[0]
    if primary in SUPPORTED_LANGS:
        return primary  # type: ignore[return-value]
    # common aliases
    if primary in {"cn", "zh-cn", "zh-tw", "zh-hk"} or code.startswith("zh"):
        return "zh"
    if primary in {"jp"} or code.startswith("ja"):
        return "ja"
    if primary in {"kr"} or code.startswith("ko"):
        return "ko"
    return "en"


_lang_override: ContextVar[ContentLang | None] = ContextVar("content_lang_override", default=None)


def content_lang() -> ContentLang:
    """Resolve active content language (no process-wide cache — tests can override env)."""
    pinned = _lang_override.get()
    if pinned:
        return pinned
    override = os.getenv("RECALLSTACK_CONTENT_LANG")
    if override and override.strip():
        return normalize_lang(override)

    env_lang = os.getenv("REPOWIKI_LANG")
    if env_lang and env_lang.strip():
        return normalize_lang(env_lang)

    try:
        from repowiki.config import Config

        return normalize_lang(Config.load().language)
    except Exception:  # noqa: BLE001
        return "en"


@contextmanager
def content_lang_scope(language: str | None) -> Iterator[ContentLang]:
    """Pin content language for this task (analyze / generate). Does not mutate env."""
    resolved = normalize_lang(language or content_lang())
    token = _lang_override.set(resolved)
    try:
        yield resolved
    finally:
        _lang_override.reset(token)


def lang_instruction(language: str | None = None) -> str:
    """Same instruction strings RepoWiki injects into LLM system prompts."""
    lang = normalize_lang(language or content_lang())
    try:
        from repowiki.llm.prompts import _lang_instruction

        return _lang_instruction(lang)
    except Exception:  # noqa: BLE001
        return _LANG_INSTRUCTIONS.get(lang, _LANG_INSTRUCTIONS["en"])


def t(en: str, zh: str = "", *, ja: str = "", ko: str = "", language: str | None = None) -> str:
    """Pick a localized string for the active (or explicit) content language.

    Usage (matches existing call sites)::

        t("Project goal", "项目目标")
        t("Hello", "你好", ja="こんにちは", ko="안녕하세요")
    """
    lang = normalize_lang(language or content_lang())
    table: dict[str, str] = {
        "en": en,
        "zh": zh or en,
        "ja": ja or en,
        "ko": ko or en,
    }
    return table.get(lang, en)
