# Learning Design

## Principles

1. Concepts must map to real code evidence.
2. Questions first, answers after submission.
3. Hints are progressive (module → file → symbol → partial chain → outline).
4. Evaluation is rubric-first, not wording similarity.
5. Spaced repetition via FSRS, with score/hint-aware rating mapping.
6. Evidence is a first-class learning signal: path/symbol citation beats fluent prose.

## Evidence loop (v0.1.1+)

```
source_references on concept/item
  -> session UI evidence snippets (local repo, sandbox path, collapsed by default)
  -> hint level 4 partial chain loads real code windows
  -> rubric scorer rewards path + symbol hits, soft-penalizes missing evidence
  -> optional LLM evaluation blended with deterministic evidence anchor
```

Local-only snippet loading goes through `learning/code_loader.py` (path stay-under-root + blocked secrets).

## Session queue

A concept practice run is a queue, not a single page hop:

1. `GET /sessions/concept/{id}` or `/sessions/item/{id}`
2. answer → `POST /items/{id}/attempts`
3. UI follows `next_item_id` until the queue ends
4. review mode uses the same queue with `?mode=review`

Item order: `active_recall` → `code_trace` → `teach_back`.

## Item types (v0.1)

- `active_recall`
- `code_trace`
- `teach_back`

## Mastery

`MasteryCalculator` blends rubric score with hint usage and confidence calibration, then FSRS updates `next_review_at`.
