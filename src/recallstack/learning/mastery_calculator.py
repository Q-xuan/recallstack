"""Mastery score calculation from attempts and FSRS state."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class MasterySignals:
    score: float
    confidence: int
    hints_used: list[dict]
    revealed_answer: bool
    duration_seconds: int = 0
    previous_mastery: float = 0.0
    attempts_count: int = 0


class MasteryCalculator:
    """Combines rubric score with learning behavior signals."""

    def compute(self, signals: MasterySignals) -> float:
        score = max(0.0, min(1.0, signals.score))
        max_hint = 0
        for h in signals.hints_used or []:
            try:
                max_hint = max(max_hint, int(h.get("level", 0)))
            except (TypeError, ValueError):
                continue

        # hint penalty (does not rewrite correctness)
        if max_hint >= 5 or signals.revealed_answer:
            score *= 0.55
        elif max_hint >= 4:
            score *= 0.7
        elif max_hint >= 2:
            score *= 0.85

        # confidence calibration: weak signal only
        if signals.confidence >= 4 and signals.score < 0.4:
            score *= 0.9  # overconfident miss
        elif signals.confidence <= 2 and signals.score >= 0.8:
            score = min(1.0, score + 0.05)  # underconfident success

        # duration: only weak dampening for extremely fast empty-ish answers
        if signals.duration_seconds and signals.duration_seconds < 8 and signals.score < 0.5:
            score *= 0.95

        # EMA with history
        if signals.attempts_count <= 0:
            blended = score
        else:
            alpha = 0.45
            blended = alpha * score + (1 - alpha) * signals.previous_mastery

        return round(max(0.0, min(1.0, blended)), 4)
