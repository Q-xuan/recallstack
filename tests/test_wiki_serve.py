"""Serve-time materialize: cheap GET, IA, reading-guide links, subsystem diagrams."""

from __future__ import annotations

from types import SimpleNamespace

from recallstack.api.serializers import path_out, wiki_out
from recallstack.learning.learning_contract import fill_wiki_key_type_lines
from recallstack.learning.wiki_generator import link_reading_guide_markdown
from recallstack.learning.wiki_serve import (
    PATH_SERVE_REVISION,
    WIKI_SERVE_REVISION,
    materialize_wiki_payload,
    wiki_is_materialized,
)
from repowiki.core.wiki_builder import (
    enrich_overview_from_topic_pages,
    thicken_subsystem_diagrams,
)


def test_link_reading_guide_zh_and_en_steps():
    concepts = [
        SimpleNamespace(slug="project-goal", title="项目目标"),
        SimpleNamespace(slug="agent-loop", title="Agent Loop"),
    ]
    zh = (
        "# 导读\n\n"
        "## 步骤 1: 项目目标 (~10 min)\n\n先读概述。\n\n"
        "## 步骤 2: Agent Loop (15 min)\n"
    )
    linked = link_reading_guide_markdown(zh, concepts)
    assert "](concepts/project-goal)" in linked
    assert "](concepts/agent-loop)" in linked
    en = "## Step 1: Project goal (~10 min)\n"
    # title mismatch → fall back to step order
    assert "](concepts/project-goal)" in link_reading_guide_markdown(en, concepts)


def test_fill_wiki_stamps_subsystem_symbol_keeps_path_only():
    store = {
        "crates/codegen/xai-grok-agent/src/tool_bridge.rs": (
            "\n" * 2 + "pub struct ToolBridge {\n"
        )
    }
    md = (
        "## 核心子系统\n\n"
        "### 工具层\n\n"
        "- ToolBridge — 按名分发 — "
        "`crates/codegen/xai-grok-agent/src/tool_bridge.rs ToolBridge`\n"
        "- 工具层 — `crates/codegen/xai-grok-agent/src/tool_bridge.rs`\n"
    )
    filled = fill_wiki_key_type_lines(md, store)
    assert "`crates/codegen/xai-grok-agent/src/tool_bridge.rs:3 ToolBridge`" in filled
    assert "- 工具层 — `crates/codegen/xai-grok-agent/src/tool_bridge.rs`" in filled


def test_thicken_subsystem_replaces_toy_mermaid():
    md = (
        "## 核心子系统\n\n"
        "### Agent Loop\n\n"
        "pager 把一轮交给 start_turn。\n\n"
        "```mermaid\n"
        "flowchart LR\n"
        "  A[Pager] --> B[Agent]\n"
        "```\n\n"
        "- start_turn — 开一轮 — `app/agent.rs:10 start_turn`\n"
        "- ToolBridge — 执行 — `tool_bridge.rs:3 ToolBridge`\n"
        "- Pager — 画布 — `pager.rs:3 Pager`\n"
    )
    out = thicken_subsystem_diagrams(md)
    assert "flowchart LR" in out
    assert 'A["start_turn"]' in out
    assert 'B["ToolBridge"]' in out
    assert 'C["Pager"]' in out
    assert "A --> B" in out
    assert "B --> C" in out


def test_overview_subsystems_copy_types_from_topic_pages():
    pages = [
        {
            "id": "index",
            "title": "概述",
            "content": (
                "# grok-study\n\n"
                "## 核心子系统\n\n"
                "### Agent Loop\n\n"
                "一轮从 pager 进 start_turn。\n\n"
                "```mermaid\n"
                "A --> B\n"
                "```\n"
            ),
        },
        {
            "id": "topics/agent-loop",
            "title": "Agent Loop",
            "content": (
                "# Agent Loop\n\n"
                "## 关键类型\n\n"
                "- start_turn — pager 开一轮 — `app/agent.rs:791 start_turn`\n"
                "- ToolBridge — 执行 tool call — `tool_bridge.rs:3 ToolBridge`\n"
                "- Pager — 画布 — `pager.rs:3 Pager`\n\n"
                "```mermaid\n"
                "flowchart LR\n"
                "  A[\"Pager\"] --> B[\"start_turn\"] --> C[\"ToolBridge\"]\n"
                "```\n"
            ),
        },
    ]
    enrich_overview_from_topic_pages(pages)
    md = pages[0]["content"]
    assert "start_turn — pager 开一轮" in md
    assert "flowchart LR" in md
    assert "ToolBridge" in md


def test_wiki_out_puts_guide_and_concepts_in_ia(monkeypatch):
    monkeypatch.setenv("RECALLSTACK_CONTENT_LANG", "zh")

    class _Version:
        id = "ver-ia"
        wiki_pages = {
            "project_name": "grok-study",
            "pages": [
                {"id": "index", "title": "概述", "content": "# 概述\n"},
                {"id": "reading-guide", "title": "导读", "content": "## 步骤 1: 入口 (~10 min)\n"},
                {"id": "architecture", "title": "架构概览", "content": "# 架构\n"},
                {"id": "topics/agent-loop", "title": "Agent Loop", "content": "# loop\n"},
                {"id": "concepts/entry-and-boot", "title": "入口", "content": "# 入口\n"},
            ],
            "sidebar": [
                {
                    "title": "入门指南",
                    "page_id": "",
                    "children": [{"title": "概述", "page_id": "index", "children": []}],
                },
                {
                    "title": "深入探索",
                    "page_id": "",
                    "children": [
                        {"title": "Agent Loop", "page_id": "topics/agent-loop", "children": []},
                    ],
                },
            ],
        }

    concepts = [
        SimpleNamespace(id="c1", slug="entry-and-boot", title="入口", wiki_page_id="concepts/entry-and-boot"),
    ]
    out = wiki_out("repo-1", _Version(), concepts=concepts)
    getting = next(item for item in out.sidebar if item.title == "入门指南")
    assert any(c.page_id == "reading-guide" for c in getting.children)
    guide = next(p for p in out.pages if p.id == "reading-guide")
    assert "](concepts/entry-and-boot)" in guide.content
    deep = next(item for item in out.sidebar if item.title == "深入探索")
    glossary = next(c for c in deep.children if c.title == "词条")
    assert any(c.page_id == "concepts/entry-and-boot" for c in glossary.children)


def test_wiki_out_materialized_skips_store_load(monkeypatch):
    monkeypatch.setenv("RECALLSTACK_CONTENT_LANG", "zh")

    def boom(_vid):
        raise AssertionError("scan store must not load on a materialized GET")

    monkeypatch.setattr(
        "recallstack.learning.code_loader.load_version_file_texts", boom
    )

    class _Version:
        id = "ver-cheap"
        wiki_pages = {
            "serve_revision": WIKI_SERVE_REVISION,
            "project_name": "grok-study",
            "pages": [
                {"id": "index", "title": "概述", "content": "# 概述\n已经升级\n"},
            ],
            "sidebar": [
                {
                    "title": "入门指南",
                    "page_id": "",
                    "children": [{"title": "概述", "page_id": "index", "children": []}],
                }
            ],
        }

    out = wiki_out("repo-1", _Version())
    assert out.pages[0].content.startswith("# 概述")
    assert wiki_is_materialized(materialize_wiki_payload(_Version.wiki_pages, [], None))


def test_path_out_uses_persisted_chips_without_store(monkeypatch):
    monkeypatch.setenv("RECALLSTACK_CONTENT_LANG", "zh")
    concept = SimpleNamespace(
        id="c-loop",
        repository_id="r",
        repository_version_id="v",
        slug="agent-loop",
        title="Agent Loop",
        description="",
        difficulty=2,
        importance=0.9,
        source_references=[],
        content_hash="",
        stale=False,
        why_learn="",
        estimated_minutes=15,
        wiki_page_id="topics/agent-loop",
    )
    path = SimpleNamespace(
        id="p1",
        repository_version_id="v",
        title="路径",
        description="",
        estimated_minutes=40,
        resolved={
            "serve_revision": PATH_SERVE_REVISION,
            "chips": {"c-loop": "crates/tui/src/app.rs:791 start_turn"},
        },
        nodes=[
            SimpleNamespace(
                id="n1",
                concept_id="c-loop",
                position=1,
                reason="",
                concept=concept,
            )
        ],
    )
    out = path_out(path)
    assert out.nodes[0].evidence_chip == "crates/tui/src/app.rs:791 start_turn"
    assert "`crates/tui/src/app.rs:791 start_turn`" in out.nodes[0].worksheet
