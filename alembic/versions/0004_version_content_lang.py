"""persist analyze content language on repository versions

Revision ID: 0004_content_lang
Revises: 0003_progress
Create Date: 2026-08-14
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0004_content_lang"
down_revision: Union[str, None] = "0003_progress"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "repository_versions",
        sa.Column("content_lang", sa.String(length=8), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("repository_versions", "content_lang")
