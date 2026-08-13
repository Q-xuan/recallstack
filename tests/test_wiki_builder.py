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
    upgrade_legacy_module_markdown,
    upgrade_source_chip_markdown,
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
    assert [c.title for c in app.children] == ["api", "services"]
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
    assert "## How it actually runs" in content
    assert "main() returns 1." in content
    assert "## How a call runs" in content
    assert "### boot" in content
    assert "## Failures and edges" in content
    assert "## Source Evidence" in content
    assert "`app/main.py:1`" in content
    assert content.index("## How a call runs") < content.index("## Related source")
    assert content.index("## How a call runs") < content.index("## How it actually runs")
    assert "## Implementation" not in content
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
    assert "## 术语小贴士" in overview
    assert "**PageRank**" in overview
    assert "## Tech Stack" not in overview

    arch = wiki.get_page("architecture").content
    assert arch.startswith("# 架构概览")
    assert "codebase-modules" in arch
    assert "## 链路里的角色" in arch
    assert "crates/lib.py" in arch
    assert "## 术语小贴士" in arch
    assert "**Type:**" not in arch
    assert "## Components" not in arch
    assert "## 组成" not in arch
    assert "**类型:**" not in arch

    page = wiki.get_page("modules/crates")
    assert page.title == "crates"
    content = page.content
    assert content.startswith("# crates")
    assert "## 一次调用怎么走" in content
    assert "## 这条链路怎么转" in content
    assert "## 失败与边界" in content
    assert "## 相关源码" in content
    assert "## 源码证据" in content
    assert "## 术语小贴士" in content
    assert "**ACP**" in content
    assert "## 实现细节" not in content
    assert "## 关键调用链" not in content
    assert "## Implementation" not in content
    assert "## Key Call Chains" not in content
    assert content.index("## 一次调用怎么走") < content.index("## 相关源码")
    assert content.index("## 一次调用怎么走") < content.index("## 这条链路怎么转")

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
    assert "## How a call runs" in content
    assert "## Related source" in content
    assert content.index("## How a call runs") < content.index("## Related source")
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
    assert "## 一次调用怎么走" in upgraded
    assert "## 相关源码" in upgraded
    assert "## 关键调用链" not in upgraded
    assert upgraded.index("## 一次调用怎么走") < upgraded.index("## 相关源码")
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
    assert "## 一次调用怎么走" in content
    assert "## 相关源码" in content
    assert content.index("## 一次调用怎么走") < content.index("## 相关源码")
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
    assert "这篇文档讲" in overview
    assert "## 它是什么" in overview
    assert "## 系统架构" in overview
    assert "架构见图" in overview
    assert "[架构概览](architecture)" in overview
    assert "| 技术 |" in overview
    assert "Python" in overview
    assert "- **Python**" not in overview
    assert "`app/main.py:1`" in overview
    assert overview.index("相关源码") < overview.index("## 它是什么")
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
    assert "## 它是什么" in overview
    assert "## 系统架构" in overview
    assert "## 代码如何拆分" in overview
    assert "## 核心子系统" in overview
    assert "```mermaid" in overview
    assert "| 名称 |" in overview
    assert "crates/agent" in overview
    assert "`Session`" in overview
    assert "[架构概览](architecture)" in overview
    assert "[Agent Loop](topics/agent-loop)" in overview
    assert "## 主要能力" not in overview
    assert "key_features" not in overview
    assert "本步要你干什么" not in overview
    assert overview.index("相关源码") < overview.index("## 它是什么")
    assert overview.index("## 它是什么") < overview.index("## 系统架构")
    assert overview.index("```mermaid") < overview.index("用户输入进")
    assert overview.index("## 系统架构") < overview.index("## 代码如何拆分")
    assert overview.index("## 代码如何拆分") < overview.index("## 核心子系统")

    topic = wiki.get_page("topics/agent-loop").content
    assert "## 它是什么" in topic
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
    assert "`main` — 启动进程 — `app/main.py`" in arch
    assert "  - 文件:" not in arch


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

