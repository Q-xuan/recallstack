"""Structured LLM calls with retry, timeout, and schema validation."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from recallstack.config import RecallStackConfig

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

_JSON_FENCE = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.I)


def extract_json_text(text: str) -> str:
    text = (text or "").strip()
    if not text:
        return ""
    m = _JSON_FENCE.search(text)
    if m:
        return m.group(1).strip()
    # best-effort object/array slice
    for open_c, close_c in (("{", "}"), ("[", "]")):
        start = text.find(open_c)
        end = text.rfind(close_c)
        if start != -1 and end != -1 and end > start:
            return text[start : end + 1]
    return text


class StructuredLLM:
    """Wraps RepoWiki LLMClient with retries and pydantic validation."""

    def __init__(self, llm, config: RecallStackConfig | None = None):
        self.llm = llm
        self.config = config or RecallStackConfig.load()

    async def complete_model(
        self,
        messages: list[dict],
        model_type: type[T],
        *,
        temperature: float | None = None,
        allow_repair: bool = True,
    ) -> T | None:
        last_err: Exception | None = None
        retries = max(1, self.config.llm_max_retries)
        for attempt in range(retries):
            try:
                raw = await asyncio.wait_for(
                    self.llm.complete(
                        messages,
                        temperature=temperature
                        if temperature is not None
                        else self.config.llm_temperature,
                        response_format={"type": "json_object"},
                    ),
                    timeout=self.config.llm_timeout_seconds,
                )
                if isinstance(raw, str) and raw.startswith("[LLM Error:"):
                    raise RuntimeError(raw)
                parsed = self._parse(raw, model_type)
                if parsed is not None:
                    return parsed
                if allow_repair and attempt + 1 < retries:
                    messages = list(messages) + [
                        {
                            "role": "user",
                            "content": (
                                "Your previous output failed schema validation. "
                                "Return corrected JSON only, no markdown."
                            ),
                        }
                    ]
                    allow_repair = False
            except Exception as exc:  # noqa: BLE001
                last_err = exc
                logger.warning("structured LLM attempt %s failed: %s", attempt + 1, type(exc).__name__)
                await asyncio.sleep(min(2**attempt, 8))
        if last_err:
            logger.error("structured LLM failed: %s", last_err)
        return None

    def _parse(self, raw: str, model_type: type[T]) -> T | None:
        text = extract_json_text(raw)
        if not text:
            return None
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return None
        try:
            return model_type.model_validate(data)
        except ValidationError:
            return None
