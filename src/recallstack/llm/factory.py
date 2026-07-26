"""Build StructuredLLM when provider credentials are available."""

from __future__ import annotations

import logging

from recallstack.config import RecallStackConfig
from recallstack.llm.structured import StructuredLLM

logger = logging.getLogger(__name__)


def build_structured_llm(config: RecallStackConfig | None = None) -> StructuredLLM | None:
    """Return a StructuredLLM client, or None when LLM is unavailable."""
    cfg = config or RecallStackConfig.load()
    if not cfg.llm_enabled:
        return None
    try:
        from repowiki.config import Config as RepoWikiConfig
        from repowiki.llm.client import LLMClient
    except Exception as exc:  # noqa: BLE001
        logger.warning("LLM imports unavailable: %s", type(exc).__name__)
        return None

    rw = RepoWikiConfig.load()
    if not rw.api_key or not rw.model:
        return None
    try:
        client = LLMClient(model=rw.model, api_key=rw.api_key, api_base=rw.api_base or "")
        return StructuredLLM(client, cfg)
    except Exception as exc:  # noqa: BLE001
        logger.warning("failed to build LLM client: %s", type(exc).__name__)
        return None
