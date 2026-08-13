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
        _file("crates/agent/src/runtime.rs", "pub struct AgentRuntime;\n" + filler),
        _file("crates/agent/src/loop.rs", "pub fn agent_loop() {}\n" + filler),
        _file("crates/agent/src/prompt.rs", "pub fn system_prompt() {}\n" + filler),
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
    assert "caching" not in path_slugs
    assert "authentication" not in path_slugs
    assert "request-routing" not in path_slugs
    assert any(s not in {"project-goal", "getting-started"} for s in path_slugs)


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
