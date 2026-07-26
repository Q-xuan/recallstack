# Architecture

## Product boundary

RecallStack is **one product**: scan a repository once, then read its Wiki, walk concepts, practice, and review.

- `src/repowiki` — knowledge engine (scan, graph, wiki builders, RAG, LiteLLM, cache)
- `src/recallstack` — learning system + fusion layer (concepts, path, items, attempts, mastery, FSRS, wiki payload persistence)
- `frontend` — single shell: Dashboard / Repository workbench / Concept / Session / Review

## Product principle

**Wiki is primary. Learning is attached.**

- Reading flow lives in the repository workbench (`RepositoryPage`)
- Concept pages under `concepts/*` are first-class wiki pages
- Practice (probe / session) attaches to the current wiki page; it is not a parallel app
- Generated content language is **shared with RepoWiki**: `en` / `zh` / `ja` / `ko`
  - Resolve: `RECALLSTACK_CONTENT_LANG` → `REPOWIKI_LANG` → `~/.repowiki/config.json` → `en`
  - Deterministic templates: `recallstack.learning.i18n.t`
  - LLM prompts: same `lang_instruction` strings as `repowiki.llm.prompts`

## Fusion model (v0.1)

```
scan_repository
  -> dependency graph
  -> extract_concepts
  -> build_wiki_payload (WikiBuilder + concept pages)
  -> build_learning_path
  -> generate_learning_items
  -> persist repository_versions.wiki_pages + concepts + items
```

Shared objects:

| Object | Storage | Notes |
|---|---|---|
| Repository / Version | `repositories`, `repository_versions` | version carries `wiki_pages` JSON |
| Wiki pages | `repository_versions.wiki_pages` | RepoWiki-compatible `{project_name, pages, sidebar}` |
| Concepts | `concepts` | `wiki_page_id` links to `concepts/{slug}` page |
| Learning path / items | `learning_paths*`, `learning_items` | generated from the same concept set |
| Mastery / reviews | `mastery`, `review_logs`, `attempts` | user learning state |

## Data isolation

- RepoWiki cache (optional LLM/wiki cache): `~/.repowiki/cache.db`
- RecallStack learning DB: `RECALLSTACK_DATABASE_URL` (default `./data/recallstack.db`)
- Wiki markdown for the product UI is **not** a second in-memory product store; it is persisted on the analyzed version.

## Request flow

```
UI  -> /api/recallstack/*
    -> application services
    -> learning/* + repowiki.core.*
    -> SQLite (RECALLSTACK_DATABASE_URL)
```

Key endpoints:

- `POST /repositories/{id}/analyze` — one scan produces wiki + learning
- `GET  /repositories/{id}/wiki` — full wiki payload
- `GET  /repositories/{id}/wiki/pages/{page_id}` — single page (+ concept binding)
- `GET  /repositories/{id}/concepts` / `learning-path` — learning graph
- `GET  /sessions/concept/{id}` / `/sessions/item/{id}` / `/sessions/review` — practice queue
- `POST /items/{id}/attempts` — evaluate (+ optional LLM blend) and return next item

## Session queue

`SessionQueueService` orders a concept's items:
`active_recall → code_trace → teach_back`.

Submit response carries `next_item_id` + queue progress so the UI can run a continuous session.

## Evaluation path

```
deterministic rubric scorer (always)
  optional StructuredLLM grade (if RECALLSTACK_LLM_* enabled + provider key)
  blend scores (LLM primary, evidence anchor from deterministic)
  mastery + FSRS update
```

## Frontend workbench

`RepositoryPage` is the unified workbench:

- **阅读** — sidebar + Wiki markdown (`WikiContent`)
- **学习** — learning path / concepts (each concept links to its wiki page)
- **复习** — due items entry

Legacy routes (`/learn/*`, `/wiki`, `/wiki-tools`, `/project/*`) redirect into the unified routes.

## Jobs

`InProcessJobRunner` executes analyze jobs in-process for v0.1. Protocol allows a future queue swap.

## Migrations

- `0001_initial_recallstack` — learning schema
- `0002_wiki_pages_on_version` — `repository_versions.wiki_pages`, `concepts.wiki_page_id`
- Dev bootstrap also adds missing additive columns when Alembic has not been run
