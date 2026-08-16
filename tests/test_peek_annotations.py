"""Lazy SourcePeek teaching annotations — overlay only, never into the repo."""

from __future__ import annotations

import asyncio

from recallstack.learning.peek_annotations import (
    ANNOTATE_SYSTEM,
    annotation_cache_key,
    annotations_for_snippet,
    build_annotate_messages,
    parse_evidence_chip,
    parse_model_notes,
    sanitize_notes,
    save_cached_annotations,
    snippet_content_hash,
)


def test_prompt_refuses_syntax_narration():
    assert "不要讲语法" in ANNOTATE_SYSTEM
    assert "docstring" in ANNOTATE_SYSTEM
    messages = build_annotate_messages(
        path="crates/codegen/xai-grok-pager/src/app/agent.rs",
        start_line=791,
        end_line=793,
        snippet="    pub fn start_turn(&mut self) {\n        self.call_model();\n    }",
        principles="没有 start_turn 就没有一轮对话。",
        pass_gate_text="指出谁在 start_turn 之后调模型。",
    )
    user = messages[-1]["content"]
    assert "不要语法叙述" in user
    assert '{"notes":[]}' in user
    assert "791|" in user
    assert "先回到原理" in user
    assert "过关" in user
    assert "你" in ANNOTATE_SYSTEM


def test_sanitize_drops_syntax_narration_and_out_of_range():
    notes = sanitize_notes(
        {
            "notes": [
                {"line": 791, "note": "这一行保证一轮对话从这里进入模型。"},
                {"line": 792, "note": "这是一个函数定义"},
                {"line": 1, "note": "片段外"},
                {"line": 793, "note": "this is a function"},
            ]
        },
        path="app/agent.rs",
        start_line=791,
        end_line=800,
    )
    assert notes == [
        {
            "path": "app/agent.rs",
            "line": 791,
            "note": "这一行保证一轮对话从这里进入模型。",
        }
    ]


def test_empty_on_missing_snippet():
    notes = asyncio.run(
        annotations_for_snippet(
            version_id="v",
            path="missing.rs",
            start_line=1,
            end_line=1,
            snippet="",
        )
    )
    assert notes == []


def test_cache_hit_skips_llm(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    snippet = "    pub fn start_turn(&mut self) {\n        self.call_model();\n    }"
    digest = snippet_content_hash(snippet)
    key = annotation_cache_key("ver-1", "app/agent.rs", 791, digest)
    save_cached_annotations(
        key,
        [{"path": "app/agent.rs", "line": 791, "note": "这一行保证进入模型。"}],
    )

    class Boom:
        async def complete(self, *args, **kwargs):
            raise AssertionError("LLM must not run on cache hit")

    notes = asyncio.run(
        annotations_for_snippet(
            version_id="ver-1",
            path="app/agent.rs",
            start_line=791,
            end_line=793,
            snippet=snippet,
            slug="agent-loop",
            llm=Boom(),
        )
    )
    assert notes[0]["line"] == 791
    assert "保证" in notes[0]["note"]


def test_parse_model_notes_accepts_bare_array():
    notes = parse_model_notes(
        '[{"line": 40, "note": "这一行保证按名字分发工具。"}]',
        path="tool_bridge.rs",
        start_line=38,
        end_line=44,
    )
    assert notes == [
        {"path": "tool_bridge.rs", "line": 40, "note": "这一行保证按名字分发工具。"}
    ]


def test_parse_evidence_chip():
    assert parse_evidence_chip(
        "`crates/codegen/xai-grok-pager/src/app/agent.rs:791 start_turn`"
    ) == ("crates/codegen/xai-grok-pager/src/app/agent.rs", 791)
    assert parse_evidence_chip("README.md:1") == ("README.md", 1)
    assert parse_evidence_chip("") is None
