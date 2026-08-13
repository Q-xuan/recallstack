"""Build RepoWiki-compatible pages from the same analyze pipeline.

This is the fusion layer: learning concepts and wiki pages come from one scan.
LLM-enhanced WikiData is optional; deterministic pages always exist.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any

from recallstack.domain.schemas import ConceptDraft, ConceptTermTip
from recallstack.learning.concept_extractor import readme_prose_excerpt
from recallstack.learning.i18n import content_lang, t
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
    TermTip,
    WikiData,
)
from repowiki.core.modules import ROOT_NAME, group_into_modules
from repowiki.core.wiki_builder import Wiki, WikiBuilder, WikiPage

logger = logging.getLogger(__name__)


def _generic_term_tips() -> list[TermTip]:
    return [
        TermTip(
            term="PageRank",
            tip=t(
                "Here PageRank ranks files by import centrality so the wiki can write deeper pages for hubs, not dump a directory listing.",
                "这里的 PageRank 按 import 图给文件打重要性分，用来决定哪些模块值得写深，而不是用来罗列文件。",
            ),
        ),
        TermTip(
            term="crate",
            tip=t(
                "A Rust/Cargo package. Keep the crate name as it appears in Cargo.toml.",
                "Rust/Cargo 的包单位。crate 名保持 Cargo.toml 里的英文原文，不要音译。",
            ),
        ),
        TermTip(
            term="entrypoint",
            tip=t(
                "A process start file (main, bin, CLI). Read these first to see how the rest of the graph is wired.",
                "进程入口（main / bin / CLI）。先读入口才能看清其余模块是怎么被串起来的。",
            ),
        ),
    ]


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
        description = readme_prose_excerpt(
            readme.content or readme.preview or "", max_paragraphs=3, max_chars=1200
        )

    ranked = graph.rank_files()
    top_files = [p for p, _ in ranked[:12]]
    entry_files = graph.get_entry_points()[:8] or [
        f.path for f in project.files if getattr(f, "is_entrypoint", False)
    ][:8]

    overview = ProjectOverview(
        name=project.name,
        one_liner=t(
            f"{project.name}: a learnable wiki of how this repo is wired",
            f"{project.name}：讲清这个仓库怎么串起来的可学习 Wiki",
        ),
        description=description
        or t(
            "This wiki is a handbook, not a directory listing. Start at the entrypoints, "
            "then follow import-graph hubs to see how responsibility is split. Concept pages "
            "and the reading path come from the same scan.",
            "本 Wiki 是内部手册，不是文件清单。先从入口看进程怎么启动，再顺着 import 图上的枢纽包"
            "看职责怎么切。词条与阅读路径来自同一次扫描。",
        ),
        key_features=[
            t(
                "Scan + import graph produce a reading path; start at entrypoints, then hubs.",
                "扫描与 import 图搭出阅读路径：先从入口进，再读枢纽模块。",
            ),
            t(
                f"{len(concepts)} practice concepts mapped onto source evidence",
                f"{len(concepts)} 个可练习词条，对齐源码证据",
            ) if concepts else t(
                "Learning concepts will appear once the concept graph is built",
                "概念图谱生成后会出现可练习词条",
            ),
        ],
        setup_instructions=[
            t("Read Overview and Architecture first", "先读概述与架构概览"),
            t("Follow the Reading Guide / learning path page by page", "按导读 / 学习路径逐步打开词条"),
            t("Do the 30-second probe on a concept page, then go deeper", "在词条内完成 30 秒自测，再进入深入练习"),
        ],
        term_tips=_generic_term_tips(),
    )

    # Same grouping the LLM path and the dependency graph use, so a module keeps
    # one name across all three and its page can find its own edges.
    modules_map = group_into_modules(project.files)

    module_docs: list[ModuleDoc] = []
    for name, files in sorted(modules_map.items(), key=lambda x: (-len(x[1]), x[0])):
        is_root = name == ROOT_NAME
        file_docs = [
            FileDoc(
                path=f.path,
                purpose=t("Entrypoint", "入口文件") if getattr(f, "is_entrypoint", False) else t("Source file", "源码文件"),
                key_symbols=[],
            )
            for f in files[:12]
        ]
        module_docs.append(
            ModuleDoc(
                name=name,
                purpose=t(
                    f"Owns the `{name}` package boundary",
                    f"负责 `{name}` 这一层的职责边界",
                ),
                description=(
                    t(
                        "Loose root files (README, config, etc.). Read them for how the repo is started and configured, not as a file dump.",
                        "仓库根目录下的散落文件（README、配置等）。用来看仓库怎么启动、怎么配置，不要当成文件清单。",
                    )
                    if is_root
                    else t(
                        f"`{name}/` is a directory boundary. This page states what the package is for and how it connects; the file list is evidence, not the article.",
                        f"`{name}/` 是一层目录边界。本页先讲这包负责什么、和谁协作；文件列表只是证据，不是正文。",
                    )
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
        description=t(
            "The repo is split by directory modules. Data enters at the entrypoints, "
            "then moves through the highest-centrality packages. Use the diagram to see "
            "coupling; PageRank only ranks which pages to write first, not a table of contents.",
            "仓库按目录划成模块。请求从入口文件进来，经过图上最中心的包，再扩散到依赖方。"
            "结构图用来看耦合；PageRank 只决定先写哪几页，不是目录清单。",
        ),
        components=components,
        mermaid_component=graph.to_mermaid() or "",
        data_flow=t(
            "Entrypoints → core modules → dependents (see the dependency diagram and the learning path).",
            "入口文件 → 核心模块 → 依赖模块（见结构图与学习路径）。",
        ),
        term_tips=_generic_term_tips(),
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


def _format_ref(ref: Any) -> str:
    """Render a source reference as ``path:start-end``.

    The frontend detects this shape inside inline code and turns it into an
    expandable snippet, so the format has to stay stable — and it still reads
    fine as plain text in an exported Markdown wiki.
    """
    loc = ref.path.replace("\\", "/")
    if ref.start_line:
        loc += f":{ref.start_line}"
        if ref.end_line and ref.end_line != ref.start_line:
            loc += f"-{ref.end_line}"
    return loc


def _is_html_dump(text: str) -> bool:
    if not text or not text.strip():
        return True
    low = text.lower()
    return bool(
        "<div" in low
        or "<picture" in low
        or "<source" in low
        or "srcset=" in low
        or re.search(r"</?(img|table|center)\b", low)
    )


def _clean_concept_body(text: str) -> str:
    if not text or _is_html_dump(text):
        return ""
    if "<" in text:
        stripped = re.sub(r"<[^>]+>", "", text).strip()
        if not stripped or _is_html_dump(stripped):
            return ""
        return stripped
    return text.strip()


def _not_this_for(concept: ConceptDraft) -> list[str]:
    if concept.not_this:
        return [item.strip() for item in concept.not_this if item and item.strip()][:5]
    slug = concept.slug
    if slug == "project-goal":
        return [
            t(
                "Not a dump of every file in the repository.",
                "不是把仓库里每个文件列一遍。",
            ),
            t(
                "Not a substitute for reading the entrypoints.",
                "不能替代去读入口文件（entrypoint）。",
            ),
        ]
    if slug == "application-entry":
        return [
            t(
                "Not the whole architecture — only where the process starts.",
                "不是整份架构说明，只讲进程从哪启动。",
            ),
            t(
                "Not configuration or persistence, unless the entrypoint wires them in.",
                "不是配置或持久化本身，除非入口把它们接上。",
            ),
        ]
    return []


def _tips_for_concept(concept: ConceptDraft) -> list[TermTip]:
    if concept.term_tips:
        return [TermTip(term=tip.term, tip=tip.tip) for tip in concept.term_tips if tip.term]
    generic = _generic_term_tips()
    blob = f"{concept.slug} {concept.title} {concept.description} {concept.why_learn}".lower()
    if concept.slug == "project-goal":
        return generic
    picked: list[TermTip] = []
    by_term = {tip.term.lower(): tip for tip in generic}
    if "entry" in concept.slug or "入口" in concept.title:
        picked.append(by_term["entrypoint"])
    if any(key in blob for key in ("crate", "cargo", "rust")):
        picked.append(by_term["crate"])
    if any(key in blob for key in ("pagerank", "module-", "依赖", "graph")):
        picked.append(by_term["pagerank"])
    if "acp" in blob:
        picked.append(
            TermTip(
                term="ACP",
                tip=t(
                    "Agent Communication Protocol in this repo — keep the acronym in English.",
                    "本仓库里的 Agent Communication Protocol；缩写保持英文 ACP。",
                ),
            )
        )
    # unique by term, stable order
    seen: set[str] = set()
    out: list[TermTip] = []
    for tip in picked:
        key = tip.term.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(tip)
    return out


def _role_heading(concept: ConceptDraft) -> str:
    if concept.slug == "project-goal":
        return t("## What this repo does\n", "## 这份仓库做什么\n")
    return t("## Responsibility and boundaries\n", "## 职责与边界\n")


def _role_body(concept: ConceptDraft, project_name: str) -> str:
    body = _clean_concept_body(concept.description)
    why = (concept.why_learn or "").strip()
    if body and why and body == why:
        body = ""
    if body:
        return body
    name = project_name or concept.title
    if concept.slug == "project-goal":
        return t(
            f"{name} solves a specific problem for its users. This page states the goal "
            "and capability boundary; how the implementation is wired belongs on the "
            "entrypoint and module pages.",
            f"{name} 用来解决一类具体问题、给特定读者用。"
            "本页讲目标与能力边界；实现怎么串，放到入口和模块词条。",
        )
    return t(
        f"`{concept.title}` is a responsibility boundary in this repo. Read the evidence "
        "below to see what it owns and who it collaborates with.",
        f"「{concept.title}」是本仓库里的一块职责边界。先看它负责什么、不负责什么，"
        "再顺着下面的源码证据读实现。",
    )


def _self_check(concept: ConceptDraft) -> str:
    title = concept.title
    if concept.slug == "project-goal":
        return t(
            f"1. In one sentence, who is `{title}` for and what problem does it solve?\n"
            "2. Name one thing this repo is NOT responsible for\n"
            "3. Point to the README or an entrypoint that supports that claim\n",
            f"1. 用一句话说清「{title}」给谁用、解决什么问题\n"
            "2. 举一件这个仓库明确不负责的事\n"
            "3. 指出 README 或入口文件里支撑该判断的证据\n",
        )
    if concept.slug == "application-entry":
        return t(
            f"1. Name the entrypoint file for `{title}` and what it calls first\n"
            "2. What does the entrypoint own vs. what it only wires in?\n"
            "3. Point to one source location on this page that shows the boot path\n",
            f"1. 指出「{title}」对应的入口文件，以及它首先调用了什么\n"
            "2. 入口自己负责什么，只是装配进来的又是什么？\n"
            "3. 在本页源码证据里指出一处能看出启动路径的位置\n",
        )
    return t(
        f"1. In your own words, what does `{title}` own — and where does that stop?\n"
        "2. Point to at least one source evidence path on this page\n"
        "3. Name one prerequisite or follow-on concept that changes if this boundary moves\n",
        f"1. 用自己的话说明「{title}」负责什么、边界停在哪里\n"
        "2. 指出本页至少一处源码证据（路径即可）\n"
        "3. 如果这条边界移动，会影响到哪条先修或后续概念？\n",
    )


def _append_term_tips_md(lines: list[str], tips: list[TermTip]) -> None:
    if not tips:
        return
    lines.append(t("## Term tips\n", "## 术语小贴士\n"))
    for tip in tips:
        if tip.tip:
            lines.append(f"> **{tip.term}** — {tip.tip}")
        else:
            lines.append(f"> **{tip.term}**")
    lines.append("")


def append_concept_pages(wiki: Wiki, concepts: list[ConceptDraft]) -> Wiki:
    """Attach concept wiki pages so learning objects live inside the wiki tree.

    Handbook layout: title, one-line why, meta, role/boundaries, not-this,
    term tips, evidence, cross-links, then a concept-specific self-check.
    """
    if not concepts:
        return wiki

    from repowiki.core.wiki_builder import SidebarItem

    title_by_slug = {c.slug: c.title for c in concepts}
    dependents: dict[str, list[str]] = {}
    for c in concepts:
        for pre in c.prerequisites:
            if pre in title_by_slug:
                dependents.setdefault(pre, []).append(c.slug)

    def link(slug: str) -> str:
        return f"[{title_by_slug.get(slug, slug)}](concepts/{slug})"

    concept_sidebar = SidebarItem(title=t("Concepts", "词条"), page_id="", children=[])
    for i, c in enumerate(concepts):
        page_id = f"concepts/{c.slug}"
        minutes = c.estimated_minutes or 10
        why = (c.why_learn or "").strip()
        lines = [
            f"# {c.title}\n",
        ]
        if why:
            lines.append(f"> {why}\n")
        lines.append(
            t(
                f"**Difficulty** {c.difficulty}/5 · **Reading time** ~{minutes} min · "
                f"**Importance** {c.importance:.2f}\n",
                f"**难度** {c.difficulty}/5 · **阅读时长** 约 {minutes} 分钟 · "
                f"**重要度** {c.importance:.2f}\n",
            )
        )
        lines.append(_role_heading(c))
        lines.append(f"{_role_body(c, wiki.project_name)}\n")

        not_this = _not_this_for(c)
        if not_this:
            lines.append(t("## What this is not\n", "## 不是什么\n"))
            for item in not_this:
                lines.append(f"- {item}")
            lines.append("")

        _append_term_tips_md(lines, _tips_for_concept(c))

        lines.append(t("## Source evidence\n", "## 源码证据\n"))
        if c.source_references:
            for ref in c.source_references[:8]:
                symbol = f" — `{ref.symbol}`" if ref.symbol else ""
                lines.append(f"- `{_format_ref(ref)}`{symbol}")
        else:
            lines.append(
                t(
                    "_No file-level evidence was extracted for this concept._",
                    "_该概念未能提取到文件级证据。_",
                )
            )
        lines.append("")

        prereqs = [p for p in c.prerequisites if p in title_by_slug]
        if prereqs:
            lines.append(t("## Read first\n", "## 先读\n"))
            for p in prereqs:
                lines.append(f"- {link(p)}")
            lines.append("")

        unlocks = dependents.get(c.slug, [])
        if unlocks:
            lines.append(t("## Leads to\n", "## 继续读\n"))
            for d in unlocks[:8]:
                lines.append(f"- {link(d)}")
            lines.append("")

        lines.extend(
            [
                t("## Self-check\n", "## 自测\n"),
                _self_check(c),
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


def link_reading_guide(wiki: Wiki, concepts: list[ConceptDraft]) -> Wiki:
    """Turn Reading Guide step headings into links to their concept pages.

    The guide's steps are generated 1:1 from concepts, so leaving them as plain
    text forces the reader back to the sidebar to find the page being described.
    """
    if not concepts:
        return wiki
    slug_by_title = {c.title: c.slug for c in concepts}
    for page in wiki.pages:
        if page.id != "reading-guide":
            continue
        out: list[str] = []
        for line in page.content.split("\n"):
            match = re.match(r"^## Step (\d+): (.+?)( \(~[^)]*\))?$", line)
            if match:
                number, title, suffix = match.group(1), match.group(2), match.group(3) or ""
                slug = slug_by_title.get(title)
                if slug:
                    out.append(f"## Step {number}: [{title}](concepts/{slug}){suffix}")
                    continue
            out.append(line)
        page.content = "\n".join(out)
    return wiki


def _select_concepts_to_enrich(concepts: list[ConceptDraft], *, limit: int = 6) -> list[ConceptDraft]:
    selected: list[ConceptDraft] = []
    goal = next((c for c in concepts if c.slug == "project-goal"), None)
    if goal:
        selected.append(goal)
    rest = sorted(
        (c for c in concepts if c.slug != "project-goal"),
        key=lambda c: -c.importance,
    )
    for item in rest:
        if len(selected) >= limit:
            break
        selected.append(item)
    return selected


async def _enrich_top_concepts(llm: Any, concepts: list[ConceptDraft], project: ProjectContext) -> None:
    """Rewrite project-goal + top concepts. Never raises to the caller."""
    from repowiki.llm.prompts import extract_json

    language = content_lang()
    readme = next(
        (f for f in project.files if f.path.lower() in {"readme.md", "readme"}),
        None,
    )
    cleaned = ""
    if readme and (readme.content or readme.preview):
        cleaned = readme_prose_excerpt(readme.content or readme.preview or "")
    file_list = "\n".join(f.path for f in project.files[:40])
    targets = _select_concepts_to_enrich(concepts)
    for concept in targets:
        try:
            raw = await llm.complete(
                _concept_enrich_messages(concept, cleaned, file_list, language, project.name),
                max_tokens=1024,
                response_format={"type": "json_object"},
            )
            data = extract_json(raw)
            if not isinstance(data, dict):
                continue
            desc = str(data.get("description") or "").strip()
            if desc and not _is_html_dump(desc):
                concept.description = desc
            why = str(data.get("why_learn") or "").strip()
            if why and not _is_html_dump(why):
                concept.why_learn = why
            not_this = data.get("not_this") or []
            if isinstance(not_this, list):
                concept.not_this = [
                    str(item).strip() for item in not_this if str(item).strip()
                ][:5]
            tips_raw = data.get("term_tips") or []
            tips: list[ConceptTermTip] = []
            if isinstance(tips_raw, list):
                for item in tips_raw:
                    if isinstance(item, dict) and item.get("term"):
                        tips.append(
                            ConceptTermTip(
                                term=str(item["term"]).strip(),
                                tip=str(item.get("tip") or "").strip(),
                            )
                        )
            if tips:
                concept.term_tips = tips[:8]
        except Exception as exc:  # noqa: BLE001
            logger.warning("concept enrich failed for %s: %s", concept.slug, exc)


def _concept_enrich_messages(
    concept: ConceptDraft,
    cleaned_readme: str,
    file_list: str,
    language: str,
    project_name: str,
) -> list[dict]:
    from repowiki.llm.prompts import _json_instruction, _lang_instruction

    return [
        {
            "role": "system",
            "content": (
                "You write a short handbook entry for one learning concept in a codebase wiki. "
                "Be specific to THIS repository. No HTML. No file inventory. "
                f"{_lang_instruction(language)}"
            ),
        },
        {
            "role": "user",
            "content": (
                f"Project: {project_name}\n"
                f"Concept: {concept.title} (slug {concept.slug})\n"
                f"Current description: {(concept.description or '')[:800]}\n"
                f"Current why_learn: {concept.why_learn or '(none)'}\n\n"
                f"## Cleaned README excerpt\n{cleaned_readme or '(none)'}\n\n"
                f"## Files (sample)\n{file_list or '(none)'}\n\n"
                "Return JSON:\n"
                "{\n"
                '  "description": "2-4 sentences: what it is for, who uses it, capability boundary",\n'
                '  "why_learn": "one sentence",\n'
                '  "not_this": ["common confusion 1"],\n'
                '  "term_tips": [{"term": "PageRank", "tip": "how THIS repo uses it"}]\n'
                "}\n"
                "not_this: 1-3 bullets of what this concept is NOT. "
                "term_tips: 2-5 repo-specific jargon tips; keep `term` in English. "
                "Do not invent file paths.\n\n"
                f"{_json_instruction(language)}"
            ),
        },
    ]


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

    try:
        await _enrich_top_concepts(llm, concepts, project)
    except Exception as exc:  # noqa: BLE001
        logger.warning("concept enrich skipped: %s", exc)

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
    from repowiki.core.cite_check import verify_wiki_data

    if wiki_data is None:
        wiki_data = build_deterministic_wiki_data(project, graph, concepts)
    wiki_data = verify_wiki_data(wiki_data, project)
    wiki = WikiBuilder().build(project, wiki_data, graph, language=content_lang())
    wiki = append_concept_pages(wiki, concepts)
    wiki = link_reading_guide(wiki, concepts)
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
