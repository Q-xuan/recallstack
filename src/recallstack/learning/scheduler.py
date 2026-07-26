"""FSRS review scheduler adapter.

Domain code depends only on ReviewScheduler protocol + JSON card dicts.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Protocol


class ReviewScheduler(Protocol):
    def create_card(self) -> dict[str, Any]: ...

    def review(
        self,
        card: dict[str, Any],
        rating: int,
        reviewed_at: datetime,
    ) -> tuple[dict[str, Any], dict[str, Any]]: ...


def _ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


class FSRSReviewScheduler:
    """Adapter around the fsrs package."""

    def __init__(self, desired_retention: float = 0.9):
        self.desired_retention = desired_retention
        # lazy import so domain/tests can mock without fsrs installed in some envs
        from fsrs import Scheduler

        try:
            self._scheduler = Scheduler(desired_retention=desired_retention)
        except TypeError:
            # older/newer signature differences
            self._scheduler = Scheduler()

    def create_card(self) -> dict[str, Any]:
        from fsrs import Card

        card = Card()
        return self._card_to_dict(card)

    def review(
        self,
        card: dict[str, Any],
        rating: int,
        reviewed_at: datetime,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        from fsrs import Rating

        reviewed_at = _ensure_utc(reviewed_at)
        fsrs_card = self._dict_to_card(card)
        rating_enum = self._to_rating(rating, Rating)
        result = self._scheduler.review_card(fsrs_card, rating_enum, reviewed_at)

        # fsrs versions return (card, review_log) or a ReviewResult-like object
        if isinstance(result, tuple) and len(result) >= 2:
            new_card, review_log = result[0], result[1]
        else:
            new_card = getattr(result, "card", result)
            review_log = getattr(result, "review_log", None)

        card_dict = self._card_to_dict(new_card)
        log_dict = self._log_to_dict(review_log, rating=rating, reviewed_at=reviewed_at)
        return card_dict, log_dict

    def _to_rating(self, rating: int, rating_cls: Any) -> Any:
        # FSRS Rating: 1=Again, 2=Hard, 3=Good, 4=Easy
        mapping = {
            1: rating_cls.Again,
            2: rating_cls.Hard,
            3: rating_cls.Good,
            4: rating_cls.Easy,
        }
        return mapping.get(int(rating), rating_cls.Good)

    def _card_to_dict(self, card: Any) -> dict[str, Any]:
        if card is None:
            return {}
        if hasattr(card, "to_dict"):
            data = card.to_dict()
            return data if isinstance(data, dict) else dict(data)
        data: dict[str, Any] = {}
        for key in (
            "card_id",
            "state",
            "step",
            "stability",
            "difficulty",
            "due",
            "last_review",
            "reps",
            "lapses",
        ):
            if hasattr(card, key):
                val = getattr(card, key)
                if isinstance(val, datetime):
                    data[key] = _ensure_utc(val).isoformat()
                elif hasattr(val, "value"):
                    data[key] = val.value
                else:
                    data[key] = val
        return data

    def _dict_to_card(self, data: dict[str, Any]) -> Any:
        from fsrs import Card

        if not data:
            return Card()
        if hasattr(Card, "from_dict"):
            return Card.from_dict(data)

        card = Card()
        for key, val in data.items():
            if not hasattr(card, key):
                continue
            if key in {"due", "last_review"} and isinstance(val, str):
                try:
                    val = datetime.fromisoformat(val)
                except ValueError:
                    continue
            try:
                setattr(card, key, val)
            except Exception:  # noqa: BLE001
                continue
        return card

    def _log_to_dict(
        self, review_log: Any, *, rating: int, reviewed_at: datetime
    ) -> dict[str, Any]:
        if review_log is None:
            return {
                "rating": rating,
                "reviewed_at": _ensure_utc(reviewed_at).isoformat(),
            }
        if hasattr(review_log, "to_dict"):
            data = review_log.to_dict()
            return data if isinstance(data, dict) else dict(data)
        data: dict[str, Any] = {"rating": rating}
        for key in ("rating", "review_datetime", "review_duration"):
            if hasattr(review_log, key):
                val = getattr(review_log, key)
                if isinstance(val, datetime):
                    data[key] = _ensure_utc(val).isoformat()
                elif hasattr(val, "value"):
                    data[key] = val.value
                else:
                    data[key] = val
        data.setdefault("reviewed_at", _ensure_utc(reviewed_at).isoformat())
        return data


def map_score_to_rating(
    score: float,
    *,
    hints_used: list[dict] | None = None,
    revealed_answer: bool = False,
    again_below: float = 0.40,
    hard_below: float = 0.65,
    good_below: float = 0.90,
) -> int:
    """Map rubric score + hint usage to FSRS rating 1..4."""
    hints_used = hints_used or []
    max_hint = 0
    for h in hints_used:
        try:
            max_hint = max(max_hint, int(h.get("level", 0)))
        except (TypeError, ValueError):
            continue

    if revealed_answer:
        return 1 if score < hard_below else 2
    if score < again_below:
        return 1
    if score < hard_below:
        return 2
    if score < good_below:
        return 3
    # high score
    if max_hint >= 4:
        return 3
    if max_hint >= 1:
        return 3
    return 4
