"""Shared domain schemas used across learning modules and APIs."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class SourceReference(BaseModel):
    path: str
    start_line: int | None = None
    end_line: int | None = None
    symbol: str | None = None
    commit_sha: str | None = None

    @field_validator("path")
    @classmethod
    def path_not_empty(cls, v: str) -> str:
        v = v.strip().replace("\\", "/")
        if not v or v.startswith("/") or ".." in v.split("/"):
            raise ValueError("invalid source path")
        return v


class RubricPoint(BaseModel):
    id: str
    description: str
    weight: float = 0.2
    source_references: list[SourceReference] = Field(default_factory=list)


class Rubric(BaseModel):
    required_points: list[RubricPoint] = Field(default_factory=list)
    common_misconceptions: list[str] = Field(default_factory=list)
    maximum_score: float = 1.0


class ConceptTermTip(BaseModel):
    """Repo-specific jargon on a learning concept page (术语小贴士)."""

    term: str
    tip: str = ""


class ConceptDraft(BaseModel):
    slug: str
    title: str
    description: str = ""
    difficulty: int = 2
    importance: float = 0.5
    why_learn: str = ""
    estimated_minutes: int = 15
    source_references: list[SourceReference] = Field(default_factory=list)
    prerequisites: list[str] = Field(default_factory=list)  # slugs
    not_this: list[str] = Field(default_factory=list)
    term_tips: list[ConceptTermTip] = Field(default_factory=list)


class ConceptGenerationResult(BaseModel):
    concepts: list[ConceptDraft] = Field(default_factory=list)


class LearningPathNodeDraft(BaseModel):
    concept_slug: str
    position: int
    reason: str = ""


class LearningPathGenerationResult(BaseModel):
    title: str = "Core understanding path"
    description: str = ""
    estimated_minutes: int = 60
    nodes: list[LearningPathNodeDraft] = Field(default_factory=list)


class LearningItemDraft(BaseModel):
    item_type: Literal["active_recall", "code_trace", "teach_back"] = "active_recall"
    prompt: str
    expected_answer_outline: str = ""
    difficulty: int = 2
    rubric: Rubric = Field(default_factory=Rubric)
    source_references: list[SourceReference] = Field(default_factory=list)


class LearningItemGenerationResult(BaseModel):
    items: list[LearningItemDraft] = Field(default_factory=list)


class AttemptEvaluationResult(BaseModel):
    score: float = 0.0
    covered_points: list[str] = Field(default_factory=list)
    missing_points: list[str] = Field(default_factory=list)
    misconceptions: list[str] = Field(default_factory=list)
    source_evidence: list[SourceReference] = Field(default_factory=list)
    feedback: str = ""
    suggested_revision: str = ""
    follow_up_question: str = ""

    @field_validator("score")
    @classmethod
    def clamp_score(cls, v: float) -> float:
        return max(0.0, min(1.0, float(v)))


class ErrorBody(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class RepositoryCreate(BaseModel):
    name: str | None = None
    source_type: Literal["local", "github"] = "local"
    source_location: str
    default_branch: str = "main"


class RepositoryOut(BaseModel):
    id: str
    name: str
    source_type: str
    source_location: str
    default_branch: str
    created_at: datetime
    updated_at: datetime


class VersionOut(BaseModel):
    id: str
    repository_id: str
    commit_sha: str
    content_hash: str
    status: str
    progress_message: str | None = None
    error_message: str | None = None
    has_wiki: bool = False
    created_at: datetime
    completed_at: datetime | None = None


class WikiPageOut(BaseModel):
    id: str
    title: str
    content: str
    parent_id: str = ""
    order: int = 0
    concept_id: str | None = None
    concept_slug: str | None = None


class WikiSidebarItemOut(BaseModel):
    title: str
    page_id: str = ""
    children: list["WikiSidebarItemOut"] = Field(default_factory=list)


class WikiOut(BaseModel):
    repository_id: str
    repository_version_id: str
    project_name: str
    pages: list[WikiPageOut]
    sidebar: list[WikiSidebarItemOut]


class WikiSearchResultOut(BaseModel):
    page_id: str
    title: str
    kind: str
    score: float
    matched_terms: int = 0
    snippet: str = ""
    concept_id: str | None = None


class WikiSearchOut(BaseModel):
    query: str
    total: int
    results: list[WikiSearchResultOut] = Field(default_factory=list)


class WikiAskTurn(BaseModel):
    question: str = Field(max_length=2000)
    answer: str = Field(max_length=20000)


class WikiAskIn(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    # Prior turns, oldest first, so follow-ups can say "it" and "那个函数".
    history: list[WikiAskTurn] = Field(default_factory=list, max_length=8)


class WikiAskSourceOut(BaseModel):
    page_id: str
    title: str
    kind: str
    snippet: str = ""


class WikiAskOut(BaseModel):
    question: str
    answer: str
    # "llm" when a model wrote the answer; "search" for the extractive fallback.
    engine: str
    sources: list[WikiAskSourceOut] = Field(default_factory=list)


class ConceptOut(BaseModel):
    id: str
    repository_id: str
    repository_version_id: str
    slug: str
    title: str
    description: str
    difficulty: int
    importance: float
    source_references: list[dict[str, Any]]
    content_hash: str
    stale: bool
    why_learn: str = ""
    estimated_minutes: int = 15
    wiki_page_id: str | None = None
    mastery_score: float | None = None
    next_review_at: datetime | None = None


class ConceptEdgeOut(BaseModel):
    id: str
    source_concept_id: str
    target_concept_id: str
    relation_type: str


class ConceptGraphOut(BaseModel):
    concepts: list[ConceptOut]
    edges: list[ConceptEdgeOut]


class LearningPathNodeOut(BaseModel):
    id: str
    concept_id: str
    position: int
    reason: str
    concept: ConceptOut | None = None


class LearningPathOut(BaseModel):
    id: str
    repository_version_id: str
    title: str
    description: str
    estimated_minutes: int
    nodes: list[LearningPathNodeOut]


class EvidenceSnippet(BaseModel):
    path: str
    start_line: int | None = None
    end_line: int | None = None
    symbol: str | None = None
    commit_sha: str | None = None
    snippet: str = ""
    available: bool = False


class LearningItemOut(BaseModel):
    id: str
    concept_id: str
    item_type: str
    prompt: str
    difficulty: int
    source_references: list[dict[str, Any]]
    stale: bool
    # Safe evidence windows for the session UI (no full answer outline).
    evidence_snippets: list[EvidenceSnippet] = Field(default_factory=list)
    # never expose outline/rubric until after attempt submission in session UX;
    # API may include them for review after attempt.


class LearningItemDetailOut(LearningItemOut):
    rubric: dict[str, Any] = Field(default_factory=dict)
    expected_answer_outline: str = ""


class HintRequest(BaseModel):
    current_level: int = 0
    hints_used: list[dict[str, Any]] = Field(default_factory=list)


class HintResponse(BaseModel):
    level: int
    content: str
    revealed_answer: bool = False


class AttemptCreate(BaseModel):
    answer: str
    confidence: int = Field(default=3, ge=1, le=5)
    hints_used: list[dict[str, Any]] = Field(default_factory=list)
    duration_seconds: int = 0
    revealed_answer: bool = False


class AttemptOut(BaseModel):
    id: str
    learning_item_id: str
    answer: str
    score: float
    confidence: int
    hints_used: list[dict[str, Any]]
    duration_seconds: int
    evaluation: dict[str, Any]
    fsrs_rating: int | None
    revealed_answer: bool
    created_at: datetime
    mastery_score: float | None = None
    next_review_at: datetime | None = None
    expected_answer_outline: str | None = None
    evaluation_source: str | None = None
    concept_id: str | None = None
    next_item_id: str | None = None
    session: "SessionQueueOut | None" = None


class SessionQueueItemOut(BaseModel):
    id: str
    item_type: str
    prompt: str
    difficulty: int = 2
    stale: bool = False
    attempted: bool = False


class SessionQueueOut(BaseModel):
    mode: Literal["concept", "review"] = "concept"
    concept_id: str
    concept_title: str
    repository_id: str
    item_ids: list[str] = Field(default_factory=list)
    position: int = 1
    total: int = 0
    current_item_id: str
    next_item_id: str | None = None
    prev_item_id: str | None = None
    remaining_count: int = 0
    completed_count: int = 0
    items: list[SessionQueueItemOut] = Field(default_factory=list)
    current_item: LearningItemOut | None = None


class DueReviewOut(BaseModel):
    concept_id: str
    title: str
    mastery_score: float
    next_review_at: datetime | None
    stale: bool = False
    item_id: str | None = None
    # Never attempted: queued for its first study pass rather than a re-review.
    is_new: bool = False


class DashboardOut(BaseModel):
    due_review_count: int
    learning_concept_count: int
    interval_review_count: int
    code_trace_count: int
    current_repository: RepositoryOut | None = None
    recent_concepts: list[ConceptOut] = Field(default_factory=list)
    weak_concepts: list[ConceptOut] = Field(default_factory=list)
    due_reviews: list[DueReviewOut] = Field(default_factory=list)
    progress_percent: float = 0.0
