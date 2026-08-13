"""Deterministic wiki outline (Pass 1) from modules + PageRank + entrypoints."""

from __future__ import annotations

from pathlib import Path

from repowiki.core.graph import DependencyGraph
from repowiki.core.models import FileInfo, ModuleOutline, ProjectContext, WikiOutline
from repowiki.core.outline import build_deterministic_outline, merge_outline
from repowiki.ingest.local import ingest_local


def _file(path: str, content: str, *, entry: bool = False, config: bool = False) -> FileInfo:
    return FileInfo(
        path=path,
        size=len(content),
        language="python" if path.endswith(".py") else "markdown",
        lines=content.count("\n") + 1,
        preview=content,
        content=content,
        is_entrypoint=entry,
        is_config=config,
    )


def _hub_project() -> tuple[ProjectContext, dict[str, list[FileInfo]]]:
    """Every satellite imports hub.py, so PageRank puts hub first.

    Modules are grouped by hand so the outline test is not coupled to the
    tiny-module folder that would otherwise collapse this fixture into ``misc``.
    """
    files = [
        _file("README.md", "# demo\n", config=True),
        _file("app/main.py", "from app.hub import run\n\ndef main():\n    run()\n", entry=True),
        _file("app/hub.py", "def run():\n    return 1\n"),
        _file("app/a.py", "from app.hub import run\n"),
        _file("app/b.py", "from app.hub import run\n"),
        _file("app/c.py", "from app.hub import run\n"),
        _file("util/helpers.py", "X = 1\n"),
    ]
    project = ProjectContext(name="demo", root=".", files=files, file_tree="app/\nutil/")
    modules = {
        "app": [f for f in files if f.path.startswith("app/")],
        "util": [f for f in files if f.path.startswith("util/")],
        "root": [f for f in files if "/" not in f.path],
    }
    return project, modules


def test_deterministic_outline_without_llm():
    project, modules = _hub_project()
    graph = DependencyGraph.build_from_project(project)
    outline = build_deterministic_outline(project, modules, graph)

    assert outline.modules
    assert outline.reading_order
    assert "overview" in outline.emphasized_pages
    assert any(item.depth == "deep" for item in outline.modules)
    app = outline.module_for("app")
    assert app is not None
    assert "app/main.py" in app.key_files
    assert "app/hub.py" in app.key_files
    # entrypoint module leads the reading order
    assert outline.reading_order[0] == "app"
    assert "app/main.py" in outline.overview_focus
    assert "Heaviest modules by PageRank" not in outline.architecture_focus
    assert "file inventory" in outline.architecture_focus.lower() or "not a file" in outline.architecture_focus.lower()


def test_deterministic_outline_on_mini_repo():
    project = ingest_local(Path("fixtures/mini_repo"))
    graph = DependencyGraph.build_from_project(project)
    modules = {
        "app": [f for f in project.files if f.path.startswith("app/")],
        "tests": [f for f in project.files if f.path.startswith("tests/")],
    }
    modules = {k: v for k, v in modules.items() if v}
    outline = build_deterministic_outline(project, modules, graph)

    names = {m.name for m in outline.modules}
    assert "app" in names
    app = outline.module_for("app")
    assert app is not None
    assert "app/main.py" in app.key_files


def test_merge_outline_drops_unknown_modules_and_paths():
    base = WikiOutline(
        overview_focus="base",
        architecture_focus="arch",
        emphasized_pages=["overview", "app"],
        reading_order=["app"],
        modules=[
            ModuleOutline(
                name="app",
                priority=3,
                depth="deep",
                key_files=["app/main.py"],
                notes="keep",
            )
        ],
    )
    llm = WikiOutline(
        overview_focus="llm focus",
        reading_order=["ghost", "app"],
        modules=[
            ModuleOutline(
                name="ghost",
                depth="deep",
                key_files=["nope.py"],
            ),
            ModuleOutline(
                name="app",
                depth="standard",
                priority=2,
                key_files=["app/main.py", "invented.py"],
                notes="from llm",
            ),
        ],
    )
    merged = merge_outline(base, llm, known_modules={"app"}, known_paths={"app/main.py"})
    assert merged.overview_focus == "llm focus"
    assert [m.name for m in merged.modules] == ["app"]
    assert merged.module_for("app").depth == "standard"
    assert merged.module_for("app").key_files == ["app/main.py"]
    assert "ghost" not in merged.reading_order
    assert merged.reading_order[0] == "app"
