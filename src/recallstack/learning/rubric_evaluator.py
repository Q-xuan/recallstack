"""Evaluate learner answers against rubrics with deterministic scoring + optional LLM."""

from __future__ import annotations

import re
from pathlib import PurePosixPath
from typing import Any

from recallstack.domain.schemas import AttemptEvaluationResult, Rubric, SourceReference
from recallstack.learning.i18n import t


def _tokens(text: str) -> set[str]:
    # keep CJK unigrams/bigrams-ish by also including length-1 CJK chars
    parts = [t for t in re.split(r"[^\w\u4e00-\u9fff]+", text.lower()) if t]
    tokens: set[str] = set()
    for p in parts:
        if len(p) >= 2:
            tokens.add(p)
        # add CJK characters for short answers
        for ch in p:
            if "\u4e00" <= ch <= "\u9fff":
                tokens.add(ch)
    return tokens


def _answer_mentions_path(answer_lower: str, path: str) -> bool:
    """True if answer cites full path, basename, or stem (e.g. service.py / service)."""
    path = path.replace("\\", "/").lstrip("./")
    if not path:
        return False
    if path.lower() in answer_lower:
        return True
    name = PurePosixPath(path).name.lower()
    if name and name in answer_lower:
        return True
    stem = PurePosixPath(path).stem.lower()
    # avoid ultra-short stems matching noise (e.g. "db")
    if stem and len(stem) >= 3 and re.search(rf"\b{re.escape(stem)}\b", answer_lower):
        return True
    return False


def _answer_mentions_symbol(answer_lower: str, symbol: str | None) -> bool:
    if not symbol:
        return False
    sym = str(symbol).strip()
    if not sym:
        return False
    if sym.lower() in answer_lower:
        return True
    # Class.method → also accept bare method / class names
    parts = re.split(r"[.:/]", sym)
    for part in parts:
        p = part.strip().lower()
        if len(p) >= 3 and re.search(rf"\b{re.escape(p)}\b", answer_lower):
            return True
    return False


class RubricEvaluator:
    """Score answers primarily by rubric point coverage + source evidence."""

    def evaluate_deterministic(
        self,
        *,
        answer: str,
        rubric: dict[str, Any] | Rubric,
        source_references: list[dict[str, Any]] | None = None,
        expected_outline: str = "",
        item_type: str = "active_recall",
        revealed_answer: bool = False,
    ) -> AttemptEvaluationResult:
        if isinstance(rubric, dict):
            try:
                rub = Rubric.model_validate(rubric)
            except Exception:  # noqa: BLE001
                rub = Rubric()
        else:
            rub = rubric

        answer = answer or ""
        answer_lower = answer.lower()
        ans_tokens = _tokens(answer)
        refs = list(source_references or [])

        path_hits = 0
        symbol_hits = 0
        evidence: list[SourceReference] = []
        for ref in refs:
            path = str(ref.get("path", ""))
            symbol = ref.get("symbol")
            hit_path = _answer_mentions_path(answer_lower, path)
            hit_symbol = _answer_mentions_symbol(answer_lower, symbol if isinstance(symbol, str) else None)
            if hit_path:
                path_hits += 1
            if hit_symbol:
                symbol_hits += 1
            try:
                evidence.append(SourceReference.model_validate(ref))
            except Exception:  # noqa: BLE001
                continue

        covered: list[str] = []
        missing: list[str] = []
        score = 0.0
        total_w = 0.0

        for point in rub.required_points:
            total_w += max(point.weight, 0.0)
            keywords = _tokens(point.description)
            # also use id fragments
            keywords |= _tokens(point.id.replace("-", " "))
            # fold point-level source refs into matching vocabulary
            point_refs = [r.model_dump() for r in point.source_references] if point.source_references else []
            for pref in point_refs or refs:
                p = str(pref.get("path", ""))
                if p:
                    keywords.add(PurePosixPath(p).stem.lower())
                    keywords.add(PurePosixPath(p).name.lower())
                sym = pref.get("symbol")
                if sym:
                    keywords |= _tokens(str(sym).replace(".", " ").replace(":", " "))

            overlap = keywords & ans_tokens
            # Chinese answers may be short; use partial credit via overlap ratio
            if not keywords:
                hit = len(answer.strip()) >= 20
            else:
                ratio = len(overlap) / max(len(keywords), 1)
                hit = ratio >= 0.25 or any(k in answer_lower for k in keywords if len(k) >= 3)

            # evidence-centric points: path/symbol citation counts as coverage
            pid = point.id.lower()
            is_evidence_point = pid in {"evidence", "start", "next-call"} or "证据" in point.description
            if not hit and is_evidence_point and (path_hits or symbol_hits):
                hit = True

            if hit:
                covered.append(point.id)
                score += max(point.weight, 0.0)
            else:
                missing.append(point.id)

        if total_w > 0:
            score = score / total_w
        else:
            # fallback lexical similarity to outline
            outline_tokens = _tokens(expected_outline)
            if outline_tokens:
                score = len(ans_tokens & outline_tokens) / len(outline_tokens)
            else:
                score = 0.2 if len(answer.strip()) > 30 else 0.0

        # evidence bonus: real code citations matter more than wording
        if path_hits:
            score = min(1.0, score + 0.08 + 0.02 * min(path_hits - 1, 2))
        if symbol_hits:
            score = min(1.0, score + 0.06)
        # missing evidence penalty when rubric expects it
        if any(p.id == "evidence" for p in rub.required_points) and path_hits == 0 and symbol_hits == 0:
            score = max(0.0, score - 0.08)

        if revealed_answer:
            score = min(score, 0.45)

        misconceptions: list[str] = []
        for m in rub.common_misconceptions:
            if m and m.lower() in answer_lower:
                misconceptions.append(m)

        # code_trace: reward explicit step language slightly, soft-penalize flat answers
        if item_type == "code_trace":
            step_markers = ("->", "→", "然后", "接着", "next", "calls", "调用")
            if not any(m in answer_lower or m in answer for m in step_markers):
                score = max(0.0, score - 0.05)
            else:
                score = min(1.0, score + 0.03)

        feedback_parts = []
        if covered:
            feedback_parts.append(t(f"Covered: {', '.join(covered)}.", f"你已经覆盖了：{', '.join(covered)}。"))
        else:
            feedback_parts.append(t("Almost no rubric points were hit.", "这次几乎没有命中评分点。"))
        if missing:
            feedback_parts.append(t(f"Top gap: {missing[0]}.", f"最需要补上的是：{missing[0]}。"))
        if path_hits == 0 and refs:
            feedback_parts.append(t("No concrete source file was cited yet.", "回答里还没有落到具体源码文件。"))
        elif path_hits and symbol_hits == 0:
            feedback_parts.append(t("File cited; naming a key symbol would make this stronger.", "已引用文件；若能点名关键符号会更扎实。"))
        if misconceptions:
            feedback_parts.append(t(f"Possible misconception: {misconceptions[0]}.", f"注意可能的误解：{misconceptions[0]}。"))

        suggested = ""
        if missing and rub.required_points:
            mp = next((p for p in rub.required_points if p.id == missing[0]), None)
            if mp:
                suggested = t(f"Please add: {mp.description}", f"请补充：{mp.description}")
        if not suggested and refs and path_hits == 0:
            first = str(refs[0].get("path") or "")
            if first:
                suggested = t(f"Cite at least one source location, e.g. {first}", f"请至少引用一个源码位置，例如 {first}")

        follow = t("If you could prove understanding with one source symbol, which and why?", "如果只用一个源码符号证明你的理解，你会选哪一个？为什么？")
        if symbol_hits and path_hits:
            follow = t("If you redrew the boundary, which logic would you extract and why?", "这个实现如果换一种边界划分，你会把哪段逻辑拆出去？为什么？")

        return AttemptEvaluationResult(
            score=round(max(0.0, min(1.0, score)), 4),
            covered_points=covered,
            missing_points=missing,
            misconceptions=misconceptions,
            source_evidence=evidence[:6],
            feedback="".join(feedback_parts),
            suggested_revision=suggested,
            follow_up_question=follow,
        )
