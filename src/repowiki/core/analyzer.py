"""orchestrates the multi-pass LLM analysis pipeline: outline → write → cite-check."""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Callable

from repowiki.core.cache import Cache, content_hash
from repowiki.core.cite_check import (
    CiteIndex,
    collect_invalid_paths,
    parse_citation_string,
    verify_module,
    verify_wiki_data,
)
from repowiki.core.context_pack import pack_key_files, pack_module_context
from repowiki.core.graph import DependencyGraph
from repowiki.core.models import (
    ArchitectureDiagram,
    Citation,
    Component,
    FileInfo,
    KeyType,
    ModuleDoc,
    ModuleOutline,
    ProjectContext,
    ProjectOverview,
    ReadingGuide,
    ReadingStep,
    TermTip,
    TopicDoc,
    WikiData,
    WikiOutline,
)
from repowiki.core.module_handbook import fallback_module_doc
from repowiki.core.modules import group_into_modules
from repowiki.core.outline import build_deterministic_outline, merge_outline
from repowiki.core.topics import (
    GROK_LOOP_SEQUENCE,
    codebase_structure_for,
    fallback_topic_doc,
    runtime_mermaid_for,
    sequence_tools_before_model,
    subsystems_from_topics,
    topic_wiki_links,
)
from repowiki.llm.client import LLMClient
from repowiki.llm.prompts import (
    build_architecture_prompt,
    build_citation_repair_prompt,
    build_module_prompt,
    build_outline_prompt,
    build_overview_prompt,
    build_reading_guide_prompt,
    extract_json,
)

logger = logging.getLogger(__name__)

# One repair call per deep module, and only when many cites failed.
_REPAIR_MIN_INVALID = 3
_MAX_REPAIRS = 3
# grok-study-scale outlines (~16 topics) truncated at 2048 and failed to parse.
OUTLINE_MAX_TOKENS = 8192


class Analyzer:
    """runs the full wiki generation pipeline."""

    def __init__(
        self,
        llm: LLMClient,
        cache: Cache,
        language: str = "en",
        concurrency: int = 5,
    ):
        self.llm = llm
        self.cache = cache
        self.language = language
        self._sem = asyncio.Semaphore(concurrency)

    def _llm_enabled(self) -> bool:
        """Skip network calls when the client has no key; test stubs without api_key still run."""
        return bool(getattr(self.llm, "api_key", "yes"))

    def _lang(self) -> str:
        code = (self.language or "en").strip().lower().replace("_", "-")
        primary = code.split("-", 1)[0]
        if primary in {"zh", "cn"}:
            return "zh"
        return "en"

    async def _complete_json(self, messages: list[dict], *, max_tokens: int = 4096) -> str:
        """Wiki JSON steps: ask the hub for a JSON object (DeepSeek / OpenAI compatible)."""
        return await self.llm.complete(
            messages,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
        )

    async def analyze(
        self,
        project: ProjectContext,
        on_progress: Callable[[str], None] | None = None,
    ) -> WikiData:
        """run the full analysis pipeline and return WikiData."""

        def progress(msg: str):
            if on_progress:
                on_progress(msg)

        progress("Preparing file context...")
        graph = DependencyGraph.build_from_project(project)
        modules_map = self._group_into_modules(project.files)
        key_files_text = pack_key_files(project)
        tree_hash = content_hash(project.file_tree + key_files_text)

        progress("Outlining wiki...")
        outline = await self._generate_outline(project, modules_map, graph, tree_hash)

        progress("Generating project overview...")
        overview = await self._generate_overview(
            project, key_files_text, tree_hash, outline, graph
        )

        progress(f"Writing {len(modules_map)} modules...")
        module_docs = await self._analyze_modules(
            modules_map, overview.one_liner, project, graph, outline, progress
        )

        topic_docs: list[TopicDoc] = []
        if outline.topics:
            progress(f"Writing {len(outline.topics)} topics...")
            topic_docs = await self._analyze_topics(
                outline, overview.one_liner, project, graph, progress
            )

        progress("Detecting architecture...")
        architecture = await self._generate_architecture(
            project, key_files_text, tree_hash, outline, graph
        )

        progress("Creating reading guide...")
        reading_guide = await self._generate_reading_guide(
            project, module_docs, tree_hash, outline=outline, graph=graph
        )

        progress("Verifying citations...")
        wiki = WikiData(
            overview=overview,
            modules=module_docs,
            topics=topic_docs,
            architecture=architecture,
            reading_guide=reading_guide,
            outline=outline,
        )
        wiki = await self._verify_citations(wiki, project, outline)

        progress("Done!")
        return wiki

    async def _generate_outline(
        self,
        project: ProjectContext,
        modules: dict[str, list[FileInfo]],
        graph: DependencyGraph,
        tree_hash: str,
    ) -> WikiOutline:
        base = build_deterministic_outline(
            project, modules, graph, language=self._lang()
        )
        cache_key = f"outline:v2:{self.language}:{tree_hash}"
        cached = await self.cache.get(cache_key)
        if cached:
            try:
                llm_outline = WikiOutline(**cached)
                return merge_outline(
                    base,
                    llm_outline,
                    known_modules=set(modules),
                    known_paths={f.path for f in project.files},
                )
            except Exception:
                pass

        if not self._llm_enabled():
            return base

        module_lines = []
        weights = graph.module_weights()
        for name, files in sorted(modules.items(), key=lambda kv: -weights.get(kv[0], 0.0)):
            module_lines.append(
                f"- {name}: {len(files)} files, PageRank weight {weights.get(name, 0.0):.4f}"
            )
        rankings = self._rankings_text(project, graph, limit=20)
        entries = []
        for f in project.files:
            if f.is_entrypoint:
                entries.append(f"- {f.path} [entrypoint]")
            elif f.is_config:
                entries.append(f"- {f.path} [config]")

        messages = build_outline_prompt(
            project.file_tree,
            "\n".join(module_lines),
            rankings,
            "\n".join(entries) or "(none)",
            self.language,
        )
        raw = await self._complete_json(messages, max_tokens=OUTLINE_MAX_TOKENS)
        data = extract_json(raw)
        if not data or not isinstance(data, dict):
            logger.warning(
                "Failed to parse outline JSON, using deterministic outline; raw[:400]=%r",
                (raw or "")[:400],
            )
            return base

        filtered = {k: v for k, v in data.items() if k in WikiOutline.model_fields}
        try:
            llm_outline = WikiOutline(**filtered)
        except Exception:
            logger.warning(
                "Outline JSON failed validation, using deterministic outline; raw[:400]=%r",
                (raw or "")[:400],
            )
            return base

        merged = merge_outline(
            base,
            llm_outline,
            known_modules=set(modules),
            known_paths={f.path for f in project.files},
        )
        if llm_outline.topics or llm_outline.overview_focus:
            await self.cache.put(cache_key, llm_outline.model_dump())
        return merged

    async def _generate_overview(
        self,
        project: ProjectContext,
        key_files: str,
        tree_hash: str,
        outline: WikiOutline | None = None,
        graph: DependencyGraph | None = None,
    ) -> ProjectOverview:
        cache_key = f"overview:v3:{self.language}:{tree_hash}"
        cached = await self.cache.get(cache_key)
        if cached:
            try:
                return ProjectOverview(**cached)
            except Exception:
                pass

        fallback = self._fallback_overview(project, outline, graph)
        if not self._llm_enabled():
            return fallback

        emphasized = ""
        focus = ""
        topic_titles: list[str] = []
        if outline:
            focus = outline.overview_focus
            emphasized = ", ".join(outline.emphasized_pages[:12])
            topic_titles = [
                t.title or t.id
                for t in outline.topics
                if t.section != "getting-started" and t.id != "getting-started"
            ]
        messages = build_overview_prompt(
            project.file_tree,
            key_files,
            self.language,
            outline_focus=focus,
            emphasized=emphasized,
            topic_titles=topic_titles,
        )
        raw = await self._complete_json(messages, max_tokens=4096)
        data = extract_json(raw)
        if not data or not isinstance(data, dict):
            logger.warning("Failed to parse overview JSON, using defaults")
            return fallback

        overview = _coerce_model(data, ProjectOverview, name=project.name)
        if not overview.name:
            overview.name = project.name
        overview = self._fill_overview_gaps(overview, project, outline, graph)
        if (
            overview.one_liner
            or overview.description
            or overview.what_it_is
            or overview.subsystems
        ):
            await self.cache.put(cache_key, overview.model_dump())
        return overview

    def _group_into_modules(self, files: list[FileInfo]) -> dict[str, list[FileInfo]]:
        """group files into documentable modules (see repowiki.core.modules)."""
        return group_into_modules(files)

    async def _analyze_modules(
        self,
        modules: dict[str, list[FileInfo]],
        project_summary: str,
        project: ProjectContext,
        graph: DependencyGraph,
        outline: WikiOutline,
        progress: Callable[[str], None],
    ) -> list[ModuleDoc]:
        tasks = []
        for name, files in modules.items():
            tasks.append(
                self._analyze_one_module(
                    name, files, project_summary, project, graph, outline
                )
            )

        results = []
        for i, coro in enumerate(asyncio.as_completed(tasks)):
            doc = await coro
            if doc:
                results.append(doc)
            progress(f"Wrote module {i + 1}/{len(tasks)}")

        priority = {m.name: m.priority for m in outline.modules}
        results.sort(key=lambda m: (-priority.get(m.name, 0), -len(m.files), m.name))
        return results

    async def _analyze_topics(
        self,
        outline: WikiOutline,
        project_summary: str,
        project: ProjectContext,
        graph: DependencyGraph,
        progress: Callable[[str], None],
    ) -> list[TopicDoc]:
        files_by_path = {f.path.replace("\\", "/"): f for f in project.files}
        tasks = []
        for topic in outline.topics:
            key_files = [
                files_by_path[p.replace("\\", "/")]
                for p in topic.key_files
                if p.replace("\\", "/") in files_by_path
            ]
            if not key_files and topic.section != "getting-started":
                continue
            tasks.append(
                self._analyze_one_topic(
                    topic, key_files, project_summary, project, graph
                )
            )
        results: list[TopicDoc] = []
        for i, coro in enumerate(asyncio.as_completed(tasks)):
            doc = await coro
            if doc:
                results.append(doc)
            progress(f"Wrote topic {i + 1}/{len(tasks)}")
        order = {t.id: i for i, t in enumerate(outline.topics)}
        results.sort(key=lambda t: order.get(t.name, 100))
        return results

    async def _analyze_one_topic(
        self,
        topic,
        files: list[FileInfo],
        project_summary: str,
        project: ProjectContext,
        graph: DependencyGraph,
    ) -> TopicDoc | None:
        async with self._sem:
            fallback = fallback_topic_doc(
                topic, files, language=self._lang(), graph=graph
            )
            if not files:
                return _ensure_topic_flow(fallback, topic, fallback)
            plan = ModuleOutline(
                name=topic.title or topic.id,
                depth=topic.depth if topic.depth in {"deep", "standard", "brief"} else "standard",
                key_files=list(topic.key_files),
                key_symbols=list(topic.key_symbols),
                notes=topic.purpose,
            )
            files_context = pack_module_context(
                files, depth=plan.depth, outline=plan, graph=graph, project=project
            )
            content_parts = [(f.content or f.preview or "") for f in files]
            cache_key = (
                f"topic:v6:{self.language}:{plan.depth}:{topic.id}:"
                f"{content_hash(''.join(content_parts))}"
            )
            cached = await self.cache.get(cache_key)
            if cached:
                try:
                    return _ensure_topic_flow(TopicDoc(**cached), topic, fallback)
                except Exception:
                    pass
            if not self._llm_enabled():
                return _ensure_topic_flow(fallback, topic, fallback)
            messages = build_module_prompt(
                topic.title or topic.id,
                files_context,
                project_summary,
                self.language,
                depth=plan.depth,
                outline_notes=topic.purpose,
                key_files=topic.key_files,
                key_symbols=topic.key_symbols,
                topic_id=topic.id,
            )
            raw = await self._complete_json(messages, max_tokens=4096)
            data = extract_json(raw)
            if not data or not isinstance(data, dict):
                logger.warning(
                    "Failed to parse topic '%s' JSON; raw[:400]=%r",
                    topic.id,
                    (raw or "")[:400],
                )
                return _ensure_topic_flow(fallback, topic, fallback)
            data.setdefault("name", topic.id)
            doc = _ensure_topic_flow(_coerce_topic(data, topic), topic, fallback)
            if doc.description or doc.implementation_details or doc.files or doc.call_chains:
                await self.cache.put(cache_key, doc.model_dump())
            return doc

    async def _analyze_one_module(
        self,
        name: str,
        files: list[FileInfo],
        project_summary: str,
        project: ProjectContext,
        graph: DependencyGraph,
        outline: WikiOutline,
    ) -> ModuleDoc | None:
        async with self._sem:
            plan = outline.module_for(name)
            depth = plan.depth if plan else "standard"
            files_context = pack_module_context(
                files, depth=depth, outline=plan, graph=graph, project=project
            )
            content_parts = [(f.content or f.preview or "") for f in files]
            cache_key = (
                f"module:v2:{self.language}:{depth}:{name}:"
                f"{content_hash(''.join(content_parts))}"
            )

            cached = await self.cache.get(cache_key)
            if cached:
                try:
                    return ModuleDoc(**cached)
                except Exception:
                    pass

            fallback = self._fallback_module_doc(name, files, plan, graph)
            if not self._llm_enabled():
                return fallback

            messages = build_module_prompt(
                name,
                files_context,
                project_summary,
                self.language,
                depth=depth,
                outline_notes=plan.notes if plan else "",
                key_files=plan.key_files if plan else None,
                key_symbols=plan.key_symbols if plan else None,
                sections=plan.sections if plan else None,
            )
            raw = await self._complete_json(messages, max_tokens=4096)
            data = extract_json(raw)
            if not data or not isinstance(data, dict):
                logger.warning("Failed to parse module '%s' JSON", name)
                return fallback

            data.setdefault("name", name)
            doc = _coerce_module(data, name)
            if doc.description or doc.implementation_details or (
                doc.files and any(f.key_symbols for f in doc.files)
            ):
                await self.cache.put(cache_key, doc.model_dump())
            return doc

    async def _generate_architecture(
        self,
        project: ProjectContext,
        key_files: str,
        tree_hash: str,
        outline: WikiOutline | None = None,
        graph: DependencyGraph | None = None,
    ) -> ArchitectureDiagram:
        cache_key = f"arch:v3:{self.language}:{tree_hash}"
        cached = await self.cache.get(cache_key)
        if cached:
            try:
                return ArchitectureDiagram(**cached)
            except Exception:
                pass

        fallback = self._fallback_architecture(project, outline, graph)
        if not self._llm_enabled():
            return fallback

        focus = outline.architecture_focus if outline else ""
        core = ""
        if outline:
            core = ", ".join(
                (t.title or t.id)
                for t in outline.topics
                if t.section != "getting-started"
            ) or ", ".join(m.name for m in outline.modules if m.depth == "deep")
        messages = build_architecture_prompt(
            project.file_tree,
            key_files,
            self.language,
            outline_focus=focus,
            core_modules=core,
        )
        raw = await self._complete_json(messages, max_tokens=4096)
        data = extract_json(raw)
        if not data or not isinstance(data, dict):
            logger.warning(
                "Failed to parse architecture JSON; raw[:400]=%r",
                (raw or "")[:400],
            )
            data = None

        arch = _coerce_model(data, ArchitectureDiagram) if data else ArchitectureDiagram()
        if not (arch.mermaid_component or "").strip():
            logger.warning("Architecture mermaid empty, retrying once")
            raw = await self._complete_json(messages, max_tokens=4096)
            data2 = extract_json(raw)
            if data2 and isinstance(data2, dict):
                retry = _coerce_model(data2, ArchitectureDiagram)
                if (retry.mermaid_component or "").strip() or not data:
                    arch = retry
            elif not data:
                return fallback

        arch = self._fill_architecture_gaps(arch, project, outline, graph)
        if arch.architecture_type or arch.description or arch.mermaid_component:
            await self.cache.put(cache_key, arch.model_dump())
        return arch

    async def _generate_reading_guide(
        self,
        project: ProjectContext,
        module_docs: list[ModuleDoc],
        tree_hash: str,
        outline: WikiOutline | None = None,
        graph: DependencyGraph | None = None,
    ) -> ReadingGuide:
        # PageRank over the import graph decides which files matter; scan order
        # only fills the tail when the graph is smaller than the display limit.
        graph = graph or DependencyGraph.build_from_project(project)
        rankings = self._rankings_text(project, graph, limit=20)

        module_parts = []
        for m in module_docs:
            module_parts.append(f"- **{m.name}**: {m.purpose}")
        module_summaries = "\n".join(module_parts)
        reading_order = ""
        if outline and outline.reading_order:
            reading_order = "\n".join(
                f"{i}. {n}" for i, n in enumerate(outline.reading_order, 1)
            )

        # key on the actual prompt inputs so an import-only edit that reshuffles
        # the ranking also invalidates the cached guide
        cache_key = (
            f"guide:{self.language}:{tree_hash}:"
            f"{content_hash(rankings + module_summaries + reading_order)}"
        )
        cached = await self.cache.get(cache_key)
        if cached:
            try:
                return ReadingGuide(**cached)
            except Exception:
                pass

        fallback = self._fallback_reading_guide(project, graph, outline)
        if not self._llm_enabled():
            return fallback

        messages = build_reading_guide_prompt(
            rankings,
            module_summaries,
            self.language,
            reading_order=reading_order,
        )
        raw = await self._complete_json(messages, max_tokens=4096)
        data = extract_json(raw)
        if not data or not isinstance(data, dict):
            logger.warning("Failed to parse reading guide JSON")
            return fallback

        guide = _coerce_model(data, ReadingGuide)
        if guide.introduction or guide.steps:
            await self.cache.put(cache_key, guide.model_dump())
        return guide

    async def _verify_citations(
        self,
        wiki: WikiData,
        project: ProjectContext,
        outline: WikiOutline,
    ) -> WikiData:
        index = CiteIndex.from_project(project)
        invalid_by_module: dict[str, list[str]] = {}
        for mod in wiki.modules:
            bad = collect_invalid_paths(mod, index)
            if bad:
                invalid_by_module[mod.name] = bad

        wiki = verify_wiki_data(wiki, project)

        if not self._llm_enabled() or not invalid_by_module:
            return wiki

        repairs = 0
        valid_paths = sorted(index.paths)
        for i, mod in enumerate(wiki.modules):
            if repairs >= _MAX_REPAIRS:
                break
            plan = outline.module_for(mod.name)
            if not plan or plan.depth != "deep":
                continue
            bad = invalid_by_module.get(mod.name) or []
            if len(bad) < _REPAIR_MIN_INVALID:
                continue
            repaired = await self._repair_module(mod, bad, valid_paths)
            if repaired is None:
                continue
            if not (
                repaired.files
                or repaired.implementation_details
                or repaired.description
                or repaired.citations
            ):
                continue
            wiki.modules[i] = verify_module(repaired, index)
            repairs += 1
        return wiki

    async def _repair_module(
        self,
        mod: ModuleDoc,
        invalid_paths: list[str],
        valid_paths: list[str],
    ) -> ModuleDoc | None:
        async with self._sem:
            messages = build_citation_repair_prompt(
                mod.name,
                mod.model_dump_json(),
                invalid_paths,
                valid_paths,
                self.language,
            )
            raw = await self._complete_json(messages, max_tokens=2048)
            data = extract_json(raw)
            if not data or not isinstance(data, dict):
                return None
            data.setdefault("name", mod.name)
            try:
                return _coerce_module(data, mod.name)
            except Exception:
                return None

    def _rankings_text(
        self,
        project: ProjectContext,
        graph: DependencyGraph,
        limit: int = 20,
    ) -> str:
        ranked = graph.rank_files()
        by_path = {f.path: f for f in project.files}
        ranked_paths = [path for path, _ in ranked[:limit]]
        seen = set(ranked_paths)
        for f in project.files:
            if len(ranked_paths) >= limit:
                break
            if f.path not in seen:
                ranked_paths.append(f.path)
                seen.add(f.path)

        lines = []
        for i, path in enumerate(ranked_paths, 1):
            f = by_path[path]
            tag = ""
            if f.is_entrypoint:
                tag = " [entrypoint]"
            elif f.is_config:
                tag = " [config]"
            lines.append(f"{i}. {path}{tag} ({f.lines} lines)")
        return "\n".join(lines)

    def _fallback_overview(
        self,
        project: ProjectContext,
        outline: WikiOutline | None,
        graph: DependencyGraph | None = None,
    ) -> ProjectOverview:
        return self._fill_overview_gaps(
            ProjectOverview(
                name=project.name,
                term_tips=_generic_term_tips(self._lang()),
            ),
            project,
            outline,
            graph,
        )

    def _fill_overview_gaps(
        self,
        overview: ProjectOverview,
        project: ProjectContext,
        outline: WikiOutline | None,
        graph: DependencyGraph | None,
    ) -> ProjectOverview:
        zh = self._lang() == "zh"
        readme = next(
            (f for f in project.files if f.path.lower() in {"readme.md", "readme"}),
            None,
        )
        entries = [f for f in project.files if f.is_entrypoint]
        if not overview.citations:
            cites: list[Citation] = []
            if readme:
                cites.append(Citation(path=readme.path, start_line=1, note="README"))
            for f in entries:
                cites.append(Citation(path=f.path, note="entrypoint"))
            overview.citations = cites
        if not overview.document_scope:
            if zh:
                overview.document_scope = (
                    f"这篇文档讲 {project.name} 是什么、一次真实调用怎么走、仓库怎么拆。"
                    "读完你应能不靠目录讲清目标与边界，并指出链路上的关键类型。"
                )
            else:
                overview.document_scope = (
                    f"This page covers what {project.name} is, how one real call runs, "
                    "and how the repo is split. After reading you should name the "
                    "goal and the types on that path without leaning on the folder tree."
                )
        if not overview.what_it_is:
            overview.what_it_is = _fallback_what_it_is(project, outline, zh)
        if not overview.description:
            overview.description = (
                (readme.content or readme.preview or "").strip()[:800]
                if readme and (readme.content or readme.preview)
                else (outline.overview_focus if outline else "")
            )
        if not overview.runtime_flow:
            if outline and outline.overview_focus:
                overview.runtime_flow = outline.overview_focus
            elif zh:
                overview.runtime_flow = (
                    "请求从入口进程进来，经过枢纽包上的类型，再交到依赖方。"
                    "下面的结构图按这条链路画，而不是按 crate 目录。"
                )
            else:
                overview.runtime_flow = (
                    "Work enters at the process entrypoint, moves through hub types, "
                    "then out to dependents. The diagram follows that call, not the crate tree."
                )
        if not overview.mermaid_component:
            overview.mermaid_component = (graph.to_mermaid() if graph else "") or ""
        if not overview.mermaid_component:
            overview.mermaid_component = runtime_mermaid_for(
                entry_files=[f.path for f in project.files if f.is_entrypoint],
                topics=(outline.topics if outline else None),
            )
        if not overview.codebase_structure:
            overview.codebase_structure = codebase_structure_for(
                project, language=self._lang()
            )
        if overview.subsystems:
            for sub in overview.subsystems:
                name = sub.name or ""
                if "上下文装配" in name and "Agent Loop" in name:
                    sub.name = "Agent Loop"
                sub.key_types = [
                    kt
                    for kt in (sub.key_types or [])
                    if (kt.path or "").strip()
                    and "/" not in (kt.name or "")
                    and not str(kt.name or "").endswith(".rs")
                ]
            overview.subsystems = [
                s for s in overview.subsystems if s.key_types or s.files
            ]
        if not overview.subsystems and outline:
            overview.subsystems = subsystems_from_topics(outline.topics)
        if not overview.see_also and outline:
            overview.see_also = topic_wiki_links(outline.topics)
        if overview.tech_stack:
            from repowiki.core.wiki_builder import filter_tech_stack

            overview.tech_stack = filter_tech_stack(overview.tech_stack, project)
        if not overview.term_tips:
            overview.term_tips = _generic_term_tips(self._lang())
        return overview

    def _fallback_architecture(
        self,
        project: ProjectContext,
        outline: WikiOutline | None,
        graph: DependencyGraph | None = None,
    ) -> ArchitectureDiagram:
        return self._fill_architecture_gaps(
            ArchitectureDiagram(
                architecture_type="codebase-modules",
                term_tips=_generic_term_tips(self._lang()),
            ),
            project,
            outline,
            graph,
        )

    def _fill_architecture_gaps(
        self,
        arch: ArchitectureDiagram,
        project: ProjectContext,
        outline: WikiOutline | None,
        graph: DependencyGraph | None,
    ) -> ArchitectureDiagram:
        zh = self._lang() == "zh"
        if not arch.components and outline and outline.topics:
            for item in outline.topics:
                if item.section == "getting-started":
                    continue
                types = [
                    KeyType(
                        name=symbol,
                        role="",
                        path=(item.key_files[0] if item.key_files else ""),
                    )
                    for symbol in (item.key_symbols or [])[:4]
                ]
                arch.components.append(
                    Component(
                        name=item.title or item.id,
                        role=item.purpose,
                        purpose=item.purpose,
                        files=list(item.key_files[:6]),
                        key_types=types,
                    )
                )
        elif not arch.components and outline:
            for item in outline.modules[:12]:
                arch.components.append(
                    Component(name=item.name, files=list(item.key_files[:6]))
                )
        for comp in arch.components:
            if not comp.role:
                comp.role = comp.purpose
            if "上下文装配" in (comp.name or "") and "Agent Loop" in (comp.name or ""):
                comp.name = "Agent Loop"
            comp.key_types = [
                kt
                for kt in (comp.key_types or [])
                if (kt.path or "").strip()
                and "/" not in (kt.name or "")
                and not str(kt.name or "").endswith(".rs")
            ]
        if arch.description:
            arch.description = arch.description.replace("AgentLoop", "start_turn")
            arch.description = arch.description.replace(
                "Agent Loop 与上下文装配", "Agent Loop"
            )
        has_loop = bool(
            outline
            and any(
                (t.id or t.name) == "agent-loop"
                for t in outline.topics
            )
        )
        seq = (arch.mermaid_sequence or "").strip()
        if has_loop and (not seq or sequence_tools_before_model(seq)):
            arch.mermaid_sequence = GROK_LOOP_SEQUENCE
        if not arch.description:
            if zh:
                arch.description = (
                    "仓库按一次调用真正经过的系统切页，而不是按目录罗列。"
                    "请求从入口进来，经过运行时、工具层和界面。"
                    "结构图用来看耦合；类型在链路上是角色，不是文件清单。"
                )
            else:
                focus = (outline.architecture_focus if outline else "").strip()
                if "Heaviest modules by PageRank" in focus:
                    focus = ""
                arch.description = focus or (
                    "The repo is split by the systems that actually run a call. "
                    "Work enters at the entrypoints, then through runtime, tools, and UI. "
                    "Types are roles on that path, not a file inventory."
                )
        if not arch.mermaid_component:
            arch.mermaid_component = (graph.to_mermaid() if graph else "") or ""
        if not arch.mermaid_component:
            arch.mermaid_component = runtime_mermaid_for(
                entry_files=[f.path for f in project.files if f.is_entrypoint],
                topics=(outline.topics if outline else None),
            )
        if not arch.term_tips:
            arch.term_tips = _generic_term_tips(self._lang())
        return arch

    def _fallback_reading_guide(
        self,
        project: ProjectContext,
        graph: DependencyGraph,
        outline: WikiOutline | None,
    ) -> ReadingGuide:
        steps: list[ReadingStep] = []
        if outline:
            for i, name in enumerate(outline.reading_order[:10], 1):
                plan = outline.module_for(name)
                files = list(plan.key_files[:4]) if plan else []
                steps.append(
                    ReadingStep(
                        order=i,
                        title=name,
                        files=files,
                        explanation=plan.notes if plan else "",
                        time_estimate="10 min",
                    )
                )
        if not steps:
            ranked = [p for p, _ in graph.rank_files()[:8]]
            for i, path in enumerate(ranked, 1):
                steps.append(ReadingStep(order=i, title=path, files=[path]))
        return ReadingGuide(steps=steps)

    def _fallback_module_doc(
        self,
        name: str,
        files: list[FileInfo],
        plan: ModuleOutline | None,
        graph: DependencyGraph | None = None,
    ) -> ModuleDoc:
        return fallback_module_doc(
            name,
            files,
            language=self._lang(),
            graph=graph,
            notes=(plan.notes if plan else "") or "",
        )


def _ensure_topic_flow(doc: TopicDoc, topic, fallback: TopicDoc) -> TopicDoc:
    """DeepWiki topic pages need a call flow (steps and/or mermaid)."""
    if getattr(topic, "section", "") == "getting-started" or getattr(topic, "id", "") == "getting-started":
        return doc
    has_steps = any(getattr(c, "steps", None) for c in (doc.call_chains or []))
    if not has_steps and fallback.call_chains:
        doc.call_chains = list(fallback.call_chains)
        has_steps = any(getattr(c, "steps", None) for c in doc.call_chains)
    if not (doc.mermaid or "").strip():
        fb = (getattr(fallback, "mermaid", "") or "").strip()
        if fb:
            doc.mermaid = fb
        elif getattr(topic, "depth", "") == "deep" or not has_steps:
            doc.mermaid = runtime_mermaid_for(
                entry_files=list(getattr(topic, "key_files", None) or [])[:1],
                topics=[topic],
            )
    return doc


def _fallback_what_it_is(
    project: ProjectContext, outline: WikiOutline | None, zh: bool
) -> list[str]:
    items: list[str] = []
    readme = next(
        (f for f in project.files if f.path.lower() in {"readme.md", "readme"}),
        None,
    )
    if readme:
        if zh:
            items.append(f"仓库目标与边界写在 README，而不是目录名。 `{readme.path}:1`")
        else:
            items.append(f"The goal lives in the README, not the folder names. `{readme.path}:1`")
    for f in project.files:
        if not f.is_entrypoint:
            continue
        if zh:
            items.append(f"进程从 `{f.path}:1` 启动，一次调用从这里进图。")
        else:
            items.append(f"The process starts at `{f.path}:1`; one call enters the graph here.")
        if len(items) >= 4:
            break
    if outline:
        for topic in outline.topics:
            if topic.section == "getting-started" or not topic.key_files:
                continue
            path = topic.key_files[0]
            cite = path if re.search(r":\d+", path) else f"{path}:1"
            title = topic.title or topic.id
            if zh:
                items.append(f"「{title}」接住链路上的一段工作，证据在 `{cite}`。")
            else:
                items.append(f"{title} owns one stretch of the call path; see `{cite}`.")
            if len(items) >= 6:
                break
    return items[:6]


def _generic_term_tips(language: str) -> list[TermTip]:
    if language == "zh":
        return [
            TermTip(
                term="PageRank",
                tip="按 import 图给文件打重要性分，用来决定哪些模块值得写深，而不是用来罗列文件。",
            ),
            TermTip(
                term="crate",
                tip="Rust/Cargo 的包单位。crate 名保持 Cargo.toml 里的英文原文，不要音译。",
            ),
            TermTip(
                term="entrypoint",
                tip="进程入口（main / bin / CLI）。先读入口才能看清其余模块是怎么被串起来的。",
            ),
        ]
    return [
        TermTip(
            term="PageRank",
            tip="Ranks files by import centrality so the wiki can write deeper pages for hubs, not dump a directory listing.",
        ),
        TermTip(
            term="crate",
            tip="A Rust/Cargo package. Keep the crate name as it appears in Cargo.toml.",
        ),
        TermTip(
            term="entrypoint",
            tip="A process start file (main, bin, CLI). Read these first to see how the rest of the graph is wired.",
        ),
    ]


def _coerce_model(data: dict, model_cls, **defaults):
    filtered = {k: v for k, v in data.items() if k in model_cls.model_fields}
    if "term_tips" in model_cls.model_fields:
        filtered["term_tips"] = _coerce_term_tips(filtered.get("term_tips"))
    if "citations" in model_cls.model_fields and "citations" in data:
        filtered["citations"] = _coerce_citations(filtered.get("citations"))
    if "what_it_is" in model_cls.model_fields:
        filtered["what_it_is"] = _coerce_what_it_is(filtered.get("what_it_is"))
    if "codebase_structure" in model_cls.model_fields:
        filtered["codebase_structure"] = _coerce_codebase_structure(
            filtered.get("codebase_structure")
        )
    if "subsystems" in model_cls.model_fields:
        filtered["subsystems"] = _coerce_subsystems(filtered.get("subsystems"))
    if "key_types" in model_cls.model_fields:
        filtered["key_types"] = _coerce_key_types(filtered.get("key_types"))
    if "components" in model_cls.model_fields:
        filtered["components"] = _coerce_components(filtered.get("components"))
    if "see_also" in model_cls.model_fields:
        filtered["see_also"] = _coerce_strings(filtered.get("see_also"))
    if "mermaid_component" in model_cls.model_fields:
        filtered["mermaid_component"] = _coerce_mermaid(filtered.get("mermaid_component"))
    if "mermaid" in model_cls.model_fields:
        filtered["mermaid"] = _coerce_mermaid(filtered.get("mermaid"))
    for key, value in defaults.items():
        filtered.setdefault(key, value)
    try:
        return model_cls(**filtered)
    except Exception:
        return model_cls(**defaults)


def _coerce_module(data: dict, name: str) -> ModuleDoc:
    payload = dict(data)
    payload.setdefault("name", name)
    _coerce_handbook_fields(payload)
    filtered = {k: v for k, v in payload.items() if k in ModuleDoc.model_fields}
    try:
        return ModuleDoc(**filtered)
    except Exception:
        return ModuleDoc(name=name, purpose=str(payload.get("purpose") or ""))


def _coerce_topic(data: dict, topic) -> TopicDoc:
    payload = dict(data)
    payload.setdefault("name", topic.id)
    _coerce_handbook_fields(payload)
    filtered = {k: v for k, v in payload.items() if k in TopicDoc.model_fields}
    filtered["name"] = topic.id
    filtered["title"] = topic.title or str(filtered.get("title") or topic.id)
    filtered["section"] = topic.section or "deep-dive"
    if topic.purpose and not filtered.get("purpose"):
        filtered["purpose"] = topic.purpose
    if topic.purpose and not filtered.get("document_scope"):
        filtered["document_scope"] = topic.purpose
    try:
        return TopicDoc(**filtered)
    except Exception:
        return TopicDoc(
            name=topic.id,
            title=topic.title,
            section=topic.section,
            purpose=topic.purpose or str(payload.get("purpose") or ""),
        )


def _coerce_handbook_fields(payload: dict) -> None:
    payload["call_chains"] = _coerce_call_chains(payload.get("call_chains"))
    payload["edge_cases"] = _coerce_strings(payload.get("edge_cases"))
    payload["citations"] = _coerce_citations(payload.get("citations"))
    payload["term_tips"] = _coerce_term_tips(payload.get("term_tips"))
    payload["what_it_is"] = _coerce_what_it_is(payload.get("what_it_is"))
    payload["key_types"] = _coerce_key_types(payload.get("key_types"))
    payload["mermaid"] = _coerce_mermaid(payload.get("mermaid"))
    payload["see_also"] = _coerce_strings(payload.get("see_also"))


def _coerce_mermaid(raw) -> str:
    if not raw:
        return ""
    if isinstance(raw, list):
        return "\n".join(str(x) for x in raw if str(x).strip())
    return str(raw)


def _coerce_what_it_is(raw) -> list[str]:
    items = raw if isinstance(raw, list) else ([raw] if raw else [])
    out: list[str] = []
    for item in items:
        if isinstance(item, str) and item.strip():
            out.append(item.strip())
        elif isinstance(item, dict):
            text = str(
                item.get("text")
                or item.get("sentence")
                or item.get("characteristic")
                or ""
            ).strip()
            path = str(item.get("path") or "").strip()
            line = item.get("start_line") or item.get("line")
            cite = f"{path}:{line}" if path and line else path
            if text and cite and cite not in text:
                out.append(f"{text} `{cite}`")
            elif text:
                out.append(text)
            elif cite:
                out.append(f"`{cite}`")
    return out


def _coerce_codebase_structure(raw) -> list[dict]:
    if not raw:
        return []
    items = raw if isinstance(raw, list) else [raw]
    out: list[dict] = []
    for item in items:
        if isinstance(item, str) and item.strip():
            out.append({"name": item.strip(), "location": item.strip(), "purpose": ""})
        elif isinstance(item, dict):
            name = str(item.get("name") or "").strip()
            if not name:
                continue
            out.append(
                {
                    "name": name,
                    "location": str(item.get("location") or item.get("path") or ""),
                    "purpose": str(item.get("purpose") or item.get("role") or ""),
                }
            )
    return out


def _coerce_key_types(raw) -> list[dict]:
    if not raw:
        return []
    items = raw if isinstance(raw, list) else [raw]
    out: list[dict] = []
    for item in items:
        if isinstance(item, str):
            continue
        if not isinstance(item, dict):
            continue
        name = str(
            item.get("name") or item.get("type") or item.get("symbol") or ""
        ).strip()
        path = str(item.get("path") or item.get("file") or "").strip()
        if not name or not path:
            continue
        try:
            line = int(item.get("line") or item.get("start_line") or 0)
        except (TypeError, ValueError):
            line = 0
        loc = path.split()[0]
        match = re.search(r":(\d+)(?:-\d+)?$", loc)
        if match:
            if not line:
                line = int(match.group(1))
            path = loc[: match.start()]
        out.append(
            {
                "name": name,
                "role": str(item.get("role") or item.get("purpose") or ""),
                "path": path,
                "line": line,
            }
        )
    return out


def _coerce_subsystems(raw) -> list[dict]:
    if not raw:
        return []
    items = raw if isinstance(raw, list) else [raw]
    out: list[dict] = []
    for item in items:
        if isinstance(item, str) and item.strip():
            out.append(
                {"name": item.strip(), "role": "", "key_types": [], "files": []}
            )
        elif isinstance(item, dict):
            name = str(item.get("name") or item.get("title") or "").strip()
            if not name:
                continue
            out.append(
                {
                    "name": name,
                    "role": str(item.get("role") or item.get("purpose") or ""),
                    "key_types": _coerce_key_types(item.get("key_types")),
                    "files": _coerce_strings(item.get("files")),
                    "mermaid": _coerce_mermaid(item.get("mermaid")),
                }
            )
    return out


def _coerce_components(raw) -> list[dict]:
    if not raw:
        return []
    items = raw if isinstance(raw, list) else [raw]
    out: list[dict] = []
    for item in items:
        if isinstance(item, str) and item.strip():
            out.append({"name": item.strip(), "purpose": "", "files": []})
        elif isinstance(item, dict):
            name = str(item.get("name") or "").strip()
            if not name:
                continue
            role = str(item.get("role") or item.get("purpose") or "")
            out.append(
                {
                    "name": name,
                    "role": role,
                    "purpose": str(item.get("purpose") or role),
                    "files": _coerce_strings(item.get("files")),
                    "key_types": _coerce_key_types(item.get("key_types")),
                }
            )
    return out


def _coerce_call_chains(raw) -> list[dict]:
    if not raw:
        return []
    out: list[dict] = []
    for item in raw:
        if isinstance(item, str):
            out.append({"name": item[:80], "description": item})
        elif isinstance(item, dict):
            chain = {
                "name": str(item.get("name") or "chain"),
                "description": str(item.get("description") or ""),
                "steps": _coerce_strings(item.get("steps")),
                "files": _coerce_strings(item.get("files")),
            }
            out.append(chain)
    return out


def _coerce_strings(raw) -> list[str]:
    if not raw:
        return []
    if isinstance(raw, str):
        return [raw]
    out: list[str] = []
    for item in raw:
        if isinstance(item, str):
            out.append(item)
        elif isinstance(item, dict):
            text = item.get("text") or item.get("description") or item.get("name") or ""
            if text:
                out.append(str(text))
    return out


def _coerce_citations(raw) -> list[dict]:
    if not raw:
        return []
    out: list[dict] = []
    for item in raw:
        if isinstance(item, str):
            parsed = parse_citation_string(item)
            if parsed:
                out.append(parsed.model_dump())
        elif isinstance(item, dict) and item.get("path"):
            out.append(item)
    return out


def _coerce_term_tips(raw) -> list[dict]:
    if not raw:
        return []
    out: list[dict] = []
    for item in raw:
        if isinstance(item, str) and item.strip():
            out.append({"term": item.strip(), "tip": ""})
        elif isinstance(item, dict):
            term = str(item.get("term") or item.get("name") or "").strip()
            if not term:
                continue
            out.append({"term": term, "tip": str(item.get("tip") or item.get("explanation") or "")})
    return out
