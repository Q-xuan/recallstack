"""Turn a conceptual topic plan into RecallStack learning concepts.

RepoWiki's ``topics.py`` must not import recallstack; this is the glue.
"""

from __future__ import annotations

from typing import Any

from recallstack.domain.schemas import ConceptDraft, SourceReference
from recallstack.learning.i18n import t
from recallstack.learning.learning_contract import step_task_for_slug
from repowiki.core.models import ProjectContext, TopicOutline
from repowiki.core.topics import wiki_page_id_for_topic


def topics_to_concepts(
    topics: list[TopicOutline],
    project: ProjectContext,
    *,
    commit_sha: str = "",
    files_by_path: dict[str, Any] | None = None,
    make_refs=None,
) -> list[ConceptDraft]:
    """Overview first, then 深入探索 topics. Quick start is not a path node."""
    files_by_path = files_by_path or {f.path: f for f in project.files}
    drafts: list[ConceptDraft] = []

    readme = next(
        (f.path for f in project.files if f.path.lower() in {"readme.md", "readme"}),
        "",
    )
    overview_refs = _refs(
        make_refs, [readme] if readme else [], files_by_path, commit_sha, "project-goal"
    )
    drafts.append(
        ConceptDraft(
            slug="project-goal",
            title=t("Project goal", "项目目标"),
            description=t(
                f"{project.name}: what it is for, and what it does not do.",
                f"{project.name}：给谁用、解决什么、明确不做什么。",
            ),
            difficulty=1,
            importance=1.0,
            why_learn=t(
                "State the goal before reading any system page.",
                "先讲清目标，再读各个系统页。",
            ),
            estimated_minutes=10,
            source_references=overview_refs,
            prerequisites=[],
            task=step_task_for_slug("project-goal"),
            wiki_page_id="index",
        )
    )

    prev = "project-goal"
    for topic in topics:
        if topic.section == "getting-started" or topic.id == "getting-started":
            continue
        refs = _refs(make_refs, list(topic.key_files), files_by_path, commit_sha, topic.id)
        drafts.append(
            ConceptDraft(
                slug=topic.id,
                title=topic.title or topic.id,
                description=topic.purpose
                or t(
                    f"How `{topic.title}` sits on the call path.",
                    f"{topic.title} 在调用链上接住哪一段工作。",
                ),
                difficulty=3 if topic.depth == "deep" else 2,
                importance=0.9 if topic.depth == "deep" else 0.75,
                why_learn=topic.purpose,
                estimated_minutes=15 if topic.depth == "deep" else 12,
                source_references=refs,
                prerequisites=[prev],
                task=step_task_for_slug(topic.id, topic.title),
                wiki_page_id=wiki_page_id_for_topic(topic.id),
            )
        )
        prev = topic.id
    return drafts


def _refs(
    make_refs,
    paths: list[str],
    files_by_path: dict[str, Any],
    commit_sha: str,
    slug: str = "",
):
    if make_refs is not None:
        return make_refs(paths, files_by_path, commit_sha, slug)
    from recallstack.learning.learning_contract import bind_concept_source_references

    store = {
        (p or "").replace("\\", "/"): (getattr(f, "content", None) or getattr(f, "preview", None) or "")
        for p, f in (files_by_path or {}).items()
        if f and (getattr(f, "content", None) or getattr(f, "preview", None))
    }
    return bind_concept_source_references(paths, store, slug=slug, commit_sha=commit_sha)
