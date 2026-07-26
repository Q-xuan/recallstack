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
        session.commit()
        logger.info("RecallStack DB ready (%s)", url.split("://")[0])
    finally:
        session.close()


def _ensure_optional_columns(engine) -> None:
    """Dev-friendly additive columns when Alembic hasn't been run yet."""
    from sqlalchemy import inspect, text

    insp = inspect(engine)
    if "repository_versions" in insp.get_table_names():
        cols = {c["name"] for c in insp.get_columns("repository_versions")}
        if "wiki_pages" not in cols:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE repository_versions ADD COLUMN wiki_pages JSON"))
            logger.info("Added repository_versions.wiki_pages")
    if "concepts" in insp.get_table_names():
        cols = {c["name"] for c in insp.get_columns("concepts")}
        if "wiki_page_id" not in cols:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE concepts ADD COLUMN wiki_page_id VARCHAR(255)"))
            logger.info("Added concepts.wiki_page_id")
