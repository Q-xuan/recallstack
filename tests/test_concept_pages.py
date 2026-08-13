"""README excerpt + handbook-style concept pages."""

from __future__ import annotations

import re

from recallstack.domain.schemas import ConceptDraft, SourceReference
from recallstack.learning.concept_extractor import ConceptExtractor, readme_prose_excerpt
from recallstack.learning.wiki_generator import append_concept_pages, build_deterministic_wiki_data
from repowiki.core.graph import DependencyGraph
from repowiki.core.models import FileInfo, ProjectContext
from repowiki.core.wiki_builder import Wiki

HTML_README = """\
<div align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/logo-dark.svg">
    <img alt="xAI logo" src="docs/logo.svg">
  </picture>
</div>

# grok-study

Grok-study is a local research workbench for Grok.

[![CI](https://img.shields.io/badge/ci-passing-green)](https://ci.example)

## Install

Clone the repo and run the binary.
"""


def test_readme_excerpt_skips_picture_and_keeps_prose():
    excerpt = readme_prose_excerpt(HTML_README)
    assert "<" not in excerpt
    assert "picture" not in excerpt.lower()
    assert "srcset" not in excerpt.lower()
    assert "Grok-study is a local research workbench" in excerpt
    assert "grok-study" in excerpt.lower()


def test_readme_excerpt_empty_html_falls_back_to_blank():
    assert readme_prose_excerpt('<div align="center"><picture></picture></div>') == ""


def test_project_goal_desc_does_not_paste_html():
    project = ProjectContext(
        name="grok-study",
        root=".",
        files=[
            FileInfo(
                path="README.md",
                size=len(HTML_README),
                language="markdown",
                content=HTML_README,
                preview=HTML_README,
                is_config=True,
            )
        ],
    )
    desc = ConceptExtractor()._project_goal_desc(project, "README.md")
    assert "<" not in desc
    assert "picture" not in desc.lower()
    assert "Grok-study is a local research workbench" in desc


def test_overview_description_strips_readme_html():
    project = ProjectContext(
        name="grok-study",
        root=".",
        files=[
            FileInfo(
                path="README.md",
                size=len(HTML_README),
                language="markdown",
                content=HTML_README,
                preview=HTML_README,
                is_config=True,
            ),
            FileInfo(
                path="app/main.py",
                size=10,
                language="python",
                content="def main():\n    return 1\n",
                is_entrypoint=True,
            ),
        ],
    )
    graph = DependencyGraph.build_from_project(project)
    data = build_deterministic_wiki_data(project, graph, [])
    assert "<picture" not in data.overview.description
    assert "srcset" not in data.overview.description
    assert "<" not in data.overview.description
    assert "workbench" in data.overview.description.lower()


def test_concept_page_handbook_not_template_dump(monkeypatch):
    monkeypatch.setenv("RECALLSTACK_CONTENT_LANG", "zh")
    why = "先建立对仓库目标与边界的心智模型，再深入实现。"
    wiki = Wiki(project_name="grok-study", pages=[], sidebar=[])
    draft = ConceptDraft(
        slug="project-goal",
        title="项目目标",
        description='<div align="center"><picture><source media="(prefers-color-scheme: dark)" srcset="x">',
        why_learn=why,
        source_references=[SourceReference(path="README.md", start_line=1, end_line=48)],
    )
    page = append_concept_pages(wiki, [draft]).get_page("concepts/project-goal")
    assert page is not None
    content = page.content
    assert content.count(why) == 1
    assert "为什么重要" not in content
    assert "<picture" not in content
    assert "srcset" not in content
    headings = [line for line in content.splitlines() if line.startswith("## ")]
    assert headings[0] == "## 它是什么"
    assert "## 本步要你干什么" not in content
    assert "## 过关" not in content
    assert "## 先回到原理" not in content
    assert "## 只看这一处证据" not in content
    assert "## 它是什么" in content
    assert "## 它在系统里的位置" in content
    assert "## 不是什么" in content
    assert "## 术语小贴士" in content
    assert "## 这份仓库做什么" not in content
    assert "## 自测" not in content
    assert "## 源码证据" not in content
    assert "`README.md:1-48`" in content
    assert "点击展开" not in content
    assert "先点开证据再往下" not in content
    assert "#practice" not in content
    assert "**难度**" not in content
    assert "用两句话写出" not in content
    assert "相关源码" in content
    assert "## 一次调用怎么走" not in content


def test_non_goal_concept_uses_first_principles_heading(monkeypatch):
    monkeypatch.setenv("RECALLSTACK_CONTENT_LANG", "zh")
    wiki = Wiki(project_name="demo", pages=[], sidebar=[])
    draft = ConceptDraft(
        slug="application-entry",
        title="应用入口",
        description="程序从哪里启动。",
        why_learn="入口是阅读调用链的起点。",
        prerequisites=["project-goal"],
        source_references=[SourceReference(path="app/main.py", start_line=1)],
    )
    other = ConceptDraft(slug="project-goal", title="项目目标", why_learn="目标")
    page = append_concept_pages(wiki, [other, draft]).get_page("concepts/application-entry")
    assert page is not None
    assert "## 本步要你干什么" not in page.content
    assert "## 过关" not in page.content
    assert "## 先回到原理" not in page.content
    assert "## 它是什么" in page.content
    assert "## 它在系统里的位置" in page.content
    assert "## 一次调用怎么走" in page.content
    assert "## 职责与边界" not in page.content
    assert "## 这份仓库做什么" not in page.content
    assert "为什么重要" not in page.content
    assert page.content.count("入口是阅读调用链的起点。") == 1
    assert "`app/main.py:1`" in page.content
    assert "点击展开" not in page.content
    assert "## 先读" in page.content
    assert "concepts/project-goal" in page.content


def test_upgrade_legacy_concept_markdown_strips_homework(monkeypatch):
    monkeypatch.setenv("RECALLSTACK_CONTENT_LANG", "zh")
    from recallstack.learning.learning_contract import (
        step_task_for_slug,
        upgrade_legacy_concept_markdown,
    )

    old = """# 项目目标

> 先建立对仓库目标与边界的心智模型，再深入实现。

**难度** 2/5 · **阅读时长** 约 10 分钟 · **重要度** 0.90

## 本步要你干什么

用两句话写出这个仓库为谁、解决什么、明确不做什么。

## 先回到原理

grok-study 是本地研究工作台。

## 只看这一处证据

先点开证据再往下。

- 点击展开 `README.md:1-48`（第 1–48 行）

## 自测

1. 用一句话说清目标

## 过关

1. 用一句话说清目标
先看证据，再到底部练习区作答。[打开练习](#practice)
"""
    upgraded = upgrade_legacy_concept_markdown(old, slug="project-goal", title="项目目标")
    assert "## 本步要你干什么" not in upgraded
    assert "用两句话写出这个仓库为谁" not in upgraded
    assert "## 过关" not in upgraded
    assert "## 自测" not in upgraded
    assert "## 先回到原理" not in upgraded
    assert "## 只看这一处证据" not in upgraded
    assert "为什么重要" not in upgraded
    assert "## 它是什么" in upgraded
    assert "grok-study 是本地研究工作台。" in upgraded
    assert "## 它在系统里的位置" in upgraded
    assert "`README.md:1-48`" in upgraded
    assert "点击展开" not in upgraded
    assert "先点开证据" not in upgraded
    assert "#practice" not in upgraded
    assert "**难度**" not in upgraded
    assert "这篇说明这个仓库解决什么问题" in upgraded
    # Path UI still has the task; wiki GET must not re-insert it.
    assert "两句话" in step_task_for_slug("project-goal", "项目目标")
    again = upgrade_legacy_concept_markdown(upgraded, slug="project-goal", title="项目目标")
    assert again == upgraded
    assert again.count("## 它是什么") == 1
    assert again.count("相关源码") == 1


def test_upgrade_legacy_concept_markdown_rewrites_old_template(monkeypatch):
    monkeypatch.setenv("RECALLSTACK_CONTENT_LANG", "zh")
    from recallstack.learning.learning_contract import upgrade_legacy_concept_markdown

    old = """# 项目目标

> 先建立对仓库目标与边界的心智模型，再深入实现。

## 为什么重要

> 先建立对仓库目标与边界的心智模型，再深入实现。

## 这份仓库做什么

grok-study 是本地研究工作台。

## 源码证据

- `README.md:1-48`

## 自测

1. 用一句话说清目标
"""
    upgraded = upgrade_legacy_concept_markdown(old, slug="project-goal", title="项目目标")
    assert "## 本步要你干什么" not in upgraded
    assert "用两句话写出这个仓库为谁" not in upgraded
    assert "为什么重要" not in upgraded
    assert "## 它是什么" in upgraded
    assert "grok-study 是本地研究工作台。" in upgraded
    assert "## 先回到原理" not in upgraded
    assert "## 只看这一处证据" not in upgraded
    assert "`README.md:1-48`" in upgraded
    assert "点击展开" not in upgraded
    assert "## 过关" not in upgraded
    assert "## 自测" not in upgraded
    assert "相关源码" in upgraded


def test_source_ref_re_matches_readme_span():
    from pathlib import Path

    src = Path("frontend/src/lib/markdown.ts").read_text(encoding="utf-8")
    match = re.search(r"export const SOURCE_REF_RE =\s*/(.+)/;", src)
    assert match, "SOURCE_REF_RE must be exported from markdown.ts"
    regex = re.compile(match.group(1))
    assert regex.fullmatch("README.md:1-48")
    assert regex.fullmatch("README.md")
    assert regex.fullmatch("Cargo.toml")
    assert regex.fullmatch("app/main.py:12-40")
    assert regex.fullmatch("crates/foo/src/lib.rs:1")
    assert regex.fullmatch("bin/grok.rs:1 Agent")
    assert regex.fullmatch("crates/agent/src/app.rs:40 AppServer")
    assert regex.fullmatch("crates/codegen/xai-grok-pager/src/lib.rs")
    assert regex.fullmatch("crates/codegen/xai-grok-pager/src/lib.rs Pager")
    assert regex.fullmatch("crates/xai-chat/src/lib.rs:10 mod channel")
    assert not regex.fullmatch("README")
    assert not regex.fullmatch("just a sentence")

    def source_ref_value(raw: str) -> str:
        found = regex.fullmatch((raw or "").strip())
        if not found:
            return (raw or "").strip()
        path, start, end = found.group(1), found.group(2), found.group(3)
        if start and end:
            return f"{path}:{start}-{end}"
        if start:
            return f"{path}:{start}"
        return f"{path}:1"

    assert source_ref_value("README.md") == "README.md:1"
    assert source_ref_value("crates/codegen/xai-grok-pager/src/lib.rs") == (
        "crates/codegen/xai-grok-pager/src/lib.rs:1"
    )
    assert source_ref_value("bin/grok.rs:1 Agent") == "bin/grok.rs:1"
    assert source_ref_value("app/main.py:12-40") == "app/main.py:12-40"
    assert source_ref_value("crates/xai-chat/src/lib.rs:10 mod channel") == (
        "crates/xai-chat/src/lib.rs:10"
    )

    assert "export function sourceRefValue" in src
    fn = re.search(
        r"export function sourceRefValue\(raw: string\): string \{[\s\S]*?\n\}",
        src,
    )
    assert fn, "sourceRefValue must be exported"
    assert "SOURCE_REF_RE.exec" in fn.group(0)
    assert "${path}:1" in fn.group(0)
    assert "rs-related-source" in src
    assert "data-md-block=\"related-source\"" in src
    assert 'data-md-block="list-item"' in src
    assert "export function isPathLikeChip" in src
    assert "rs-ref-sym" in src


def test_markdown_ts_normalizes_bare_mermaid():
    from pathlib import Path

    src = Path("frontend/src/lib/markdown.ts").read_text(encoding="utf-8")
    diagram = Path("frontend/src/components/MermaidDiagram.tsx").read_text(encoding="utf-8")
    assert "export function normalizeMermaidSource" in src
    assert "flowchart LR" in src
    assert "→" in src and "⟶" in src
    assert 'replace(/[→⟶' in src
    assert "normalizeMermaidSource(body)" in src
    assert "flowchart|graph|sequenceDiagram|classDiagram|stateDiagram" in src
    assert "from \"../lib/markdown\"" in diagram
    assert "normalizeMermaidSource(code)" in diagram
    fn = re.search(
        r"export function normalizeMermaidSource\(code: string\): string \{[\s\S]*?\n\}",
        src,
    )
    assert fn, "normalizeMermaidSource must be exported from markdown.ts"
    body = fn.group(0)
    assert "MERMAID_TYPE_RE.test" in body
    assert "flowchart LR" in body
    assert 'startsWith("%%")' in body


def test_wiki_content_peek_hitbox_is_chip_only():
    from pathlib import Path

    wiki = Path("frontend/src/components/WikiContent.tsx").read_text(encoding="utf-8")
    css = Path("frontend/src/index.css").read_text(encoding="utf-8")
    md = Path("frontend/src/lib/markdown.ts").read_text(encoding="utf-8")
    peek = Path("frontend/src/components/SourcePeek.tsx").read_text(encoding="utf-8")
    assert "chipFromEvent" in wiki
    assert 'closest(".rs-ref")' in wiki
    assert ".rs-ref[data-ref]" not in wiki
    assert "p:has(.rs-ref)" not in css
    sym = re.search(r"\.rs-ref-sym \{[^}]+\}", css)
    assert sym and "pointer-events: none" in sym.group(0)
    assert 'data-md-block="list-item"' in md
    assert "closest(\"[data-md-block], .rs-related-source\")" in wiki.replace("'", '"')
    assert ".rs-related-source" in css
    assert "flex: 0 0 auto" in css
    assert "display: flex" in css
    assert "flex-wrap: wrap" in css
    assert "path:line Symbol" in peek
    assert "normalizeMermaidSource" in md

