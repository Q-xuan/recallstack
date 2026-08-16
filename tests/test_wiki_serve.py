"""Serve-time materialize: cheap GET, IA, reading-guide links, subsystem diagrams."""

from __future__ import annotations

from types import SimpleNamespace

from recallstack.api.serializers import path_out, wiki_out
from recallstack.learning.learning_contract import fill_wiki_key_type_lines
from recallstack.learning.wiki_generator import link_reading_guide_markdown
from recallstack.domain.schemas import ConceptDraft, SourceReference
from recallstack.learning.question_generator import QuestionGenerator
from recallstack.learning.wiki_serve import (
    PATH_CHIP_RESTAMP,
    PATH_SERVE_REVISION,
    WIKI_SERVE_REVISION,
    cheap_upgrade_path_resolved,
    materialize_wiki_payload,
    path_chips_ready,
    path_is_materialized,
    path_needs_chip_restamp,
    persist_path_from_loaded_store,
    restamp_weak_path_chips,
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


def _agent_loop_path(resolved):
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
    return SimpleNamespace(
        id="p1",
        repository_version_id="v",
        title="路径",
        description="",
        estimated_minutes=40,
        resolved=resolved,
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


def test_path_chips_ready_accepts_stale_revision():
    stale = {"serve_revision": 1, "chips": {"c-loop": "crates/tui/src/app.rs:791 start_turn"}}
    assert path_chips_ready(stale)
    assert path_is_materialized(stale)
    assert not path_chips_ready({"serve_revision": PATH_SERVE_REVISION})
    assert not path_chips_ready({"serve_revision": PATH_SERVE_REVISION, "chips": {}})


def test_path_out_uses_rev1_chips_without_store(monkeypatch):
    monkeypatch.setenv("RECALLSTACK_CONTENT_LANG", "zh")

    def boom_load(_vid):
        raise AssertionError("scan store must not load when chips are already persisted")

    def boom_chip(*_a, **_k):
        raise AssertionError("path_evidence_chip must not walk the store on a cheap GET")

    monkeypatch.setattr(
        "recallstack.learning.code_loader.load_version_file_texts", boom_load
    )
    monkeypatch.setattr(
        "recallstack.api.serializers.path_evidence_chip", boom_chip
    )
    monkeypatch.setattr(
        "recallstack.learning.learning_contract.path_evidence_chip", boom_chip
    )

    path = _agent_loop_path(
        {
            "serve_revision": 1,
            "chips": {"c-loop": "crates/tui/src/app.rs:791 start_turn"},
        }
    )
    out = path_out(path)
    assert out.nodes[0].evidence_chip == "crates/tui/src/app.rs:791 start_turn"
    assert "`crates/tui/src/app.rs:791 start_turn`" in out.nodes[0].worksheet
    assert "你签字" in out.nodes[0].pass_gate


def test_cheap_upgrade_path_fills_contract_without_store(monkeypatch):
    monkeypatch.setenv("RECALLSTACK_CONTENT_LANG", "zh")

    def boom_chip(*_a, **_k):
        raise AssertionError("cheap upgrade must use the persisted chip")

    monkeypatch.setattr(
        "recallstack.learning.learning_contract.path_evidence_chip", boom_chip
    )
    path = _agent_loop_path(
        {
            "serve_revision": 1,
            "chips": {"c-loop": "crates/tui/src/app.rs:791 start_turn"},
        }
    )
    upgraded = cheap_upgrade_path_resolved(path, path.resolved)
    assert upgraded["serve_revision"] == PATH_SERVE_REVISION
    assert upgraded["chips"]["c-loop"] == "crates/tui/src/app.rs:791 start_turn"
    contract = upgraded["nodes"]["c-loop"]
    assert contract["chip"] == "crates/tui/src/app.rs:791 start_turn"
    assert contract["symbol"] == "start_turn"


def test_persist_path_from_loaded_store_skips_when_chips_ready():
    class _Session:
        def commit(self):
            raise AssertionError("must not persist when chips already exist")

        def rollback(self):
            raise AssertionError("must not persist when chips already exist")

    path = _agent_loop_path(
        {"serve_revision": 1, "chips": {"c-loop": "crates/tui/src/app.rs:791 start_turn"}}
    )
    persist_path_from_loaded_store(_Session(), path, {"app.rs": "fn start_turn() {}"})
    persist_path_from_loaded_store(_Session(), None, {})


def test_persist_path_from_loaded_store_writes_chips_once(monkeypatch):
    monkeypatch.setenv("RECALLSTACK_CONTENT_LANG", "zh")
    wrote: dict = {}

    def fake_persist(_session, path, resolved):
        wrote["resolved"] = resolved
        path.resolved = resolved

    monkeypatch.setattr(
        "recallstack.learning.wiki_serve.persist_path_resolved", fake_persist
    )
    monkeypatch.setattr(
        "recallstack.learning.wiki_serve.sync_path_contract_items",
        lambda *_a, **_k: None,
    )
    path = _agent_loop_path(None)
    persist_path_from_loaded_store(
        SimpleNamespace(commit=lambda: wrote.setdefault("commit", True), rollback=lambda: None),
        path,
        {"crates/tui/src/app.rs": ("\n" * 790) + "pub fn start_turn() {}\n"},
    )
    assert wrote.get("commit")
    assert "c-loop" in (wrote.get("resolved") or {}).get("chips", {})
    assert "start_turn" in wrote["resolved"]["chips"]["c-loop"]


def _leftover_path(resolved):
    goal = SimpleNamespace(
        id="c-goal",
        repository_id="r",
        repository_version_id="v",
        slug="project-goal",
        title="项目目标",
        description="",
        difficulty=1,
        importance=1.0,
        source_references=[{"path": "README.md", "start_line": 1}],
        content_hash="",
        stale=False,
        why_learn="",
        estimated_minutes=10,
        wiki_page_id="topics/project-goal",
    )
    runtime = SimpleNamespace(
        id="c-runtime",
        repository_id="r",
        repository_version_id="v",
        slug="agent-runtime",
        title="Agent Runtime",
        description="",
        difficulty=2,
        importance=0.8,
        source_references=[
            {"path": "crates/codegen/xai-agent-lifecycle/src/lib.rs", "start_line": None}
        ],
        content_hash="",
        stale=False,
        why_learn="",
        estimated_minutes=15,
        wiki_page_id="topics/agent-runtime",
    )
    return SimpleNamespace(
        id="p1",
        repository_version_id="v",
        title="路径",
        description="",
        estimated_minutes=40,
        resolved=resolved,
        nodes=[
            SimpleNamespace(id="n1", concept_id="c-goal", position=1, reason="", concept=goal),
            SimpleNamespace(
                id="n2", concept_id="c-runtime", position=2, reason="", concept=runtime
            ),
        ],
    )


def test_path_needs_chip_restamp_only_for_leftover_chips():
    good = _agent_loop_path(
        {"serve_revision": PATH_SERVE_REVISION, "chips": {"c-loop": "crates/tui/src/app.rs:791 start_turn"}}
    )
    assert not path_needs_chip_restamp(good, good.resolved)

    leftover = _leftover_path(
        {
            "serve_revision": PATH_SERVE_REVISION,
            "chips": {
                "c-goal": "README.md:1",
                "c-runtime": "crates/codegen/xai-agent-lifecycle/src/lib.rs",
            },
        }
    )
    assert path_needs_chip_restamp(leftover, leftover.resolved)
    leftover.resolved["chip_restamp"] = PATH_CHIP_RESTAMP
    assert not path_needs_chip_restamp(leftover, leftover.resolved)


def test_restamp_weak_path_chips_binds_start_turn_and_agent_runtime():
    path = _leftover_path(
        {
            "serve_revision": PATH_SERVE_REVISION,
            "chips": {
                "c-goal": "README.md:1",
                "c-runtime": "crates/codegen/xai-agent-lifecycle/src/lib.rs",
            },
        }
    )
    store = {
        "README.md": "# grok\n",
        "crates/codegen/xai-grok-pager/src/app/agent.rs": ("\n" * 790)
        + "    pub fn start_turn(&mut self) {\n",
        "crates/codegen/xai-agent-lifecycle/src/lib.rs": (
            "pub mod runtime;\npub use runtime::AgentRuntime;\n"
        ),
        "crates/codegen/xai-agent-lifecycle/src/runtime.rs": (
            "// pad\n" * 21 + "pub struct AgentRuntime {\n"
        ),
    }
    upgraded = restamp_weak_path_chips(path, path.resolved, store)
    assert upgraded["chip_restamp"] == PATH_CHIP_RESTAMP
    assert upgraded["chips"]["c-goal"] == (
        "crates/codegen/xai-grok-pager/src/app/agent.rs:791 start_turn"
    )
    assert upgraded["chips"]["c-runtime"] == (
        "crates/codegen/xai-agent-lifecycle/src/runtime.rs:22 AgentRuntime"
    )
    goal_node = upgraded["nodes"]["c-goal"]
    assert goal_node["symbol"] == "start_turn"
    assert goal_node["line"] == 791
    runtime_node = upgraded["nodes"]["c-runtime"]
    assert runtime_node["symbol"] == "AgentRuntime"
    assert runtime_node["line"] == 22

    items = QuestionGenerator().generate_from_contract(
        title="Agent Runtime",
        contract=runtime_node,
        concept=ConceptDraft(
            slug="agent-runtime",
            title="Agent Runtime",
            source_references=[
                SourceReference(
                    path="crates/codegen/xai-agent-lifecycle/src/lib.rs",
                    start_line=None,
                )
            ],
        ),
        file_texts=store,
    ).items
    assert items[0].source_references[0].start_line == 22
    assert items[0].source_references[0].symbol == "AgentRuntime"


def test_persist_path_from_loaded_store_restamps_leftovers(monkeypatch):
    wrote: dict = {}

    def fake_persist(_session, path, resolved):
        wrote["resolved"] = resolved
        path.resolved = resolved

    monkeypatch.setattr(
        "recallstack.learning.wiki_serve.persist_path_resolved", fake_persist
    )
    monkeypatch.setattr(
        "recallstack.learning.wiki_serve.sync_path_contract_items",
        lambda *_a, **_k: None,
    )
    path = _leftover_path(
        {
            "serve_revision": PATH_SERVE_REVISION,
            "chips": {
                "c-goal": "README.md:1",
                "c-runtime": "crates/codegen/xai-agent-lifecycle/src/lib.rs",
            },
        }
    )
    store = {
        "README.md": "# grok\n",
        "crates/codegen/xai-grok-pager/src/app/agent.rs": ("\n" * 790)
        + "    pub fn start_turn(&mut self) {\n",
        "crates/codegen/xai-agent-lifecycle/src/lib.rs": "pub mod runtime;\n",
        "crates/codegen/xai-agent-lifecycle/src/runtime.rs": (
            "// pad\n" * 21 + "pub struct AgentRuntime {\n"
        ),
    }
    persist_path_from_loaded_store(
        SimpleNamespace(commit=lambda: wrote.setdefault("commit", True), rollback=lambda: None),
        path,
        store,
    )
    assert wrote.get("commit")
    chips = wrote["resolved"]["chips"]
    assert chips["c-goal"] == "crates/codegen/xai-grok-pager/src/app/agent.rs:791 start_turn"
    assert chips["c-runtime"] == (
        "crates/codegen/xai-agent-lifecycle/src/runtime.rs:22 AgentRuntime"
    )
