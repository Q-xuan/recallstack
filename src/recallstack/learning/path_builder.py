"""Build a single core understanding learning path from concepts."""

from __future__ import annotations

from collections import defaultdict, deque

from recallstack.domain.schemas import (
    ConceptDraft,
    LearningPathGenerationResult,
    LearningPathNodeDraft,
)
from recallstack.learning.i18n import t

# preferred thematic order for core path
_THEME_ORDER = [
    "project-goal",
    "application-entry",
    "configuration",
    "request-routing",
    "authentication",
    "data-persistence",
    "caching",
    "error-handling",
    "background-tasks",
    "testing-structure",
]


class PathBuilder:
    def build(self, concepts: list[ConceptDraft]) -> LearningPathGenerationResult:
        if not concepts:
            return LearningPathGenerationResult(
                title=t("Core understanding path", "核心理解路径"),
                description=t("No concepts yet", "暂无概念"),
                estimated_minutes=0,
                nodes=[],
            )

        by_slug = {c.slug: c for c in concepts}
        prereq = {c.slug: [p for p in c.prerequisites if p in by_slug] for c in concepts}

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

        nodes: list[LearningPathNodeDraft] = []
        total_minutes = 0
        for i, slug in enumerate(ordered, start=1):
            c = by_slug[slug]
            total_minutes += c.estimated_minutes or 10
            reason = c.why_learn or t(
                f"Ordered by prerequisites and importance: {c.title}",
                f"按先修关系与重要度安排：{c.title}",
            )
            nodes.append(
                LearningPathNodeDraft(
                    concept_slug=slug,
                    position=i,
                    reason=reason,
                )
            )

        return LearningPathGenerationResult(
            title=t("Core understanding path", "核心理解路径"),
            description=t(
                "A progressive path from project goal to entrypoints, main flow, storage, error handling, and tests.",
                "从项目目标到入口、主流程、存储、错误处理与测试的渐进路径。",
            ),
            estimated_minutes=total_minutes or 60,
            nodes=nodes,
        )
