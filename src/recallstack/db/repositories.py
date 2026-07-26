"""Data access helpers for RecallStack entities."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from recallstack.db.models import (
    Attempt,
    Concept,
    ConceptEdge,
    LearningItem,
    LearningPath,
    LearningPathNode,
    Mastery,
    Repository,
    RepositoryVersion,
    ReviewLog,
    User,
    utcnow,
)


class RepositoryStore:
    def __init__(self, session: Session):
        self.session = session

    def ensure_default_user(self, user_id: str, name: str = "default-user") -> User:
        user = self.session.get(User, user_id)
        if user:
            return user
        user = User(id=user_id, name=name)
        self.session.add(user)
        self.session.flush()
        return user

    def create_repository(
        self,
        *,
        name: str,
        source_type: str,
        source_location: str,
        default_branch: str = "main",
    ) -> Repository:
        repo = Repository(
            name=name,
            source_type=source_type,
            source_location=source_location,
            default_branch=default_branch,
        )
        self.session.add(repo)
        self.session.flush()
        return repo

    def list_repositories(self) -> list[Repository]:
        return list(self.session.scalars(select(Repository).order_by(Repository.created_at.desc())))

    def get_repository(self, repository_id: str) -> Repository | None:
        return self.session.get(Repository, repository_id)

    def get_latest_version(self, repository_id: str) -> RepositoryVersion | None:
        stmt = (
            select(RepositoryVersion)
            .where(RepositoryVersion.repository_id == repository_id)
            .order_by(RepositoryVersion.created_at.desc())
            .limit(1)
        )
        return self.session.scalars(stmt).first()

    def get_version_by_commit(
        self, repository_id: str, commit_sha: str
    ) -> RepositoryVersion | None:
        stmt = select(RepositoryVersion).where(
            RepositoryVersion.repository_id == repository_id,
            RepositoryVersion.commit_sha == commit_sha,
        )
        return self.session.scalars(stmt).first()

    def create_version(
        self,
        *,
        repository_id: str,
        commit_sha: str,
        content_hash: str = "",
        status: str = "pending",
    ) -> RepositoryVersion:
        version = RepositoryVersion(
            repository_id=repository_id,
            commit_sha=commit_sha,
            content_hash=content_hash,
            status=status,
        )
        self.session.add(version)
        self.session.flush()
        return version

    def list_concepts(self, repository_id: str, version_id: str | None = None) -> list[Concept]:
        stmt = select(Concept).where(Concept.repository_id == repository_id)
        if version_id:
            stmt = stmt.where(Concept.repository_version_id == version_id)
        stmt = stmt.order_by(Concept.importance.desc())
        return list(self.session.scalars(stmt))

    def get_concept(self, concept_id: str) -> Concept | None:
        return self.session.get(Concept, concept_id)

    def list_edges_for_concepts(self, concept_ids: list[str]) -> list[ConceptEdge]:
        if not concept_ids:
            return []
        stmt = select(ConceptEdge).where(
            ConceptEdge.source_concept_id.in_(concept_ids)
            | ConceptEdge.target_concept_id.in_(concept_ids)
        )
        return list(self.session.scalars(stmt))

    def get_learning_path(self, repository_version_id: str) -> LearningPath | None:
        stmt = (
            select(LearningPath)
            .options(selectinload(LearningPath.nodes).selectinload(LearningPathNode.concept))
            .where(LearningPath.repository_version_id == repository_version_id)
            .order_by(LearningPath.created_at.desc())
            .limit(1)
        )
        return self.session.scalars(stmt).first()

    def list_items(self, concept_id: str) -> list[LearningItem]:
        stmt = (
            select(LearningItem)
            .where(LearningItem.concept_id == concept_id)
            .order_by(LearningItem.created_at.asc())
        )
        return list(self.session.scalars(stmt))

    def get_item(self, item_id: str) -> LearningItem | None:
        return self.session.get(LearningItem, item_id)

    def latest_attempt_for_item(self, user_id: str, item_id: str) -> Attempt | None:
        stmt = (
            select(Attempt)
            .where(Attempt.user_id == user_id, Attempt.learning_item_id == item_id)
            .order_by(Attempt.created_at.desc())
            .limit(1)
        )
        return self.session.scalars(stmt).first()

    def create_attempt(self, **kwargs) -> Attempt:
        attempt = Attempt(**kwargs)
        self.session.add(attempt)
        self.session.flush()
        return attempt

    def get_mastery(self, user_id: str, concept_id: str) -> Mastery | None:
        stmt = select(Mastery).where(Mastery.user_id == user_id, Mastery.concept_id == concept_id)
        return self.session.scalars(stmt).first()

    def upsert_mastery(self, mastery: Mastery) -> Mastery:
        self.session.add(mastery)
        self.session.flush()
        return mastery

    def create_review_log(self, **kwargs) -> ReviewLog:
        log = ReviewLog(**kwargs)
        self.session.add(log)
        self.session.flush()
        return log

    def due_masteries(self, user_id: str, now: datetime | None = None) -> list[Mastery]:
        now = now or utcnow()
        # normalize naive timestamps for sqlite
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        stmt = (
            select(Mastery)
            .where(Mastery.user_id == user_id)
            .where(Mastery.next_review_at.is_not(None))
            .where(Mastery.next_review_at <= now)
            .order_by(Mastery.next_review_at.asc())
        )
        return list(self.session.scalars(stmt))

    def unlearned_concepts(self, user_id: str, limit: int = 10) -> list[Concept]:
        """Concepts this user has never attempted, most important first.

        These seed the review queue: without them a fresh install has no
        mastery rows, ``due_masteries`` is empty forever, and review mode is a
        dead end until the user happens to self-test from a concept page.
        """
        learned = select(Mastery.concept_id).where(Mastery.user_id == user_id)
        stmt = (
            select(Concept)
            .where(Concept.id.not_in(learned))
            .where(Concept.stale.is_(False))
            .order_by(Concept.importance.desc(), Concept.created_at.asc())
            .limit(limit)
        )
        return list(self.session.scalars(stmt))

    def recent_attempts(self, user_id: str, limit: int = 10) -> list[Attempt]:
        stmt = (
            select(Attempt)
            .where(Attempt.user_id == user_id)
            .order_by(Attempt.created_at.desc())
            .limit(limit)
        )
        return list(self.session.scalars(stmt))
