from repowiki.core.graph import DependencyGraph
from repowiki.core.models import (
    ArchitectureDiagram,
    CallChain,
    Citation,
    FileInfo,
    ModuleDoc,
    ProjectContext,
    ReadingGuide,
    ReadingStep,
    WikiData,
)
from repowiki.core.modules import ROOT_NAME, group_into_modules
from repowiki.core.wiki_builder import WikiBuilder

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
    modules = next(item for item in wiki.sidebar if item.title == "Modules")

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
                citations=[Citation(path="app/main.py", start_line=1, symbol="main")],
            )
        ]
    )
    wiki = WikiBuilder().build(project, data, graph)
    content = wiki.get_page("modules/app").content
    assert "## Implementation" in content
    assert "main() returns 1." in content
    assert "## Key Call Chains" in content
    assert "### boot" in content
    assert "## Edge Cases" in content
    assert "## Source Evidence" in content
    assert "`app/main.py:1`" in content


def test_module_page_omits_empty_deep_sections():
    wiki, names = _build(_project({"solo/thing.py": "x = 1\n"}))
    assert names == ["solo"]
    content = wiki.get_page("modules/solo").content
    assert "## Implementation" not in content
    assert "## Key Call Chains" not in content
    assert "## Edge Cases" not in content
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
    assert titles[0] == "Overview"
    assert "Architecture" in titles
    assert "Reading Guide" in titles
    assert "Dependencies" in titles
    modules = next(item for item in wiki.sidebar if item.title == "Modules")
    assert ROOT_NAME in names
    root = next(c for c in modules.children if c.page_id == "modules/root")
    assert root.title == "Root"
    crates = next(c for c in modules.children if c.title == "crates")
    assert crates.page_id == "modules/crates"
    assert wiki.get_page("index").id == "index"
    assert wiki.get_page("modules/root").id == "modules/root"
    assert wiki.get_page("architecture").content.startswith("# Architecture")
    assert wiki.get_page("reading-guide").content.startswith("# Reading Guide")
    assert wiki.get_page("dependencies").content.startswith("# Dependencies")
    assert wiki.get_page("modules/root").content.startswith("# Root")


def test_zh_structural_sidebar_titles_and_headings():
    wiki, names = _structural_wiki("zh")
    titles = [item.title for item in wiki.sidebar]
    assert titles[0] == "总览"
    assert "架构" in titles
    assert "导读" in titles
    assert "依赖" in titles
    assert "Overview" not in titles
    assert "Modules" not in titles
    modules = next(item for item in wiki.sidebar if item.title == "模块")
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
    assert wiki.get_page("index").title == "总览"
    assert wiki.get_page("architecture").title == "架构"
    assert wiki.get_page("reading-guide").title == "导读"
    assert wiki.get_page("dependencies").title == "依赖"
    assert wiki.get_page("modules/root").id == "modules/root"
    assert wiki.get_page("modules/root").title == "根目录"
    assert wiki.get_page("architecture").content.startswith("# 架构")
    assert wiki.get_page("reading-guide").content.startswith("# 导读")
    assert wiki.get_page("dependencies").content.startswith("# 依赖")
    assert wiki.get_page("modules/root").content.startswith("# 根目录")
    assert "# Architecture" not in wiki.get_page("architecture").content


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
