"""Citation verification drops hallucinated paths and keeps real ones."""

from __future__ import annotations

from repowiki.core.cite_check import (
    CiteIndex,
    collect_invalid_paths,
    sanitize_text,
    verify_wiki_data,
)
from repowiki.core.models import (
    ArchitectureDiagram,
    CallChain,
    Citation,
    Component,
    FileDoc,
    FileInfo,
    ModuleDoc,
    ProjectContext,
    ProjectOverview,
    ReadingGuide,
    ReadingStep,
    Relationship,
    WikiData,
)


def _project() -> ProjectContext:
    main = "from app.core import boot\n\ndef main():\n    return boot()\n"
    core = "def boot():\n    return 'ok'\n"
    return ProjectContext(
        name="demo",
        root=".",
        files=[
            FileInfo(path="app/main.py", size=len(main), language="python", lines=4, content=main),
            FileInfo(path="app/core.py", size=len(core), language="python", lines=2, content=core),
        ],
    )


def test_cite_check_drops_bad_paths_and_keeps_good_ones():
    project = _project()
    data = WikiData(
        overview=ProjectOverview(
            name="demo",
            description="Starts in `app/main.py:3` and never in `ghost/x.py:1`.",
            citations=[
                Citation(path="app/main.py", start_line=3, note="entry"),
                Citation(path="totally/fake.py", start_line=1, note="nope"),
            ],
        ),
        architecture=ArchitectureDiagram(
            architecture_type="monolith",
            components=[
                Component(name="app", files=["app/main.py", "missing.py"]),
            ],
        ),
        modules=[
            ModuleDoc(
                name="app",
                purpose="core",
                description="See `app/core.py:1` and `no/such.py`.",
                implementation_details="boot lives in `app/core.py:99`.",
                files=[
                    FileDoc(path="app/main.py", purpose="entry"),
                    FileDoc(path="does/not/exist.py", purpose="hallucination"),
                ],
                relationships=[
                    Relationship(source="app/main.py", target="app/core.py", description="imports"),
                    Relationship(source="app/main.py", target="ghost.py", description="bad"),
                ],
                call_chains=[
                    CallChain(
                        name="boot",
                        files=["app/main.py", "app/core.py", "missing.py"],
                        steps=["`app/main.py:3` calls boot"],
                    )
                ],
                citations=[
                    Citation(path="app/core.py", start_line=1),
                    Citation(path="invented.py", start_line=4),
                ],
            )
        ],
        reading_guide=ReadingGuide(
            steps=[
                ReadingStep(order=1, title="start", files=["app/main.py", "ghost.py"]),
            ]
        ),
    )

    index = CiteIndex.from_project(project)
    assert collect_invalid_paths(data.modules[0], index) == [
        "does/not/exist.py",
        "ghost.py",
        "invented.py",
        "missing.py",
    ]

    cleaned = verify_wiki_data(data, project)
    mod = cleaned.modules[0]
    assert [f.path for f in mod.files] == ["app/main.py"]
    assert [(r.source, r.target) for r in mod.relationships] == [("app/main.py", "app/core.py")]
    assert mod.call_chains[0].files == ["app/main.py", "app/core.py"]
    assert [c.path for c in mod.citations] == ["app/core.py"]
    assert "does/not/exist.py" not in mod.description
    assert "`app/core.py:1`" in mod.description
    # out-of-range line dropped, path kept
    assert "`app/core.py`" in mod.implementation_details
    assert ":99" not in mod.implementation_details
    assert [c.path for c in cleaned.overview.citations] == ["app/main.py"]
    assert cleaned.architecture.components[0].files == ["app/main.py"]
    assert cleaned.reading_guide.steps[0].files == ["app/main.py"]
    assert "`app/main.py:3`" in cleaned.overview.description
    assert "ghost/x.py" not in cleaned.overview.description


def test_sanitize_text_resolves_unique_basename():
    index = CiteIndex.from_project(_project())
    out = sanitize_text("look at `main.py:3`", index)
    assert out == "look at `app/main.py:3`"


def test_cite_check_works_without_llm_on_deterministic_content():
    """Offline path: still strip impossible paths if any slipped in."""
    project = _project()
    data = WikiData(
        modules=[
            ModuleDoc(
                name="app",
                files=[FileDoc(path="app/main.py"), FileDoc(path="not/here.py")],
            )
        ]
    )
    cleaned = verify_wiki_data(data, project)
    assert [f.path for f in cleaned.modules[0].files] == ["app/main.py"]
