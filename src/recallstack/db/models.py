"""SQLAlchemy models for RecallStack learning system."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON

from recallstack.db.base import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_uuid() -> str:
    return str(uuid.uuid4())


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    name: Mapped[str] = mapped_column(String(128), nullable=False, default="default-user")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Repository(Base):
    __tablename__ = "repositories"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)  # local | github
    source_location: Mapped[str] = mapped_column(Text, nullable=False)
    default_branch: Mapped[str] = mapped_column(String(128), nullable=False, default="main")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    versions: Mapped[list[RepositoryVersion]] = relationship(back_populates="repository")
    concepts: Mapped[list[Concept]] = relationship(back_populates="repository")


class RepositoryVersion(Base):
    __tablename__ = "repository_versions"
    __table_args__ = (UniqueConstraint("repository_id", "commit_sha", name="uq_repo_commit"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    repository_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("repositories.id"), nullable=False, index=True
    )
    commit_sha: Mapped[str] = mapped_column(String(64), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    # RepoWiki-compatible payload: {project_name, pages[], sidebar[]}
    wiki_pages: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    repository: Mapped[Repository] = relationship(back_populates="versions")
    concepts: Mapped[list[Concept]] = relationship(back_populates="repository_version")
    learning_paths: Mapped[list[LearningPath]] = relationship(back_populates="repository_version")


class Concept(Base):
    __tablename__ = "concepts"
    __table_args__ = (
        UniqueConstraint("repository_version_id", "slug", name="uq_concept_slug_version"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    repository_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("repositories.id"), nullable=False, index=True
    )
    repository_version_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("repository_versions.id"), nullable=False, index=True
    )
    slug: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    difficulty: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    importance: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    source_references: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    stale: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    why_learn: Mapped[str] = mapped_column(Text, nullable=False, default="")
    estimated_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=15)
    wiki_page_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    repository: Mapped[Repository] = relationship(back_populates="concepts")
    repository_version: Mapped[RepositoryVersion] = relationship(back_populates="concepts")
    learning_items: Mapped[list[LearningItem]] = relationship(back_populates="concept")


class ConceptEdge(Base):
    __tablename__ = "concept_edges"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    source_concept_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("concepts.id"), nullable=False, index=True
    )
    target_concept_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("concepts.id"), nullable=False, index=True
    )
    relation_type: Mapped[str] = mapped_column(String(32), nullable=False)


class LearningPath(Base):
    __tablename__ = "learning_paths"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    repository_version_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("repository_versions.id"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    estimated_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    repository_version: Mapped[RepositoryVersion] = relationship(back_populates="learning_paths")
    nodes: Mapped[list[LearningPathNode]] = relationship(
        back_populates="learning_path", order_by="LearningPathNode.position"
    )


class LearningPathNode(Base):
    __tablename__ = "learning_path_nodes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    learning_path_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("learning_paths.id"), nullable=False, index=True
    )
    concept_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("concepts.id"), nullable=False, index=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")

    learning_path: Mapped[LearningPath] = relationship(back_populates="nodes")
    concept: Mapped[Concept] = relationship()


class LearningItem(Base):
    __tablename__ = "learning_items"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    concept_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("concepts.id"), nullable=False, index=True
    )
    item_type: Mapped[str] = mapped_column(String(32), nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    rubric: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    expected_answer_outline: Mapped[str] = mapped_column(Text, nullable=False, default="")
    source_references: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    difficulty: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    stale: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    concept: Mapped[Concept] = relationship(back_populates="learning_items")
    attempts: Mapped[list[Attempt]] = relationship(back_populates="learning_item")


class Attempt(Base):
    __tablename__ = "attempts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    learning_item_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("learning_items.id"), nullable=False, index=True
    )
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    confidence: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    hints_used: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    duration_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    evaluation: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    fsrs_rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    revealed_answer: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    learning_item: Mapped[LearningItem] = relationship(back_populates="attempts")


class Mastery(Base):
    __tablename__ = "mastery"
    __table_args__ = (UniqueConstraint("user_id", "concept_id", name="uq_mastery_user_concept"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    concept_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("concepts.id"), nullable=False, index=True
    )
    mastery_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    attempts_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_review_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    fsrs_card: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class ReviewLog(Base):
    __tablename__ = "review_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), nullable=False)
    concept_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("concepts.id"), nullable=False, index=True
    )
    learning_item_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("learning_items.id"), nullable=True
    )
    attempt_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("attempts.id"), nullable=True
    )
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    fsrs_review_log: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    next_review_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
