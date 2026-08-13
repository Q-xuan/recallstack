from repowiki.core.graph import DependencyGraph
from repowiki.core.models import (
    CallChain,
    Citation,
    FileInfo,
    ModuleDoc,
    ProjectContext,
    WikiData,
)
from repowiki.core.modules import group_into_modules
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
