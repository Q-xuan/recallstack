"""Answer free-form questions about a repository from its generated wiki.

The retrieval layer is the deterministic wiki search: it ranks pages, the top
pages become the model's only context, and the model is told to cite them. So
every answer is grounded in pages the reader can open, and when no LLM key is
configured the same retrieval degrades into an extractive answer instead of a
dead feature.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Any

from recallstack.learning.i18n import t
from recallstack.learning.wiki_search import SearchDocument, search

logger = logging.getLogger(__name__)

# Context budget in characters, not tokens: the corpus is our own generated
# markdown, where ~3 chars/token is a safe planning ratio for mixed zh/en.
MAX_PAGES = 4
PAGE_CHAR_BUDGET = 5000
ANSWER_MAX_TOKENS = 1400

_SYSTEM_PROMPT = """\
You are the wiki assistant for the repository "{project}". Answer the reader's
question using ONLY the wiki excerpts provided. Rules:

- Answer in the same language as the question.
- Cite the pages you drew from as inline markdown links whose target is the
  page id exactly as given (it is a route, not a URL). Example: a page with
  id "modules/core" and title "core" is cited as [core](modules/core).
- Quote file paths and symbols in backticks.
- If the excerpts do not contain the answer, say so plainly and point to the
  closest page instead of guessing.
- Be concise: a few short paragraphs or a list, no preamble.
"""


def select_context(
    docs: list[SearchDocument], question: str, limit: int = MAX_PAGES
) -> list[dict[str, Any]]:
    """Rank pages against the question and keep the top few, trimmed to budget."""
    ranked = search(docs, question, limit=limit)
    by_id = {d.page_id: d for d in docs}
    picked: list[dict[str, Any]] = []
    for row in ranked:
        doc = by_id.get(row["page_id"])
        if doc is None:
            continue
        picked.append(
            {
                "page_id": doc.page_id,
                "title": doc.title,
                "kind": doc.kind,
                "snippet": row["snippet"],
                "content": doc.content[:PAGE_CHAR_BUDGET],
            }
        )
    return picked


def _context_block(sources: list[dict[str, Any]]) -> str:
    parts = []
    for src in sources:
        parts.append(
            f'<page id="{src["page_id"]}" title="{src["title"]}">\n{src["content"]}\n</page>'
        )
    return "\n\n".join(parts)


def fallback_answer(question: str, sources: list[dict[str, Any]]) -> str:
    """Extractive answer when no LLM is configured: point at the best pages."""
    if not sources:
        return t(
            "No wiki page matched this question. Try different keywords, or regenerate the wiki.",
            "在 Wiki 中没有找到与这个问题相关的页面。换个关键词试试,或先重新生成 Wiki。",
        )
    lines = [
        t(
            "No LLM is configured. These wiki pages are the closest match:",
            "没有配置 LLM,以下是与问题最相关的 Wiki 页面:",
        ),
        "",
    ]
    for src in sources:
        snippet = f" — {src['snippet']}" if src.get("snippet") else ""
        lines.append(f"- [{src['title']}]({src['page_id']}){snippet}")
    return "\n".join(lines)


# Keep replayed answers short: they anchor pronouns, they are not the context.
HISTORY_TURNS = 4
HISTORY_ANSWER_CHARS = 1500


async def answer_question(
    question: str,
    docs: list[SearchDocument],
    *,
    project_name: str,
    llm: Any | None = None,
    history: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Return ``{answer, engine, sources}``; never raises on LLM failure."""
    history = (history or [])[-HISTORY_TURNS:]
    # A follow-up like "它在哪里被调用?" carries no searchable terms of its own,
    # so the previous question joins the retrieval query.
    retrieval_query = question
    if history:
        retrieval_query = f"{history[-1]['question']} {question}"
    sources = select_context(docs, retrieval_query)
    slim = [{k: s[k] for k in ("page_id", "title", "kind", "snippet")} for s in sources]

    if llm is None or not sources:
        return {"answer": fallback_answer(question, slim), "engine": "search", "sources": slim}

    messages = _qa_messages(project_name, sources, question, history)
    try:
        text = await llm.complete(messages, temperature=0.2, max_tokens=ANSWER_MAX_TOKENS)
    except Exception as exc:  # noqa: BLE001
        logger.warning("wiki QA LLM call failed: %s", type(exc).__name__)
        text = ""
    # The client reports transport-level failures inline rather than raising.
    if not text or text.startswith("[LLM Error"):
        return {"answer": fallback_answer(question, slim), "engine": "search", "sources": slim}
    return {"answer": text, "engine": "llm", "sources": slim}


def _qa_messages(
    project_name: str,
    sources: list[dict[str, Any]],
    question: str,
    history: list[dict[str, str]],
) -> list[dict[str, str]]:
    messages = [{"role": "system", "content": _SYSTEM_PROMPT.format(project=project_name)}]
    for turn in history:
        messages.append({"role": "user", "content": turn["question"]})
        messages.append({"role": "assistant", "content": turn["answer"][:HISTORY_ANSWER_CHARS]})
    messages.append(
        {
            "role": "user",
            "content": f"{_context_block(sources)}\n\nQuestion: {question}",
        }
    )
    return messages


async def stream_answer_question(
    question: str,
    docs: list[SearchDocument],
    *,
    project_name: str,
    llm: Any | None = None,
    history: list[dict[str, str]] | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """Yield SSE payloads: meta, content chunks, optional fallback, then done."""
    history = (history or [])[-HISTORY_TURNS:]
    retrieval_query = question
    if history:
        retrieval_query = f"{history[-1]['question']} {question}"
    sources = select_context(docs, retrieval_query)
    slim = [{k: s[k] for k in ("page_id", "title", "kind", "snippet")} for s in sources]

    if llm is None or not sources:
        yield {"type": "meta", "engine": "search", "sources": slim}
        yield {"type": "content", "content": fallback_answer(question, slim)}
        yield {"type": "done"}
        return

    yield {"type": "meta", "engine": "llm", "sources": slim}
    messages = _qa_messages(project_name, sources, question, history)
    try:
        stream = llm.stream(messages, temperature=0.2, max_tokens=ANSWER_MAX_TOKENS)
        async for chunk in stream:
            if not chunk:
                continue
            if str(chunk).startswith("[LLM Error"):
                yield {
                    "type": "fallback",
                    "engine": "search",
                    "content": fallback_answer(question, slim),
                    "sources": slim,
                }
                yield {"type": "done"}
                return
            yield {"type": "content", "content": chunk}
    except Exception as exc:  # noqa: BLE001
        logger.warning("wiki QA stream failed: %s", type(exc).__name__)
        yield {
            "type": "fallback",
            "engine": "search",
            "content": fallback_answer(question, slim),
            "sources": slim,
        }
        yield {"type": "done"}
        return
    yield {"type": "done"}
