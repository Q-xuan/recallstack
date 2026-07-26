# 0002. Separate learning database

## Context

RepoWiki already uses a SQLite cache for LLM outputs.

## Decision

Store learning state in a separate database configured by `RECALLSTACK_DATABASE_URL`.

## Consequences

- Clear ownership boundaries
- Avoid polluting cache schema
- PostgreSQL-compatible SQLAlchemy models for future deploy
