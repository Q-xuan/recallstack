"""RecallStack configuration (separate from RepoWiki cache/config)."""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from recallstack.learning.i18n import normalize_lang

load_dotenv()

DEFAULT_USER_ID = "00000000-0000-4000-8000-000000000001"


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class RecallStackConfig:
    database_url: str = "sqlite:///./data/recallstack.db"
    default_user_id: str = DEFAULT_USER_ID
    fsrs_desired_retention: float = 0.9
    max_repository_size_mb: int = 200
    max_file_size_kb: int = 200
    llm_timeout_seconds: float = 60.0
    llm_max_retries: int = 3
    llm_temperature: float = 0.2
    llm_max_concurrency: int = 3
    # Master switch for optional LLM enrichment (evaluation today; generation later).
    llm_enabled: bool = True
    llm_evaluation: bool = True
    # Content language for generated wiki/learning text — same codes as RepoWiki (en/zh/ja/ko).
    # Resolved from RECALLSTACK_CONTENT_LANG → REPOWIKI_LANG → RepoWiki config → en.
    content_lang: str = "en"
    max_concepts: int = 20
    max_items_per_concept: int = 3
    prompt_version: str = "v1"

    # score → FSRS rating thresholds
    rating_again_below: float = 0.40
    rating_hard_below: float = 0.65
    rating_good_below: float = 0.90

    @classmethod
    def load(cls) -> RecallStackConfig:
        def _float(name: str, default: float) -> float:
            raw = os.getenv(name)
            if raw is None or raw == "":
                return default
            return float(raw)

        def _int(name: str, default: int) -> int:
            raw = os.getenv(name)
            if raw is None or raw == "":
                return default
            return int(raw)

        cfg = cls(
            database_url=os.getenv(
                "RECALLSTACK_DATABASE_URL", "sqlite:///./data/recallstack.db"
            ),
            default_user_id=os.getenv("RECALLSTACK_DEFAULT_USER_ID", DEFAULT_USER_ID),
            fsrs_desired_retention=_float("RECALLSTACK_FSRS_DESIRED_RETENTION", 0.9),
            max_repository_size_mb=_int("RECALLSTACK_MAX_REPOSITORY_SIZE_MB", 200),
            max_file_size_kb=_int("RECALLSTACK_MAX_FILE_SIZE_KB", 200),
            llm_timeout_seconds=_float("REPOWIKI_LLM_TIMEOUT_SECONDS", 60.0),
            llm_max_retries=_int("REPOWIKI_LLM_MAX_RETRIES", 3),
            llm_enabled=_env_bool("RECALLSTACK_LLM_ENABLED", True),
            llm_evaluation=_env_bool("RECALLSTACK_LLM_EVALUATION", True),
            content_lang="en",
        )

        # validate UUID-shaped default user id
        try:
            uuid.UUID(cfg.default_user_id)
        except ValueError:
            cfg.default_user_id = DEFAULT_USER_ID

        # content language: explicit override → REPOWIKI_LANG → RepoWiki config file
        override = os.getenv("RECALLSTACK_CONTENT_LANG")
        if override and override.strip():
            cfg.content_lang = normalize_lang(override)
        elif os.getenv("REPOWIKI_LANG"):
            cfg.content_lang = normalize_lang(os.getenv("REPOWIKI_LANG"))
        else:
            try:
                from repowiki.config import Config as RepoWikiConfig

                cfg.content_lang = normalize_lang(RepoWikiConfig.load().language)
            except Exception:  # noqa: BLE001
                cfg.content_lang = "en"

        # ensure sqlite parent dir exists for relative paths
        if cfg.database_url.startswith("sqlite:///./"):
            db_path = Path(cfg.database_url.removeprefix("sqlite:///"))
            db_path.parent.mkdir(parents=True, exist_ok=True)

        return cfg
