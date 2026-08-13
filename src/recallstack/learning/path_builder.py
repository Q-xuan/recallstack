"""Build a single core understanding learning path from concepts."""

from __future__ import annotations

from recallstack.domain.schemas import (
    ConceptDraft,
    LearningPathGenerationResult,
    LearningPathNodeDraft,
)
from recallstack.learning.i18n import t
from recallstack.learning.learning_contract import (
    CORE_PATH_CAP,
    is_core_path_concept,
    is_filler_concept,
    path_mission,
    path_rank,
    step_task_for_slug,
)


class PathBuilder:
    def build(self, concepts: list[ConceptDraft]) -> LearningPathGenerationResult:
        if not concepts:
            return LearningPathGenerationResult(
                title=t("Core understanding path", "核心理解路径"),
                description=path_mission(),
                estimated_minutes=0,
                nodes=[],
            )

        selected = [c for c in concepts if is_core_path_concept(c)]
        if not selected:
            selected = [c for c in concepts if not is_filler_concept(c)]
        if not selected:
            selected = list(concepts)

        selected.sort(key=lambda c: (path_rank(c.slug), -c.importance, c.slug))
        selected = selected[:CORE_PATH_CAP]

        nodes: list[LearningPathNodeDraft] = []
        total_minutes = 0
        for i, c in enumerate(selected, start=1):
            total_minutes += c.estimated_minutes or 10
            nodes.append(
                LearningPathNodeDraft(
                    concept_slug=c.slug,
                    position=i,
                    reason=step_task_for_slug(c.slug, c.title),
                )
            )

        return LearningPathGenerationResult(
            title=t("Core understanding path", "核心理解路径"),
            description=path_mission(),
            estimated_minutes=total_minutes or 60,
            nodes=nodes,
        )
