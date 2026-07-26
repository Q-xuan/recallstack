"""Unit tests for the wiki Q&A grounding layer."""

from __future__ import annotations

import asyncio

from recallstack.learning.wiki_qa import answer_question, fallback_answer, select_context
from recallstack.learning.wiki_search import SearchDocument


def _docs() -> list[SearchDocument]:
    return [
        SearchDocument(
            page_id="index",
            title="Overview",
            kind="overview",
            content="# Overview\nThe scanner walks the repository tree.",
        ),
        SearchDocument(
            page_id="modules/app",
            title="app",
            kind="module",
            content="# app\nThe boot function starts the service." + " filler" * 3000,
        ),
    ]


def test_select_context_ranks_and_trims():
    picked = select_context(_docs(), "boot function")
    assert picked
    assert picked[0]["page_id"] == "modules/app"
    # long pages are cut to the per-page budget so the prompt stays bounded
    assert all(len(p["content"]) <= 5000 for p in picked)


class _FakeLLM:
    def __init__(self, reply: str):
        self.reply = reply
        self.messages = None

    async def complete(self, messages, **kwargs):
        self.messages = messages
        return self.reply


def test_llm_answer_carries_engine_and_sources():
    llm = _FakeLLM("Boot lives in [app](modules/app).")
    result = asyncio.run(
        answer_question("where is boot?", _docs(), project_name="demo", llm=llm)
    )
    assert result["engine"] == "llm"
    assert "modules/app" in result["answer"]
    assert any(s["page_id"] == "modules/app" for s in result["sources"])
    # the context block actually contains the page the model cites
    assert 'id="modules/app"' in llm.messages[1]["content"]


def test_llm_error_text_degrades_to_search():
    llm = _FakeLLM("[LLM Error: HTTP 500]")
    result = asyncio.run(
        answer_question("where is boot?", _docs(), project_name="demo", llm=llm)
    )
    assert result["engine"] == "search"
    assert result["sources"]


def test_fallback_answer_without_hits():
    assert "没有找到" in fallback_answer("q", [])
