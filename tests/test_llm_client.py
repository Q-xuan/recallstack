"""LLM completion text extraction and thinking defaults."""

from __future__ import annotations

import asyncio

from repowiki.llm.client import (
    LLMClient,
    extract_completion_text,
    thinking_option,
)
from repowiki.llm.prompts import (
    build_architecture_prompt,
    build_module_prompt,
    build_outline_prompt,
    build_overview_prompt,
    extract_json,
)


def test_extract_completion_text_falls_back_to_reasoning_content():
    message = {"content": "  ", "reasoning_content": '{"name": "app", "purpose": "boot"}'}
    text = extract_completion_text(message)
    assert extract_json(text) == {"name": "app", "purpose": "boot"}


def test_extract_completion_text_flattens_list_parts():
    message = {
        "content": [{"type": "text", "text": '{"ok": true}'}],
        "reasoning_content": "ignored",
    }
    assert extract_json(extract_completion_text(message)) == {"ok": True}


def test_thinking_disabled_by_default(monkeypatch):
    monkeypatch.delenv("REPOWIKI_LLM_THINKING", raising=False)
    assert thinking_option() == {"type": "disabled"}
    monkeypatch.setenv("REPOWIKI_LLM_THINKING", "enabled")
    assert thinking_option() is None


def test_complete_uses_reasoning_content_and_disables_thinking(monkeypatch):
    monkeypatch.setenv("REPOWIKI_LLM_MIN_INTERVAL", "0")
    monkeypatch.delenv("REPOWIKI_LLM_THINKING", raising=False)
    client = LLMClient(model="flash", api_key="k", api_base="http://example.invalid")
    bodies: list[dict] = []

    async def fake_post(body, timeout):
        bodies.append(body)
        return {
            "choices": [
                {
                    "message": {
                        "content": "",
                        "reasoning_content": '{"name": "app"}',
                    }
                }
            ],
            "usage": {"prompt_tokens": 1, "completion_tokens": 2},
        }

    client._post = fake_post  # type: ignore[method-assign]
    text = asyncio.run(client.complete([{"role": "user", "content": "hi"}]))
    assert extract_json(text) == {"name": "app"}
    assert bodies[0]["thinking"] == {"type": "disabled"}


def test_complete_omits_thinking_when_enabled(monkeypatch):
    monkeypatch.setenv("REPOWIKI_LLM_MIN_INTERVAL", "0")
    monkeypatch.setenv("REPOWIKI_LLM_THINKING", "enabled")
    client = LLMClient(model="flash", api_key="k", api_base="http://example.invalid")
    bodies: list[dict] = []

    async def fake_post(body, timeout):
        bodies.append(body)
        return {"choices": [{"message": {"content": "{}"}}], "usage": {}}

    client._post = fake_post  # type: ignore[method-assign]
    asyncio.run(client.complete([{"role": "user", "content": "hi"}]))
    assert "thinking" not in bodies[0]


def test_zh_prompts_ask_for_handbook_prose_and_term_tips():
    overview = build_overview_prompt("tree", "files", "zh")
    assert "手册正文" in overview[0]["content"]
    assert "用「你」不用「您」" in overview[0]["content"]
    assert "禁止翻译腔" in overview[0]["content"]
    assert "term_tips" in overview[-1]["content"]
    overview_user = overview[-1]["content"]
    assert "what_it_is" in overview_user
    assert "codebase_structure" in overview_user
    assert "subsystems" in overview_user
    assert "mermaid_component" in overview_user
    assert "file inventory" in overview_user
    assert "key_features" in overview_user
    assert "本步要你干什么" in overview[0]["content"]
    arch = build_architecture_prompt("tree", "files", "zh")
    assert "PageRank file dump" in arch[-1]["content"]
    assert "term_tips" in arch[-1]["content"]
    assert "ROLE in the flow" in arch[-1]["content"]
    assert "key_types" in arch[-1]["content"]
    assert "homework" in arch[0]["content"]
    assert "model BEFORE tools" in arch[-1]["content"]
    assert "never cli-tool" in arch[-1]["content"]
    assert "AgentLoop" in arch[-1]["content"]
    assert "TurnRunning" in arch[-1]["content"]
    assert "ToolBridge" in arch[-1]["content"]
    overview_user = overview[-1]["content"]
    assert "`path:line Symbol`" in overview_user or "path:line Symbol" in overview_user
    assert "Agent Loop 与上下文装配" in overview_user
    assert "Pager" in overview_user
    deep = build_module_prompt("app", "src", "demo", "zh", depth="deep")
    assert "term_tips is REQUIRED" in deep[-1]["content"]
    assert "`PtyHandle`" in deep[0]["content"]
    assert "接口清单" in deep[0]["content"]
    user = deep[-1]["content"]
    assert "The entry point is lib.rs" in user
    assert "is_alive" in user
    assert "Heaviest modules" in user
    assert "call_chains: REQUIRED" in user
    assert "Omit files[].key_symbols" in user
    standard = build_module_prompt("app", "src", "demo", "zh", depth="standard")
    assert "Walkthrough + at least one call_chain" in standard[-1]["content"]
    assert "key_symbols\": [{\"name\": \"func_name\"" not in standard[-1]["content"]
    titled = build_overview_prompt(
        "tree", "files", "zh", topic_titles=["Agent Loop", "Tool System"]
    )
    assert "Agent Loop" in titled[-1]["content"]
    assert "Tool System" in titled[-1]["content"]
    assert "see_also" in titled[-1]["content"]
    assert "代码图谱" in titled[-1]["content"]
    loop = build_module_prompt(
        "Agent Loop", "src", "demo", "zh", depth="deep", topic_id="agent-loop"
    )
    loop_user = loop[-1]["content"]
    assert "收用户输入" in loop_user
    assert "调模型" in loop_user
    assert "解析 tool calls" in loop_user
    assert "执行工具" in loop_user
    assert "再调模型" in loop_user
    assert "mermaid is REQUIRED" in loop_user
    assert "下一轮" in loop_user
    assert "observe" in loop_user
    assert "工具调用" in loop_user
    assert "AgentLoop" in loop_user
    assert "replace_or_insert_system_head" in loop_user
    assert "FORBIDDEN as the spine/lede" in loop_user
    assert "topics/context-assembly" in loop_user


def test_outline_prompt_splits_agent_loop_from_context_assembly():
    prompt = build_outline_prompt("tree", "mods", "ranks", "entries", "zh")
    user = prompt[-1]["content"]
    assert "agent-loop key_files MUST be the runtime loop" in user
    assert "NEVER conversation_util.rs" in user
    assert "topic id context-assembly" in user
    assert "replace_or_insert_system_head" in user
    assert "entry-and-boot key_files MUST be the grok binary" in user
    assert "tool-system key_files MUST include ToolBridge" in user


def test_extract_json_recovers_truncated_topics_payload():
    parsed = extract_json('{ "topics": [ { "id": "a" ')
    assert parsed is not None
    assert parsed["topics"][0]["id"] == "a"


def test_extract_json_strips_trailing_commas_and_fences():
    raw = """```json
{"topics": [{"id": "agent-loop",}], "overview_focus": "boot",}
```"""
    parsed = extract_json(raw)
    assert parsed["topics"][0]["id"] == "agent-loop"
    assert parsed["overview_focus"] == "boot"


def test_outline_prompt_is_topics_only_and_compact():
    prompt = build_outline_prompt("tree", "mods", "ranks", "entries", "zh")
    user = prompt[-1]["content"]
    assert "Output a wiki outline as JSON" in user
    assert '"topics"' in user
    assert "Do NOT emit modules[]" in user
    assert '"sections": ["purpose", "implementation"' not in user


def test_outline_max_tokens_constant():
    from repowiki.core.analyzer import OUTLINE_MAX_TOKENS

    assert OUTLINE_MAX_TOKENS >= 4096
