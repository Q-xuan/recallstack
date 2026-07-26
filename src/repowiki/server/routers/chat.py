"""Q&A chat endpoint with RAG (full chat + inline wiki explain)."""

from __future__ import annotations

import json

from fastapi import APIRouter, Header
from fastapi.responses import StreamingResponse

from repowiki.config import Config
from repowiki.server.app import get_projects
from repowiki.server.models import ChatRequest

router = APIRouter()


@router.post("/project/{project_id}/chat")
async def chat(project_id: str, req: ChatRequest, x_api_key: str | None = Header(None)):
    """SSE streaming chat response with RAG retrieval.

    Modes:
    - chat: free-form Q&A (default)
    - inline_explain: explain a selection while reading a wiki page
    """
    projects = get_projects()
    proj = projects.get(project_id)
    if not proj or not proj.get("project"):
        return {"error": "Project not ready"}

    project = proj["project"]
    mode = (req.mode or "chat").strip().lower()
    if mode not in {"chat", "inline_explain"}:
        mode = "chat"

    selection = (req.selection or "").strip()
    question = (req.question or "").strip()
    if mode == "inline_explain" and not selection and not question:
        return {"error": "selection or question required"}
    if mode == "chat" and not question:
        return {"error": "question required"}

    # build RAG index if not cached
    if "rag" not in proj:
        from repowiki.core.rag import SimpleRAG

        rag = SimpleRAG()
        rag.index(project)
        proj["rag"] = rag
    else:
        rag = proj["rag"]

    # retrieve: prefer selection + question for better grounding
    if mode == "inline_explain":
        retrieve_q = " ".join(p for p in [selection, question, req.wiki_page_title] if p)
    else:
        retrieve_q = question
    chunks = rag.retrieve(retrieve_q, top_k=5)
    context_parts = []
    references = []
    for chunk in chunks:
        context_parts.append(
            f"### {chunk.file_path} (lines {chunk.line_start}-{chunk.line_end})\n"
            f"```\n{chunk.content}\n```"
        )
        references.append(
            {
                "path": chunk.file_path,
                "line_start": chunk.line_start,
                "line_end": chunk.line_end,
                "snippet": chunk.content[:200],
            }
        )

    context_text = "\n\n".join(context_parts)

    # get LLM config
    cfg = Config.load()
    if x_api_key:
        cfg.api_key = x_api_key

    if not cfg.api_key:
        return {"error": "No API key configured"}

    from repowiki.llm.client import LLMClient
    from repowiki.llm.prompts import build_chat_prompt, build_inline_explain_prompt

    llm = LLMClient(model=cfg.model, api_key=cfg.api_key, api_base=cfg.api_base)
    if mode == "inline_explain":
        messages = build_inline_explain_prompt(
            selection=selection or question,
            question=question,
            context_chunks=context_text,
            wiki_page_title=req.wiki_page_title or "",
            surrounding_text=req.surrounding_text or "",
            language=cfg.language,
        )
    else:
        messages = build_chat_prompt(question, context_text, cfg.language)

    async def event_stream():
        # send references first
        yield f"data: {json.dumps({'references': references, 'mode': mode})}\n\n"

        # stream the answer
        async for chunk in llm.stream(messages):
            yield f"data: {json.dumps({'content': chunk})}\n\n"

        yield f"data: {json.dumps({'done': True})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
