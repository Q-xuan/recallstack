"""Build RepoWiki-compatible pages from the same analyze pipeline.

This is the fusion layer: learning concepts and wiki pages come from one scan.
LLM-enhanced WikiData is optional; deterministic pages always exist.
"""

from __future__ import annotations

import os
from typing import Any

from recallstack.domain.schemas import ConceptDraft
from recallstack.learning.i18n import t
from repowiki.core.graph import DependencyGraph
from repowiki.core.models import (
    ArchitectureDiagram,
    Component,
    FileDoc,
    ModuleDoc,
    ProjectContext,
    ProjectOverview,
    ReadingGuide,
    ReadingStep,
    WikiData,
)
from repowiki.core.wiki_builder import Wiki, WikiBuilder, WikiPage


def build_deterministic_wiki_data(
    project: ProjectContext,
    graph: DependencyGraph,
    concepts: list[ConceptDraft] | None = None,
) -> WikiData:
    """Construct WikiData without LLM so wiki always ships with learning."""
    concepts = concepts or []
    readme = next((f for f in project.files if f.path.lower() in {"readme.md", "readme"}), None)
    description = ""
    if readme and (readme.content or readme.preview):
        text = (readme.content or readme.preview or "").strip()
        description = text[:1200]

    ranked = graph.rank_files()
    top_files = [p for p, _ in ranked[:12]]
    entry_files = graph.get_entry_points()[:8] or [
        f.path for f in project.files if getattr(f, "is_entrypoint", False)
    ][:8]

    overview = ProjectOverview(
        name=project.name,
        one_liner=t(f"Learnable code wiki for {project.name} (scan + dependency graph)", f"{project.name} 的可学习代码 Wiki（由扫描 + 依赖图生成）"),
        description=description
        or t("Repository scanned. Concept graph and reading path generated from structure and dependency graph.", "该仓库已扫描并生成概念图谱与阅读路径。以下内容来自源码结构与依赖图。"),
        key_features=[
            t(f"Scanned {len(project.files)} files", f"扫描文件 {len(project.files)} 个"),
            t(f"Core files: {', '.join(top_files[:5])}", f"核心文件示例：{', '.join(top_files[:5])}") if top_files else t("Dependency graph built", "依赖图已构建"),
            t(f"{len(concepts)} learning concepts", f"学习概念 {len(concepts)} 个"),
        ],
        setup_instructions=[
            t("Read Overview and Architecture first", "先读 Overview 与 Architecture"),
            t("Follow the Reading Guide / learning path page by page", "按 Reading Guide / 学习路径逐步打开词条"),
            t("Do the 30-second probe on a concept page, then go deeper", "在词条内完成 30 秒自测，再进入深入练习"),
        ],
    )

    # modules from directory roots
    modules_map: dict[str, list[Any]] = {}
    for f in project.files:
        parts = f.path.replace("\\", "/").split("/")
        mod = parts[0] if len(parts) > 1 else "Root"
        if mod in {".", ""}:
            mod = "Root"
        modules_map.setdefault(mod, []).append(f)

    module_docs: list[ModuleDoc] = []
    for name, files in sorted(modules_map.items(), key=lambda x: (-len(x[1]), x[0]))[:20]:
        display = "Root" if name in {"(root)", "root", "Root"} else name
        file_docs = [
            FileDoc(
                path=f.path.replace("\\", "/"),
                purpose=t("Entrypoint", "入口文件") if getattr(f, "is_entrypoint", False) else t("Source file", "源码文件"),
                key_symbols=[],
            )
            for f in files[:12]
        ]
        module_docs.append(
            ModuleDoc(
                name=display,
                purpose=t(f"{display} module · {len(files)} files", f"{display} 模块 · {len(files)} 个文件"),
                description=(
                    t("Loose root files (README, config, etc.).", "仓库根目录下的散落文件（如 README、配置）。")
                    if display == "Root"
                    else t(f"`{display}/` directory boundary from scan + dependency graph.", f"`{display}/` 目录边界，来自扫描与依赖图。")
                ),
                files=file_docs,
            )
        )

    components = [
        Component(
            name=m.name,
            purpose=m.purpose,
            files=[fd.path for fd in m.files[:6]],
        )
        for m in module_docs[:12]
    ]
    architecture = ArchitectureDiagram(
        architecture_type="codebase-modules",
        description=t("Architecture sketch from directory boundaries and dependency graph. LLM can enrich this later.", "基于目录边界与依赖图的架构草图。有 LLM 时可被更丰富的架构说明替换。"),
        components=components,
        mermaid_component=graph.to_mermaid() or "",
        data_flow=t("Entrypoints → core modules → dependents (see Dependencies + learning path).", "入口文件 → 核心模块 → 依赖模块（见 Dependencies 页与学习路径）。"),
    )

    steps: list[ReadingStep] = []
    if concepts:
        for i, c in enumerate(concepts[:12], start=1):
            files = [r.path for r in c.source_references[:4]]
            steps.append(
                ReadingStep(
                    order=i,
                    title=c.title,
                    files=files,
                    explanation=c.why_learn or c.description,
                    time_estimate=f"{c.estimated_minutes or 10} min",
                )
            )
    else:
        for i, path in enumerate((entry_files or top_files)[:8], start=1):
            steps.append(
                ReadingStep(
                    order=i,
                    title=path,
                    files=[path],
                    explanation=t("Reading step ordered by entrypoints/importance", "按入口/重要度排序的阅读步骤"),
                    time_estimate="10 min",
                )
            )

    reading_guide = ReadingGuide(
        introduction=t("This is the reading script. Each step maps to a practice concept: read evidence, then recall.", "这是仓库的阅读剧本。每一步对应一个可练习概念：先读证据，再做回忆。"),
        steps=steps,
        tips=[
            t("Don't skim directory names — open source evidence before probing", "不要只扫目录名，点开源码证据再做自测"),
            t("If prerequisites are weak, go back and re-read them first", "先修概念没掌握时，先回退阅读"),
            t("Reviews are scheduled by concept, not by scattered items", "复习队列按概念调度，不按散题调度"),
        ],
    )

    return WikiData(
        overview=overview,
        modules=module_docs,
        architecture=architecture,
        reading_guide=reading_guide,
    )


def append_concept_pages(wiki: Wiki, concepts: list[ConceptDraft]) -> Wiki:
    """Attach concept wiki pages so learning objects live inside the wiki tree."""
    if not concepts:
        return wiki

    from repowiki.core.wiki_builder import SidebarItem

    concept_sidebar = SidebarItem(title="Concepts", page_id="", children=[])
    for i, c in enumerate(concepts):
        page_id = f"concepts/{c.slug}"
        lines = [
            f"# {c.title}\n",
            f"> {c.why_learn or c.description}\n",
            f"{c.description}\n",
            "## Why this matters\n",
            f"{c.why_learn or t('Understanding this concept builds a mental model of the main flow.', '理解该概念有助于建立仓库主流程心智模型。')}\n",
            "## Source evidence\n",
        ]
        for ref in c.source_references[:8]:
            loc = ref.path
            if ref.start_line:
                loc += f":{ref.start_line}"
                if ref.end_line:
                    loc += f"-{ref.end_line}"
            if ref.symbol:
                loc += f" (`{ref.symbol}`)"
            lines.append(f"- `{loc}`")
        lines.append("")
        if c.prerequisites:
            lines.append("## Prerequisites\n")
            for p in c.prerequisites:
                lines.append(f"- `{p}`")
            lines.append("")
        lines.extend(
            [
                "## Practice\n",
                t(
                    "1. Explain the responsibility boundary in your own words\n"
                    "2. Point to at least one source evidence location\n"
                    "3. Relate it to prerequisite concepts\n",
                    "1. 用自己的话说明这个概念的职责边界\n"
                    "2. 指出至少一处源码证据\n"
                    "3. 说明它与先修概念的关系\n",
                ),
                "\n",
                f"_concept_slug: `{c.slug}`_\n",
            ]
        )
        wiki.pages.append(
            WikiPage(
                id=page_id,
                title=c.title,
                content="\n".join(lines),
                parent_id="concepts",
                order=100 + i,
            )
        )
        concept_sidebar.children.append(SidebarItem(title=c.title, page_id=page_id))
    if concept_sidebar.children:
        wiki.sidebar.append(concept_sidebar)
    return wiki


async def build_llm_enriched_wiki_data(
    project: ProjectContext,
    graph: DependencyGraph,
    concepts: list[ConceptDraft],
    on_progress: Any = None,
) -> WikiData:
    """Run repowiki's LLM Analyzer and merge with deterministic concept-derived pages.

    The LLM owns overview / modules / architecture (semantic understanding).
    The reading guide stays deterministic because its steps map 1:1 to RecallStack
    learning concepts — that linkage is what powers the practice loop.

    Raises when LLM credentials are absent; callers must fall back to deterministic.
    """
    from repowiki.config import Config as RepoWikiConfig
    from repowiki.core.analyzer import Analyzer
    from repowiki.core.cache import Cache
    from repowiki.llm.client import LLMClient

    rw = RepoWikiConfig.load()
    if not rw.api_key or not rw.model:
        raise RuntimeError("LLM credentials not configured")

    llm = LLMClient(model=rw.model, api_key=rw.api_key, api_base=rw.api_base or "")
    cache = Cache()
    await cache.init()
    try:
        analyzer = Analyzer(
            llm=llm,
            cache=cache,
            language=rw.language,
            concurrency=int(os.getenv("RECALLSTACK_LLM_MAX_CONCURRENCY", "3")),
        )
        llm_wd = await analyzer.analyze(project, on_progress=on_progress)
    finally:
        await cache.close()

    det_wd = build_deterministic_wiki_data(project, graph, concepts)
    return WikiData(
        overview=llm_wd.overview if (llm_wd.overview and llm_wd.overview.name) else det_wd.overview,
        modules=llm_wd.modules or det_wd.modules,
        architecture=(
            llm_wd.architecture
            if (
                llm_wd.architecture
                and (llm_wd.architecture.architecture_type or llm_wd.architecture.description)
            )
            else det_wd.architecture
        ),
        reading_guide=det_wd.reading_guide,
        file_index=llm_wd.file_index or det_wd.file_index,
    )


def build_wiki_payload(
    project: ProjectContext,
    graph: DependencyGraph,
    concepts: list[ConceptDraft],
    *,
    wiki_data: WikiData | None = None,
) -> dict[str, Any]:
    """Return JSON-serializable wiki payload for persistence.

    Pass ``wiki_data`` to render LLM-enriched pages; leave None for the
    deterministic path.
    """
    if wiki_data is None:
        wiki_data = build_deterministic_wiki_data(project, graph, concepts)
    wiki = WikiBuilder().build(project, wiki_data, graph)
    wiki = append_concept_pages(wiki, concepts)
    return {
        "project_name": wiki.project_name,
        "pages": [
            {
                "id": p.id,
                "title": p.title,
                "content": p.content,
                "parent_id": p.parent_id,
                "order": p.order,
            }
            for p in wiki.pages
        ],
        "sidebar": [_sidebar_to_dict(s) for s in wiki.sidebar],
    }


def _sidebar_to_dict(item: Any) -> dict[str, Any]:
    return {
        "title": item.title,
        "page_id": item.page_id,
        "children": [_sidebar_to_dict(c) for c in (item.children or [])],
    }


def empty_wiki_payload(name: str = "") -> dict[str, Any]:
    return {"project_name": name, "pages": [], "sidebar": []}
