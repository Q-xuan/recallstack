"""orchestrates the multi-pass LLM analysis pipeline: outline → write → cite-check."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

from repowiki.core.cache import Cache, content_hash
from repowiki.core.cite_check import (
    CiteIndex,
    collect_invalid_paths,
    parse_citation_string,
    verify_module,
    verify_wiki_data,
)
from repowiki.core.context_pack import harvest_symbols, pack_key_files, pack_module_context
from repowiki.core.graph import DependencyGraph
from repowiki.core.models import (
    ArchitectureDiagram,
    Citation,
    Component,
    FileDoc,
    FileInfo,
    ModuleDoc,
    ModuleOutline,
    ProjectContext,
    ProjectOverview,
    ReadingGuide,
    ReadingStep,
    TermTip,
    WikiData,
    WikiOutline,
)
from repowiki.core.modules import group_into_modules
from repowiki.core.outline import build_deterministic_outline, merge_outline
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
            project, key_files_text, tree_hash, outline
        )

        progress(f"Writing {len(modules_map)} modules...")
        module_docs = await self._analyze_modules(
            modules_map, overview.one_liner, project, graph, outline, progress
        )

        progress("Detecting architecture...")
        architecture = await self._generate_architecture(
            project, key_files_text, tree_hash, outline
        )

        progress("Creating reading guide...")
        reading_guide = await self._generate_reading_guide(
            project, module_docs, tree_hash, outline=outline, graph=graph
        )

        progress("Verifying citations...")
        wiki = WikiData(
            overview=overview,
            modules=module_docs,
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
        base = build_deterministic_outline(project, modules, graph)
        cache_key = f"outline:{self.language}:{tree_hash}"
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
        raw = await self._complete_json(messages, max_tokens=2048)
        data = extract_json(raw)
        if not data or not isinstance(data, dict):
            logger.warning("Failed to parse outline JSON, using deterministic outline")
            return base

        filtered = {k: v for k, v in data.items() if k in WikiOutline.model_fields}
        try:
            llm_outline = WikiOutline(**filtered)
        except Exception:
            logger.warning("Outline JSON failed validation, using deterministic outline")
            return base

        merged = merge_outline(
            base,
            llm_outline,
            known_modules=set(modules),
            known_paths={f.path for f in project.files},
        )
        if llm_outline.modules or llm_outline.overview_focus:
            await self.cache.put(cache_key, llm_outline.model_dump())
        return merged

    async def _generate_overview(
        self,
        project: ProjectContext,
        key_files: str,
        tree_hash: str,
        outline: WikiOutline | None = None,
    ) -> ProjectOverview:
        cache_key = f"overview:{self.language}:{tree_hash}"
        cached = await self.cache.get(cache_key)
        if cached:
            try:
                return ProjectOverview(**cached)
            except Exception:
                pass

        fallback = self._fallback_overview(project, outline)
        if not self._llm_enabled():
            return fallback

        emphasized = ""
        focus = ""
        if outline:
            focus = outline.overview_focus
            emphasized = ", ".join(outline.emphasized_pages[:12])
        messages = build_overview_prompt(
            project.file_tree,
            key_files,
            self.language,
            outline_focus=focus,
            emphasized=emphasized,
        )
        raw = await self._complete_json(messages, max_tokens=4096)
        data = extract_json(raw)
        if not data or not isinstance(data, dict):
            logger.warning("Failed to parse overview JSON, using defaults")
            return fallback

        overview = _coerce_model(data, ProjectOverview, name=project.name)
        if not overview.name:
            overview.name = project.name
        if overview.one_liner or overview.description:
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
                f"module:{self.language}:{depth}:{name}:"
                f"{content_hash(''.join(content_parts))}"
            )

            cached = await self.cache.get(cache_key)
            if cached:
                try:
                    return ModuleDoc(**cached)
                except Exception:
                    pass

            fallback = self._fallback_module_doc(name, files, plan)
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
    ) -> ArchitectureDiagram:
        cache_key = f"arch:{self.language}:{tree_hash}"
        cached = await self.cache.get(cache_key)
        if cached:
            try:
                return ArchitectureDiagram(**cached)
            except Exception:
                pass

        fallback = self._fallback_architecture(project, outline)
        if not self._llm_enabled():
            return fallback

        focus = outline.architecture_focus if outline else ""
        core = ""
        if outline:
            core = ", ".join(m.name for m in outline.modules if m.depth == "deep")
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
            logger.warning("Failed to parse architecture JSON")
            return fallback

        arch = _coerce_model(data, ArchitectureDiagram)
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
        self, project: ProjectContext, outline: WikiOutline | None
    ) -> ProjectOverview:
        readme = next(
            (f for f in project.files if f.path.lower() in {"readme.md", "readme"}),
            None,
        )
        description = ""
        if readme and (readme.content or readme.preview):
            description = (readme.content or readme.preview or "").strip()[:1200]
        elif self._lang() == "zh":
            description = (
                f"{project.name} 按目录划成模块。先从入口文件看进程怎么启动，"
                "再顺着 import 图读枢纽包的职责与边界，而不是把 Wiki 写成文件清单。"
            )
            if outline and outline.overview_focus:
                names = ", ".join(f"`{m.name}`" for m in outline.modules[:6])
                if names:
                    description += f" 枢纽包包括 {names}。"
        elif outline and outline.overview_focus:
            description = outline.overview_focus
        else:
            description = (
                f"{project.name} is organized as directory modules. Start at the "
                "entrypoints, then follow imports into the hub packages — this page "
                "states purpose and boundaries, not a file inventory."
            )
        cites: list[Citation] = []
        if readme:
            cites.append(Citation(path=readme.path, start_line=1, note="README"))
        for f in project.files:
            if f.is_entrypoint:
                cites.append(Citation(path=f.path, note="entrypoint"))
        return ProjectOverview(
            name=project.name,
            description=description,
            citations=cites,
            term_tips=_generic_term_tips(self._lang()),
        )

    def _fallback_architecture(
        self, project: ProjectContext, outline: WikiOutline | None
    ) -> ArchitectureDiagram:
        components: list[Component] = []
        if outline:
            for item in outline.modules[:12]:
                components.append(
                    Component(name=item.name, files=list(item.key_files[:6]))
                )
        focus = ""
        if self._lang() == "zh":
            focus = (
                "仓库按目录模块分层。请求从入口进入，经过 import 图上最中心的包，"
                "再扩散到依赖方。architecture_type 只是机器标签；正文讲职责怎么切、数据怎么走。"
                "PageRank 只决定哪些模块值得先写深，不是目录清单。"
            )
            if outline:
                names = ", ".join(f"`{m.name}`" for m in outline.modules[:6])
                if names:
                    focus += f" 优先读 {names}。"
        else:
            focus = (outline.architecture_focus if outline else "").strip()
            if "Heaviest modules by PageRank" in focus:
                focus = ""
            if not focus:
                focus = (
                    "The repo is split by directory modules. Work enters at the "
                    "entrypoints, moves through the highest-centrality packages, then "
                    "out to dependents. PageRank only ranks which packages to explain "
                    "first — it is not a table of contents."
                )
        return ArchitectureDiagram(
            architecture_type="codebase-modules",
            description=focus,
            components=components,
            term_tips=_generic_term_tips(self._lang()),
        )

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
    ) -> ModuleDoc:
        file_docs = []
        for f in files[:16]:
            content = f.content or f.preview or ""
            file_docs.append(
                FileDoc(
                    path=f.path,
                    purpose=("入口文件" if self._lang() == "zh" else "Entrypoint")
                    if f.is_entrypoint
                    else "",
                    key_symbols=harvest_symbols(content),
                )
            )
        notes = (plan.notes if plan else "") or ""
        if self._lang() == "zh":
            purpose = notes or f"负责 `{name}` 这一层的职责边界"
            description = (
                f"`{name}` 是仓库里的一块职责边界。先看它对外承诺什么、和谁协作；"
                "下面的文件列表只是扫描证据，不是正文。"
            )
        else:
            purpose = notes or f"Owns the `{name}` package boundary"
            description = (
                f"`{name}` is a directory boundary. This page states what the "
                "package is for and how it connects; the file list is evidence, "
                "not the article."
            )
        return ModuleDoc(
            name=name,
            purpose=purpose,
            description=description,
            files=file_docs,
            citations=[Citation(path=f.path) for f in files[:8]],
            term_tips=_generic_term_tips(self._lang()),
        )


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
    for key, value in defaults.items():
        filtered.setdefault(key, value)
    try:
        return model_cls(**filtered)
    except Exception:
        return model_cls(**defaults)


def _coerce_module(data: dict, name: str) -> ModuleDoc:
    payload = dict(data)
    payload.setdefault("name", name)
    payload["call_chains"] = _coerce_call_chains(payload.get("call_chains"))
    payload["edge_cases"] = _coerce_strings(payload.get("edge_cases"))
    payload["citations"] = _coerce_citations(payload.get("citations"))
    payload["term_tips"] = _coerce_term_tips(payload.get("term_tips"))
    filtered = {k: v for k, v in payload.items() if k in ModuleDoc.model_fields}
    try:
        return ModuleDoc(**filtered)
    except Exception:
        return ModuleDoc(name=name, purpose=str(payload.get("purpose") or ""))


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
