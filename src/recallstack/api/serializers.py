"""ORM → response schema mappers."""

from __future__ import annotations

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
    is_filler_slug_title,
    path_mission,
    step_task_for_slug,
    upgrade_legacy_concept_markdown,
)
from repowiki.core.wiki_builder import upgrade_legacy_module_markdown


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
    pages: list[WikiPageOut] = []
    for p in payload.get("pages") or []:
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
            )
        elif page_id.startswith("modules/"):
            content = upgrade_legacy_module_markdown(content, language=content_lang())
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

    return WikiOut(
        repository_id=repository_id,
        repository_version_id=version.id,
        project_name=payload.get("project_name") or "",
        pages=pages,
        sidebar=map_sidebar(payload.get("sidebar") or []),
    )


def path_out(path: LearningPath) -> LearningPathOut:
    nodes: list[LearningPathNodeOut] = []
    for n in path.nodes or []:
        concept = getattr(n, "concept", None)
        slug = concept.slug if concept else ""
        title = concept.title if concept else ""
        if is_filler_slug_title(slug, title):
            continue
        nodes.append(
            LearningPathNodeOut(
                id=n.id,
                concept_id=n.concept_id,
                position=len(nodes) + 1,
                reason=step_task_for_slug(slug, title) if slug else (n.reason or ""),
                concept=concept_out(concept) if concept else None,
            )
        )
        if len(nodes) >= CORE_PATH_CAP:
            break
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
