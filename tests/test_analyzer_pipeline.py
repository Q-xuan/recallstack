"""Multi-pass analyzer: outline → write → cite-check, including the no-LLM path."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from repowiki.core.analyzer import Analyzer
from repowiki.core.cache import Cache
from repowiki.core.graph import DependencyGraph
from repowiki.core.models import FileInfo, ProjectContext
from repowiki.core.wiki_builder import WikiBuilder


def _run(coro):
    return asyncio.run(coro)


class NullLLM:
    """No key — Analyzer must not call complete()."""

    api_key = ""

    async def complete(self, messages, max_tokens=4096, **kwargs):
        raise AssertionError("LLM should not be called without an API key")


class ScriptedLLM:
    """Returns canned JSON keyed off the prompt, and records calls."""

    api_key = "test"

    def __init__(self):
        self.calls: list[str] = []
        self.kwargs: list[dict] = []

    async def complete(self, messages, max_tokens=4096, **kwargs):
        text = messages[-1]["content"]
        self.calls.append(text)
        self.kwargs.append(kwargs)
        if "Output a wiki outline as JSON" in text:
            return json.dumps(
                {
                    "overview_focus": "tiny boot service",
                    "architecture_focus": "entrypoint to persistence",
                    "emphasized_pages": ["overview", "architecture", "app"],
                    "reading_order": ["app"],
                    "modules": [
                        {
                            "name": "app",
                            "priority": 3,
                            "depth": "deep",
                            "sections": ["implementation", "call_chains", "edge_cases"],
                            "key_files": ["app/main.py", "app/core.py"],
                            "key_symbols": ["main", "boot"],
                            "notes": "start at main()",
                        }
                    ],
                }
            )
        if "Document the '" in text:
            start = text.find("Document the '") + len("Document the '")
            end = text.find("' module", start)
            name = text[start:end] if end != -1 else "app"
            if name != "app":
                return json.dumps({"name": name, "purpose": f"{name} files", "files": []})
            return json.dumps(
                {
                    "name": "app",
                    "purpose": "boot the service",
                    "description": "The entrypoint in `app/main.py:7` calls boot.",
                    "implementation_details": (
                        "`app/main.py:7` calls `boot` in `app/core.py:5`, then "
                        "`save` in `app/db.py:7`. Ignore `ghost/nope.py:1`."
                    ),
                    "call_chains": [
                        {
                            "name": "boot",
                            "description": "process start",
                            "steps": ["main() -> boot() -> save()"],
                            "files": ["app/main.py", "app/core.py", "app/db.py", "missing.py"],
                        }
                    ],
                    "edge_cases": ["save appends even if status is unexpected"],
                    "files": [
                        {"path": "app/main.py", "purpose": "entry", "key_symbols": []},
                        {"path": "does/not/exist.py", "purpose": "hallucination", "key_symbols": []},
                    ],
                    "relationships": [
                        {
                            "source": "app/main.py",
                            "target": "app/core.py",
                            "description": "imports boot",
                        }
                    ],
                    "key_concepts": [],
                    "citations": [
                        {"path": "app/main.py", "start_line": 7, "symbol": "main", "note": "entry"},
                        {"path": "totally/fake.py", "start_line": 1, "note": "nope"},
                    ],
                }
            )
        if "Invalid paths" in text and "Current JSON" in text:
            return json.dumps(
                {
                    "name": "app",
                    "purpose": "boot the service",
                    "description": "The entrypoint in `app/main.py:7` calls boot.",
                    "implementation_details": (
                        "`app/main.py:7` calls `boot` in `app/core.py:5`, then "
                        "`save` in `app/db.py:7`."
                    ),
                    "call_chains": [
                        {
                            "name": "boot",
                            "files": ["app/main.py", "app/core.py", "app/db.py"],
                            "steps": ["main() -> boot() -> save()"],
                        }
                    ],
                    "edge_cases": ["save appends even if status is unexpected"],
                    "files": [{"path": "app/main.py", "purpose": "entry"}],
                    "citations": [
                        {"path": "app/main.py", "start_line": 7, "symbol": "main", "note": "entry"}
                    ],
                }
            )
        if "Generate a project overview" in text:
            return json.dumps(
                {
                    "name": "mini_repo",
                    "one_liner": "tiny boot service",
                    "description": "Starts at `app/main.py`.",
                    "tech_stack": [{"name": "Python", "category": "language"}],
                    "setup_instructions": ["read app/main.py"],
                    "key_features": ["boot"],
                    "citations": [{"path": "app/main.py", "start_line": 1}],
                }
            )
        if "Analyze the architecture" in text:
            return json.dumps(
                {
                    "architecture_type": "monolith",
                    "description": "entrypoint to db",
                    "components": [
                        {
                            "name": "app",
                            "purpose": "core",
                            "files": ["app/main.py", "nope.py"],
                        }
                    ],
                    "mermaid_component": "graph TD\n  A-->B",
                    "data_flow": "main to db",
                    "citations": [{"path": "app/core.py", "start_line": 5}],
                }
            )
        if "Create a reading guide" in text:
            return json.dumps(
                {
                    "introduction": "start at main",
                    "steps": [
                        {
                            "order": 1,
                            "title": "entry",
                            "files": ["app/main.py", "ghost.py"],
                            "explanation": "look at main()",
                            "time_estimate": "5 min",
                        }
                    ],
                    "tips": ["follow boot"],
                }
            )
        return "{}"


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


def _padded(content: str, lines: int = 80) -> str:
    """Keep the real code, then pad so grouping does not fold the module away."""
    extra = "\n".join(f"# pad {i}" for i in range(lines))
    return content.rstrip() + "\n" + extra + "\n"


def _project() -> ProjectContext:
    """Mini-repo shape with enough lines that `app` stays its own module."""
    files = [
        _file("README.md", "# Mini\nA tiny service.\n" + "#\n" * 70, config=True),
        _file(
            "app/main.py",
            _padded("from app.core import boot\nfrom app.db import save\n\ndef main() -> str:\n    result = boot()\n    save({'status': result})\n    return result\n"),
            entry=True,
        ),
        _file("app/core.py", _padded("def boot() -> str:\n    return 'ok'\n")),
        _file("app/db.py", _padded("def save(data):\n    return data\n")),
        _file("app/__init__.py", _padded("")),
        _file("tests/test_core.py", _padded("from app.core import boot\n\ndef test_boot():\n    assert boot() == 'ok'\n")),
    ]
    return ProjectContext(
        name="mini_repo",
        root=".",
        files=files,
        file_tree="\n".join(f.path for f in files),
    )


async def _analyze(tmp_path: Path, llm, language: str = "en") -> tuple:
    cache = Cache(db_path=tmp_path / "c.db")
    await cache.init()
    try:
        analyzer = Analyzer(llm=llm, cache=cache, language=language)
        progress: list[str] = []
        project = _project()
        wiki = await analyzer.analyze(project, on_progress=progress.append)
        return wiki, progress, project
    finally:
        await cache.close()


def test_analyze_without_llm_produces_usable_wiki(tmp_path):
    wiki, progress, project = _run(_analyze(tmp_path, NullLLM()))

    assert "Outlining wiki..." in progress
    assert any(p.startswith("Writing ") and "modules" in p for p in progress)
    assert "Verifying citations..." in progress
    assert wiki.outline is not None
    assert wiki.outline.modules
    assert wiki.modules
    assert wiki.overview.name == project.name
    assert {m.name for m in wiki.modules}

    graph = DependencyGraph.build_from_project(project)
    pages = WikiBuilder().build(project, wiki, graph)
    assert pages.get_page("index") is not None
    assert any(p.id.startswith("modules/") for p in pages.pages)


def test_write_path_with_scripted_llm_and_cite_check(tmp_path):
    llm = ScriptedLLM()
    wiki, progress, project = _run(_analyze(tmp_path, llm))

    assert any("Output a wiki outline as JSON" in c for c in llm.calls)
    assert any("Document the '" in c for c in llm.calls)
    assert all(k.get("response_format") == {"type": "json_object"} for k in llm.kwargs)
    assert "Wiki outline focus" in next(c for c in llm.calls if "Generate a project overview" in c)
    assert "Outlining wiki..." in progress
    assert "Verifying citations..." in progress

    app = next(m for m in wiki.modules if m.name == "app")
    assert app.purpose == "boot the service"
    assert app.implementation_details
    assert app.call_chains
    assert app.edge_cases
    paths = {f.path for f in app.files}
    assert "app/main.py" in paths
    assert "does/not/exist.py" not in paths
    assert "ghost/nope.py" not in app.implementation_details
    assert "missing.py" not in app.call_chains[0].files
    assert {c.path for c in app.citations} == {"app/main.py"}

    assert wiki.architecture.components[0].files == ["app/main.py"]
    assert wiki.reading_guide.steps[0].files == ["app/main.py"]

    graph = DependencyGraph.build_from_project(project)
    page = WikiBuilder().build(project, wiki, graph).get_page("modules/app")
    assert "## Implementation" in page.content
    assert "## Key Call Chains" in page.content
    assert "## Edge Cases" in page.content
    assert "## Source Evidence" in page.content
    assert "does/not/exist.py" not in page.content
    assert "totally/fake.py" not in page.content


def test_zh_no_llm_fallback_is_handbook_not_inventory(tmp_path):
    wiki, _, project = _run(_analyze(tmp_path, NullLLM(), language="zh"))

    assert "Module containing" not in wiki.modules[0].purpose
    assert "Heaviest modules by PageRank" not in wiki.architecture.description
    assert "目录" in wiki.architecture.description
    assert wiki.architecture.architecture_type == "codebase-modules"
    assert any(tip.term == "PageRank" for tip in wiki.architecture.term_tips)
    graph = DependencyGraph.build_from_project(project)
    pages = WikiBuilder().build(project, wiki, graph, language="zh")
    arch = pages.get_page("architecture").content
    assert "**类型:**" in arch
    assert "**Type:**" not in arch
    assert "codebase-modules" in arch
    assert "## 术语小贴士" in arch
    assert "Heaviest modules by PageRank" not in arch
    for page in pages.pages:
        if page.id.startswith("modules/"):
            assert "Module containing" not in page.content
            assert "## 术语小贴士" in page.content
