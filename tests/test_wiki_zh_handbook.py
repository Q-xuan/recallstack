"""Generated zh wiki / concept pages must be handbook voice, not lecture notes."""

from __future__ import annotations

from recallstack.domain.schemas import ConceptDraft, SourceReference
from recallstack.learning.wiki_generator import append_concept_pages, build_deterministic_wiki_data
from recallstack.learning.wiki_judge import LECTURE_HEADINGS, LECTURE_MARKERS
from repowiki.core.graph import DependencyGraph
from repowiki.core.models import FileInfo, ProjectContext
from repowiki.core.wiki_builder import Wiki, WikiBuilder

_BAD_TERMS = ("代理人", "插件系统")


def _project() -> ProjectContext:
    readme = (
        "# demo\n\n"
        "demo 是一个开源 agent harness（智能体框架）。它采用 plugin 架构。\n"
    )
    main = "def main():\n    return 1\n"
    return ProjectContext(
        name="demo",
        root=".",
        files=[
            FileInfo(
                path="README.md",
                size=len(readme),
                language="markdown",
                content=readme,
                preview=readme,
                is_config=True,
            ),
            FileInfo(
                path="app/main.py",
                size=len(main),
                language="python",
                content=main,
                is_entrypoint=True,
            ),
        ],
    )


def _assert_handbook(text: str) -> None:
    for marker in LECTURE_MARKERS:
        assert marker not in text, marker
    for heading in LECTURE_HEADINGS:
        assert heading not in text, heading
    for term in _BAD_TERMS:
        assert term not in text, term


def test_deterministic_overview_and_architecture_are_handbook_zh(monkeypatch):
    monkeypatch.setenv("RECALLSTACK_CONTENT_LANG", "zh")
    project = _project()
    graph = DependencyGraph.build_from_project(project)
    data = build_deterministic_wiki_data(project, graph, [])
    wiki = WikiBuilder().build(project, data, graph, language="zh")
    overview = wiki.get_page("index").content
    arch = wiki.get_page("architecture").content
    _assert_handbook(overview)
    _assert_handbook(arch)
    assert "## 概述" in overview
    assert "## 系统架构" in overview
    assert "这篇文档讲" not in overview
    assert "这篇文档讲" not in arch
    assert "系统按一次真实调用串起来" in arch


def test_high_importance_concept_is_handbook_zh(monkeypatch):
    monkeypatch.setenv("RECALLSTACK_CONTENT_LANG", "zh")
    store = {
        "app/agent.py": "class Agent:\n    def start_turn(self):\n        pass\n",
    }
    wiki = Wiki(project_name="demo", pages=[], sidebar=[])
    draft = ConceptDraft(
        slug="agent-loop",
        title="Agent Loop",
        description="Agent Loop 接住一轮对话，按名执行 tool call。",
        importance=0.9,
        source_references=[
            SourceReference(path="app/agent.py", start_line=1, symbol="Agent"),
        ],
    )
    page = append_concept_pages(wiki, [draft], file_texts=store).get_page("concepts/agent-loop")
    assert page is not None
    _assert_handbook(page.content)
    assert "## 概述" in page.content
    assert "## 架构" in page.content
    assert "## 关键类型" in page.content
    assert "## 边界" in page.content
    assert "Agent" in page.content
    assert "代理人" not in page.content
