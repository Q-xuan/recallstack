"""Build a single core understanding learning path from concepts."""

from __future__ import annotations

from collections import defaultdict, deque

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
    step_task,
)

# Path order follows the topic plan (overview first). Theme ranks only break ties.
_THEME_ORDER = [
    "project-goal",
    "entry-and-boot",
    "application-entry",
]


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

        by_slug = {c.slug: c for c in selected}
        selected_slugs = set(by_slug)
        prereq = {
            c.slug: [p for p in c.prerequisites if p in selected_slugs] for c in selected
        }

        # topological order with importance/theme tie-break
        indeg = {s: 0 for s in by_slug}
        children: dict[str, list[str]] = defaultdict(list)
        for s, ps in prereq.items():
            for p in ps:
                children[p].append(s)
                indeg[s] += 1

        theme_rank = {slug: i for i, slug in enumerate(_THEME_ORDER)}

        def sort_key(slug: str) -> tuple:
            c = by_slug[slug]
            return (
                theme_rank.get(slug, 100),
                -c.importance,
                c.difficulty,
                slug,
            )

        ready = sorted([s for s, d in indeg.items() if d == 0], key=sort_key)
        ordered: list[str] = []
        q = deque(ready)
        while q:
            # re-sort frontier for stable priority
            frontier = sorted(q, key=sort_key)
            q = deque(frontier)
            n = q.popleft()
            ordered.append(n)
            for ch in children[n]:
                indeg[ch] -= 1
                if indeg[ch] == 0:
                    q.append(ch)

        # append any leftover (shouldn't happen if acyclic)
        for s in by_slug:
            if s not in ordered:
                ordered.append(s)

        ordered = ordered[:CORE_PATH_CAP]

        nodes: list[LearningPathNodeDraft] = []
        total_minutes = 0
        for i, slug in enumerate(ordered, start=1):
            c = by_slug[slug]
            total_minutes += c.estimated_minutes or 10
            nodes.append(
                LearningPathNodeDraft(
                    concept_slug=slug,
                    position=i,
                    reason=step_task(c),
                )
            )

        return LearningPathGenerationResult(
            title=t("Core understanding path", "核心理解路径"),
            description=path_mission(),
            estimated_minutes=total_minutes or 60,
            nodes=nodes,
        )
