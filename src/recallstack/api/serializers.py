"""ORM → response schema mappers."""

from __future__ import annotations

import logging

from recallstack.db.models import (
    Attempt,
    Concept,
    ConceptEdge,
    LearningItem,
    LearningPath,
    Repository,
    RepositoryVersion,
)
from recallstack.domain.schemas import (
    AttemptOut,
    ConceptEdgeOut,
    ConceptOut,
    LearningItemDetailOut,
    LearningItemOut,
    LearningPathNodeOut,
    LearningPathOut,
    RepositoryOut,
    VersionOut,
    WikiOut,
    WikiPageOut,
    WikiSidebarItemOut,
)
from recallstack.learning.i18n import content_lang
from recallstack.learning.learning_contract import (
    CORE_PATH_CAP,
    drop_duplicate_entry_slug,
    is_filler_slug_title,
    is_web_filler_path_slug,
    pass_gate,
    path_evidence_chip,
    path_mission,
    path_principles,
    path_rank,
    path_worksheet,
    step_task_for_slug,
    upgrade_legacy_concept_markdown,
    wiki_prose_excerpt,
)
from repowiki.core.topics import (
    is_generic_web_slug,
    omit_generic_web_wiki_page,
    omit_unusable_topic_stub,
)
from repowiki.core.wiki_builder import (
    prune_generic_web_sidebar,
    prune_sidebar_missing_pages,
    rank_and_cap_directory_sidebar,
    rebuild_topic_sidebar,
    sidebar_has_topic_groups,
    upgrade_legacy_module_markdown,
    upgrade_wiki_page_content,
)

logger = logging.getLogger(__name__)


def repo_out(repo: Repository) -> RepositoryOut:
    return RepositoryOut(
        id=repo.id,
        name=repo.name,
        source_type=repo.source_type,
        source_location=_safe_location(repo.source_location, repo.source_type),
        default_branch=repo.default_branch,
        created_at=repo.created_at,
        updated_at=repo.updated_at,
    )


def version_out(v: RepositoryVersion) -> VersionOut:
    return VersionOut(
        id=v.id,
        repository_id=v.repository_id,
        commit_sha=v.commit_sha,
        content_hash=v.content_hash,
        status=v.status,
        progress_message=v.progress_message,
        error_message=v.error_message,
        has_wiki=bool(v.wiki_pages and (v.wiki_pages or {}).get("pages")),
        created_at=v.created_at,
        completed_at=v.completed_at,
    )


def concept_out(
    c: Concept,
    *,
    mastery_score: float | None = None,
    next_review_at=None,
) -> ConceptOut:
    return ConceptOut(
        id=c.id,
        repository_id=c.repository_id,
        repository_version_id=c.repository_version_id,
        slug=c.slug,
        title=c.title,
        description=c.description,
        difficulty=c.difficulty,
        importance=c.importance,
        source_references=c.source_references or [],
        content_hash=c.content_hash,
        stale=bool(c.stale),
        why_learn=c.why_learn or "",
        estimated_minutes=c.estimated_minutes or 15,
        wiki_page_id=getattr(c, "wiki_page_id", None),
        mastery_score=mastery_score,
        next_review_at=next_review_at,
    )


def edge_out(e: ConceptEdge) -> ConceptEdgeOut:
    return ConceptEdgeOut(
        id=e.id,
        source_concept_id=e.source_concept_id,
        target_concept_id=e.target_concept_id,
        relation_type=e.relation_type,
    )


def wiki_out(
    repository_id: str,
    version: RepositoryVersion,
    concepts: list[Concept] | None = None,
) -> WikiOut:
    payload = version.wiki_pages or {}
    concept_by_slug = {c.slug: c for c in (concepts or [])}
    raw_pages = payload.get("pages") or []
    kept_pages = [
        item
        for item in raw_pages
        if not omit_generic_web_wiki_page(
            str(item.get("id") or ""), str(item.get("content") or "")
        )
        and not omit_unusable_topic_stub(
            str(item.get("id") or ""),
            str(item.get("content") or ""),
            title=str(item.get("title") or ""),
        )
    ]
    page_ids = {item.get("id") for item in kept_pages}
    known_ids = {str(i) for i in page_ids if i}
    overview_excerpt = wiki_prose_excerpt(
        next(
            (item.get("content") or "" for item in kept_pages if item.get("id") == "index"),
            "",
        )
    )
    pages: list[WikiPageOut] = []
    for p in kept_pages:
        page_id = p.get("id") or ""
        concept = None
        content = p.get("content") or ""
        if page_id.startswith("concepts/"):
            slug = page_id.split("/", 1)[1]
            concept = concept_by_slug.get(slug)
            content = upgrade_legacy_concept_markdown(
                content,
                slug=slug,
                title=(concept.title if concept else p.get("title")) or "",
                has_overview="index" in page_ids,
                has_architecture="architecture" in page_ids,
                overview_excerpt=overview_excerpt if slug == "project-goal" else "",
            )
        elif page_id.startswith("modules/"):
            content = upgrade_legacy_module_markdown(content, language=content_lang())
        else:
            concept = next(
                (
                    c
                    for c in (concepts or [])
                    if getattr(c, "wiki_page_id", None) == page_id
                ),
                None,
            )
        content = upgrade_wiki_page_content(
            content, known_ids, language=content_lang(), page_id=page_id
        )
        pages.append(
            WikiPageOut(
                id=page_id,
                title=p.get("title") or page_id,
                content=content,
                parent_id=p.get("parent_id") or "",
                order=int(p.get("order") or 0),
                concept_id=concept.id if concept else None,
                concept_slug=concept.slug if concept else None,
            )
        )

    def map_sidebar(items: list) -> list[WikiSidebarItemOut]:
        out: list[WikiSidebarItemOut] = []
        for item in items or []:
            out.append(
                WikiSidebarItemOut(
                    title=item.get("title") or "",
                    page_id=item.get("page_id") or "",
                    children=map_sidebar(item.get("children") or []),
                )
            )
        return out

    raw_sidebar = payload.get("sidebar") or []
    content_by_id = {item.get("id") or "": item.get("content") or "" for item in kept_pages}
    page_id_set = {str(i) for i in page_ids if i}
    # Rebuild unless this payload already has 入门指南 / 深入探索. Do not wait
    # for sidebar_looks_like_module_tree: the old Overview/Architecture/Modules
    # tree is easy to miss, and the UI relabels 模块 → 按目录 so it looks done.
    if not sidebar_has_topic_groups(raw_sidebar):
        ranked = rank_and_cap_directory_sidebar(
            prune_sidebar_missing_pages(
                prune_generic_web_sidebar(
                    rebuild_topic_sidebar(kept_pages, language=content_lang()),
                    content_by_id,
                ),
                page_id_set,
            ),
            pages=kept_pages,
        )
        mapped_sidebar = map_sidebar(ranked)
    else:
        ranked = rank_and_cap_directory_sidebar(
            prune_sidebar_missing_pages(
                prune_generic_web_sidebar(raw_sidebar, content_by_id),
                page_id_set,
            ),
            pages=kept_pages,
        )
        mapped_sidebar = map_sidebar(ranked)

    return WikiOut(
        repository_id=repository_id,
        repository_version_id=version.id,
        project_name=payload.get("project_name") or "",
        pages=pages,
        sidebar=mapped_sidebar,
    )


def path_out(
    path: LearningPath,
    file_texts: dict[str, str] | None = None,
) -> LearningPathOut:
    """GET-upgrade the learning path: rank, filter fillers, rebuild worksheets.

    Concept wiki pages are untouched. Refresh is enough when source_references
    already exist and the scan store still has the file text (so a ``:1`` chip
    can be resolved to ``start_turn``). Re-scan only if refs are empty or
    point at the wrong file.
    """
    if file_texts is None:
        version_id = getattr(path, "repository_version_id", None)
        if version_id:
            from recallstack.learning.code_loader import load_version_file_texts

            file_texts = load_version_file_texts(version_id)
    file_texts = file_texts or {}
    if not file_texts:
        logger.warning(
            "learning-path GET: scan store empty for version %s; "
            "will not emit toml/json/sh chips — re-scan if file texts were never persisted",
            getattr(path, "repository_version_id", ""),
        )

    candidates: list[tuple[int, str, object, object]] = []
    for n in path.nodes or []:
        concept = getattr(n, "concept", None)
        slug = concept.slug if concept else ""
        title = concept.title if concept else ""
        wiki_id = getattr(concept, "wiki_page_id", None) if concept else None
        if is_filler_slug_title(slug, title):
            continue
        if is_web_filler_path_slug(slug, wiki_id) or (
            is_generic_web_slug(slug) and not (wiki_id or "").startswith("topics/")
        ):
            continue
        candidates.append((path_rank(slug), slug or "", n, concept))
    selected_slugs = {item[1] for item in candidates}
    candidates = [
        item for item in candidates if not drop_duplicate_entry_slug(item[1], selected_slugs)
    ]
    candidates.sort(key=lambda item: (item[0], item[1]))

    nodes: list[LearningPathNodeOut] = []
    for _rank, slug, n, concept in candidates[:CORE_PATH_CAP]:
        title = concept.title if concept else ""
        nodes.append(
            LearningPathNodeOut(
                id=n.id,
                concept_id=n.concept_id,
                position=len(nodes) + 1,
                reason=step_task_for_slug(slug, title) if slug else (n.reason or ""),
                concept=concept_out(concept) if concept else None,
                principles=path_principles(concept) if concept else "",
                evidence_chip=path_evidence_chip(concept, file_texts=file_texts)
                if concept
                else None,
                pass_gate=pass_gate(concept) if concept else "",
                worksheet=path_worksheet(concept, file_texts=file_texts) if concept else "",
            )
        )
    return LearningPathOut(
        id=path.id,
        repository_version_id=path.repository_version_id,
        title=path.title,
        description=path_mission(),
        estimated_minutes=path.estimated_minutes,
        nodes=nodes,
    )


def item_out(
    item: LearningItem,
    *,
    detail: bool = False,
    evidence_snippets: list | None = None,
):
    base = dict(
        id=item.id,
        concept_id=item.concept_id,
        item_type=item.item_type,
        prompt=item.prompt,
        difficulty=item.difficulty,
        source_references=item.source_references or [],
        stale=bool(item.stale),
        evidence_snippets=evidence_snippets or [],
    )
    if detail:
        return LearningItemDetailOut(
            **base,
            rubric=item.rubric or {},
            expected_answer_outline=item.expected_answer_outline or "",
        )
    return LearningItemOut(**base)


def attempt_out(
    attempt: Attempt,
    *,
    mastery_score: float | None = None,
    next_review_at=None,
    expected_answer_outline: str | None = None,
    evaluation_source: str | None = None,
    concept_id: str | None = None,
    next_item_id: str | None = None,
    session=None,
) -> AttemptOut:
    source = evaluation_source
    if source is None and isinstance(attempt.evaluation, dict):
        source = attempt.evaluation.get("evaluation_source")
    return AttemptOut(
        id=attempt.id,
        learning_item_id=attempt.learning_item_id,
        answer=attempt.answer,
        score=attempt.score,
        confidence=attempt.confidence,
        hints_used=attempt.hints_used or [],
        duration_seconds=attempt.duration_seconds,
        evaluation=attempt.evaluation or {},
        fsrs_rating=attempt.fsrs_rating,
        revealed_answer=bool(attempt.revealed_answer),
        created_at=attempt.created_at,
        mastery_score=mastery_score,
        next_review_at=next_review_at,
        expected_answer_outline=expected_answer_outline,
        evaluation_source=source,
        concept_id=concept_id,
        next_item_id=next_item_id,
        session=session,
    )


def _safe_location(location: str, source_type: str) -> str:
    """Avoid leaking unrelated absolute paths for local repos in API responses."""
    if source_type != "local":
        return location
    # keep last 3 path parts only
    parts = location.replace("\\", "/").split("/")
    if len(parts) <= 3:
        return location
    return ".../" + "/".join(parts[-3:])
