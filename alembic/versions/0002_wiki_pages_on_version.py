"""store wiki pages on repository versions

Revision ID: 0002_wiki_pages
Revises: 0001_initial
Create Date: 2026-07-23
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002_wiki_pages"
down_revision: Union[str, None] = "0001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "repository_versions",
        sa.Column("wiki_pages", sa.JSON(), nullable=True),
    )
    op.add_column(
        "concepts",
        sa.Column("wiki_page_id", sa.String(length=255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("concepts", "wiki_page_id")
    op.drop_column("repository_versions", "wiki_pages")
