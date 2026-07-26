"""initial recallstack schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-07-22
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "repositories",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("source_location", sa.Text(), nullable=False),
        sa.Column("default_branch", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "repository_versions",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("repository_id", sa.String(length=36), sa.ForeignKey("repositories.id"), nullable=False),
        sa.Column("commit_sha", sa.String(length=64), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("repository_id", "commit_sha", name="uq_repo_commit"),
    )
    op.create_index("ix_repository_versions_repository_id", "repository_versions", ["repository_id"])

    op.create_table(
        "concepts",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("repository_id", sa.String(length=36), sa.ForeignKey("repositories.id"), nullable=False),
        sa.Column(
            "repository_version_id",
            sa.String(length=36),
            sa.ForeignKey("repository_versions.id"),
            nullable=False,
        ),
        sa.Column("slug", sa.String(length=255), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("difficulty", sa.Integer(), nullable=False),
        sa.Column("importance", sa.Float(), nullable=False),
        sa.Column("source_references", sa.JSON(), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("stale", sa.Boolean(), nullable=False),
        sa.Column("why_learn", sa.Text(), nullable=False),
        sa.Column("estimated_minutes", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("repository_version_id", "slug", name="uq_concept_slug_version"),
    )
    op.create_index("ix_concepts_repository_id", "concepts", ["repository_id"])
    op.create_index("ix_concepts_repository_version_id", "concepts", ["repository_version_id"])

    op.create_table(
        "concept_edges",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("source_concept_id", sa.String(length=36), sa.ForeignKey("concepts.id"), nullable=False),
        sa.Column("target_concept_id", sa.String(length=36), sa.ForeignKey("concepts.id"), nullable=False),
        sa.Column("relation_type", sa.String(length=32), nullable=False),
    )
    op.create_index("ix_concept_edges_source_concept_id", "concept_edges", ["source_concept_id"])
    op.create_index("ix_concept_edges_target_concept_id", "concept_edges", ["target_concept_id"])

    op.create_table(
        "learning_paths",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "repository_version_id",
            sa.String(length=36),
            sa.ForeignKey("repository_versions.id"),
            nullable=False,
        ),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("estimated_minutes", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_learning_paths_repository_version_id", "learning_paths", ["repository_version_id"]
    )

    op.create_table(
        "learning_path_nodes",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column(
            "learning_path_id", sa.String(length=36), sa.ForeignKey("learning_paths.id"), nullable=False
        ),
        sa.Column("concept_id", sa.String(length=36), sa.ForeignKey("concepts.id"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
    )
    op.create_index("ix_learning_path_nodes_learning_path_id", "learning_path_nodes", ["learning_path_id"])
    op.create_index("ix_learning_path_nodes_concept_id", "learning_path_nodes", ["concept_id"])

    op.create_table(
        "learning_items",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("concept_id", sa.String(length=36), sa.ForeignKey("concepts.id"), nullable=False),
        sa.Column("item_type", sa.String(length=32), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("rubric", sa.JSON(), nullable=True),
        sa.Column("expected_answer_outline", sa.Text(), nullable=False),
        sa.Column("source_references", sa.JSON(), nullable=True),
        sa.Column("difficulty", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("stale", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_learning_items_concept_id", "learning_items", ["concept_id"])

    op.create_table(
        "attempts",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column(
            "learning_item_id", sa.String(length=36), sa.ForeignKey("learning_items.id"), nullable=False
        ),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("confidence", sa.Integer(), nullable=False),
        sa.Column("hints_used", sa.JSON(), nullable=True),
        sa.Column("duration_seconds", sa.Integer(), nullable=False),
        sa.Column("evaluation", sa.JSON(), nullable=True),
        sa.Column("fsrs_rating", sa.Integer(), nullable=True),
        sa.Column("revealed_answer", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_attempts_learning_item_id", "attempts", ["learning_item_id"])

    op.create_table(
        "mastery",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("concept_id", sa.String(length=36), sa.ForeignKey("concepts.id"), nullable=False),
        sa.Column("mastery_score", sa.Float(), nullable=False),
        sa.Column("attempts_count", sa.Integer(), nullable=False),
        sa.Column("last_reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_review_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fsrs_card", sa.JSON(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "concept_id", name="uq_mastery_user_concept"),
    )
    op.create_index("ix_mastery_concept_id", "mastery", ["concept_id"])

    op.create_table(
        "review_logs",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("user_id", sa.String(length=36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("concept_id", sa.String(length=36), sa.ForeignKey("concepts.id"), nullable=False),
        sa.Column(
            "learning_item_id", sa.String(length=36), sa.ForeignKey("learning_items.id"), nullable=True
        ),
        sa.Column("attempt_id", sa.String(length=36), sa.ForeignKey("attempts.id"), nullable=True),
        sa.Column("rating", sa.Integer(), nullable=False),
        sa.Column("fsrs_review_log", sa.JSON(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("next_review_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_review_logs_concept_id", "review_logs", ["concept_id"])


def downgrade() -> None:
    op.drop_table("review_logs")
    op.drop_table("mastery")
    op.drop_table("attempts")
    op.drop_table("learning_items")
    op.drop_table("learning_path_nodes")
    op.drop_table("learning_paths")
    op.drop_table("concept_edges")
    op.drop_table("concepts")
    op.drop_table("repository_versions")
    op.drop_table("repositories")
    op.drop_table("users")
