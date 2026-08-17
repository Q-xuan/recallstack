"""End-to-end repository analysis pipeline for RecallStack."""

from __future__ import annotations

import hashlib
import logging
import re
import subprocess
from pathlib import Path

from sqlalchemy.orm import Session

from recallstack.config import RecallStackConfig
from recallstack.db.models import (
    Concept,
    ConceptEdge,
    LearningItem,
    LearningPath,
    LearningPathNode,
    Repository,
    RepositoryVersion,
    utcnow,
)
from recallstack.db.repositories import RepositoryStore
from recallstack.db.session import session_scope
from recallstack.learning.concept_extractor import ConceptExtractor, content_hash_for
from recallstack.learning.i18n import t
from recallstack.learning.path_builder import PathBuilder
from recallstack.learning.question_generator import QuestionGenerator
from recallstack.learning.stale import compute_changed_paths, mark_stale_for_changed_files
from recallstack.learning.wiki_generator import build_wiki_payload
from recallstack.security import SecurityError, validate_git_url, validate_local_path
from repowiki.core.models import ProjectContext

logger = logging.getLogger(__name__)

# repowiki's progress lines, matched back to a localizable phrase. Unmatched
# messages pass through unchanged, so adding one upstream degrades to English
# rather than to nothing.
_PROGRESS_PHRASES: tuple[tuple[re.Pattern[str], str, str], ...] = (
    (re.compile(r"^Analyzed module (\d+)/(\d+)$"), "Analyzed module {0}/{1}", "已分析模块 {0}/{1}"),
    (re.compile(r"^Wrote module (\d+)/(\d+)$"), "Wrote module {0}/{1}", "已撰写模块 {0}/{1}"),
    (re.compile(r"^Analyzing (\d+) modules"), "Analyzing {0} modules", "正在分析 {0} 个模块"),
    (re.compile(r"^Writing (\d+) modules"), "Writing {0} modules", "正在撰写 {0} 个模块"),
    (re.compile(r"^Preparing file context"), "Preparing file context", "正在准备文件上下文"),
    (re.compile(r"^Outlining wiki"), "Outlining wiki", "正在规划 Wiki 大纲"),
    (re.compile(r"^Generating project overview"), "Generating overview", "正在生成项目概览"),
    (re.compile(r"^Detecting architecture"), "Detecting architecture", "正在识别架构"),
    (re.compile(r"^Creating reading guide"), "Creating reading guide", "正在生成阅读指南"),
    (re.compile(r"^Verifying citations"), "Verifying citations", "正在核验引用"),
    (re.compile(r"^Done!?$"), "Done", "完成"),
)


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()


def detect_commit_sha(root: Path) -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
            shell=False,
        )
        if out.returncode == 0 and out.stdout.strip():
            return out.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    # fallback content-based pseudo commit
    return "local-" + hashlib.sha1(str(root).encode()).hexdigest()[:12]


def compute_repo_content_hash(file_hashes: dict[str, str]) -> str:
    h = hashlib.sha256()
    for path in sorted(file_hashes):
        h.update(path.encode())
        h.update(b":")
        h.update(file_hashes[path].encode())
        h.update(b"\n")
    return h.hexdigest()[:32]


def _run_async(coro):
    """Run a coroutine to completion, safe whether or not an event loop is running."""
    import asyncio
    import concurrent.futures

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    # already inside a loop — offload to a worker thread with its own loop
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        return ex.submit(asyncio.run, coro).result()


class AnalyzeRepositoryService:
    def __init__(self, session: Session, config: RecallStackConfig | None = None):
        self.session = session
        self.config = config or RecallStackConfig.load()
        self.store = RepositoryStore(session)

    def create_repository(
        self,
        *,
        source_type: str,
        source_location: str,
        name: str | None = None,
        default_branch: str = "main",
    ) -> Repository:
        if source_type == "github":
            source_location = validate_git_url(source_location)
            display = name or source_location.rstrip("/").split("/")[-1].removesuffix(".git")
        elif source_type == "local":
            path = validate_local_path(source_location)
            source_location = str(path)
            display = name or path.name
        else:
            raise SecurityError("invalid_source_type", "source_type must be local or github")

        return self.store.create_repository(
            name=display,
            source_type=source_type,
            source_location=source_location,
            default_branch=default_branch,
        )

    def analyze(self, repository_id: str, lang: str | None = None) -> RepositoryVersion:
        from recallstack.learning.i18n import content_lang, content_lang_scope, normalize_lang

        resolved_lang = normalize_lang(lang) if lang else content_lang()
        with content_lang_scope(resolved_lang):
            return self._analyze_in_lang(repository_id, resolved_lang)

    def _analyze_in_lang(self, repository_id: str, resolved_lang: str) -> RepositoryVersion:
        repo = self.store.get_repository(repository_id)
        if not repo:
            raise KeyError("repository_not_found")

        try:
            project, root = self._ingest(repo)
        except Exception as exc:  # noqa: BLE001
            latest = self.store.get_latest_version(repo.id)
            if latest:
                latest.status = "failed"
                latest.error_message = str(exc)[:2000]
                latest.completed_at = utcnow()
                self.session.commit()
            raise
        commit_sha = detect_commit_sha(root)
        file_hashes = {
            f.path: _sha256_text(f.content or f.preview or f.path) for f in project.files
        }
        content_hash = compute_repo_content_hash(file_hashes)
        existing = self.store.get_version_by_commit(repo.id, commit_sha)
        existing_lang = getattr(existing, "content_lang", None) if existing else None
        lang_mismatch = bool(existing_lang and existing_lang != resolved_lang)
        texts = {
            f.path: (f.content or f.preview or "")
            for f in project.files
            if (f.content or f.preview)
        }
        from repowiki.core.grounding import should_reuse_analyzed_wiki

        if (
            existing
            and not lang_mismatch
            and existing.content_hash == content_hash
            and existing.status == "ready"
            and existing.wiki_pages
            and (existing.wiki_pages or {}).get("pages")
            and should_reuse_analyzed_wiki(existing.wiki_pages, texts)
        ):
            logger.info("idempotent hit for %s@%s", repo.id, commit_sha)
            self._save_version_file_texts(existing, project)
            from recallstack.learning.wiki_serve import (
                materialize_analyzed_version,
                path_is_materialized,
                wiki_is_materialized,
            )

            path = self.store.get_learning_path(existing.id)
            if not wiki_is_materialized(existing.wiki_pages) or not path_is_materialized(
                getattr(path, "resolved", None) if path else None
            ):
                materialize_analyzed_version(
                    self.session, existing, self.store.list_concepts(repo.id, existing.id), texts
                )
            if not existing_lang:
                existing.content_lang = resolved_lang
            self.session.commit()
            return existing

        old_version = self.store.get_latest_version(repo.id)
        if existing:
            version = existing
            version.status = "pending"
            version.error_message = None
            version.content_hash = content_hash
            version.completed_at = None
        else:
            version = self.store.create_version(
                repository_id=repo.id,
                commit_sha=commit_sha,
                content_hash=content_hash,
                status="pending",
            )
        version.content_lang = resolved_lang
        self.session.commit()

        try:
            self._set_status(version, "scanning")
            from repowiki.core.graph import DependencyGraph

            graph = DependencyGraph.build_from_project(project)
            self._set_status(version, "generating_concepts")
            extractor = ConceptExtractor(max_concepts=self.config.max_concepts)
            concept_result = extractor.extract(
                project, graph, commit_sha=commit_sha, wiki_summary=""
            )
            concepts = extractor.remove_cyclic_prerequisites(concept_result.concepts)

            self._set_status(version, "generating_wiki")
            wiki_data = None
            if self.config.llm_enabled:
                try:
                    from recallstack.learning.wiki_generator import build_llm_enriched_wiki_data

                    self._set_status(version, "llm_enriching")
                    version_id = version.id
                    wiki_data = _run_async(
                        build_llm_enriched_wiki_data(
                            project,
                            graph,
                            concepts,
                            on_progress=lambda msg: self._publish_progress(version_id, msg),
                        )
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "LLM wiki enrichment failed, falling back to deterministic: %s",
                        exc,
                    )
                    wiki_data = None
            # Real RepoWiki pages from the same graph + concepts (one product, one scan)
            wiki_payload = build_wiki_payload(project, graph, concepts, wiki_data=wiki_data)
            version.wiki_pages = wiki_payload

            # stale previous content based on file hash changes
            if old_version and old_version.id != version.id:
                old_hashes = self._load_version_file_hashes(old_version)
                if old_hashes:
                    changed = compute_changed_paths(old_hashes, file_hashes)
                    mark_stale_for_changed_files(
                        self.session,
                        old_version=old_version,
                        new_version=version,
                        changed_paths=changed,
                    )

            # replace concepts for this version (idempotent re-run)
            self._clear_version_learning_data(version.id)

            concept_rows: dict[str, Concept] = {}
            for draft in concepts:
                refs = [r.model_dump() for r in draft.source_references]
                ch = content_hash_for(
                    [draft.slug, draft.title, draft.description] + [r["path"] for r in refs]
                )
                row = Concept(
                    repository_id=repo.id,
                    repository_version_id=version.id,
                    slug=draft.slug,
                    title=draft.title,
                    description=draft.description,
                    difficulty=max(1, min(5, draft.difficulty)),
                    importance=max(0.0, min(1.0, draft.importance)),
                    source_references=refs,
                    content_hash=ch,
                    stale=False,
                    why_learn=draft.why_learn,
                    estimated_minutes=draft.estimated_minutes,
                    wiki_page_id=draft.wiki_page_id
                    or (
                        "index"
                        if draft.slug in {"project-goal", "overview"}
                        else f"topics/{draft.slug}"
                        if draft.slug != "getting-started"
                        else "getting-started"
                    ),
                )
                self.session.add(row)
                self.session.flush()
                concept_rows[draft.slug] = row

            # edges: prerequisite + depends_on from module deps
            for draft in concepts:
                src = concept_rows.get(draft.slug)
                if not src:
                    continue
                for pre in draft.prerequisites:
                    tgt = concept_rows.get(pre)
                    if not tgt:
                        continue
                    self.session.add(
                        ConceptEdge(
                            source_concept_id=tgt.id,  # prerequisite -> concept
                            target_concept_id=src.id,
                            relation_type="prerequisite",
                        )
                    )

            mod_deps = graph.get_module_dependencies()
            slug_by_mod = {}
            for slug, row in concept_rows.items():
                if slug.startswith("module-"):
                    slug_by_mod[slug.removeprefix("module-")] = row
            for src_mod, targets in mod_deps.items():
                src_row = slug_by_mod.get(src_mod)
                if not src_row:
                    continue
                for dst_mod in targets:
                    dst_row = slug_by_mod.get(dst_mod)
                    if not dst_row or dst_row.id == src_row.id:
                        continue
                    self.session.add(
                        ConceptEdge(
                            source_concept_id=src_row.id,
                            target_concept_id=dst_row.id,
                            relation_type="depends_on",
                        )
                    )

            path_result = PathBuilder().build(concepts)
            path = LearningPath(
                repository_version_id=version.id,
                title=path_result.title,
                description=path_result.description,
                estimated_minutes=path_result.estimated_minutes,
            )
            self.session.add(path)
            self.session.flush()
            for node in path_result.nodes:
                crow = concept_rows.get(node.concept_slug)
                if not crow:
                    continue
                self.session.add(
                    LearningPathNode(
                        learning_path_id=path.id,
                        concept_id=crow.id,
                        position=node.position,
                        reason=node.reason,
                    )
                )

            # learning items
            qgen = QuestionGenerator(max_items=self.config.max_items_per_concept)
            valid_paths = {f.path for f in project.files}
            for draft in concepts:
                crow = concept_rows.get(draft.slug)
                if not crow:
                    continue
                items = qgen.generate_deterministic(
                    title=draft.title,
                    description=draft.description,
                    why_learn=draft.why_learn,
                    source_references=[r.model_dump() for r in draft.source_references],
                    valid_paths=valid_paths,
                    commit_sha=commit_sha,
                )
                for item in items.items:
                    self.session.add(
                        LearningItem(
                            concept_id=crow.id,
                            item_type=item.item_type,
                            prompt=item.prompt,
                            rubric=item.rubric.model_dump(),
                            expected_answer_outline=item.expected_answer_outline,
                            source_references=[r.model_dump() for r in item.source_references],
                            difficulty=item.difficulty,
                            content_hash=qgen.item_content_hash(item),
                            stale=False,
                        )
                    )

            # store file hashes on version via content_hash already; keep side map in error_message? no.
            # Use a lightweight sidecar table alternative: encode in version by separate file not needed for MVP;
            # recompute from concepts is enough for stale next time if we persist hashes in JSON file under data/.
            self._save_version_file_hashes(version, file_hashes)
            self._save_version_file_texts(version, project)
            texts = {
                f.path: (f.content or f.preview or "")
                for f in project.files
                if (f.content or f.preview)
            }
            from recallstack.learning.wiki_serve import materialize_analyzed_version

            materialize_analyzed_version(
                self.session, version, list(concept_rows.values()), texts
            )

            version.status = "ready"
            version.completed_at = utcnow()
            version.error_message = None
            repo.updated_at = utcnow()
            self.session.commit()
            self.session.refresh(version)
            return version
        except Exception as exc:  # noqa: BLE001
            logger.exception("analyze failed")
            version.status = "failed"
            version.error_message = str(exc)[:2000]
            version.completed_at = utcnow()
            self.session.commit()
            raise

    def _set_status(self, version: RepositoryVersion, status: str) -> None:
        version.status = status
        version.progress_message = None
        self.session.commit()

    @staticmethod
    def _localize_progress(message: str) -> str:
        """Translate the analyzer's progress lines for the UI.

        repowiki reports in English because its CLI prints these directly; the
        wiki it produces follows the configured content language, and a Chinese
        wiki reporting "Analyzing 24 modules..." reads like a leak.
        """
        text = message.strip()
        for pattern, en, zh in _PROGRESS_PHRASES:
            m = pattern.match(text)
            if m:
                return t(en, zh).format(*m.groups())
        return text

    def _publish_progress(self, version_id: str, message: str) -> None:
        """Record a detail line for the phase currently running.

        Uses its own short session rather than the pipeline's: the analyzer may
        invoke this from a worker thread (see ``_run_async``), and an ORM session
        is not safe to share across threads. Progress is cosmetic, so a failure
        here must never take the analysis down with it.
        """
        try:
            text = self._localize_progress(message)
            with session_scope() as session:
                session.query(RepositoryVersion).filter(
                    RepositoryVersion.id == version_id
                ).update({"progress_message": text[:255]})
        except Exception:  # noqa: BLE001
            logger.debug("could not publish progress: %s", message, exc_info=True)

    def _ingest(self, repo: Repository):
        from repowiki.ingest.local import ingest_local

        max_file = self.config.max_file_size_kb * 1024
        if repo.source_type == "local":
            root = validate_local_path(repo.source_location)
            project = ingest_local(root, max_file_size=max_file, max_files=1000)
            return project, root

        # github
        url = validate_git_url(repo.source_location)
        from repowiki.ingest.github import ingest_github

        project = ingest_github(url, max_file_size=max_file, max_files=1000)
        root = Path(project.root)
        return project, root


    def _clear_version_learning_data(self, version_id: str) -> None:
        from sqlalchemy import select

        from recallstack.db.models import Attempt, Mastery, ReviewLog

        # delete path nodes/paths, edges, items, concepts for version
        concepts = list(
            self.session.scalars(select(Concept).where(Concept.repository_version_id == version_id))
        )
        concept_ids = [c.id for c in concepts]
        if concept_ids:
            items = list(
                self.session.scalars(
                    select(LearningItem).where(LearningItem.concept_id.in_(concept_ids))
                )
            )
            item_ids = [i.id for i in items]
            # attempts / review_logs / mastery reference items+concepts — clear first
            if item_ids:
                for log in self.session.scalars(
                    select(ReviewLog).where(ReviewLog.learning_item_id.in_(item_ids))
                ):
                    self.session.delete(log)
                for att in self.session.scalars(
                    select(Attempt).where(Attempt.learning_item_id.in_(item_ids))
                ):
                    self.session.delete(att)
            for log in self.session.scalars(
                select(ReviewLog).where(ReviewLog.concept_id.in_(concept_ids))
            ):
                self.session.delete(log)
            for m in self.session.scalars(
                select(Mastery).where(Mastery.concept_id.in_(concept_ids))
            ):
                self.session.delete(m)
            self.session.flush()
            for item in items:
                self.session.delete(item)
            edges = list(
                self.session.scalars(
                    select(ConceptEdge).where(
                        ConceptEdge.source_concept_id.in_(concept_ids)
                        | ConceptEdge.target_concept_id.in_(concept_ids)
                    )
                )
            )
            for e in edges:
                self.session.delete(e)
            paths = list(
                self.session.scalars(
                    select(LearningPath).where(LearningPath.repository_version_id == version_id)
                )
            )
            for path in paths:
                nodes = list(
                    self.session.scalars(
                        select(LearningPathNode).where(
                            LearningPathNode.learning_path_id == path.id
                        )
                    )
                )
                for n in nodes:
                    self.session.delete(n)
                self.session.delete(path)
            for c in concepts:
                self.session.delete(c)
            self.session.flush()

    def _hash_path(self, version: RepositoryVersion) -> Path:
        base = Path("data") / "version_hashes"
        base.mkdir(parents=True, exist_ok=True)
        return base / f"{version.id}.json"

    def _save_version_file_hashes(
        self, version: RepositoryVersion, file_hashes: dict[str, str]
    ) -> None:
        import json

        path = self._hash_path(version)
        path.write_text(json.dumps(file_hashes), encoding="utf-8")

    def _load_version_file_hashes(self, version: RepositoryVersion) -> dict[str, str]:
        import json

        path = self._hash_path(version)
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    def _save_version_file_texts(self, version: RepositoryVersion, project: ProjectContext) -> None:
        from recallstack.learning.code_loader import save_version_file_texts

        texts = {
            f.path: (f.content or f.preview or "")
            for f in project.files
            if (f.content or f.preview)
        }
        save_version_file_texts(version.id, texts)
