"""Submit and evaluate learning attempts; update mastery + FSRS."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from recallstack.config import RecallStackConfig
from recallstack.db.models import Mastery, utcnow
from recallstack.db.repositories import RepositoryStore
from recallstack.domain.schemas import AttemptEvaluationResult
from recallstack.learning.code_loader import (
    load_code_lookup,
    resolve_local_repo_root,
    snippet_for_ref,
)
from recallstack.learning.hint_engine import HintEngine
from recallstack.learning.mastery_calculator import MasteryCalculator, MasterySignals
from recallstack.learning.rubric_evaluator import RubricEvaluator
from recallstack.learning.scheduler import FSRSReviewScheduler, map_score_to_rating
from recallstack.llm.factory import build_structured_llm
from recallstack.llm.prompts import eval_messages

logger = logging.getLogger(__name__)


class EvaluateAttemptService:
    def __init__(self, session: Session, config: RecallStackConfig | None = None):
        self.session = session
        self.config = config or RecallStackConfig.load()
        self.store = RepositoryStore(session)
        self.evaluator = RubricEvaluator()
        self.mastery_calc = MasteryCalculator()
        self.hints = HintEngine()
        self.scheduler = FSRSReviewScheduler(
            desired_retention=self.config.fsrs_desired_retention
        )

    def _code_lookup_for_item(self, item) -> dict[str, str]:
        """Load referenced source files for local repositories only."""
        concept = self.store.get_concept(item.concept_id)
        if not concept:
            return {}
        repo = self.store.get_repository(concept.repository_id)
        if not repo or repo.source_type != "local":
            return {}
        root = resolve_local_repo_root(repo.source_location)
        if not root:
            return {}
        return load_code_lookup(root, item.source_references or [])

    def evidence_snippets_for_item(self, item) -> list[dict[str, Any]]:
        """Return short source windows for the learning session UI."""
        lookup = self._code_lookup_for_item(item)
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

    def request_hint(
        self,
        item_id: str,
        *,
        current_level: int,
        hints_used: list[dict[str, Any]] | None = None,
        reveal_answer: bool = False,
    ) -> dict[str, Any]:
        item = self.store.get_item(item_id)
        if not item:
            raise KeyError("item_not_found")
        hints_used = list(hints_used or [])
        if not reveal_answer and not self.hints.validate_progression(
            hints_used + [{"level": max(int(current_level), 0) + 1}]
        ):
            # allow if current progression already valid and next is +1
            if not self.hints.validate_progression(hints_used):
                raise ValueError("invalid_hint_progression")

        code_lookup = self._code_lookup_for_item(item)
        result = self.hints.next_hint(
            current_level=current_level,
            source_references=item.source_references or [],
            expected_answer_outline=item.expected_answer_outline or "",
            code_lookup=code_lookup,
            reveal_answer=reveal_answer,
        )
        result["recorded_at"] = utcnow().isoformat()
        return result

    def submit_attempt(
        self,
        item_id: str,
        *,
        user_id: str,
        answer: str,
        confidence: int = 3,
        hints_used: list[dict[str, Any]] | None = None,
        duration_seconds: int = 0,
        revealed_answer: bool = False,
    ) -> dict[str, Any]:
        item = self.store.get_item(item_id)
        if not item:
            raise KeyError("item_not_found")

        hints_used = list(hints_used or [])
        if hints_used and not self.hints.validate_progression(hints_used):
            raise ValueError("invalid_hint_progression")

        evaluation, evaluation_source = self._evaluate(
            item=item,
            answer=answer,
            confidence=confidence,
            hints_used=hints_used,
            revealed_answer=revealed_answer,
        )

        rating = map_score_to_rating(
            evaluation.score,
            hints_used=hints_used,
            revealed_answer=revealed_answer,
            again_below=self.config.rating_again_below,
            hard_below=self.config.rating_hard_below,
            good_below=self.config.rating_good_below,
        )

        evaluation_payload = evaluation.model_dump(mode="json")
        evaluation_payload["evaluation_source"] = evaluation_source

        attempt = self.store.create_attempt(
            user_id=user_id,
            learning_item_id=item.id,
            answer=answer,
            score=evaluation.score,
            confidence=confidence,
            hints_used=hints_used,
            duration_seconds=duration_seconds,
            evaluation=evaluation_payload,
            fsrs_rating=rating,
            revealed_answer=revealed_answer,
        )

        mastery = self.store.get_mastery(user_id, item.concept_id)
        now = utcnow()
        if mastery is None:
            mastery = Mastery(
                user_id=user_id,
                concept_id=item.concept_id,
                mastery_score=0.0,
                attempts_count=0,
                fsrs_card=self.scheduler.create_card(),
            )
            self.session.add(mastery)
            self.session.flush()

        new_score = self.mastery_calc.compute(
            MasterySignals(
                score=evaluation.score,
                confidence=confidence,
                hints_used=hints_used,
                revealed_answer=revealed_answer,
                duration_seconds=duration_seconds,
                previous_mastery=mastery.mastery_score,
                attempts_count=mastery.attempts_count,
            )
        )

        card, review_log = self.scheduler.review(
            mastery.fsrs_card or self.scheduler.create_card(),
            rating,
            now,
        )
        next_review = self._extract_due(card, now)

        mastery.mastery_score = new_score
        mastery.attempts_count = int(mastery.attempts_count or 0) + 1
        mastery.last_reviewed_at = now
        mastery.next_review_at = next_review
        mastery.fsrs_card = card
        mastery.updated_at = now

        self.store.create_review_log(
            user_id=user_id,
            concept_id=item.concept_id,
            learning_item_id=item.id,
            attempt_id=attempt.id,
            rating=rating,
            fsrs_review_log=review_log,
            reviewed_at=now,
            next_review_at=next_review,
        )
        self.session.flush()

        return {
            "attempt": attempt,
            "evaluation": evaluation,
            "evaluation_source": evaluation_source,
            "mastery_score": mastery.mastery_score,
            "next_review_at": mastery.next_review_at,
            "fsrs_rating": rating,
            "expected_answer_outline": item.expected_answer_outline,
            "concept_id": item.concept_id,
        }

    def _evaluate(
        self,
        *,
        item,
        answer: str,
        confidence: int,
        hints_used: list[dict[str, Any]],
        revealed_answer: bool,
    ) -> tuple[AttemptEvaluationResult, str]:
        deterministic = self.evaluator.evaluate_deterministic(
            answer=answer,
            rubric=item.rubric or {},
            source_references=item.source_references or [],
            expected_outline=item.expected_answer_outline or "",
            item_type=item.item_type,
            revealed_answer=revealed_answer,
        )
        if not (self.config.llm_enabled and self.config.llm_evaluation):
            return deterministic, "deterministic"

        llm_result = self._try_llm_evaluate(
            item=item,
            answer=answer,
            confidence=confidence,
            hints_used=hints_used,
            revealed_answer=revealed_answer,
        )
        if llm_result is None:
            return deterministic, "deterministic"

        gate_ids = {"chip_symbol", "failure_path"}
        if deterministic.score < 0.40 and gate_ids.intersection(deterministic.missing_points):
            return deterministic, "deterministic"

        # Prefer LLM semantics, but never fully discard deterministic evidence signal.
        blended = self._blend_evaluations(deterministic, llm_result, revealed_answer)
        return blended, "llm"

    def _try_llm_evaluate(
        self,
        *,
        item,
        answer: str,
        confidence: int,
        hints_used: list[dict[str, Any]],
        revealed_answer: bool,
    ) -> AttemptEvaluationResult | None:
        structured = build_structured_llm(self.config)
        if structured is None:
            return None

        hint_levels = []
        for h in hints_used:
            try:
                hint_levels.append(int(h.get("level", 0)))
            except (TypeError, ValueError):
                continue

        lookup = self._code_lookup_for_item(item)
        excerpts: list[str] = []
        for ref in (item.source_references or [])[:3]:
            snip = snippet_for_ref(lookup, ref, max_lines=10)
            path = str(ref.get("path") or "")
            if snip:
                excerpts.append(f"# {path}\n{snip}")
        code_excerpts = "\n\n".join(excerpts) if excerpts else "(no local excerpts)"

        messages = eval_messages(
            prompt=item.prompt or "",
            item_type=item.item_type or "active_recall",
            answer=answer or "",
            confidence=str(confidence),
            hint_levels=",".join(str(x) for x in hint_levels) or "none",
            revealed=str(bool(revealed_answer)),
            rubric=json.dumps(item.rubric or {}, ensure_ascii=False, indent=2),
            outline=item.expected_answer_outline or "",
            source_refs=json.dumps(item.source_references or [], ensure_ascii=False, indent=2),
            code_excerpts=code_excerpts,
            language=self.config.content_lang,
        )
        try:
            result = self._run_coro(
                structured.complete_model(messages, AttemptEvaluationResult)
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("LLM evaluation failed: %s", type(exc).__name__)
            return None
        return result

    @staticmethod
    def _run_coro(coro):
        """Run an async coroutine from sync FastAPI handlers safely."""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coro)

        # Already inside an event loop (e.g. some ASGI paths): run in a worker thread.
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, coro).result(
                timeout=max(5.0, RecallStackConfig.load().llm_timeout_seconds + 5.0)
            )

    def _blend_evaluations(
        self,
        deterministic: AttemptEvaluationResult,
        llm: AttemptEvaluationResult,
        revealed_answer: bool,
    ) -> AttemptEvaluationResult:
        # Blend scores: LLM primary, deterministic evidence as anchor.
        score = 0.65 * llm.score + 0.35 * deterministic.score
        if revealed_answer:
            score = min(score, 0.45)

        covered = list(dict.fromkeys([*llm.covered_points, *deterministic.covered_points]))
        missing = [p for p in llm.missing_points if p not in covered]
        if not missing and deterministic.missing_points:
            missing = [p for p in deterministic.missing_points if p not in covered]

        evidence = llm.source_evidence or deterministic.source_evidence
        feedback = llm.feedback or deterministic.feedback
        if deterministic.score - llm.score >= 0.25 and deterministic.covered_points:
            feedback = (
                f"{feedback} "
                f"(系统同时检测到你命中了源码证据点：{', '.join(deterministic.covered_points[:3])})"
            ).strip()

        return AttemptEvaluationResult(
            score=round(max(0.0, min(1.0, score)), 4),
            covered_points=covered,
            missing_points=missing,
            misconceptions=llm.misconceptions or deterministic.misconceptions,
            source_evidence=evidence[:6],
            feedback=feedback,
            suggested_revision=llm.suggested_revision or deterministic.suggested_revision,
            follow_up_question=llm.follow_up_question or deterministic.follow_up_question,
        )

    def _extract_due(self, card: dict[str, Any], now: datetime) -> datetime:
        due = card.get("due")
        if isinstance(due, datetime):
            return due if due.tzinfo else due.replace(tzinfo=timezone.utc)
        if isinstance(due, str):
            try:
                dt = datetime.fromisoformat(due)
                return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
            except ValueError:
                pass
        # fallback: 1 day
        from datetime import timedelta

        return now + timedelta(days=1)
