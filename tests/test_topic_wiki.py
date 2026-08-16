"""Conceptual topic wiki IA (zread 入门指南 / 深入探索), not a crate tree."""

from __future__ import annotations

from recallstack.api.serializers import wiki_out
from recallstack.learning.concept_extractor import ConceptExtractor
from recallstack.learning.path_builder import PathBuilder
from recallstack.learning.wiki_generator import build_wiki_payload
from repowiki.core.graph import DependencyGraph
from repowiki.core.models import FileInfo, ProjectContext
from repowiki.core.wiki_builder import (
    rebuild_topic_sidebar,
    sidebar_has_topic_groups,
    sidebar_looks_like_module_tree,
)


def _file(path: str, content: str, *, entry: bool = False, language: str = "rust") -> FileInfo:
    return FileInfo(
        path=path,
        size=len(content),
        language=language,
        lines=content.count("\n") + 1,
        preview=content[:400],
        content=content,
        is_entrypoint=entry,
        is_config=path.lower() in {"readme.md", "cargo.toml"},
    )


def _grok_project() -> ProjectContext:
    filler = "pub fn f() {}\n" * 40
    files = [
        _file(
            "README.md",
            "# grok-study\n\nAn agent CLI.\n\n## Modes\nTUI, headless, ACP.\n",
            language="markdown",
        ),
        _file("Cargo.toml", "[workspace]\nmembers = [\"crates/*\"]\n", language="toml"),
        _file(
            ".cargo/config.toml",
            "[build]\ntarget = \"x86_64-unknown-linux-gnu\"\n",
            language="toml",
        ),
        _file("bin/grok.rs", "fn main() {\n    grok::run();\n}\n" + filler, entry=True),
        _file(
            "bin/protoc",
            "#!/usr/bin/env dotslash\n{\n  \"name\": \"protoc\"\n}\n",
            entry=True,
            language="text",
        ),
        _file("crates/agent/src/runtime.rs", "pub struct AgentRuntime;\n" + filler),
        _file("crates/agent/src/loop.rs", "pub fn agent_loop() {}\n" + filler),
        _file("crates/agent/src/prompt.rs", "pub fn system_prompt() {}\n" + filler),
        _file(
            "crates/xai-grok-agent/src/tool_bridge.rs",
            "pub struct ToolBridge;\n" + filler,
        ),
        _file("crates/pager/src/app.rs", "pub fn boot_pager() {}\n" + filler),
        _file(
            "crates/xai-grok-pager/src/lib.rs",
            "pub fn start_pager() {}\n" + filler,
        ),
        _file(
            "crates/code-graph/src/main.rs",
            "fn main() { code_graph::run(); }\n" + filler,
            entry=True,
        ),
        _file(
            "crates/fast-worktree/src/main.rs",
            "fn main() { worktree::run(); }\n" + filler,
            entry=True,
        ),
        _file(
            "crates/xai-chat-state/src/conversation_util.rs",
            "pub fn replace_or_insert_system_head() {}\n" + filler,
        ),
        _file("crates/tools/src/lib.rs", "pub mod tools;\n" + filler),
        _file("crates/acp/src/protocol.rs", "pub struct AcpServer;\n" + filler),
        _file("crates/tui/src/app.rs", "pub fn run_tui() {}\n" + filler),
        _file("crates/codegen/ptyctl/src/lib.rs", "pub struct PtyHandle;\n" + filler),
        _file("crates/codegen/xai-grok-tools/src/lib.rs", "pub fn tools() {}\n" + filler),
    ]
    return ProjectContext(name="grok-study", root=".", files=files, file_tree="")


def _top_level_nav_titles(sidebar) -> list[str]:
    titles: list[str] = []
    for item in sidebar:
        title = getattr(item, "title", None) or item.get("title")
        children = getattr(item, "children", None)
        if children is None and isinstance(item, dict):
            children = item.get("children") or []
        group = (title or "").strip()
        if group in {"按目录", "By directory", "模块", "Modules"}:
            continue
        for child in children or []:
            child_title = getattr(child, "title", None) or child.get("title")
            titles.append(child_title)
    return titles


def test_grok_default_sidebar_is_conceptual_not_crate_tree():
    project = _grok_project()
    graph = DependencyGraph.build_from_project(project)
    payload = build_wiki_payload(project, graph, [])
    sidebar = payload["sidebar"]
    group_titles = [item["title"] for item in sidebar]
    assert "入门指南" in group_titles or "Getting Started" in group_titles
    assert "深入探索" in group_titles or "Deep Dive" in group_titles

    nav = _top_level_nav_titles(sidebar)
    assert "概述" in nav or "Overview" in nav
    assert ".cargo" not in nav
    assert "ptyctl" not in nav
    assert not any(str(t).startswith("crates/") for t in nav)

    page_ids = {p["id"] for p in payload["pages"]}
    assert "index" in page_ids
    assert any(pid.startswith("topics/") for pid in page_ids)
    topic_pages = [p for p in payload["pages"] if p["id"].startswith("topics/")]
    assert topic_pages
    for page in topic_pages:
        assert "本步要你干什么" not in page["content"]
        assert "What this step asks of you" not in page["content"]

    overview = next(p for p in payload["pages"] if p["id"] == "index")
    content = overview["content"]
    assert "## 它是什么" in content or "## What it is" in content
    assert "## 系统架构" in content or "## System architecture" in content
    assert "## 代码如何拆分" in content or "## How the code is split" in content
    assert "## 核心子系统" in content or "## Core subsystems" in content
    assert "```mermaid" in content
    assert "本步要你干什么" not in content
    assert "30 秒自测" not in content


def test_grok_learning_path_is_topics_not_web_app_syllabus():
    project = _grok_project()
    graph = DependencyGraph.build_from_project(project)
    concepts = ConceptExtractor().extract(project, graph).concepts
    slugs = {c.slug for c in concepts}
    assert "caching" not in slugs
    assert "authentication" not in slugs
    assert "request-routing" not in slugs
    assert "project-goal" in slugs
    path = PathBuilder().build(concepts)
    path_slugs = [n.concept_slug for n in path.nodes]
    assert "project-goal" in path_slugs
    assert path_slugs[0] == "project-goal"
    assert "caching" not in path_slugs
    assert "authentication" not in path_slugs
    assert "request-routing" not in path_slugs
    assert any(s not in {"project-goal", "getting-started"} for s in path_slugs)
    if "entry-and-boot" in path_slugs and "agent-loop" in path_slugs:
        assert path_slugs[0] == "project-goal"
        assert path_slugs[1] == "entry-and-boot"
        assert path_slugs[2] == "agent-loop"
    if "agent-loop" in path_slugs:
        assert path_slugs.index("project-goal") < path_slugs.index("agent-loop")
        crate_leaves = [s for s in path_slugs if s in {"acp-protocol", "pty-control", "codebase-graph", "headless-modes"}]
        for leaf in crate_leaves:
            assert path_slugs.index("agent-loop") < path_slugs.index(leaf)


def test_grok_deterministic_topics_are_zread_systems_not_web_app():
    from repowiki.core.topics import build_deterministic_topics

    project = _grok_project()
    graph = DependencyGraph.build_from_project(project)
    topics = build_deterministic_topics(project, graph, language="zh")
    ids = {t.id for t in topics}
    titles = {t.title for t in topics}
    assert "agent-runtime" in ids or any("Agent Runtime" in t or "Runtime" in t for t in titles)
    assert "agent-loop" in ids or any("Loop" in t for t in titles)
    assert "acp-protocol" in ids or any("ACP" in t for t in titles)
    assert "terminal-ui" in ids or any("TUI" in t or "Terminal" in t for t in titles)
    assert "tool-system" in ids or any("工具" in t or "Tool" in t for t in titles)
    assert "caching" not in ids
    assert "authentication" not in ids
    assert "request-routing" not in ids
    assert "data-persistence" not in ids


def test_agent_loop_file_pack_is_agent_crate_not_conversation_util():
    from repowiki.core.models import TopicOutline
    from repowiki.core.topics import build_deterministic_topics, merge_topics

    project = _grok_project()
    graph = DependencyGraph.build_from_project(project)
    topics = build_deterministic_topics(project, graph, language="zh")
    by_id = {t.id: t for t in topics}
    assert "agent-loop" in by_id
    loop = by_id["agent-loop"]
    assert "与上下文装配" not in loop.title
    loop_joined = " ".join(loop.key_files)
    assert "conversation_util" not in loop_joined
    assert (
        "xai-grok-agent" in loop_joined
        or "loop.rs" in loop_joined
        or "/agent.rs" in loop_joined
    )
    assert "context-assembly" in by_id
    assembly_joined = " ".join(by_id["context-assembly"].key_files)
    assert "conversation_util" in assembly_joined
    assert not any("conversation_util" in p for p in loop.key_files)

    llm = [
        TopicOutline(
            id="agent-loop",
            title="Agent Loop 与上下文装配",
            section="deep-dive",
            key_files=["crates/xai-chat-state/src/conversation_util.rs"],
        )
    ]
    merged = merge_topics(topics, llm, {f.path for f in project.files})
    merged_by_id = {t.id: t for t in merged}
    rebound = merged_by_id["agent-loop"]
    assert "与上下文装配" not in rebound.title
    assert not any("conversation_util" in p for p in rebound.key_files)
    assert any(
        "xai-grok-agent" in p or p.endswith("loop.rs") or p.endswith("/agent.rs")
        for p in rebound.key_files
    )
    assert "context-assembly" in merged_by_id
    assert any(
        "conversation_util" in p for p in merged_by_id["context-assembly"].key_files
    )


def test_entry_and_boot_file_pack_is_grok_pager_not_worktree_cli():
    from repowiki.core.models import TopicOutline
    from repowiki.core.topics import ENTRY_ID, build_deterministic_topics, merge_topics

    project = _grok_project()
    graph = DependencyGraph.build_from_project(project)
    topics = build_deterministic_topics(project, graph, language="zh")
    by_id = {t.id: t for t in topics}
    assert ENTRY_ID in by_id
    joined = " ".join(by_id[ENTRY_ID].key_files)
    assert "bin/grok.rs" in joined or "pager" in joined
    assert "protoc" not in joined
    assert "worktree" not in joined
    assert "code-graph" not in joined
    assert "fast-worktree" not in joined
    primary = by_id[ENTRY_ID].key_files[0]
    assert "protoc" not in primary
    assert "grok" in primary or "pager" in primary
    tools = by_id.get("tool-system")
    assert tools is not None
    assert any("tool_bridge" in p or "tools" in p for p in tools.key_files)

    llm = [
        TopicOutline(
            id=ENTRY_ID,
            title="入口与启动",
            section="deep-dive",
            purpose="进程入口是 bin/protoc，一个 dotslash 脚本。",
            key_files=[
                "bin/protoc",
                "crates/code-graph/src/main.rs",
                "crates/fast-worktree/src/main.rs",
            ],
        )
    ]
    merged = merge_topics(topics, llm, {f.path for f in project.files})
    rebound = next(t for t in merged if t.id == ENTRY_ID)
    rebound_joined = " ".join(rebound.key_files)
    assert "protoc" not in rebound_joined
    assert "worktree" not in rebound_joined
    assert "code-graph" not in rebound_joined
    assert "bin/grok.rs" in rebound_joined or "pager" in rebound_joined
    assert "protoc" not in rebound.key_files[0]
    assert "grok" in rebound.key_files[0] or "pager" in rebound.key_files[0]
    assert "protoc" not in (rebound.purpose or "").lower()
    assert "dotslash" not in (rebound.purpose or "").lower()
    assert "grok" in (rebound.purpose or "").lower() or "pager" in (
        rebound.purpose or ""
    ).lower()


def test_entry_and_boot_excludes_protoc_dotslash_as_primary():
    from repowiki.core.topics import is_entry_boot_file, is_toolchain_boot_file

    assert is_toolchain_boot_file("bin/protoc")
    assert not is_entry_boot_file("bin/protoc")
    assert is_entry_boot_file("bin/grok.rs")
    assert is_entry_boot_file("crates/xai-grok-pager/src/lib.rs")


def test_merge_topics_drops_generic_web_slugs_on_grok_tree():
    from repowiki.core.models import TopicOutline
    from repowiki.core.topics import build_deterministic_topics, merge_topics

    project = _grok_project()
    graph = DependencyGraph.build_from_project(project)
    base = build_deterministic_topics(project, graph, language="zh")
    llm = [
        TopicOutline(
            id="caching",
            title="缓存",
            section="deep-dive",
            key_files=["crates/agent/src/runtime.rs"],
        ),
        TopicOutline(
            id="request-routing",
            title="请求路由",
            section="deep-dive",
            key_files=["bin/grok.rs"],
        ),
        TopicOutline(
            id="data-persistence",
            title="数据持久化",
            section="deep-dive",
            key_files=["crates/agent/src/loop.rs"],
        ),
        TopicOutline(
            id="authentication",
            title="身份认证",
            section="deep-dive",
            key_files=["crates/agent/src/runtime.rs"],
        ),
        TopicOutline(
            id="agent-loop",
            title="Agent Loop",
            section="deep-dive",
            key_files=["crates/agent/src/loop.rs"],
        ),
    ]
    merged = merge_topics(base, llm, {f.path for f in project.files})
    ids = {t.id for t in merged}
    assert "caching" not in ids
    assert "request-routing" not in ids
    assert "data-persistence" not in ids
    assert "authentication" not in ids
    assert "agent-loop" in ids


def test_authentication_topic_kept_when_auth_crate_exists():
    from repowiki.core.models import TopicOutline
    from repowiki.core.topics import build_deterministic_topics, merge_topics

    project = _grok_project()
    project.files.append(
        _file(
            "crates/codegen/xai-grok-auth/src/lib.rs",
            "pub struct GrokAuth;\n" + "pub fn f() {}\n" * 40,
        )
    )
    graph = DependencyGraph.build_from_project(project)
    base = build_deterministic_topics(project, graph, language="zh")
    ids = {t.id for t in base}
    assert "authentication" in ids
    assert "caching" not in ids
    llm = [
        TopicOutline(
            id="authentication",
            title="xAI Grok Auth",
            section="deep-dive",
            key_files=["crates/codegen/xai-grok-auth/src/lib.rs"],
        )
    ]
    merged = merge_topics(base, llm, {f.path for f in project.files})
    assert any(t.id == "authentication" for t in merged)


def test_rebuild_hides_legacy_module_tree():
    pages = [
        {"id": "index", "title": "概述"},
        {"id": "architecture", "title": "架构概览"},
        {"id": "modules/.cargo", "title": ".cargo"},
        {"id": "modules/crates/codegen/ptyctl", "title": "crates/codegen/ptyctl"},
        {"id": "concepts/project-goal", "title": "项目目标"},
        {"id": "concepts/application-entry", "title": "应用入口"},
    ]
    old = [
        {"title": "概述", "page_id": "index", "children": []},
        {"title": "架构概览", "page_id": "architecture", "children": []},
        {
            "title": "模块",
            "page_id": "",
            "children": [
                {"title": ".cargo", "page_id": "modules/.cargo", "children": []},
                {
                    "title": "ptyctl",
                    "page_id": "modules/crates/codegen/ptyctl",
                    "children": [],
                },
            ],
        },
    ]
    assert sidebar_looks_like_module_tree(old)
    rebuilt = rebuild_topic_sidebar(pages, language="zh")
    titles = [item["title"] for item in rebuilt]
    assert titles[0] == "入门指南"
    assert "深入探索" in titles
    nav = _top_level_nav_titles(rebuilt)
    assert "概述" in nav
    assert ".cargo" not in nav
    assert "ptyctl" not in nav
    assert "crates/codegen/ptyctl" not in nav


def test_wiki_out_rebuilds_flat_overview_architecture_modules(monkeypatch):
    """Refresh must regroup even when the detector misses the old Modules tree."""
    monkeypatch.setenv("RECALLSTACK_CONTENT_LANG", "zh")
    pages = [
        {"id": "index", "title": "概述", "content": "# 概述\n"},
        {"id": "architecture", "title": "架构概览", "content": "# 架构\n"},
        {"id": "modules/.cargo", "title": ".cargo", "content": "# .cargo\n"},
        {
            "id": "modules/crates/codegen/ptyctl",
            "title": "crates/codegen/ptyctl",
            "content": "# ptyctl\n",
        },
        {"id": "concepts/application-entry", "title": "应用入口", "content": "# 入口\n"},
    ]
    old_sidebar = [
        {"title": "概述", "page_id": "index", "children": []},
        {"title": "架构概览", "page_id": "architecture", "children": []},
        {
            "title": "模块",
            "page_id": "",
            "children": [
                {
                    "title": ".cargo",
                    "page_id": "modules/.cargo",
                    "children": [],
                },
                {
                    "title": "crates",
                    "page_id": "",
                    "children": [
                        {
                            "title": "codegen",
                            "page_id": "",
                            "children": [
                                {
                                    "title": "ptyctl",
                                    "page_id": "modules/crates/codegen/ptyctl",
                                    "children": [],
                                }
                            ],
                        }
                    ],
                },
            ],
        },
    ]
    assert not sidebar_has_topic_groups(old_sidebar)

    class _Version:
        id = "ver-1"
        wiki_pages = {
            "project_name": "grok-study",
            "pages": pages,
            "sidebar": old_sidebar,
        }

    out = wiki_out("repo-1", _Version())
    titles = [item.title for item in out.sidebar]
    assert "入门指南" in titles
    assert "深入探索" in titles
    top_children = _top_level_nav_titles(
        [item.model_dump() for item in out.sidebar]
    )
    assert "概述" in top_children
    assert ".cargo" not in top_children
    assert ".cargo" not in titles
    for item in out.sidebar:
        if item.title in {"入门指南", "深入探索"}:
            assert all(child.title != ".cargo" for child in item.children)


def test_wiki_out_upgrades_emdash_source_chips(monkeypatch):
    monkeypatch.setenv("RECALLSTACK_CONTENT_LANG", "zh")
    old = (
        "# grok-study\n\n"
        "**相关源码:** `bin/grok.rs:1` — `Agent` · `crates/acp/src/lib.rs:12` — `AcpServer`\n\n"
        "## 它是什么\n"
    )

    class _Version:
        id = "ver-1"
        wiki_pages = {
            "project_name": "grok-study",
            "pages": [{"id": "index", "title": "概述", "content": old}],
            "sidebar": [
                {"title": "入门指南", "page_id": "", "children": [
                    {"title": "概述", "page_id": "index", "children": []}
                ]},
            ],
        }

    page = wiki_out("repo-1", _Version()).pages[0]
    assert "`bin/grok.rs:1 Agent`" in page.content
    assert "`crates/acp/src/lib.rs:12 AcpServer`" in page.content
    assert " — `" not in page.content
    assert " · " not in page.content


def test_wiki_out_drops_thin_generic_web_topics_and_dead_links(monkeypatch):
    monkeypatch.setenv("RECALLSTACK_CONTENT_LANG", "zh")
    thin = (
        "# 缓存\n\n> 「缓存」在一次真实调用里做什么、缺了它哪条能力会断。\n\n"
        "## 它是什么\n\n- 这条链路经过 `crates/agent/src/runtime.rs`。\n"
    )
    overview = (
        "# grok-study\n\n"
        "> 阅读后，您应能说明：一次调用怎么走。\n\n"
        "## 继续读\n\n"
        "- [context-assembly](topics/context-assembly)\n"
        "- [pty-control](topics/pty-control)\n"
        "- [code-graph](topics/code-graph)\n"
        "- [Agent Loop](topics/agent-loop)\n"
        "- [TUI](topics/tui-pager)\n"
        "- [代码图谱](topics/codebase-graph)\n"
    )
    evidence = (
        "# Agent Loop\n\n"
        "## 源码证据\n\n"
        "- `crates/agent/src/loop.rs:40` — `Session` — 持有本轮\n"
        "- `Cli`\n"
        "- `Terminal` — draw\n"
    )
    pages = [
        {"id": "index", "title": "概述", "content": overview},
        {"id": "architecture", "title": "架构概览", "content": "# 架构\n"},
        {"id": "topics/agent-loop", "title": "Agent Loop", "content": evidence},
        {"id": "topics/tui-pager", "title": "TUI", "content": "# tui\n"},
        {"id": "topics/codebase-graph", "title": "代码图谱", "content": "# graph\n"},
        {"id": "topics/caching", "title": "缓存", "content": thin},
        {"id": "topics/request-routing", "title": "请求路由", "content": thin},
        {"id": "topics/data-persistence", "title": "持久化", "content": thin},
        {"id": "concepts/caching", "title": "缓存", "content": thin},
        {"id": "concepts/request-routing", "title": "请求路由", "content": thin},
        {"id": "concepts/data-persistence", "title": "持久化", "content": thin},
    ]
    sidebar = [
        {"title": "入门指南", "page_id": "", "children": [
            {"title": "概述", "page_id": "index", "children": []}
        ]},
        {"title": "深入探索", "page_id": "", "children": [
            {"title": "架构概览", "page_id": "architecture", "children": []},
            {"title": "Agent Loop", "page_id": "topics/agent-loop", "children": []},
            {"title": "缓存", "page_id": "topics/caching", "children": []},
            {"title": "请求路由", "page_id": "topics/request-routing", "children": []},
            {"title": "持久化", "page_id": "topics/data-persistence", "children": []},
        ]},
    ]

    class _Version:
        id = "ver-1"
        wiki_pages = {
            "project_name": "grok-study",
            "pages": pages,
            "sidebar": sidebar,
        }

    out = wiki_out("repo-1", _Version())
    ids = {p.id for p in out.pages}
    assert "concepts/caching" not in ids
    assert "concepts/request-routing" not in ids
    assert "concepts/data-persistence" not in ids
    assert "topics/caching" not in ids
    deep = next(item for item in out.sidebar if item.title == "深入探索")
    child_ids = [c.page_id for c in deep.children]
    assert "topics/agent-loop" in child_ids
    assert "topics/caching" not in child_ids
    assert "topics/request-routing" not in child_ids
    assert "topics/data-persistence" not in child_ids
    index = next(p for p in out.pages if p.id == "index")
    assert "[Agent Loop](topics/agent-loop)" in index.content
    assert "[TUI](topics/tui-pager)" in index.content
    assert "[代码图谱](topics/codebase-graph)" in index.content
    assert "topics/context-assembly" not in index.content
    assert "topics/pty-control" not in index.content
    assert "topics/code-graph" not in index.content
    assert "[pty-control](topics/tui-pager)" in index.content
    assert "[code-graph](topics/codebase-graph)" in index.content
    assert "您" not in index.content
    assert "读完应能" in index.content
    loop = next(p for p in out.pages if p.id == "topics/agent-loop")
    assert "`crates/agent/src/loop.rs:40 Session`" in loop.content
    assert " — `Session`" not in loop.content
    assert "`Cli`" not in loop.content
    assert "`Terminal`" not in loop.content


def test_wiki_out_upgrades_three_part_chip_with_spaced_symbol(monkeypatch):
    monkeypatch.setenv("RECALLSTACK_CONTENT_LANG", "zh")
    evidence = (
        "# Agent Loop\n\n"
        "## 源码证据\n\n"
        "- `crates/xai-chat/src/lib.rs:10` — `mod channel` — 通道\n"
        "- `crates/agent/src/loop.rs:40` — `Session` — 持有本轮\n"
    )

    class _Version:
        id = "ver-1"
        wiki_pages = {
            "project_name": "grok-study",
            "pages": [
                {"id": "index", "title": "概述", "content": "# grok-study\n"},
                {"id": "topics/agent-loop", "title": "Agent Loop", "content": evidence},
            ],
            "sidebar": [
                {"title": "入门指南", "page_id": "", "children": [
                    {"title": "概述", "page_id": "index", "children": []}
                ]},
                {"title": "深入探索", "page_id": "", "children": [
                    {"title": "Agent Loop", "page_id": "topics/agent-loop", "children": []},
                ]},
            ],
        }

    out = wiki_out("repo-1", _Version())
    loop = next(p for p in out.pages if p.id == "topics/agent-loop")
    assert "`crates/xai-chat/src/lib.rs:10 mod channel`" in loop.content
    assert " — 通道" in loop.content
    assert "`crates/agent/src/loop.rs:40 Session`" in loop.content
    assert " — `mod channel`" not in loop.content
    items = [ln for ln in loop.content.splitlines() if ln.startswith("- ")]
    assert len(items) == 2


def test_wiki_out_upgrades_key_types_and_agentloop(monkeypatch):
    monkeypatch.setenv("RECALLSTACK_CONTENT_LANG", "zh")
    arch = (
        "# 架构概览\n\n"
        "> 这篇文档讲系统怎么串起来（cli-tool）。\n\n"
        "## 关键类型\n\n"
        "- `Session` — 持有本轮 — `crates/agent/src/loop.rs:40`\n"
        "- `lib.rs` — crate root — `crates/foo/src/lib.rs:1`\n\n"
        "`AgentLoop` lives in lib.rs\n"
    )
    thin_gs = "# 快速开始\n\n> 这篇按 README 跑起来。\n\n## 相关源码\n\n- `README.md`\n"

    class _Version:
        id = "ver-1"
        wiki_pages = {
            "project_name": "grok-study",
            "pages": [
                {"id": "index", "title": "概述", "content": "# grok-study\n"},
                {"id": "architecture", "title": "架构概览", "content": arch},
                {"id": "getting-started", "title": "快速开始", "content": thin_gs},
                {"id": "topics/agent-loop", "title": "Agent Loop", "content": "# loop\n"},
            ],
            "sidebar": [
                {"title": "入门指南", "page_id": "", "children": [
                    {"title": "概述", "page_id": "index", "children": []},
                    {"title": "快速开始", "page_id": "getting-started", "children": []},
                ]},
                {"title": "深入探索", "page_id": "", "children": [
                    {"title": "架构概览", "page_id": "architecture", "children": []},
                ]},
                {"title": "按目录", "page_id": "", "children": [
                    {"title": f"c{i}", "page_id": f"modules/c{i}", "children": []}
                    for i in range(20)
                ]},
            ],
        }

    out = wiki_out("repo-1", _Version())
    page = next(p for p in out.pages if p.id == "architecture")
    assert "Session — 持有本轮 — `crates/agent/src/loop.rs:40 Session`" in page.content
    assert "`lib.rs`" not in page.content
    assert "AgentLoop" not in page.content
    assert "cli-tool" not in page.content
    gs = next(p for p in out.pages if p.id == "getting-started")
    assert "跑起来之后" in gs.content
    assert "[架构概览](architecture)" in gs.content
    directory = next(item for item in out.sidebar if item.title == "按目录")
    assert len(directory.children) <= 8


def _directory_leaf_titles(item) -> list[str]:
    children = getattr(item, "children", None) or []
    if not children:
        return [getattr(item, "title", "") or ""]
    out: list[str] = []
    for child in children:
        out.extend(_directory_leaf_titles(child))
    return out


def test_wiki_out_directory_nav_ranks_product_crates_not_cargo():
    pages = [
        {
            "id": "index",
            "title": "概述",
            "content": (
                "# grok-study\n\n"
                "核心在 `crates/xai-grok-pager` 与 `crates/xai-grok-agent`。\n"
            ),
        },
        {"id": "architecture", "title": "架构概览", "content": "# 架构\n"},
        {"id": "modules/.cargo", "title": ".cargo", "content": "# .cargo\n"},
        {"id": "modules/bin", "title": "bin", "content": "# bin\n"},
        {
            "id": "modules/crates/xai-grok-agent",
            "title": "xai-grok-agent",
            "content": "# agent\n",
        },
        {
            "id": "modules/crates/xai-grok-pager",
            "title": "xai-grok-pager",
            "content": "# pager\n",
        },
    ]
    crate_children = [
        {"title": f"aa-codegen-{i}", "page_id": f"modules/crates/aa-codegen-{i}", "children": []}
        for i in range(10)
    ] + [
        {
            "title": "xai-grok-agent",
            "page_id": "modules/crates/xai-grok-agent",
            "children": [],
        },
        {
            "title": "xai-grok-pager",
            "page_id": "modules/crates/xai-grok-pager",
            "children": [],
        },
    ]
    for i in range(10):
        pages.append(
            {
                "id": f"modules/crates/aa-codegen-{i}",
                "title": f"aa-codegen-{i}",
                "content": "# codegen\n",
            }
        )

    class _Version:
        id = "ver-1"
        wiki_pages = {
            "project_name": "grok-study",
            "pages": pages,
            "sidebar": [
                {
                    "title": "入门指南",
                    "page_id": "",
                    "children": [{"title": "概述", "page_id": "index", "children": []}],
                },
                {
                    "title": "按目录",
                    "page_id": "",
                    "children": [
                        {"title": ".cargo", "page_id": "modules/.cargo", "children": []},
                        {"title": "bin", "page_id": "modules/bin", "children": []},
                        {
                            "title": "crates",
                            "page_id": "",
                            "children": crate_children,
                        },
                    ],
                },
            ],
        }

    out = wiki_out("repo-1", _Version())
    directory = next(item for item in out.sidebar if item.title == "按目录")
    leaves = []
    for child in directory.children:
        leaves.extend(_directory_leaf_titles(child))
    assert ".cargo" not in leaves
    assert "bin" not in leaves
    assert "xai-grok-pager" in leaves
    assert "xai-grok-agent" in leaves
    assert len(leaves) <= 8


def test_wiki_out_drops_pty_glossary_stub_for_failed_topic():
    stub = (
        "# Markdown 渲染\n\n"
        "> 下面只跟这一条快乐路径，不把 crate 当目录念，也不给 struct 列方法。\n\n"
        "快乐路径不从目录名开始，而从 `crates/markdown/src/lib.rs:1` 开始。"
        "`surface_background` 是这条链上的角色。\n\n"
        "## 术语小贴士\n\n"
        "> **PTY** — 伪终端：字节在进程与控制器之间流动。把它当管道，不要当目录名。\n"
    )

    class _Version:
        id = "ver-1"
        wiki_pages = {
            "project_name": "grok-study",
            "pages": [
                {"id": "index", "title": "概述", "content": "# grok-study\n"},
                {
                    "id": "topics/markdown-rendering",
                    "title": "Markdown 渲染",
                    "content": stub,
                },
                {
                    "id": "topics/agent-loop",
                    "title": "Agent Loop",
                    "content": "# loop\n\nstart_turn → model → ToolBridge\n",
                },
            ],
            "sidebar": [
                {
                    "title": "深入探索",
                    "page_id": "",
                    "children": [
                        {
                            "title": "Markdown 渲染",
                            "page_id": "topics/markdown-rendering",
                            "children": [],
                        },
                        {
                            "title": "Agent Loop",
                            "page_id": "topics/agent-loop",
                            "children": [],
                        },
                    ],
                },
            ],
        }

    out = wiki_out("repo-1", _Version())
    ids = {p.id for p in out.pages}
    assert "topics/markdown-rendering" not in ids
    assert "topics/agent-loop" in ids
    md_pages = [p for p in out.pages if p.id == "topics/markdown-rendering"]
    assert not md_pages
    deep = next(item for item in out.sidebar if item.title == "深入探索")
    deep_ids = [c.page_id for c in deep.children]
    assert "topics/markdown-rendering" not in deep_ids
    assert "topics/agent-loop" in deep_ids
    combined = "\n".join(p.content for p in out.pages)
    assert "伪终端：字节在进程与控制器之间流动" not in combined


def test_wiki_out_fills_key_type_line_and_strips_guide_homework(monkeypatch):
    monkeypatch.setenv("RECALLSTACK_CONTENT_LANG", "zh")
    topic = (
        "# Markdown 渲染\n\n"
        "## 关键类型\n\n"
        "- StreamingMarkdownRenderer — 流式渲染 — "
        "`crates/markdown/src/lib.rs StreamingMarkdownRenderer`\n\n"
        "## 源码证据\n\n"
        "- `crates/markdown/src/lib.rs:40 StreamingMarkdownRenderer`\n"
    )
    guide = (
        "# 导读\n\n"
        "这是仓库的阅读剧本。每一步对应一个可练习概念：先读证据，再做回忆。\n\n"
        "## 可练习概念\n\n- Markdown\n\n"
        "## 步骤 1: 渲染 (~10 min)\n\n跟一次调用。\n"
    )

    class _Version:
        id = "ver-1"
        wiki_pages = {
            "project_name": "grok-study",
            "pages": [
                {"id": "index", "title": "概述", "content": "# grok-study\n"},
                {
                    "id": "topics/markdown-rendering",
                    "title": "Markdown 渲染",
                    "content": topic,
                },
                {"id": "reading-guide", "title": "导读", "content": guide},
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
                        {
                            "title": "Markdown 渲染",
                            "page_id": "topics/markdown-rendering",
                            "children": [],
                        }
                    ],
                },
            ],
        }

    out = wiki_out("repo-1", _Version())
    md = next(p for p in out.pages if p.id == "topics/markdown-rendering")
    assert "`crates/markdown/src/lib.rs:40 StreamingMarkdownRenderer`" in md.content
    assert "`crates/markdown/src/lib.rs StreamingMarkdownRenderer`" not in md.content
    guide_page = next(p for p in out.pages if p.id == "reading-guide")
    assert "可练习概念" not in guide_page.content
    assert "再跟一次调用" in guide_page.content
    assert "## 步骤 1: 渲染" in guide_page.content
    getting = next(item for item in out.sidebar if item.title == "入门指南")
    assert any(c.page_id == "reading-guide" for c in getting.children)


def test_wiki_out_wraps_bare_overview_mermaid():
    class _Version:
        id = "ver-1"
        wiki_pages = {
            "project_name": "grok-study",
            "pages": [
                {
                    "id": "index",
                    "title": "概述",
                    "content": (
                        "# grok-study\n\n"
                        "## 核心子系统\n\n"
                        "### Terminal UI\n\n"
                        "```mermaid\n"
                        "Pager → Terminal\n"
                        "```\n\n"
                        "### Agent Loop\n\n"
                        "```mermaid\n"
                        "Agent --> AgentClient --> Model\n"
                        "```\n"
                    ),
                },
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
    content = out.pages[0].content
    assert "flowchart LR" in content
    assert "Pager --> Terminal" in content
    assert "Agent --> AgentClient --> Model" in content
    assert "→" not in content


