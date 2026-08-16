"""Unit tests for the wiki Q&A grounding layer."""

from __future__ import annotations

import asyncio

from recallstack.learning.wiki_qa import (
    answer_question,
    fallback_answer,
    select_context,
    stream_answer_question,
)
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


def test_fallback_answer_without_hits(monkeypatch):
    monkeypatch.setenv("RECALLSTACK_CONTENT_LANG", "zh")
    assert "没有找到" in fallback_answer("q", [])


class _FakeStreamLLM:
    def __init__(self, chunks: list[str]):
        self.chunks = chunks

    async def stream(self, messages, **kwargs):
        for chunk in self.chunks:
            yield chunk


def test_stream_answer_yields_tokens_then_done():
    llm = _FakeStreamLLM(["Boot ", "lives in app."])
    events = asyncio.run(
        _collect_stream("where is boot?", llm)
    )
    types = [e["type"] for e in events]
    assert types[0] == "meta"
    assert events[0]["engine"] == "llm"
    assert [e.get("content") for e in events if e["type"] == "content"] == [
        "Boot ",
        "lives in app.",
    ]
    assert types[-1] == "done"


def test_stream_without_llm_falls_back_to_search():
    events = asyncio.run(_collect_stream("where is boot?", None))
    assert events[0]["type"] == "meta"
    assert events[0]["engine"] == "search"
    assert events[1]["type"] == "content"
    assert events[1]["content"]
    assert events[-1]["type"] == "done"


def test_stream_llm_error_falls_back_to_search():
    llm = _FakeStreamLLM(["[LLM Error: HTTP 500]"])
    events = asyncio.run(_collect_stream("where is boot?", llm))
    assert any(e["type"] == "fallback" and e["engine"] == "search" for e in events)
    assert events[-1]["type"] == "done"


async def _collect_stream(question: str, llm):
    out = []
    async for event in stream_answer_question(
        question, _docs(), project_name="demo", llm=llm
    ):
        out.append(event)
    return out


def test_history_reaches_the_model_and_retrieval():
    llm = _FakeLLM("It is called from boot.")
    history = [{"question": "where is boot?", "answer": "Boot lives in [app](modules/app)."}]
    result = asyncio.run(
        answer_question("它在哪里被调用?", _docs(), project_name="demo", llm=llm, history=history)
    )
    assert result["engine"] == "llm"
    # prior turn replayed as user/assistant messages before the final question
    roles = [m["role"] for m in llm.messages]
    assert roles == ["system", "user", "assistant", "user"]
    assert llm.messages[1]["content"] == "where is boot?"
    # a term-free follow-up still retrieves via the previous question's terms
    assert any(s["page_id"] == "modules/app" for s in result["sources"])
