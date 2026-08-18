from __future__ import annotations

import re

from repowiki.core.graph import DependencyGraph
from repowiki.core.models import (
    ArchitectureDiagram,
    CallChain,
    Citation,
    CodebasePart,
    FileDoc,
    FileInfo,
    KeyType,
    ModuleDoc,
    ProjectContext,
    ProjectOverview,
    ReadingGuide,
    ReadingStep,
    Subsystem,
    Symbol,
    TechItem,
    TermTip,
    TopicDoc,
    WikiData,
)
from repowiki.core.modules import ROOT_NAME, group_into_modules
from repowiki.core.wiki_builder import (
    WikiBuilder,
    cap_directory_sidebar,
    clip_mermaid_label,
    fill_key_type_chip_lines,
    filter_unknown_wiki_links,
    normalize_mermaid_source,
    shorten_mermaid_node_labels,
    strip_reading_wiki_homework,
    upgrade_architecture_loop_wording,
    upgrade_key_type_chip_markdown,
    upgrade_legacy_module_markdown,
    upgrade_mermaid_fences,
    upgrade_source_chip_markdown,
    upgrade_wiki_page_content,
)

_FILLER = "x = 1\n" * 200


def _project(files: dict[str, str]) -> ProjectContext:
    return ProjectContext(
        name="fixture",
        root=".",
        files=[
            FileInfo(
                path=path,
                size=len(content),
                language="python",
                content=content,
                lines=content.count("\n") + 1,
            )
            for path, content in files.items()
        ],
    )


def _split_project() -> ProjectContext:
    """Large enough that the grouping splits `app` into its subdirectories."""
    files = {f"app/api/view{i}.py": _FILLER for i in range(4)}
    files |= {f"app/services/svc{i}.py": _FILLER for i in range(4)}
    files["app/api/routes.py"] = "from app.services.svc0 import thing\n" + _FILLER
    return _project(files)


def _build(project: ProjectContext):
    """Build a wiki whose modules come from the shared grouping, as in production."""
    graph = DependencyGraph.build_from_project(project)
    names = sorted(group_into_modules(project.files))
    data = WikiData(modules=[ModuleDoc(name=n) for n in names])
    return WikiBuilder().build(project, data, graph), names


def test_module_page_carries_its_own_dependency_diagram():
    """Each module page shows its neighbourhood, not the whole project graph.

    Before this the only diagram in the wiki was on the architecture page.
    """
    wiki, names = _build(_split_project())

    assert names == ["app/api", "app/services"]
    page = wiki.get_page("modules/app/api")
    assert "```mermaid" in page.content
    assert "app/services" in page.content


def test_module_without_edges_gets_no_empty_diagram():
    wiki, names = _build(_project({"solo/thing.py": "x = 1\n"}))

    assert names == ["solo"]
    assert "```mermaid" not in wiki.get_page("modules/solo").content


def test_module_sidebar_nests_by_path():
    """Module names are full paths; listed flat they are wide and repetitive."""
    wiki, _ = _build(_split_project())
    modules = next(item for item in wiki.sidebar if item.title == "By directory")

    app = next(c for c in modules.children if c.title == "app")
    assert app.page_id == ""  # intermediate directory, no page of its own
    assert {c.title for c in app.children} == {"api", "services"}
    assert {c.page_id for c in app.children} == {"modules/app/api", "modules/app/services"}


def test_module_page_renders_deep_sections_when_present():
    project = _project({"app/main.py": "def main():\n    return 1\n"})
    graph = DependencyGraph.build_from_project(project)
    data = WikiData(
        modules=[
            ModuleDoc(
                name="app",
                purpose="entry",
                description="The process starts here.",
                implementation_details="main() returns 1.",
                call_chains=[
                    CallChain(
                        name="boot",
                        description="process start",
                        steps=["main() runs"],
                        files=["app/main.py"],
                    )
                ],
                edge_cases=["main has no arguments"],
                files=[
                    FileDoc(
                        path="app/main.py",
                        purpose="happy path enters here",
                        key_symbols=[Symbol(name="spawn", kind="function")],
                    )
                ],
                citations=[Citation(path="app/main.py", start_line=1, symbol="main")],
            )
        ]
    )
    wiki = WikiBuilder().build(project, data, graph)
    content = wiki.get_page("modules/app").content
    assert "## Implementation" in content
    assert "main() returns 1." in content
    assert "## Call path" in content
    assert "### boot" in content
    assert "## Boundaries" in content
    assert "## Source Evidence" in content
    assert "`app/main.py:1 main`" in content
    assert " — `main`" not in content
    assert content.index("## Call path") < content.index("## Related source")
    assert content.index("## Call path") < content.index("## Implementation")
    assert "## How it actually runs" not in content
    assert "## Key Call Chains" not in content
    assert "`spawn` (function)" not in content


def test_module_page_omits_empty_deep_sections():
    wiki, names = _build(_project({"solo/thing.py": "x = 1\n"}))
    assert names == ["solo"]
    content = wiki.get_page("modules/solo").content
    assert "## Implementation" not in content
    assert "## How it actually runs" not in content
    assert "## Key Call Chains" not in content
    assert "## How a call runs" not in content
    assert "## Edge Cases" not in content
    assert "## Failures and edges" not in content
    assert "## Source Evidence" not in content


def _structural_project() -> ProjectContext:
    """Root files + two path modules, with a cross-module import for Dependencies."""
    files = {f"app/view{i}.py": _FILLER for i in range(2)}
    files["app/main.py"] = "from util.helpers import x\n" + _FILLER
    files["util/helpers.py"] = "x = 1\n" + _FILLER
    files["crates/lib.py"] = _FILLER
    files["README.md"] = "# demo\n" + _FILLER
    return _project(files)


def _structural_wiki(language: str = "en"):
    project = _structural_project()
    graph = DependencyGraph.build_from_project(project)
    names = sorted(group_into_modules(project.files))
    data = WikiData(
        modules=[ModuleDoc(name=n) for n in names],
        architecture=ArchitectureDiagram(architecture_type="monolith", description="layers"),
        reading_guide=ReadingGuide(
            steps=[ReadingStep(order=1, title="start", files=["app/main.py"])]
        ),
    )
    return WikiBuilder().build(project, data, graph, language=language), names


def test_en_structural_sidebar_titles_stay_english():
    wiki, names = _structural_wiki("en")
    titles = [item.title for item in wiki.sidebar]
    assert titles[0] == "Getting Started"
    assert "Deep Dive" in titles
    assert "By directory" in titles
    assert "Reading Guide" not in titles
    assert "Dependencies" not in titles
    modules = next(item for item in wiki.sidebar if item.title == "By directory")
    assert ROOT_NAME in names
    root = next(c for c in modules.children if c.page_id == "modules/root")
    assert root.title == "Root"
    crates = next(c for c in modules.children if c.title == "crates")
    assert crates.page_id == "modules/crates"
    getting = next(item for item in wiki.sidebar if item.title == "Getting Started")
    assert any(c.page_id == "index" for c in getting.children)
    deep = next(item for item in wiki.sidebar if item.title == "Deep Dive")
    assert any(c.page_id == "architecture" for c in deep.children)
    assert wiki.get_page("index").id == "index"
    assert wiki.get_page("modules/root").id == "modules/root"
    assert wiki.get_page("architecture").content.startswith("# Architecture")
    assert wiki.get_page("reading-guide").content.startswith("# Reading Guide")
    assert wiki.get_page("dependencies").content.startswith("# Dependencies")
    assert wiki.get_page("modules/root").content.startswith("# Root")


def test_zh_structural_sidebar_titles_and_headings():
    wiki, names = _structural_wiki("zh")
    titles = [item.title for item in wiki.sidebar]
    assert titles[0] == "入门指南"
    assert "深入探索" in titles
    assert "按目录" in titles
    assert "Overview" not in titles
    assert "Modules" not in titles
    assert "总览" not in titles
    modules = next(item for item in wiki.sidebar if item.title == "按目录")
    assert ROOT_NAME in names
    root = next(c for c in modules.children if c.page_id == "modules/root")
    assert root.title == "根目录"
    assert root.page_id == "modules/root"
    # Real path segments stay as in the repo.
    crates = next(c for c in modules.children if c.page_id == "modules/crates")
    assert crates.title == "crates"
    app = next(c for c in modules.children if c.title == "app")
    assert app.title == "app"
    assert wiki.get_page("index").id == "index"
    assert wiki.get_page("index").title == "概述"
    assert wiki.get_page("architecture").title == "架构概览"
    assert wiki.get_page("reading-guide").title == "导读"
    assert wiki.get_page("dependencies").title == "依赖"
    assert wiki.get_page("modules/root").id == "modules/root"
    assert wiki.get_page("modules/root").title == "根目录"
    assert wiki.get_page("architecture").content.startswith("# 架构概览")
    assert wiki.get_page("reading-guide").content.startswith("# 导读")
    assert wiki.get_page("dependencies").content.startswith("# 依赖")
    assert wiki.get_page("modules/root").content.startswith("# 根目录")
    assert "# Architecture" not in wiki.get_page("architecture").content


def test_old_json_parses_without_term_tips():
    overview = ProjectOverview.model_validate({"name": "demo", "description": "x"})
    arch = ArchitectureDiagram.model_validate({"architecture_type": "monolith"})
    mod = ModuleDoc.model_validate({"name": "app", "purpose": "boot"})
    assert overview.term_tips == []
    assert overview.what_it_is == []
    assert overview.codebase_structure == []
    assert overview.subsystems == []
    assert overview.mermaid_component == ""
    assert arch.term_tips == []
    assert arch.components == []
    assert mod.term_tips == []
    assert mod.what_it_is == []
    assert mod.key_types == []


def test_term_tips_section_omitted_when_empty():
    project = _project({"app/main.py": "def main():\n    return 1\n"})
    graph = DependencyGraph.build_from_project(project)
    data = WikiData(
        overview=ProjectOverview(name="fixture", description="boot"),
        architecture=ArchitectureDiagram(architecture_type="monolith", description="layers"),
        modules=[ModuleDoc(name="app", purpose="entry", description="starts here")],
    )
    wiki = WikiBuilder().build(project, data, graph, language="zh")
    assert "术语小贴士" not in wiki.get_page("index").content
    assert "术语小贴士" not in wiki.get_page("architecture").content
    assert "术语小贴士" not in wiki.get_page("modules/app").content
    assert "Term tips" not in wiki.get_page("modules/app").content


def test_zh_headings_term_tips_and_unchanged_paths():
    project = _structural_project()
    graph = DependencyGraph.build_from_project(project)
    data = WikiData(
        overview=ProjectOverview(
            name="fixture",
            description="手册正文",
            term_tips=[TermTip(term="PageRank", tip="按 import 图给文件打分")],
        ),
        architecture=ArchitectureDiagram(
            architecture_type="codebase-modules",
            description="按目录划模块，而不是罗列文件。",
            components=[{"name": "crates", "purpose": "lib", "files": ["crates/lib.py"]}],
            term_tips=[TermTip(term="crate", tip="Cargo 包单位")],
        ),
        modules=[
            ModuleDoc(
                name="crates",
                purpose="lib boundary",
                description="职责边界",
                implementation_details="`crates/lib.py:1` 提供实现。",
                call_chains=[
                    CallChain(name="boot", description="启动", steps=["run()"], files=["crates/lib.py"])
                ],
                edge_cases=["缺配置时失败"],
                files=[FileDoc(path="crates/lib.py", purpose="快乐路径上的 lib")],
                citations=[Citation(path="crates/lib.py", start_line=1)],
                term_tips=[TermTip(term="ACP", tip="本仓库的 agent 协议")],
            )
        ],
        reading_guide=ReadingGuide(steps=[ReadingStep(order=1, title="start", files=["app/main.py"])]),
    )
    wiki = WikiBuilder().build(project, data, graph, language="zh")
    overview = wiki.get_page("index").content
    assert "## 术语" in overview
    assert "**PageRank**" in overview
    assert "## Tech Stack" not in overview

    arch = wiki.get_page("architecture").content
    assert arch.startswith("# 架构概览")
    assert "codebase-modules" in arch
    assert "## 链路里的角色" in arch
    assert "crates/lib.py" in arch
    assert "## 术语" in arch
    assert "**Type:**" not in arch
    assert "## Components" not in arch
    assert "## 组成" not in arch
    assert "**类型:**" not in arch

    page = wiki.get_page("modules/crates")
    assert page.title == "crates"
    content = page.content
    assert content.startswith("# crates")
    assert "## 调用链" in content
    assert "## 实现" in content
    assert "## 边界" in content
    assert "## 相关源码" in content
    assert "## 源码证据" in content
    assert "## 术语" in content
    assert "**ACP**" in content
    assert "## 实现细节" not in content
    assert "## 关键调用链" not in content
    assert "## Implementation" not in content
    assert "## Key Call Chains" not in content
    assert content.index("## 调用链") < content.index("## 相关源码")
    assert content.index("## 调用链") < content.index("## 实现")

    crates = next(
        c
        for item in wiki.sidebar
        if item.title == "按目录"
        for c in item.children
        if c.page_id == "modules/crates"
    )
    assert crates.title == "crates"


def test_concept_section_title_follows_content_lang(monkeypatch):
    from recallstack.domain.schemas import ConceptDraft
    from recallstack.learning.wiki_generator import append_concept_pages
    from repowiki.core.wiki_builder import Wiki, WikiPage

    wiki = Wiki(
        project_name="demo",
        pages=[WikiPage(id="index", title="Overview", content="# x\n")],
        sidebar=[],
    )
    draft = ConceptDraft(slug="project-goal", title="项目目标", description="goal")
    monkeypatch.setenv("RECALLSTACK_CONTENT_LANG", "zh")
    zh = append_concept_pages(wiki, [draft])
    assert zh.sidebar[-1].title == "词条"
    assert zh.sidebar[-1].page_id == ""
    assert zh.sidebar[-1].children[0].title == "项目目标"
    assert zh.sidebar[-1].children[0].page_id == "concepts/project-goal"

    wiki_en = Wiki(project_name="demo", pages=[], sidebar=[])
    monkeypatch.setenv("RECALLSTACK_CONTENT_LANG", "en")
    en = append_concept_pages(wiki_en, [draft])
    assert en.sidebar[-1].title == "Concepts"


def test_module_page_skips_javadoc_symbol_dump_and_puts_flow_first():
    project = _project(
        {
            "crates/codegen/ptyctl/src/lib.rs": "pub fn spawn() {}\n",
            "crates/codegen/ptyctl/src/pty.rs": "pub struct PtyHandle;\n",
        }
    )
    graph = DependencyGraph.build_from_project(project)
    data = WikiData(
        modules=[
            ModuleDoc(
                name="crates/codegen/ptyctl",
                purpose="无头 PTY 控制器",
                description="一次 WebSocket 会话从 axum 进到 PtyHandle 再读屏。",
                implementation_details=(
                    "`crates/codegen/ptyctl/src/pty.rs:1` 的 `PtyHandle` 接住会话，"
                    "把 PTY 字节拷回 socket。"
                ),
                call_chains=[
                    CallChain(
                        name="one session",
                        description="request to PTY bytes",
                        steps=[
                            "axum handler receives the websocket session",
                            "PtyHandle opens the child PTY and returns a handle",
                            "read loop copies screen bytes back to the client",
                        ],
                    )
                ],
                files=[
                    FileDoc(
                        path="crates/codegen/ptyctl/src/lib.rs",
                        purpose="crate root",
                        key_symbols=[
                            Symbol(name="spawn", kind="function"),
                            Symbol(name="resize", kind="function"),
                            Symbol(name="is_alive", kind="function"),
                        ],
                    )
                ],
            )
        ]
    )
    content = WikiBuilder().build(project, data, graph).get_page("modules/crates/codegen/ptyctl").content
    assert "`spawn` (function)" not in content
    assert "`resize` (function)" not in content
    assert "`is_alive` (function)" not in content
    assert "## Call path" in content
    assert "## Related source" in content
    assert content.index("## Call path") < content.index("## Related source")
    assert "flowchart TD" in content
    assert "```mermaid" in content


def test_upgrade_legacy_module_markdown_strips_methods_and_reorders():
    old = """# crates/codegen/ptyctl

> 无头 PTY 控制器

intro

## 实现细节

The entry point is lib.rs. Submodules are keys, pty, server.

## 文件

- `lib.rs` — crate root
  - `spawn` (function)
  - `resize` (function)
  - `is_alive` (function)

## 关键调用链

### session

1. axum handler receives the websocket session
2. PtyHandle opens the child PTY
3. read loop copies screen bytes back
"""
    upgraded = upgrade_legacy_module_markdown(old, language="zh")
    assert "`spawn` (function)" not in upgraded
    assert "`resize` (function)" not in upgraded
    assert "## 调用链" in upgraded
    assert "## 相关源码" in upgraded
    assert "## 关键调用链" not in upgraded
    assert upgraded.index("## 调用链") < upgraded.index("## 相关源码")
    assert "The entry point is lib.rs" not in upgraded
    assert "Submodules are" not in upgraded


def test_fallback_module_markdown_is_handbook_not_inventory(monkeypatch):
    monkeypatch.setenv("RECALLSTACK_CONTENT_LANG", "zh")
    from recallstack.learning.wiki_generator import build_deterministic_wiki_data

    project = _project(
        {
            "app/main.py": "def main():\n    from app.core import boot\n    boot()\n",
            "app/core.py": "def boot():\n    return 1\n",
        }
    )
    graph = DependencyGraph.build_from_project(project)
    data = build_deterministic_wiki_data(project, graph, [])
    wiki = WikiBuilder().build(project, data, graph, language="zh")
    page = wiki.get_page("modules/app")
    assert page is not None
    content = page.content
    assert "## 调用链" in content
    assert "## 相关源码" in content
    assert content.index("## 调用链") < content.index("## 相关源码")
    assert "`spawn` (function)" not in content
    assert "入口文件" not in content
    assert "源码文件" not in content
    assert "Submodules are" not in content
    assert "The entry point is lib.rs" not in content
    assert any(f.key_symbols == [] for f in data.modules[0].files) or not data.modules[0].files
    for mod in data.modules:
        for f in mod.files:
            assert f.key_symbols == []


def test_overview_is_deepwiki_handbook_not_stack_dump():
    project = _project({"app/main.py": "def main():\n    return 1\n"})
    graph = DependencyGraph.build_from_project(project)
    data = WikiData(
        overview=ProjectOverview(
            name="fixture",
            one_liner="a tiny service",
            description="fixture starts at main and answers one request.",
            tech_stack=[
                TechItem(name="Python", category="language", version="3.12"),
                TechItem(name="FastAPI", category="framework"),
            ],
            citations=[Citation(path="app/main.py", start_line=1)],
        ),
        architecture=ArchitectureDiagram(
            architecture_type="monolith",
            description="request enters main.",
            mermaid_component="graph TD\n  A[main] --> B[core]",
            components=[{"name": "app", "purpose": "receives the process", "files": ["app/main.py"]}],
        ),
    )
    wiki = WikiBuilder().build(project, data, graph, language="zh")
    overview = wiki.get_page("index").content
    assert "解决什么问题" in overview
    assert "## 概述" in overview
    assert "## 系统架构" in overview
    assert "架构见图" in overview
    assert "[架构概览](architecture)" in overview
    assert "| 技术 |" in overview
    assert "Python" in overview
    assert "- **Python**" not in overview
    assert "`app/main.py:1`" in overview
    assert overview.index("相关源码") < overview.index("## 概述")
    assert overview.index("```mermaid") < overview.index("架构见图")

    arch = wiki.get_page("architecture").content
    assert "```mermaid" in arch
    assert "## 系统架构" in arch
    assert "## 链路里的角色" in arch
    assert arch.index("```mermaid") < arch.index("## 链路里的角色")
    assert "**app**" in arch
    assert "`app/main.py`" in arch
    assert "  - 文件:" not in arch


def test_structured_overview_renders_deepwiki_sections_without_key_features():
    project = _project(
        {
            "bin/grok.rs": "fn main() {}\n",
            "crates/agent/src/loop.rs": "pub struct Session;\n",
        }
    )
    graph = DependencyGraph.build_from_project(project)
    data = WikiData(
        overview=ProjectOverview(
            name="grok-study",
            document_scope="这篇文档讲 grok-study 是什么、三种模式怎么跑、仓库怎么拆。读完应能不靠目录讲清一次调用经过谁。",
            what_it_is=[
                "进程从 `bin/grok.rs:1` 启动。",
                "`Session` 在 `crates/agent/src/loop.rs:1` 接住一次对话。",
            ],
            runtime_flow="用户输入进 `bin/grok.rs`，由 `Session` 跑完一轮再吐出回复。",
            mermaid_component="flowchart TD\n  A[bin/grok.rs] --> B[Session]",
            codebase_structure=[
                CodebasePart(name="agent", location="crates/agent", purpose="跑 Agent Loop"),
            ],
            subsystems=[
                Subsystem(
                    name="Agent Loop",
                    role="把一轮对话跑完",
                    key_types=[
                        KeyType(
                            name="Session",
                            role="持有本轮上下文",
                            path="crates/agent/src/loop.rs",
                        )
                    ],
                    files=["crates/agent/src/loop.rs"],
                )
            ],
            see_also=["architecture", "topics/agent-loop"],
            citations=[Citation(path="bin/grok.rs", start_line=1)],
        ),
        architecture=ArchitectureDiagram(
            architecture_type="cli-tool",
            mermaid_component="graph TD\n  X --> Y",
        ),
        topics=[
            TopicDoc(
                name="agent-loop",
                title="Agent Loop",
                section="deep-dive",
                purpose="读完应能指出 Session 在链路上的职责。",
                document_scope="这篇文档讲 Agent Loop 在整仓调用链上的位置。",
                what_it_is=["`Session` 在 `crates/agent/src/loop.rs:1` 接住一轮对话。"],
                key_types=[
                    KeyType(
                        name="Session",
                        role="持有本轮上下文",
                        path="crates/agent/src/loop.rs",
                    )
                ],
                mermaid="flowchart TD\n  U[User] --> S[Session]",
                files=[FileDoc(path="crates/agent/src/loop.rs", purpose="loop")],
            )
        ],
    )
    wiki = WikiBuilder().build(project, data, graph, language="zh")
    overview = wiki.get_page("index").content
    assert "## 概述" in overview
    assert "## 系统架构" in overview
    assert "## 代码如何拆分" in overview
    assert "## 核心子系统" in overview
    assert "```mermaid" in overview
    assert "| 名称 |" in overview
    assert "crates/agent" in overview
    assert "`Session`" in overview
    assert "crates/agent/src/loop.rs Session" in overview
    assert "`Session` — 持有本轮上下文 — `crates/agent/src/loop.rs`" not in overview
    assert "[架构概览](architecture)" in overview
    assert "[Agent Loop](topics/agent-loop)" in overview
    assert "## 主要能力" not in overview
    assert "key_features" not in overview
    assert "本步要你干什么" not in overview
    assert overview.index("相关源码") < overview.index("## 概述")
    assert overview.index("## 概述") < overview.index("## 系统架构")
    assert overview.index("```mermaid") < overview.index("用户输入进")
    assert overview.index("## 系统架构") < overview.index("## 代码如何拆分")
    assert overview.index("## 代码如何拆分") < overview.index("## 核心子系统")

    topic = wiki.get_page("topics/agent-loop").content
    assert "## 概述" in topic
    assert "`Session`" in topic
    assert "```mermaid" in topic
    assert "本步要你干什么" not in topic
    assert "## 过关" not in topic


def test_architecture_renders_type_roles_under_components():
    project = _project({"app/main.py": "def main():\n    return 1\n"})
    graph = DependencyGraph.build_from_project(project)
    data = WikiData(
        architecture=ArchitectureDiagram(
            architecture_type="monolith",
            description="请求从 main 进。",
            mermaid_component="graph TD\n  A[main] --> B[core]",
            components=[
                {
                    "name": "app",
                    "role": "接住进程",
                    "purpose": "receives the process",
                    "files": ["app/main.py"],
                    "key_types": [
                        {"name": "main", "role": "启动进程", "path": "app/main.py"}
                    ],
                }
            ],
        ),
    )
    arch = WikiBuilder().build(project, data, graph, language="zh").get_page(
        "architecture"
    ).content
    assert "## 系统架构" in arch
    assert arch.index("```mermaid") < arch.index("请求从 main 进")
    assert "## 核心子系统" in arch
    assert "main — 启动进程 — `app/main.py main`" in arch
    assert "  - 文件:" not in arch
    assert "`main` — 启动进程 — `app/main.py`" not in arch


def test_overview_omits_unused_languages_and_marketing_when_structured():
    project = ProjectContext(
        name="grok-study",
        root=".",
        files=[
            FileInfo(
                path="bin/grok.rs",
                size=20,
                language="rust",
                content="fn main() {}\n",
                lines=2,
                is_entrypoint=True,
            ),
            FileInfo(
                path="crates/agent/src/lib.rs",
                size=24,
                language="rust",
                content="pub struct Session;\n",
                lines=2,
            ),
        ],
    )
    graph = DependencyGraph.build_from_project(project)
    data = WikiData(
        overview=ProjectOverview(
            name="grok-study",
            what_it_is=["进程从 `bin/grok.rs:1` 启动。"],
            mermaid_component="flowchart TD\n  A --> B",
            codebase_structure=[
                CodebasePart(name="agent", location="crates/agent", purpose="loop"),
            ],
            subsystems=[
                Subsystem(name="Agent Loop", role="跑一轮对话", files=["crates/agent/src/lib.rs"]),
            ],
            tech_stack=[
                TechItem(name="Python", category="language", version="未指定"),
                TechItem(name="JavaScript", category="language", version="未指定"),
                TechItem(name="Rust", category="language"),
            ],
            key_features=["营销口号"],
        ),
    )
    overview = WikiBuilder().build(project, data, graph, language="zh").get_page("index").content
    assert "## 代码如何拆分" in overview
    assert "## 核心子系统" in overview
    assert "## 主要能力" not in overview
    assert "营销口号" not in overview
    assert "Python" not in overview
    assert "JavaScript" not in overview
    assert "未指定" not in overview
    assert "## 技术栈" not in overview


def test_related_source_chips_are_single_pills_not_emdash_pairs():
    project = _project({"app/main.py": "def main():\n    return 1\n"})
    graph = DependencyGraph.build_from_project(project)
    data = WikiData(
        overview=ProjectOverview(
            name="fixture",
            description="boot",
            citations=[
                Citation(path="app/main.py", start_line=1, symbol="Agent"),
                Citation(path="app/main.py", start_line=1, symbol="AppServer"),
            ],
        )
    )
    overview = WikiBuilder().build(project, data, graph, language="zh").get_page("index").content
    chip_line = next(ln for ln in overview.splitlines() if ln.startswith("**相关源码:**"))
    assert " — `" not in chip_line
    assert " · " not in chip_line
    assert "`app/main.py:1 Agent`" in chip_line
    assert "`app/main.py:1 AppServer`" in chip_line


def test_upgrade_source_chip_markdown_rewrites_grok_emdash_line():
    old = (
        "**相关源码:** `bin/grok.rs:1` — `Agent` · "
        "`crates/agent/src/app.rs:40` — `AppServer` · `crates/acp/src/lib.rs:12`"
    )
    upgraded = upgrade_source_chip_markdown(f"# grok-study\n\n{old}\n\n## 它是什么\n")
    line = next(ln for ln in upgraded.splitlines() if ln.startswith("**相关源码:**"))
    assert line.startswith("**相关源码:**")
    assert " — `" not in line
    assert " · " not in line
    assert "`bin/grok.rs:1 Agent`" in line
    assert "`crates/agent/src/app.rs:40 AppServer`" in line
    assert "`crates/acp/src/lib.rs:12`" in line
    # Already-upgraded pills stay stable.
    assert upgrade_source_chip_markdown(upgraded) == upgraded
    evidence = (
        "## 源码证据\n\n"
        "- `crates/agent/src/loop.rs:12` — `Session` — holds the turn\n"
        "- `bin/grok.rs:1` — `Agent`\n"
    )
    fixed = upgrade_source_chip_markdown(evidence)
    assert "`crates/agent/src/loop.rs:12 Session`" in fixed
    assert "`bin/grok.rs:1 Agent`" in fixed
    assert " — `Session`" not in fixed
    assert " — holds the turn" in fixed


def test_upgrade_source_chip_three_part_spaced_symbol_keeps_next_list_line():
    evidence = (
        "## 源码证据\n\n"
        "- `crates/xai-chat/src/lib.rs:10` — `mod channel` — 通道\n"
        "- `crates/agent/src/loop.rs:40` — `Session` — 持有本轮\n"
    )
    fixed = upgrade_source_chip_markdown(evidence)
    assert "`crates/xai-chat/src/lib.rs:10 mod channel`" in fixed
    assert " — 通道" in fixed
    assert "`crates/agent/src/loop.rs:40 Session`" in fixed
    assert " — 持有本轮" in fixed
    assert " — `mod channel`" not in fixed
    items = [ln for ln in fixed.splitlines() if ln.startswith("- ")]
    assert len(items) == 2


def test_builder_strips_unknown_topic_links_and_pathless_key_types():
    project = _project(
        {
            "bin/grok.rs": "fn main() {}\n",
            "crates/agent/src/loop.rs": "pub struct Session;\n",
        }
    )
    graph = DependencyGraph.build_from_project(project)
    data = WikiData(
        overview=ProjectOverview(
            name="grok-study",
            document_scope="这篇文档讲 grok-study。读完您应能讲清边界。",
            what_it_is=[
                "细节见 [context-assembly](topics/context-assembly)。",
                "`Session` 在 `crates/agent/src/loop.rs:1`。",
            ],
            subsystems=[
                Subsystem(
                    name="Agent Loop",
                    role="跑一轮对话",
                    key_types=[
                        KeyType(name="Cli", role="parse", path=""),
                        KeyType(name="Terminal", role="draw"),
                        KeyType(
                            name="Session",
                            role="持有本轮上下文",
                            path="crates/agent/src/loop.rs",
                        ),
                    ],
                )
            ],
            see_also=[
                "architecture",
                "topics/agent-loop",
                "topics/context-assembly",
                "[code-graph](topics/code-graph)",
            ],
        ),
        architecture=ArchitectureDiagram(architecture_type="cli-tool"),
        topics=[
            TopicDoc(
                name="agent-loop",
                title="Agent Loop",
                section="deep-dive",
                files=[FileDoc(path="crates/agent/src/loop.rs")],
            )
        ],
    )
    wiki = WikiBuilder().build(project, data, graph, language="zh")
    overview = wiki.get_page("index").content
    assert "[Agent Loop](topics/agent-loop)" in overview
    assert "[架构概览](architecture)" in overview
    assert "topics/context-assembly" not in overview
    assert "topics/code-graph" not in overview
    assert "`Cli`" not in overview
    assert "`Terminal`" not in overview
    assert "`Session`" in overview
    assert "crates/agent/src/loop.rs" in overview
    assert "您" not in overview
    assert "读完你应能" not in overview
    assert "读完应能" not in overview


def test_filter_unknown_wiki_links_keeps_planned_ids():
    text = (
        "see [Agent Loop](topics/agent-loop) and "
        "[context-assembly](topics/context-assembly) plus [arch](architecture)"
    )
    out = filter_unknown_wiki_links(
        text, {"topics/agent-loop", "architecture", "index"}
    )
    assert "[Agent Loop](topics/agent-loop)" in out
    assert "[arch](architecture)" in out
    assert "[context-assembly](topics/agent-loop)" in out
    assert "topics/context-assembly" not in out
    dropped = filter_unknown_wiki_links(
        "- [code-graph](topics/code-graph)\n- [ok](architecture)\n",
        {"architecture", "index"},
    )
    assert "topics/code-graph" not in dropped
    assert "[ok](architecture)" in dropped


def test_overview_subsystem_rows_require_path_and_chip_form():
    project = _project(
        {
            "bin/grok.rs": "fn main() {}\n",
            "crates/agent/src/loop.rs": "pub struct Session;\n",
        }
    )
    graph = DependencyGraph.build_from_project(project)
    data = WikiData(
        overview=ProjectOverview(
            name="grok-study",
            subsystems=[
                Subsystem(
                    name="Agent Loop 与上下文装配",
                    role="把一轮对话跑完",
                    key_types=[
                        KeyType(
                            name="start_turn",
                            role="pager dispatch / start_turn",
                            path="crates/agent/src/loop.rs",
                            line=40,
                        ),
                        KeyType(name="Ghost", role="no path"),
                    ],
                ),
                Subsystem(name="Terminal UI", role="empty heading"),
            ],
        ),
        architecture=ArchitectureDiagram(architecture_type="monolith"),
    )
    overview = WikiBuilder().build(project, data, graph, language="zh").get_page(
        "index"
    ).content
    assert "### Agent Loop\n" in overview
    assert "与上下文装配" not in overview
    assert "start_turn — pager dispatch / start_turn — `crates/agent/src/loop.rs:40 start_turn`" in overview
    assert "`Ghost`" not in overview
    assert "### Terminal UI" not in overview


def test_architecture_sequence_is_model_then_tools():
    from repowiki.core.analyzer import Analyzer
    from repowiki.core.models import TopicOutline, WikiOutline
    from repowiki.core.topics import GROK_LOOP_SEQUENCE, sequence_tools_before_model

    tools_first = (
        "sequenceDiagram\n"
        "  participant Tools as ToolBridge\n"
        "  participant Model\n"
        "  Tools->>Model: tools first\n"
    )
    assert sequence_tools_before_model(tools_first)
    assert not sequence_tools_before_model(GROK_LOOP_SEQUENCE)
    assert GROK_LOOP_SEQUENCE.index("Turn->>Model") < GROK_LOOP_SEQUENCE.index(
        "Turn->>Bridge"
    )

    project = _project(
        {
            "bin/grok.rs": "fn main() {}\n",
            "crates/agent/src/loop.rs": "pub fn start_turn() {}\n",
        }
    )
    graph = DependencyGraph.build_from_project(project)
    outline = WikiOutline(
        topics=[
            TopicOutline(
                id="agent-loop",
                title="Agent Loop",
                section="deep-dive",
                key_files=["crates/agent/src/loop.rs"],
            )
        ]
    )
    analyzer = Analyzer.__new__(Analyzer)
    analyzer.language = "zh"
    arch = Analyzer._fill_architecture_gaps(
        analyzer,
        ArchitectureDiagram(
            architecture_type="cli-tool",
            mermaid_sequence=tools_first,
        ),
        project,
        outline,
        graph,
    )
    seq = arch.mermaid_sequence
    assert "Turn->>Model: complete" in seq
    assert seq.index("Turn->>Model") < seq.index("Turn->>Bridge")
    data = WikiData(architecture=arch)
    page = WikiBuilder().build(project, data, graph, language="zh").get_page(
        "architecture"
    ).content
    assert "cli-tool" not in page
    assert "AgentLoop" not in page


def test_upgrade_key_type_chip_and_agentloop_wording():
    md = (
        "## 关键类型\n\n"
        "- `Session` — 持有本轮 — `crates/agent/src/loop.rs:40`\n"
        "- `lib.rs` — crate root — `crates/agent/src/lib.rs:1`\n"
    )
    chips = upgrade_key_type_chip_markdown(md)
    assert "Session — 持有本轮 — `crates/agent/src/loop.rs:40 Session`" in chips
    assert "`lib.rs`" not in chips
    looped = upgrade_architecture_loop_wording(
        "# 架构\n\n> 这篇文档讲系统怎么串起来（cli-tool）。\n\n"
        "`AgentLoop` in `xai-grok-agent/src/lib.rs`\n"
        "### Agent Loop 与上下文装配\n"
    )
    assert "cli-tool" not in looped
    assert "AgentLoop" not in looped
    assert "start_turn" in looped
    assert "与上下文装配" not in looped
    combined = upgrade_wiki_page_content(
        md + "\n`AgentLoop`\n",
        {"index", "architecture"},
        language="zh",
    )
    assert "crates/agent/src/loop.rs:40 Session" in combined
    assert "AgentLoop" not in combined


def test_fill_key_type_chip_lines_from_evidence_does_not_invent_line_one():
    md = (
        "## 关键类型\n\n"
        "- StreamingMarkdownRenderer — 流式渲染 — "
        "`crates/markdown/src/lib.rs StreamingMarkdownRenderer`\n"
        "- GhostType — 无证据 — `crates/ghost/src/lib.rs GhostType`\n\n"
        "## 源码证据\n\n"
        "- `crates/markdown/src/lib.rs:40 StreamingMarkdownRenderer`\n"
        "- `crates/other/src/lib.rs:1 Other`\n"
    )
    filled = fill_key_type_chip_lines(md)
    assert (
        "`crates/markdown/src/lib.rs:40 StreamingMarkdownRenderer`" in filled
    )
    assert "`crates/ghost/src/lib.rs GhostType`" in filled
    assert "`crates/ghost/src/lib.rs:1 GhostType`" not in filled
    via_get = upgrade_wiki_page_content(md, {"index"}, language="zh")
    assert "`crates/markdown/src/lib.rs:40 StreamingMarkdownRenderer`" in via_get
    assert ":1 GhostType`" not in via_get


def test_strip_reading_guide_homework_and_practice_concepts():
    md = (
        "# 导读\n\n"
        "这是仓库的阅读剧本。每一步对应一个可练习概念：先读证据，再做回忆。\n\n"
        "## 可练习概念\n\n"
        "- Agent Loop\n\n"
        "## 步骤 1: Agent Loop (~10 min)\n\n"
        "跟一次调用。\n"
    )
    stripped = strip_reading_wiki_homework(md, page_id="reading-guide")
    assert "可练习概念" not in stripped
    assert "## 步骤 1: Agent Loop" in stripped
    assert "再跟一次调用" in stripped
    via_get = upgrade_wiki_page_content(
        md, {"reading-guide", "topics/agent-loop"}, language="zh", page_id="reading-guide"
    )
    assert "可练习概念" not in via_get
    assert "本步要你干什么" not in via_get


def test_normalize_mermaid_wraps_bare_arrows():
    out = normalize_mermaid_source("Pager --> Terminal")
    assert out.startswith("flowchart LR")
    assert "Pager --> Terminal" in out
    chained = normalize_mermaid_source("Agent --> AgentClient --> Model")
    assert chained.startswith("flowchart LR")
    assert "Agent --> AgentClient --> Model" in chained


def test_normalize_mermaid_unicode_arrows_to_ascii():
    out = normalize_mermaid_source("Pager → Terminal")
    assert "→" not in out
    assert "⟶" not in out
    assert "Pager --> Terminal" in out
    assert out.startswith("flowchart LR")
    long_arrow = normalize_mermaid_source("A ⟶ B")
    assert "A --> B" in long_arrow
    assert "⟶" not in long_arrow


def test_normalize_mermaid_does_not_wrap_typed_diagrams():
    flow = "flowchart TD\n  A --> B"
    assert normalize_mermaid_source(flow) == flow
    seq = "sequenceDiagram\n  A->>B: hi"
    assert normalize_mermaid_source(seq) == seq
    graph = "graph LR\n  X --> Y"
    assert normalize_mermaid_source(graph) == graph
    commented = "%% init\nflowchart LR\n  A --> B"
    assert normalize_mermaid_source(commented) == commented
    already = normalize_mermaid_source("Pager --> Terminal")
    assert normalize_mermaid_source(already) == already


def test_upgrade_wiki_rewrites_bare_mermaid_fences():
    md = (
        "## 核心子系统\n\n"
        "### Terminal UI\n\n"
        "```mermaid\n"
        "Pager → Terminal\n"
        "```\n\n"
        "### Agent Loop\n\n"
        "```mermaid\n"
        "Agent --> AgentClient --> Model\n"
        "```\n"
    )
    via_fences = upgrade_mermaid_fences(md)
    via_get = upgrade_wiki_page_content(md, {"index"}, language="zh", page_id="index")
    for fixed in (via_fences, via_get):
        assert "flowchart LR" in fixed
        assert "Pager --> Terminal" in fixed
        assert "Agent --> AgentClient --> Model" in fixed
        assert "→" not in fixed
        bodies = re.findall(r"```mermaid\n(.*?)```", fixed, flags=re.S)
        assert bodies
        for body in bodies:
            first = next(line.strip() for line in body.splitlines() if line.strip())
            assert first.startswith("flowchart LR")


def test_overview_subsystem_mermaid_wraps_bare_arrows_at_generate_time():
    project = _project({"src/pager.rs": "struct Pager {}\n" + _FILLER})
    graph = DependencyGraph.build_from_project(project)
    data = WikiData(
        overview=ProjectOverview(
            name="fixture",
            document_scope="这篇文档讲子系统图。",
            what_it_is=["Pager 在 `src/pager.rs:1` 画终端。"],
            subsystems=[
                Subsystem(
                    name="Terminal UI",
                    role="把输出画到终端",
                    key_types=[
                        KeyType(name="Pager", role="画屏", path="src/pager.rs:1"),
                    ],
                    mermaid="Pager → Terminal",
                )
            ],
        )
    )
    wiki = WikiBuilder().build(project, data, graph, language="zh")
    content = wiki.get_page("index").content
    assert "```mermaid" in content
    assert "flowchart LR" in content
    assert "Pager --> Terminal" in content
    assert "Pager → Terminal" not in content


def test_coerce_mermaid_wraps_bare_arrows_at_generate_time():
    from repowiki.core.analyzer import _coerce_mermaid

    out = _coerce_mermaid("Pager → Terminal")
    assert out.startswith("flowchart LR")
    assert "Pager --> Terminal" in out
    assert "→" not in out
    typed = _coerce_mermaid("sequenceDiagram\n  A->>B: hi")
    assert typed.startswith("sequenceDiagram")


def test_shorten_mermaid_node_labels_clips_incomplete_cjk_verbs():
    md = (
        "## 一次调用怎么走\n\n"
        "```mermaid\n"
        "flowchart TD\n"
        '  A["合并为"]\n'
        '  B["调用"]\n'
        '  C["把用户输入交给模型再合并为下一轮调用"]\n'
        "  A --> B --> C\n"
        "```\n"
    )
    fixed = shorten_mermaid_node_labels(md)
    assert 'A["合并"]' in fixed
    assert "合并为" not in re.search(r'A\["([^"]+)"\]', fixed).group(1)
    assert 'B["调用"]' in fixed
    label_c = re.search(r'C\["([^"]+)"\]', fixed).group(1)
    assert len(label_c) <= 12
    assert not label_c.endswith(("为", "把", "从"))



def test_directory_sidebar_is_capped():
    children = [
        {"title": f"crate-{i}", "page_id": f"modules/crates/c{i}", "children": []}
        for i in range(20)
    ]
    sidebar = [
        {"title": "入门指南", "page_id": "", "children": []},
        {"title": "按目录", "page_id": "", "children": children},
    ]
    capped = cap_directory_sidebar(sidebar)
    directory = next(item for item in capped if item["title"] == "按目录")
    assert len(directory["children"]) <= 8


def test_directory_sidebar_excludes_cargo_and_ranks_product_crates():
    from repowiki.core.wiki_builder import rank_and_cap_directory_sidebar

    crate_children = [
        {"title": f"aa-{i}", "page_id": f"modules/crates/aa-{i}", "children": []}
        for i in range(10)
    ] + [
        {
            "title": "xai-grok-pager",
            "page_id": "modules/crates/xai-grok-pager",
            "children": [],
        },
        {
            "title": "xai-grok-agent",
            "page_id": "modules/crates/xai-grok-agent",
            "children": [],
        },
    ]
    pages = [
        {
            "id": "index",
            "title": "概述",
            "content": "`crates/xai-grok-pager` runs the TUI.\n",
        },
        {"id": "modules/.cargo", "title": ".cargo", "content": ""},
        {"id": "modules/bin", "title": "bin", "content": ""},
        {
            "id": "modules/crates/xai-grok-pager",
            "title": "xai-grok-pager",
            "content": "",
        },
        {
            "id": "modules/crates/xai-grok-agent",
            "title": "xai-grok-agent",
            "content": "",
        },
    ]
    sidebar = [
        {
            "title": "按目录",
            "page_id": "",
            "children": [
                {"title": ".cargo", "page_id": "modules/.cargo", "children": []},
                {"title": "bin", "page_id": "modules/bin", "children": []},
                {"title": "crates", "page_id": "", "children": crate_children},
            ],
        }
    ]
    ranked = rank_and_cap_directory_sidebar(sidebar, pages=pages)
    directory = next(item for item in ranked if item["title"] == "按目录")

    def leaves(item) -> list[str]:
        kids = item.get("children") or []
        if not kids:
            return [item.get("title") or ""]
        out: list[str] = []
        for child in kids:
            out.extend(leaves(child))
        return out

    titles = []
    for child in directory["children"]:
        titles.extend(leaves(child))
    assert ".cargo" not in titles
    assert "bin" not in titles
    assert "xai-grok-pager" in titles
    assert "xai-grok-agent" in titles
    assert len(titles) <= 8


def test_clip_mermaid_label_does_not_cut_mid_flag_or_path():
    assert clip_mermaid_label("launcher 解析 --profile、--config 并启动") != (
        "launcher 解析 --profile、-"
    )
    clipped = clip_mermaid_label("launcher 解析 --profile、--config 并启动")
    assert "、-" not in clipped
    assert "--profile、-" not in clipped
    mid_path = clip_mermaid_label("创建 AppWebEntry 并运行（apps/cli/src/index.ts）")
    assert not mid_path.endswith("（apps")
    assert "（apps" not in mid_path
    preset = clip_mermaid_label("`writeDefaultPreset` 构造 `")
    assert "构造 `" not in preset
    assert clip_mermaid_label("返回 undefined") == "返回 undefined"
    rendered = shorten_mermaid_node_labels(
        "```mermaid\n"
        "flowchart TD\n"
        '  s1["launcher 解析 --profile、--config 并启动"]\n'
        '  s2["创建 AppWebEntry 并运行（apps/cli/src/index.ts）"]\n'
        "```\n"
    )
    assert 's1["launcher 解析 --profile、-"]' not in rendered
    assert 's2["创建 AppWebEntry 并运行（apps"]' not in rendered


