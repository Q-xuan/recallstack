"""Learning session queues: concept practice + due review runs."""

from __future__ import annotations

from typing import Any, Literal

from sqlalchemy.orm import Session

from recallstack.config import RecallStackConfig
from recallstack.db.repositories import RepositoryStore
from recallstack.learning.code_loader import (
    load_code_lookup,
    resolve_local_repo_root,
    snippet_for_ref,
)

SessionMode = Literal["concept", "review"]

_ITEM_TYPE_ORDER = {
    "active_recall": 0,
    "code_trace": 1,
    "teach_back": 2,
}


class SessionQueueService:
    def __init__(self, session: Session, config: RecallStackConfig | None = None):
        self.session = session
        self.config = config or RecallStackConfig.load()
        self.store = RepositoryStore(session)

    def concept_queue(self, concept_id: str, *, user_id: str | None = None) -> dict[str, Any]:
        concept = self.store.get_concept(concept_id)
        if not concept:
            raise KeyError("concept_not_found")
        items = self._ordered_items(concept_id)
        if not items:
            raise KeyError("item_not_found")

        attempted: set[str] = set()
        if user_id:
            for item in items:
                if self.store.latest_attempt_for_item(user_id, item.id):
                    attempted.add(item.id)

        # prefer first unattempted item; else first item
        start = next((i for i in items if i.id not in attempted), items[0])
        return self._queue_payload(
            mode="concept",
            concept_id=concept.id,
            concept_title=concept.title,
            repository_id=concept.repository_id,
            items=items,
            current_item_id=start.id,
            attempted_ids=attempted,
        )

    def review_queue(self, user_id: str, *, concept_id: str | None = None) -> dict[str, Any]:
        """Build a review session: one concept's items, or first due concept."""
        if concept_id:
            concept = self.store.get_concept(concept_id)
            if not concept:
                raise KeyError("concept_not_found")
        else:
            due = self.store.due_masteries(user_id)
            if not due:
                raise KeyError("no_due_reviews")
            concept = self.store.get_concept(due[0].concept_id)
            if not concept:
                raise KeyError("concept_not_found")

        items = self._ordered_items(concept.id)
        if not items:
            raise KeyError("item_not_found")
        return self._queue_payload(
            mode="review",
            concept_id=concept.id,
            concept_title=concept.title,
            repository_id=concept.repository_id,
            items=items,
            current_item_id=items[0].id,
            attempted_ids=set(),
        )

    def queue_for_item(
        self,
        item_id: str,
        *,
        mode: SessionMode = "concept",
        user_id: str | None = None,
    ) -> dict[str, Any]:
        item = self.store.get_item(item_id)
        if not item:
            raise KeyError("item_not_found")
        concept = self.store.get_concept(item.concept_id)
        if not concept:
            raise KeyError("concept_not_found")
        items = self._ordered_items(concept.id)
        if not items:
            raise KeyError("item_not_found")

        attempted: set[str] = set()
        if user_id and mode == "concept":
            for it in items:
                if self.store.latest_attempt_for_item(user_id, it.id):
                    attempted.add(it.id)

        return self._queue_payload(
            mode=mode,
            concept_id=concept.id,
            concept_title=concept.title,
            repository_id=concept.repository_id,
            items=items,
            current_item_id=item.id,
            attempted_ids=attempted,
        )

    def evidence_snippets_for_item(self, item) -> list[dict[str, Any]]:
        concept = self.store.get_concept(item.concept_id)
        if not concept:
            return []
        repo = self.store.get_repository(concept.repository_id)
        if not repo or repo.source_type != "local":
            return [
                {
                    "path": str(ref.get("path") or "").replace("\\", "/"),
                    "start_line": ref.get("start_line"),
                    "end_line": ref.get("end_line"),
                    "symbol": ref.get("symbol"),
                    "commit_sha": ref.get("commit_sha"),
                    "snippet": "",
                    "available": False,
                }
                for ref in (item.source_references or [])
                if ref.get("path")
            ]
        root = resolve_local_repo_root(repo.source_location)
        if not root:
            return []
        lookup = load_code_lookup(root, item.source_references or [])
        out: list[dict[str, Any]] = []
        for ref in item.source_references or []:
            path = str(ref.get("path") or "").replace("\\", "/")
            if not path:
                continue
            snippet = snippet_for_ref(lookup, ref)
            out.append(
                {
                    "path": path,
                    "start_line": ref.get("start_line"),
                    "end_line": ref.get("end_line"),
                    "symbol": ref.get("symbol"),
                    "commit_sha": ref.get("commit_sha"),
                    "snippet": snippet,
                    "available": bool(snippet),
                }
            )
        return out

    def _ordered_items(self, concept_id: str):
        items = list(self.store.list_items(concept_id))
        items.sort(
            key=lambda i: (
                _ITEM_TYPE_ORDER.get(i.item_type, 9),
                int(i.difficulty or 0),
                i.created_at.isoformat() if i.created_at else "",
            )
        )
        return items

    def _queue_payload(
        self,
        *,
        mode: SessionMode,
        concept_id: str,
        concept_title: str,
        repository_id: str,
        items: list,
        current_item_id: str,
        attempted_ids: set[str],
    ) -> dict[str, Any]:
        ids = [i.id for i in items]
        try:
            pos = ids.index(current_item_id)
        except ValueError:
            pos = 0
            current_item_id = ids[0]
        next_id = ids[pos + 1] if pos + 1 < len(ids) else None
        prev_id = ids[pos - 1] if pos > 0 else None
        remaining = [i for i in ids[pos + 1 :] if i not in attempted_ids]
        return {
            "mode": mode,
            "concept_id": concept_id,
            "concept_title": concept_title,
            "repository_id": repository_id,
            "item_ids": ids,
            "position": pos + 1,  # 1-based
            "total": len(ids),
            "current_item_id": current_item_id,
            "next_item_id": next_id,
            "prev_item_id": prev_id,
            "remaining_count": len(remaining) + (0 if current_item_id in attempted_ids else 1),
            "completed_count": len([i for i in ids if i in attempted_ids]),
            "items": [
                {
                    "id": i.id,
                    "item_type": i.item_type,
                    "prompt": i.prompt,
                    "difficulty": i.difficulty,
                    "stale": bool(i.stale),
                    "attempted": i.id in attempted_ids,
                }
                for i in items
            ],
        }
