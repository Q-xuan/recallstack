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
    overview_refs = _refs(make_refs, [readme] if readme else [], files_by_path, commit_sha)
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
        refs = _refs(make_refs, list(topic.key_files), files_by_path, commit_sha)
        drafts.append(
            ConceptDraft(
                slug=topic.id,
                title=topic.title or topic.id,
                description=topic.purpose
                or t(
                    f"How `{topic.title}` sits on a real call path.",
                    f"「{topic.title}」在一次真实调用里做什么。",
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


def _refs(make_refs, paths: list[str], files_by_path: dict[str, Any], commit_sha: str):
    if make_refs is not None:
        return make_refs(paths, files_by_path, commit_sha)
    out: list[SourceReference] = []
    for path in paths:
        if not path:
            continue
        f = files_by_path.get(path)
        end = min(getattr(f, "lines", 20) or 20, 40) if f else 20
        out.append(
            SourceReference(
                path=path.replace("\\", "/"),
                start_line=1,
                end_line=end,
                commit_sha=commit_sha or None,
            )
        )
    return out
