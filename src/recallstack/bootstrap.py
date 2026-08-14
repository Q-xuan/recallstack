"""Bootstrap RecallStack database schema and default user."""

from __future__ import annotations

import logging

from recallstack.config import RecallStackConfig
from recallstack.db import models as _models  # noqa: F401 — register mappers
from recallstack.db.base import Base
from recallstack.db.repositories import RepositoryStore
from recallstack.db.session import get_engine, get_session_factory, reset_engine

logger = logging.getLogger(__name__)


def init_recallstack(database_url: str | None = None) -> None:
    """Create tables if needed and ensure default user exists.

    Alembic is the formal migration path; create_all is a dev bootstrap fallback
    so `repowiki serve` works out of the box for v0.1.
    """
    cfg = RecallStackConfig.load()
    url = database_url or cfg.database_url
    if database_url:
        reset_engine()
    engine = get_engine(url)
    Base.metadata.create_all(bind=engine)
    _ensure_optional_columns(engine)
    factory = get_session_factory(url)
    session = factory()
    try:
        store = RepositoryStore(session)
        store.ensure_default_user(cfg.default_user_id)
        _fail_interrupted_versions(session)
        session.commit()
        logger.info("RecallStack DB ready (%s)", url.split("://")[0])
    finally:
        session.close()


# Statuses that only a live analysis run can move out of. Analyses run in an
# in-process thread, so nothing survives a restart to advance them.
RUNNING_STATUSES = (
    "queued",
    "pending",
    "scanning",
    "generating_concepts",
    "generating_wiki",
    "llm_enriching",
)


def _fail_interrupted_versions(session) -> None:
    """Mark runs abandoned by a previous process as failed.

    A version left mid-pipeline stays there forever otherwise, and the frontend
    polls a status that can never change.
    """
    from recallstack.db.models import RepositoryVersion, utcnow

    orphans = (
        session.query(RepositoryVersion)
        .filter(RepositoryVersion.status.in_(RUNNING_STATUSES))
        .all()
    )
    for version in orphans:
        version.status = "failed"
        version.progress_message = None
        version.error_message = "Analysis was interrupted before it finished. Please run it again."
        version.completed_at = version.completed_at or utcnow()
    if orphans:
        logger.info("Marked %d interrupted analysis run(s) as failed", len(orphans))


# Columns added after 0001, as (table, column, type). create_all() leaves an
# existing table alone, so a database made before one of these was introduced
# needs it backfilled here or every query against that model fails.
_OPTIONAL_COLUMNS: tuple[tuple[str, str, str], ...] = (
    ("repository_versions", "wiki_pages", "JSON"),
    ("repository_versions", "progress_message", "VARCHAR(255)"),
    ("concepts", "wiki_page_id", "VARCHAR(255)"),
    ("learning_paths", "resolved", "JSON"),
    ("repository_versions", "content_lang", "VARCHAR(8)"),
)


def _ensure_optional_columns(engine) -> None:
    """Dev-friendly additive columns when Alembic hasn't been run yet."""
    from sqlalchemy import inspect, text

    insp = inspect(engine)
    tables = set(insp.get_table_names())
    for table, column, coltype in _OPTIONAL_COLUMNS:
        if table not in tables:
            continue
        if column in {c["name"] for c in insp.get_columns(table)}:
            continue
        with engine.begin() as conn:
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {coltype}"))
        logger.info("Added %s.%s", table, column)
