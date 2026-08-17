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
from recallstack.learning.learning_contract import (
    deepen_concept_markdown,
    first_principles,
    flow_narrative,
    handbook_lede,
    handbook_position,
    related_source_chip_line,
    wiki_prose_excerpt,
)
from repowiki.core.graph import DependencyGraph
from repowiki.core.models import (
    ArchitectureDiagram,
    Citation,
    Component,
    ProjectContext,
    ProjectOverview,
    ReadingGuide,
    ReadingStep,
    TermTip,
    WikiData,
)
from repowiki.core.module_handbook import fallback_module_doc
from repowiki.core.modules import group_into_modules
from repowiki.core.topics import (
    codebase_structure_for,
    fallback_topic_doc,
    is_generic_web_slug,
    runtime_mermaid_for,
    subsystems_from_topics,
    topic_wiki_links,
)
from repowiki.core.wiki_builder import Wiki, WikiBuilder, WikiPage, structural_title

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

    lang = content_lang()

    # Same grouping the LLM path and the dependency graph use, so a module keeps
    # one name across all three and its page can find its own edges.
    modules_map = group_into_modules(project.files)

    from repowiki.core.outline import build_deterministic_outline

    outline = build_deterministic_outline(project, modules_map, graph, language=lang)

    cites: list[Citation] = []
    if readme:
        cites.append(Citation(path=readme.path, start_line=1, note="README"))
    for path in entry_files[:4]:
        cites.append(Citation(path=path, note="entrypoint"))

    what_it_is: list[str] = []
    if readme:
        what_it_is.append(
            t(
                f"The goal lives in the README, not the folder names. `{readme.path}:1`",
                f"仓库目标与边界写在 README，而不是目录名。 `{readme.path}:1`",
            )
        )
    for path in entry_files[:3]:
        what_it_is.append(
            t(
                f"The process starts at `{path}:1`; one call enters the graph here.",
                f"进程从 `{path}:1` 启动，一次调用从这里进图。",
            )
        )
    for topic in outline.topics:
        if topic.section == "getting-started" or not topic.key_files:
            continue
        title = topic.title or topic.id
        path = topic.key_files[0]
        what_it_is.append(
            t(
                f"{title} owns one stretch of the call path; see `{path}`.",
                f"「{title}」接住链路上的一段工作，证据在 `{path}`。",
            )
        )
        if len(what_it_is) >= 6:
            break

    overview = ProjectOverview(
        name=project.name,
        one_liner=t(
            f"{project.name}: how this repo is wired on one real call",
            f"{project.name}：一次真实调用里这个仓库怎么串起来",
        ),
        document_scope=t(
            f"{project.name}: the goal, who a real call passes through, and how the repo is split. "
            "Key types stay English identifiers; evidence is `path:line Symbol` next to the claim.",
            f"{project.name} 的目标、一次真实调用经过谁、仓库怎么拆。"
            "关键类型保持英文 identifier，证据用 `path:line Symbol` 贴在断言旁边。",
        ),
        description=description
        or t(
            "This wiki is a handbook, not a directory listing. Start at the entrypoints, "
            "then follow the systems that actually run a call — not a crate inventory.",
            "本 Wiki 是内部手册，不是文件清单。先从入口看进程怎么启动，再顺着一次调用经过的"
            "系统读下去，而不是把 crate 列一遍。",
        ),
        what_it_is=what_it_is,
        runtime_flow=(
            outline.overview_focus
            if outline.overview_focus
            else t(
                "Work enters at the process entrypoint, moves through hub types, "
                "then out to dependents. The diagram follows that call, not the crate tree.",
                "请求从入口进程进来，经过枢纽包上的类型，再交到依赖方。"
                "下面的结构图按这条链路画，而不是按 crate 目录。",
            )
        ),
        mermaid_component=graph.to_mermaid()
        or runtime_mermaid_for(entry_files=entry_files, topics=outline.topics),
        codebase_structure=codebase_structure_for(project, language=lang),
        subsystems=subsystems_from_topics(outline.topics),
        see_also=topic_wiki_links(outline.topics),
        citations=cites,
        term_tips=_generic_term_tips(),
    )

    module_docs = [
        fallback_module_doc(
            name,
            files,
            language=lang,
            graph=graph,
        )
        for name, files in sorted(modules_map.items(), key=lambda x: (-len(x[1]), x[0]))
    ]

    files_by_path = {f.path.replace("\\", "/"): f for f in project.files}
    topic_docs = []
    for topic in outline.topics:
        key_files = [
            files_by_path[p.replace("\\", "/")]
            for p in topic.key_files
            if p.replace("\\", "/") in files_by_path
        ]
        topic_docs.append(
            fallback_topic_doc(topic, key_files, language=lang, graph=graph)
        )

    components = [
        Component(
            name=doc.title or doc.name,
            role=doc.purpose,
            purpose=doc.purpose,
            files=[fd.path for fd in doc.files[:6]],
            key_types=list(getattr(doc, "key_types", None) or [])[:4],
        )
        for doc in topic_docs
        if doc.section != "getting-started"
    ][:12]
    if not components:
        components = [
            Component(
                name=m.name,
                role=m.purpose,
                purpose=m.purpose,
                files=[fd.path for fd in m.files[:6]],
            )
            for m in module_docs[:12]
        ]
    architecture = ArchitectureDiagram(
        architecture_type="system-topics",
        description=t(
            "The repo is split by the systems that actually run a call. Data enters at "
            "the entrypoints, then through this repo's own packages and seams. Use the "
            "diagram to see coupling; the left nav is conceptual, not a crate tree.",
            "仓库按一次调用真正经过的系统切页。请求从入口进来，经过本仓库自己的核心包和 seam。"
            "结构图用来看耦合；左侧是概念导航，不是 crate 树。",
        ),
        components=components,
        mermaid_component=graph.to_mermaid()
        or runtime_mermaid_for(entry_files=entry_files, topics=outline.topics),
        data_flow=t(
            "Entrypoints → core systems → dependents (see architecture and the learning path).",
            "入口文件 → 核心系统 → 依赖方（见架构概览与学习路径）。",
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
        topics=topic_docs,
        architecture=architecture,
        reading_guide=reading_guide,
        outline=outline,
    )


def _concept_evidence_prompt(concept: ConceptDraft) -> str:
    rows: list[str] = []
    for ref in concept.source_references[:8]:
        loc = _format_ref(ref)
        symbol = (ref.symbol or "").strip()
        pill = f"{loc} {symbol}".strip() if symbol else loc
        if pill:
            rows.append(f"- `{pill}`")
    return "\n".join(rows) or "(none — do not invent paths)"


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


def _what_body(concept: ConceptDraft, folded: str = "") -> str:
    """Handbook 'what it is' — description / why, not the path-step task."""
    parts: list[str] = []
    body = _clean_concept_body(concept.description)
    why = (concept.why_learn or "").strip()
    if why and _is_html_dump(why):
        why = ""
    if body and why and body == why:
        why = ""
    if body:
        parts.append(body)
    if why and why not in body:
        parts.append(why)
    if folded and not any(folded in p or p in folded for p in parts):
        parts.append(folded)
    if parts:
        return "\n\n".join(parts)
    return first_principles(concept, "")


def _position_body(concept: ConceptDraft, wiki: Wiki) -> str:
    parts = [handbook_position(concept.slug, concept.title)]
    links: list[str] = []
    if wiki.get_page("index"):
        links.append(t("[Overview](index)", "[概述](index)"))
    if wiki.get_page("architecture"):
        links.append(t("[Architecture](architecture)", "[架构概览](architecture)"))
    module_links = 0
    for page in wiki.pages:
        if not (page.id.startswith("modules/") and page.title):
            continue
        links.append(f"[{page.title}]({page.id})")
        module_links += 1
        if module_links >= 3:
            break
    if links:
        parts.append(t("See also: ", "相关页面：") + " · ".join(links))
    return "\n\n".join(parts)


def _type_role_lines(prose: str, concept: ConceptDraft) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for match in re.finditer(r"`([A-Z][A-Za-z0-9_]+)`", prose or ""):
        name = match.group(1)
        if name not in seen:
            seen.add(name)
            names.append(name)
    for ref in concept.source_references:
        symbol = (ref.symbol or "").strip()
        if symbol and symbol[0].isupper() and symbol in prose and symbol not in seen:
            seen.add(symbol)
            names.append(symbol)
    if not names:
        return []
    lines = [t("## Key types\n", "## 关键类型\n")]
    for name in names[:8]:
        lines.append(
            t(
                f"- **`{name}`** — on the call path above",
                f"- **`{name}`** — 出现在上文调用链中",
            )
        )
    lines.append("")
    return lines


def _fold_overview_architecture(wiki: Wiki, concept: ConceptDraft) -> str:
    if concept.slug not in {"project-goal"}:
        return ""
    chunks: list[str] = []
    for page_id in ("index", "architecture"):
        page = wiki.get_page(page_id)
        if page is None:
            continue
        excerpt = wiki_prose_excerpt(page.content, max_chars=280)
        if excerpt:
            chunks.append(excerpt)
    return " ".join(chunks[:2]).strip()


def _append_term_tips_md(lines: list[str], tips: list[TermTip]) -> None:
    if not tips:
        return
    lines.append(t("## Terms\n", "## 术语\n"))
    for tip in tips:
        if tip.tip:
            lines.append(f"> **{tip.term}** — {tip.tip}")
        else:
            lines.append(f"> **{tip.term}**")
    lines.append("")


def append_concept_pages(
    wiki: Wiki,
    concepts: list[ConceptDraft],
    file_texts: dict[str, str] | None = None,
) -> Wiki:
    """Attach concept wiki pages as DeepWiki handbook entries.

    Learning-path homework (step_task / 本步要你干什么 / 过关) stays on the
    path UI. Concept pages here are what/where/flow, with source chips as
    evidence — not a first-principles worksheet.
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
        if is_generic_web_slug(c.slug):
            continue
        page_id = f"concepts/{c.slug}"
        folded = _fold_overview_architecture(wiki, c)
        what = _what_body(c, folded)
        flow = flow_narrative(c.slug, c.title)
        lines = [
            f"# {c.title}\n",
            f"> {handbook_lede(c.slug, c.title)}\n",
        ]
        chip_locs = [_format_ref(ref) for ref in c.source_references[:8]]
        chip_symbols = [(ref.symbol or "") for ref in c.source_references[:8]]
        chip_line = related_source_chip_line(chip_locs, symbols=chip_symbols)
        if chip_line:
            lines.append(f"{chip_line}\n")

        lines.append(t("## Overview\n", "## 概述\n"))
        lines.append(f"{what}\n")

        lines.append(t("## Architecture\n", "## 架构\n"))
        lines.append(f"{_position_body(c, wiki)}\n")

        if flow:
            lines.append(t("## Call path\n", "## 调用链\n"))
            if c.source_references:
                lines.append(f"{flow} `{_format_ref(c.source_references[0])}`\n")
            else:
                lines.append(f"{flow}\n")

        prose_for_types = "\n".join([what, flow])
        lines.extend(_type_role_lines(prose_for_types, c))

        not_this = _not_this_for(c)
        if not_this:
            lines.append(t("## What this is not\n", "## 不是什么\n"))
            for item in not_this:
                lines.append(f"- {item}")
            lines.append("")

        _append_term_tips_md(lines, _tips_for_concept(c))

        prereqs = [p for p in c.prerequisites if p in title_by_slug]
        if prereqs:
            lines.append(t("## Read first\n", "## 先读\n"))
            for p in prereqs:
                lines.append(f"- {link(p)}")
            lines.append("")

        unlocks = dependents.get(c.slug, [])
        if unlocks:
            lines.append(t("## Next\n", "## 接下来\n"))
            for d in unlocks[:8]:
                lines.append(f"- {link(d)}")
            lines.append("")

        content = "\n".join(lines)
        if file_texts:
            content = deepen_concept_markdown(content, c, file_texts)
        wiki.pages.append(
            WikiPage(
                id=page_id,
                title=c.title,
                content=content,
                parent_id="concepts",
                order=100 + i,
            )
        )
        concept_sidebar.children.append(SidebarItem(title=c.title, page_id=page_id))
    has_topics = any(p.id.startswith("topics/") for p in wiki.pages)
    if concept_sidebar.children:
        if has_topics:
            deep_title = structural_title("deep-dive", content_lang())
            placed = False
            for item in wiki.sidebar:
                if item.title == deep_title:
                    item.children.append(concept_sidebar)
                    placed = True
                    break
            if not placed:
                wiki.sidebar.append(concept_sidebar)
        else:
            wiki.sidebar.append(concept_sidebar)
    return wiki


_STEP_HEADING_RE = re.compile(
    r"^(##[ \t]+(?:Step|步骤|ステップ|단계)[ \t]+(\d+):)[ \t]+(.+?)$"
)
_STEP_TIME_SUFFIX_RE = re.compile(r"[ \t]+(\([^)]*\))\s*$")


def link_reading_guide_markdown(content: str, concepts: list[Any]) -> str:
    """Turn 步骤/Step headings into ``](concepts/slug)`` links (zh and en)."""
    if not content or not concepts:
        return content
    slug_by_title = {
        str(getattr(c, "title", "") or ""): str(getattr(c, "slug", "") or "")
        for c in concepts
        if getattr(c, "title", None) and getattr(c, "slug", None)
    }
    ordered = [c for c in concepts if getattr(c, "slug", None)]
    out: list[str] = []
    for line in content.split("\n"):
        if "](concepts/" in line:
            out.append(line)
            continue
        match = _STEP_HEADING_RE.match(line)
        if not match:
            out.append(line)
            continue
        prefix, number_s, rest = match.group(1), match.group(2), match.group(3)
        suffix = ""
        time_m = _STEP_TIME_SUFFIX_RE.search(rest)
        title = rest
        if time_m:
            title = rest[: time_m.start()].strip()
            suffix = rest[time_m.start() :]
        slug = slug_by_title.get(title)
        if not slug:
            try:
                idx = int(number_s) - 1
            except ValueError:
                idx = -1
            if 0 <= idx < len(ordered):
                slug = str(getattr(ordered[idx], "slug", "") or "")
        if slug:
            out.append(f"{prefix} [{title}](concepts/{slug}){suffix}")
        else:
            out.append(line)
    return "\n".join(out)


def link_reading_guide(wiki: Wiki, concepts: list[ConceptDraft]) -> Wiki:
    """Turn Reading Guide step headings into links to their concept pages.

    The guide's steps are generated 1:1 from concepts, so leaving them as plain
    text forces the reader back to the sidebar to find the page being described.
    """
    if not concepts:
        return wiki
    for page in wiki.pages:
        if page.id != "reading-guide":
            continue
        page.content = link_reading_guide_markdown(page.content, concepts)
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
            impl = str(data.get("implementation_details") or "").strip()
            if impl and not _is_html_dump(impl):
                concept.implementation_notes = impl
            key_types = data.get("key_types") or []
            if isinstance(key_types, list):
                cleaned_types: list[dict[str, Any]] = []
                for item in key_types:
                    if not isinstance(item, dict) or not item.get("name"):
                        continue
                    path = str(item.get("path") or "").strip().replace("\\", "/")
                    if path and path not in {f.path.replace("\\", "/") for f in project.files}:
                        continue
                    try:
                        line = int(item.get("line") or 0)
                    except (TypeError, ValueError):
                        line = 0
                    cleaned_types.append(
                        {
                            "name": str(item["name"]).strip(),
                            "role": str(item.get("role") or "").strip(),
                            "path": path,
                            "line": line,
                        }
                    )
                if cleaned_types:
                    concept.key_type_roles = cleaned_types[:8]
            bounds = data.get("boundaries") or []
            if isinstance(bounds, list):
                concept.boundary_notes = [
                    str(item).strip() for item in bounds if str(item).strip()
                ][:5]
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
                "You write a short DeepWiki handbook entry for one concept in a codebase wiki. "
                "Be specific to THIS repository. No HTML. No file inventory. "
                "No homework headings (what this step asks, pass check, first principles worksheet). "
                "Handbook Chinese: state facts; keep identifiers English; "
                "never write 读完应能 / After reading you should / "
                "你负责 / 并签字 / 过关 / 北极星 / 缺了它哪条能力会断. "
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
                "Grounded evidence already bound for this concept "
                f"(cite only these paths, or omit the cite):\n"
                f"{_concept_evidence_prompt(concept)}\n\n"
                "Return JSON:\n"
                "{\n"
                '  "description": "2-4 handbook sentences: what it is, who uses it, where it sits — not a quiz prompt",\n'
                '  "why_learn": "one sentence the wiki can fold into the opening",\n'
                '  "not_this": ["common confusion 1"],\n'
                '  "term_tips": [{"term": "PageRank", "tip": "how THIS repo uses it"}],\n'
                '  "implementation_details": "2-4 sentences with `path:line Symbol` cites from the evidence list",\n'
                '  "key_types": [{"name": "Type", "role": "role on the call path", "path": "real/file.rs", "line": 12}],\n'
                '  "boundaries": ["what this is NOT, with a cite if possible"]\n'
                "}\n"
                "not_this: 1-3 bullets of what this concept is NOT. "
                "term_tips: 2-5 repo-specific jargon tips; keep `term` in English. "
                "implementation_details / key_types / boundaries deepen the handbook. "
                "Do not invent file paths or line numbers missing from the evidence list.\n\n"
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
        topics=llm_wd.topics or det_wd.topics,
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
        outline=llm_wd.outline or det_wd.outline,
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
    store = {
        (f.path or "").replace("\\", "/"): (f.content or f.preview or "")
        for f in project.files
        if (f.content or f.preview)
    }
    wiki = append_concept_pages(wiki, concepts, file_texts=store or None)
    wiki = link_reading_guide(wiki, concepts)
    topic_plan = []
    if wiki_data.outline and wiki_data.outline.topics:
        topic_plan = [item.model_dump() for item in wiki_data.outline.topics]
    elif wiki_data.topics:
        topic_plan = [
            {
                "id": t.name,
                "title": t.title,
                "section": t.section,
                "purpose": t.purpose,
            }
            for t in wiki_data.topics
        ]
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
        "topic_plan": topic_plan,
    }


def _sidebar_to_dict(item: Any) -> dict[str, Any]:
    return {
        "title": item.title,
        "page_id": item.page_id,
        "children": [_sidebar_to_dict(c) for c in (item.children or [])],
    }


def empty_wiki_payload(name: str = "") -> dict[str, Any]:
    return {"project_name": name, "pages": [], "sidebar": []}
