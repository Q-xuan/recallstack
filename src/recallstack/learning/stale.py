"""Mark learning content stale when source files change across versions."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from recallstack.db.models import Concept, LearningItem, RepositoryVersion


def mark_stale_for_changed_files(
    session: Session,
    *,
    old_version: RepositoryVersion | None,
    new_version: RepositoryVersion,
    changed_paths: set[str],
) -> int:
    """Mark concepts/items whose source_references intersect changed_paths.

    Returns number of concepts marked stale.
    """
    if not old_version or not changed_paths:
        return 0

    concepts = list(
        session.scalars(
            select(Concept).where(Concept.repository_version_id == old_version.id)
        )
    )
    marked = 0
    for concept in concepts:
        refs = concept.source_references or []
        paths = {str(r.get("path", "")).replace("\\", "/") for r in refs}
        if paths & changed_paths:
            concept.stale = True
            marked += 1
            items = list(
                session.scalars(
                    select(LearningItem).where(LearningItem.concept_id == concept.id)
                )
            )
            for item in items:
                item.stale = True
    session.flush()
    return marked


def compute_changed_paths(
    old_file_hashes: dict[str, str],
    new_file_hashes: dict[str, str],
) -> set[str]:
    changed: set[str] = set()
    all_paths = set(old_file_hashes) | set(new_file_hashes)
    for path in all_paths:
        if old_file_hashes.get(path) != new_file_hashes.get(path):
            changed.add(path)
    return changed
