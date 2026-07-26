"""Extract learning concepts from RepoWiki scan signals.

Primary path is deterministic (no LLM required). Optional LLM enrichment.
"""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from recallstack.domain.schemas import ConceptDraft, ConceptGenerationResult, SourceReference
from recallstack.learning.i18n import t
from recallstack.security import filter_source_references
from repowiki.core.graph import DependencyGraph
from repowiki.core.models import ProjectContext

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(text: str) -> str:
    s = _SLUG_RE.sub("-", text.lower()).strip("-")
    return s or "concept"


def content_hash_for(parts: list[str]) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update(p.encode("utf-8", errors="ignore"))
        h.update(b"\0")
    return h.hexdigest()[:24]


class ConceptExtractor:
    def __init__(self, max_concepts: int = 20):
        self.max_concepts = max_concepts

    def extract(
        self,
        project: ProjectContext,
        graph: DependencyGraph,
        *,
        commit_sha: str = "",
        wiki_summary: str = "",
    ) -> ConceptGenerationResult:
        ranked = graph.rank_files()
        rank_map = {path: score for path, score in ranked}
        files_by_path = {f.path: f for f in project.files}
        valid_paths = set(files_by_path)

        entry_files = [f.path for f in project.files if f.is_entrypoint]
        if not entry_files:
            entry_files = graph.get_entry_points()[:5]

        # group by top-level module / directory
        modules: dict[str, list[str]] = defaultdict(list)
        for f in project.files:
            if f.is_config:
                continue
            mod = self._module_name(f.path)
            modules[mod].append(f.path)

        drafts: list[ConceptDraft] = []

        # 1) project goal / overview
        readme = self._find_readme(project)
        drafts.append(
            ConceptDraft(
                slug="project-goal",
                title=t("Project goal", "项目目标"),
                description=self._project_goal_desc(project, readme),
                difficulty=1,
                importance=1.0,
                why_learn=t("Build a mental model of the repo goal and boundaries before diving into implementation.", "先建立对仓库目标与边界的心智模型，再深入实现。"),
                estimated_minutes=10,
                source_references=self._refs(
                    [readme] if readme else entry_files[:1],
                    files_by_path,
                    commit_sha,
                ),
                prerequisites=[],
            )
        )

        # 2) application entry
        if entry_files:
            drafts.append(
                ConceptDraft(
                    slug="application-entry",
                    title=t("Application entry", "应用入口"),
                    description=t("Where the program starts and how the entrypoint wires core components.", "程序从哪里启动，以及入口如何装配核心组件。"),
                    difficulty=2,
                    importance=0.95,
                    why_learn=t("The entrypoint is the start of the call chain and shapes the main flow.", "入口是阅读调用链的起点，决定主流程如何展开。"),
                    estimated_minutes=15,
                    source_references=self._refs(entry_files[:3], files_by_path, commit_sha),
                    prerequisites=["project-goal"],
                )
            )

        # 3) core modules by pagerank clusters
        core_files = [p for p, _ in ranked[: min(30, len(ranked))]]
        module_scores: dict[str, float] = defaultdict(float)
        module_files: dict[str, list[str]] = defaultdict(list)
        for path in core_files:
            mod = self._module_name(path)
            module_scores[mod] += rank_map.get(path, 0.0)
            module_files[mod].append(path)

        # classify special concepts from path hints
        special_rules = [
            (
                "configuration",
                t("Configuration", "配置加载"),
                ("config", "settings", "env"),
                t("How configuration enters runtime and shapes later behavior.", "配置如何进入运行时，影响所有后续行为。"),
            ),
            (
                "request-routing",
                t("Request routing", "请求路由"),
                ("router", "route", "api", "server", "handler", "endpoint"),
                t("How external requests reach business logic.", "理解外部请求如何进入业务逻辑。"),
            ),
            (
                "data-persistence",
                t("Data persistence", "数据持久化"),
                ("db", "model", "repository", "store", "sql", "migration"),
                t("How data is written and read — key state transitions.", "数据如何写入与读取，是状态变化的关键。"),
            ),
            (
                "caching",
                t("Caching", "缓存策略"),
                ("cache",),
                t("Caching trades performance against consistency.", "缓存影响性能与一致性权衡。"),
            ),
            (
                "error-handling",
                t("Error handling", "错误处理"),
                ("error", "exception", "fault"),
                t("Failure paths determine robustness.", "失败路径决定系统鲁棒性。"),
            ),
            (
                "background-tasks",
                t("Background tasks", "后台任务"),
                ("task", "worker", "job", "queue", "celery", "cron"),
                t("Async paths are easy to miss but often carry side effects.", "异步路径常被忽略，却承载关键副作用。"),
            ),
            (
                "testing-structure",
                t("Testing structure", "测试体系"),
                ("test", "tests", "spec"),
                t("Tests reveal expected behavior and safety boundaries.", "测试揭示预期行为与安全边界。"),
            ),
            (
                "authentication",
                t("Authentication", "身份认证"),
                ("auth", "login", "session", "jwt", "oauth"),
                t("Auth cuts across modules and is central to security understanding.", "认证横切多个模块，是安全理解的核心。"),
            ),
        ]

        used_files: set[str] = set()
        for slug, title, keywords, why in special_rules:
            matched = [
                p
                for p in core_files
                if any(k in p.lower().replace("\\", "/") for k in keywords)
            ]
            if not matched:
                # also search all files for tests etc.
                matched = [
                    f.path
                    for f in project.files
                    if any(k in f.path.lower().replace("\\", "/") for k in keywords)
                ][:5]
            if not matched:
                continue
            importance = min(0.93, 0.45 + sum(rank_map.get(p, 0.01) for p in matched[:5]))
            prereq = ["application-entry"] if slug != "testing-structure" else ["project-goal"]
            if slug == "data-persistence" and any(d.slug == "request-routing" for d in drafts):
                prereq = ["request-routing"]
            drafts.append(
                ConceptDraft(
                    slug=slug,
                    title=title,
                    description=t(f"Core responsibilities and collaboration around {title}.", f"围绕 {title} 相关模块与符号的核心职责与协作方式。"),
                    difficulty=2 if slug in {"configuration", "testing-structure"} else 3,
                    importance=importance,
                    why_learn=why,
                    estimated_minutes=15,
                    source_references=self._refs(matched[:4], files_by_path, commit_sha),
                    prerequisites=prereq,
                )
            )
            used_files.update(matched[:4])

        # 4) remaining high-importance modules as concepts
        for mod, score in sorted(module_scores.items(), key=lambda x: -x[1]):
            if len(drafts) >= self.max_concepts:
                break
            if mod in {"", ".", "node_modules", "dist", "build", "vendor", "tests", "test"}:
                # tests handled specially
                if mod not in {"tests", "test"}:
                    continue
            paths = [p for p in module_files[mod] if p not in used_files][:4]
            if not paths:
                paths = module_files[mod][:3]
            if not paths:
                continue
            slug = slugify(f"module-{mod}")
            if any(d.slug == slug for d in drafts):
                continue
            # skip if already covered heavily by special concepts
            if set(paths) <= used_files:
                continue
            drafts.append(
                ConceptDraft(
                    slug=slug,
                    title=t(f"Module: {mod}", f"模块：{mod}"),
                    description=t(f"Responsibility boundary, public surface, and internal collaboration of `{mod}`.", f"{mod} 模块的职责边界、对外接口与内部协作。"),
                    difficulty=3,
                    importance=min(0.9, 0.3 + score * 5),
                    why_learn=t(f"`{mod}` ranks high in the dependency graph and is a key piece of the main flow.", f"{mod} 在依赖图中具有较高重要性，是理解主流程的关键拼图。"),
                    estimated_minutes=12,
                    source_references=self._refs(paths, files_by_path, commit_sha),
                    prerequisites=["application-entry"] if entry_files else ["project-goal"],
                )
            )
            used_files.update(paths)

        # ensure at least 5 concepts when possible
        if len(drafts) < 5:
            for path, score in ranked:
                if len(drafts) >= 5:
                    break
                slug = slugify(f"file-{Path(path).stem}")
                if any(d.slug == slug for d in drafts):
                    continue
                drafts.append(
                    ConceptDraft(
                        slug=slug,
                        title=t(f"Key file: {Path(path).name}", f"关键文件：{Path(path).name}"),
                        description=t(f"Understand the role and call relationships of `{path}`.", f"理解 {path} 在系统中的职责与调用关系。"),
                        difficulty=2,
                        importance=min(0.85, 0.4 + score * 4),
                        why_learn=t("This file ranks high by PageRank in the dependency graph.", "该文件在 PageRank 中排名靠前。"),
                        estimated_minutes=10,
                        source_references=self._refs([path], files_by_path, commit_sha),
                        prerequisites=["project-goal"],
                    )
                )

        # still short? create generic role concepts from available files
        if len(drafts) < 5:
            role_templates = [
                ("call-flow", t("Main call flow", "主调用链"), t("Trace the call order from entry to core logic.", "追踪入口到核心逻辑的调用顺序。")),
                ("module-boundaries", t("Module boundaries", "模块边界"), t("How directories/modules split responsibilities.", "理解目录/模块如何划分职责。")),
                ("extension-points", t("Extension points", "扩展点"), t("Interfaces and config points that can grow later.", "识别后续可扩展的接口与配置点。")),
                ("core-data", t("Core data structures", "核心数据结构"), t("Key data objects and how they move.", "识别关键数据对象及其流转。")),
            ]
            all_paths = [f.path for f in project.files if not f.is_config] or [f.path for f in project.files]
            for slug, title, why in role_templates:
                if len(drafts) >= 5:
                    break
                if any(d.slug == slug for d in drafts):
                    continue
                pick = all_paths[:3]
                drafts.append(
                    ConceptDraft(
                        slug=slug,
                        title=title,
                        description=t(f"{title}: a learning concept grounded in the current file structure.", f"{title}：基于当前仓库文件结构的学习概念。"),
                        difficulty=2,
                        importance=0.55,
                        why_learn=why,
                        estimated_minutes=12,
                        source_references=self._refs(pick, files_by_path, commit_sha),
                        prerequisites=["project-goal"],
                    )
                )

        # validate source refs
        cleaned: list[ConceptDraft] = []
        for d in drafts[: self.max_concepts]:
            refs = filter_source_references(
                [r.model_dump() for r in d.source_references], valid_paths
            )
            if not refs and d.slug != "project-goal":
                # still keep project-goal even without refs if needed
                continue
            cleaned.append(
                d.model_copy(
                    update={
                        "source_references": [SourceReference.model_validate(r) for r in refs]
                        if refs
                        else d.source_references
                    }
                )
            )

        if len(cleaned) < 5:
            # pad with remaining drafts that had refs dropped? rebuild from top files
            top = [p for p, _ in ranked] or [f.path for f in project.files]
            idx = 0
            while len(cleaned) < 5 and top:
                path = top[idx % len(top)]
                idx += 1
                slug = slugify(f"focus-{Path(path).stem}-{len(cleaned)}")
                if any(c.slug == slug for c in cleaned):
                    if idx > len(top) * 3:
                        break
                    continue
                refs = self._refs([path], files_by_path, commit_sha)
                if not refs:
                    if idx > len(top) * 3:
                        break
                    continue
                cleaned.append(
                    ConceptDraft(
                        slug=slug,
                        title=t(f"Focus: {Path(path).name}", f"聚焦：{Path(path).name}"),
                        description=t(f"Build understanding of `{path}` before reading or changing it.", f"围绕 {path} 建立阅读与改动前的理解。"),
                        difficulty=2,
                        importance=0.5,
                        why_learn=t("Fills out the minimum concept set needed for the learning path.", "补齐学习路径所需的最小概念集合。"),
                        source_references=refs,
                        prerequisites=["project-goal"] if any(c.slug == "project-goal" for c in cleaned) else [],
                    )
                )

        if not cleaned:
            # absolute fallback
            top = [p for p, _ in ranked[:3]] or [f.path for f in project.files[:3]]
            cleaned = [
                ConceptDraft(
                    slug="core-codebase",
                    title=t("Core codebase structure", "代码库核心结构"),
                    description=t("Main files and dependency structure of the repository.", "仓库的主要文件与依赖结构。"),
                    difficulty=1,
                    importance=1.0,
                    why_learn=t("Establish a basic map of how the repository is organized.", "建立对仓库文件组织的基本认识。"),
                    source_references=self._refs(top, files_by_path, commit_sha),
                )
            ]

        # drop cyclic prerequisites by simple topo filter later; here only self-prereq
        for c in cleaned:
            c.prerequisites = [p for p in c.prerequisites if p != c.slug]

        return ConceptGenerationResult(concepts=cleaned)

    def remove_cyclic_prerequisites(
        self, concepts: list[ConceptDraft]
    ) -> list[ConceptDraft]:
        """Remove prerequisite edges that participate in cycles."""
        by_slug = {c.slug: c for c in concepts}
        graph: dict[str, set[str]] = {c.slug: set(c.prerequisites) for c in concepts}

        # Kahn-like: repeatedly remove edges that keep cycles
        def has_cycle(g: dict[str, set[str]]) -> list[str] | None:
            temp: set[str] = set()
            perm: set[str] = set()
            cycle_node: list[str] = []

            def visit(n: str) -> bool:
                if n in perm:
                    return False
                if n in temp:
                    cycle_node.append(n)
                    return True
                temp.add(n)
                for m in g.get(n, set()):
                    if m in g and visit(m):
                        return True
                temp.remove(n)
                perm.add(n)
                return False

            for node in list(g):
                if visit(node):
                    return cycle_node
            return None

        # remove edges until acyclic
        guard = 0
        while guard < 100:
            guard += 1
            cyc = has_cycle(graph)
            if not cyc:
                break
            # remove one edge from cycle node
            n = cyc[0]
            if graph[n]:
                graph[n].pop()
            else:
                break

        result = []
        for c in concepts:
            prereqs = [p for p in graph.get(c.slug, set()) if p in by_slug]
            result.append(c.model_copy(update={"prerequisites": prereqs}))
        return result

    def _module_name(self, path: str) -> str:
        parts = Path(path.replace("\\", "/")).parts
        if not parts:
            return "root"
        if parts[0] in {"src", "lib", "app", "pkg"} and len(parts) > 1:
            return parts[1]
        return parts[0]

    def _find_readme(self, project: ProjectContext) -> str | None:
        for f in project.files:
            name = Path(f.path).name.lower()
            if name in {"readme.md", "readme.rst", "readme.txt", "readme"}:
                return f.path
        return None

    def _project_goal_desc(self, project: ProjectContext, readme: str | None) -> str:
        if readme:
            for f in project.files:
                if f.path == readme and (f.preview or f.content):
                    text = (f.preview or f.content).strip().splitlines()
                    snippet = " ".join(text[:8])[:400]
                    return f"{project.name}：{snippet}"
        return t(f"{project.name}: goals, capability boundaries, and primary usage.", f"{project.name} 代码仓库的目标、能力边界与主要使用方式。")

    def _refs(
        self,
        paths: list[str],
        files_by_path: dict[str, Any],
        commit_sha: str,
    ) -> list[SourceReference]:
        refs: list[SourceReference] = []
        for path in paths:
            if not path:
                continue
            f = files_by_path.get(path)
            symbol = None
            start = 1
            end = min(getattr(f, "lines", 20) or 20, 40) if f else 20
            if f and (f.content or f.preview):
                text = f.content or f.preview
                for line in text.splitlines()[:80]:
                    s = line.strip()
                    if s.startswith("def ") or s.startswith("class ") or s.startswith("async def "):
                        symbol = s.split("(")[0].replace("async def ", "").replace("def ", "").replace("class ", "").strip(":")
                        break
            refs.append(
                SourceReference(
                    path=path.replace("\\", "/"),
                    start_line=start,
                    end_line=end,
                    symbol=symbol,
                    commit_sha=commit_sha or None,
                )
            )
        return refs
