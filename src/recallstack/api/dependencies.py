"""FastAPI dependencies for RecallStack."""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy.orm import Session

from recallstack.config import DEFAULT_USER_ID, RecallStackConfig
from recallstack.db.repositories import RepositoryStore
from recallstack.db.session import get_session_factory


def get_config() -> RecallStackConfig:
    return RecallStackConfig.load()


def get_db_session() -> Generator[Session, None, None]:
    factory = get_session_factory()
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_current_user_id(config: RecallStackConfig | None = None) -> str:
    cfg = config or RecallStackConfig.load()
    return cfg.default_user_id or DEFAULT_USER_ID


def ensure_user(session: Session, user_id: str | None = None) -> str:
    cfg = RecallStackConfig.load()
    uid = user_id or cfg.default_user_id
    store = RepositoryStore(session)
    store.ensure_default_user(uid)
    return uid
