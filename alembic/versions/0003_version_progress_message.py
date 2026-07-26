"""track fine-grained analysis progress on repository versions

Revision ID: 0003_progress
Revises: 0002_wiki_pages
Create Date: 2026-07-26
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0003_progress"
down_revision: Union[str, None] = "0002_wiki_pages"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "repository_versions",
        sa.Column("progress_message", sa.String(length=255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("repository_versions", "progress_message")
