"""Generate learning items from concepts (deterministic + optional LLM)."""

from __future__ import annotations

import hashlib
from typing import Any

from recallstack.domain.schemas import (
    LearningItemDraft,
    LearningItemGenerationResult,
    Rubric,
    RubricPoint,
    SourceReference,
)
from recallstack.learning.i18n import t
from recallstack.learning.learning_contract import (
    parse_path_chip,
    path_step_contract,
)
from recallstack.security import filter_source_references


class QuestionGenerator:
    def __init__(self, max_items: int = 3):
        self.max_items = max_items

    def generate_deterministic(
        self,
        *,
        title: str,
        description: str,
        why_learn: str,
        source_references: list[dict[str, Any]],
        valid_paths: set[str],
        commit_sha: str = "",
    ) -> LearningItemGenerationResult:
        refs = filter_source_references(source_references, valid_paths)
        if not refs and source_references:
            refs = source_references
        src_models = [SourceReference.model_validate(r) for r in refs[:4]] if refs else []

        files = ", ".join(sorted({r["path"] for r in refs})) if refs else t(
            "related source", "相关源码"
        )
        symbols = [str(r.get("symbol")) for r in refs if r.get("symbol")]
        primary_path = str(refs[0].get("path")) if refs else ""
        primary_symbol = symbols[0] if symbols else ""
        evidence_hint = primary_path
        if primary_symbol and primary_path:
            evidence_hint = f"{primary_path}::{primary_symbol}"
        elif primary_symbol:
            evidence_hint = primary_symbol
        items: list[LearningItemDraft] = []

        # active recall
        points = [
            RubricPoint(
                id="responsibility",
                description=t(
                    f'State the main responsibility of "{title}"',
                    f"说明「{title}」的主要职责",
                ),
                weight=0.35,
                source_references=src_models[:1],
            ),
            RubricPoint(
                id="boundary",
                description=t(
                    "State the boundary: what this concept is NOT responsible for",
                    "说明该概念的边界：它不负责什么",
                ),
                weight=0.25,
                source_references=src_models[:1],
            ),
            RubricPoint(
                id="evidence",
                description=(
                    t(
                        f"Cite source evidence (e.g. {evidence_hint})",
                        f"引用源码证据（例如 {evidence_hint}）",
                    )
                    if evidence_hint
                    else t(
                        "Cite at least one key file/symbol as evidence",
                        "引用至少一个关键文件/符号作为证据",
                    )
                ),
                weight=0.40,
                source_references=src_models[:2],
            ),
        ]
        items.append(
            LearningItemDraft(
                item_type="active_recall",
                prompt=(
                    t(
                        f'What is the main responsibility of "{title}" in this repository? Ground your answer in source code',
                        f"「{title}」在本仓库中的主要职责是什么？请结合源码说明",
                    )
                    + (
                        t(f" (start from {evidence_hint}).", f"（可从 {evidence_hint} 切入）。")
                        if evidence_hint
                        else t(".", "。")
                    )
                ),
                expected_answer_outline=t(
                    f"- Responsibility: {description or title}\n- Why it matters: {why_learn}\n- Evidence: {evidence_hint or files}",
                    f"- 职责：{description or title}\n- 为什么重要：{why_learn}\n- 证据：{evidence_hint or files}",
                ),
                difficulty=2,
                rubric=Rubric(required_points=points, maximum_score=1.0),
                source_references=src_models,
            )
        )

        # code trace
        if len(items) < self.max_items:
            start_ref = src_models[0] if src_models else None
            next_ref = src_models[1] if len(src_models) > 1 else start_ref
            start_label = (
                f"{start_ref.path}"
                + (f"::{start_ref.symbol}" if start_ref and start_ref.symbol else "")
                if start_ref
                else files
            )
            next_label = (
                f"{next_ref.path}"
                + (f"::{next_ref.symbol}" if next_ref and next_ref.symbol else "")
                if next_ref
                else t("next call", "下一跳调用")
            )
            trace_points = [
                RubricPoint(
                    id="start",
                    description=t(
                        f"Name the starting point (e.g. {start_label})",
                        f"指出追踪起点（如 {start_label}）",
                    ),
                    weight=0.3,
                    source_references=src_models[:1],
                ),
                RubricPoint(
                    id="next-call",
                    description=t(
                        f"Describe the next key call or data hop (e.g. {next_label})",
                        f"说明下一个关键调用或数据去向（如 {next_label}）",
                    ),
                    weight=0.4,
                    source_references=src_models[1:2] or src_models[:1],
                ),
                RubricPoint(
                    id="effect",
                    description=t(
                        "Describe the final effect (state change / output / side effect)",
                        "说明最终效果（状态变化/输出/副作用）",
                    ),
                    weight=0.3,
                    source_references=src_models[-1:],
                ),
            ]
            items.append(
                LearningItemDraft(
                    item_type="code_trace",
                    prompt=(
                        t(
                            f'Starting from code related to "{title}", trace one key execution path: start, key calls, and final effect.',
                            f"从「{title}」相关代码出发，追踪一次关键执行路径：起点、关键调用、最终效果分别是什么？",
                        )
                        + (
                            t(f" Suggested start: {start_label}.", f" 建议从 {start_label} 开始。")
                            if start_label
                            else ""
                        )
                    ),
                    expected_answer_outline=t(
                        f'- Start: {start_label}\n- Key call: {next_label}\n- Final effect: fulfills "{title}"',
                        f"- 起点：{start_label}\n- 关键调用：{next_label}\n- 最终效果：完成「{title}」职责",
                    ),
                    difficulty=3,
                    rubric=Rubric(required_points=trace_points, maximum_score=1.0),
                    source_references=src_models,
                )
            )

        # teach back
        if len(items) < self.max_items:
            tb_points = [
                RubricPoint(
                    id="audience",
                    description=t(
                        "Explain the concept in terms a newcomer understands",
                        "用新人能懂的话解释概念",
                    ),
                    weight=0.25,
                ),
                RubricPoint(
                    id="relations",
                    description=t(
                        "Explain relationships to neighboring concepts/modules",
                        "说明与相邻概念/模块的关系",
                    ),
                    weight=0.35,
                    source_references=src_models[:2],
                ),
                RubricPoint(
                    id="tradeoff",
                    description=t(
                        "State at least one design tradeoff (benefit vs cost)",
                        "说明至少一个设计选择的好处与代价",
                    ),
                    weight=0.40,
                ),
            ]
            items.append(
                LearningItemDraft(
                    item_type="teach_back",
                    prompt=(
                        t(
                            f'Explain "{title}" to a new teammate: what it is, how it collaborates, and one design tradeoff.',
                            f"请向刚加入项目的开发者解释「{title}」：它是什么、如何与其他部分协作、设计上的好处与代价。",
                        )
                        + (
                            t(f" Use {files} as evidence.", f" 可用 {files} 作为证据。")
                            if files not in {"related source", "相关源码"}
                            else ""
                        )
                    ),
                    expected_answer_outline=t(
                        f"- What it is: {description}\n- Collaboration: dependents/dependencies\n- Evidence files: {files}\n- Tradeoff: complexity / performance / maintainability",
                        f"- 是什么：{description}\n- 协作关系：依赖/被依赖模块\n- 证据文件：{files}\n- 权衡：复杂度/性能/可维护性",
                    ),
                    difficulty=3,
                    rubric=Rubric(required_points=tb_points, maximum_score=1.0),
                    source_references=src_models,
                )
            )

        return LearningItemGenerationResult(items=items[: self.max_items])

    def generate_from_contract(
        self,
        *,
        title: str,
        contract: dict[str, Any] | None = None,
        concept: Any = None,
        file_texts: dict[str, str] | None = None,
        commit_sha: str = "",
    ) -> LearningItemGenerationResult:
        """Practice items from the 4-part path contract, locked to one chip."""
        snap = dict(contract or {})
        if not snap.get("chip") and concept is not None:
            snap = path_step_contract(concept, file_texts=file_texts)
        chip = str(snap.get("chip") or "")
        path, line, chip_sym = parse_path_chip(chip)
        symbol = str(snap.get("symbol") or chip_sym or "")
        gate = str(snap.get("gate") or "")
        task = str(snap.get("task") or "")
        failure = list(snap.get("failure_tokens") or [])
        loc = f"{path}:{line}" if path and line else (path or chip)
        chip_ref = []
        if path:
            try:
                chip_ref = [
                    SourceReference(
                        path=path,
                        start_line=int(line) if line else None,
                        end_line=int(line) if line else None,
                        symbol=symbol or None,
                        commit_sha=commit_sha or None,
                    )
                ]
            except ValueError:
                chip_ref = []
        contract_meta = {
            "path": path,
            "line": int(line or 0),
            "symbol": symbol,
            "failure_tokens": failure,
            "gate": gate,
            "chip": chip,
        }
        items: list[LearningItemDraft] = []
        items.append(
            LearningItemDraft(
                item_type="active_recall",
                prompt=t(
                    f"You own this step. Look only at `{chip or loc}`. "
                    f"Name `{symbol or title}` and say what that line must keep true. "
                    "Restating the heading does not pass.",
                    f"你负责这一步。只看 `{chip or loc}`。"
                    f"点名 `{symbol or title}`，说出这一行必须保住的不变量。"
                    "复述标题不算过关。",
                ),
                expected_answer_outline=t(
                    f"- Symbol: {symbol}\n- Chip: {chip}\n- Task: {task}",
                    f"- 符号：{symbol}\n- 证据：{chip}\n- 本步：{task}",
                ),
                difficulty=2,
                rubric=Rubric(
                    required_points=[
                        RubricPoint(
                            id="chip_symbol",
                            description=t(
                                f"Name the chip symbol {symbol}",
                                f"点名证据符号 {symbol}",
                            ),
                            weight=0.45,
                            source_references=chip_ref,
                        ),
                        RubricPoint(
                            id="invariant",
                            description=t(
                                "State the invariant that line protects",
                                "说出这一行保住的不变量",
                            ),
                            weight=0.55,
                            source_references=chip_ref,
                        ),
                    ],
                    maximum_score=1.0,
                    contract=contract_meta,
                ),
                source_references=chip_ref,
            )
        )
        if len(items) < self.max_items:
            items.append(
                LearningItemDraft(
                    item_type="code_trace",
                    prompt=t(
                        f"From `{chip or loc}` take one hop: who calls `{symbol or title}` "
                        "or what does it call? If that line vanished, what does the user see?",
                        f"从 `{chip or loc}` 往下走一跳：谁调用 `{symbol or title}`，"
                        "或它调用谁？若这一行消失，用户看见什么？",
                    ),
                    expected_answer_outline=t(
                        f"- Start: {chip}\n- Next hop from {symbol}\n- User-visible break",
                        f"- 起点：{chip}\n- 下一跳：{symbol}\n- 用户能看见的损坏",
                    ),
                    difficulty=3,
                    rubric=Rubric(
                        required_points=[
                            RubricPoint(
                                id="start",
                                description=t(
                                    f"Start at {symbol} on {loc}",
                                    f"从 {loc} 的 {symbol} 出发",
                                ),
                                weight=0.4,
                                source_references=chip_ref,
                            ),
                            RubricPoint(
                                id="next-call",
                                description=t(
                                    "Name the next call or state",
                                    "说出下一跳调用或状态",
                                ),
                                weight=0.3,
                                source_references=chip_ref,
                            ),
                            RubricPoint(
                                id="effect",
                                description=t(
                                    "Name the user-visible failure if the line is gone",
                                    "说出删掉这一行后用户看见的失败",
                                ),
                                weight=0.3,
                                source_references=chip_ref,
                            ),
                        ],
                        maximum_score=1.0,
                        contract=contract_meta,
                    ),
                    source_references=chip_ref,
                )
            )
        if len(items) < self.max_items:
            items.append(
                LearningItemDraft(
                    item_type="teach_back",
                    prompt=t(
                        f"{gate or 'Sign off this step.'} You must name `{symbol or title}` "
                        "and the failure path. Copying the heading does not pass.",
                        f"{gate or '你签字。'}必须点名 `{symbol or title}`，并写出失败路径。"
                        "复述标题不算过关。",
                    ),
                    expected_answer_outline=t(
                        f"- Function/type: {symbol}\n- Failure path: {', '.join(failure) or 'user-visible break'}\n- Chip: {chip}",
                        f"- 函数/类型：{symbol}\n- 失败路径：{'、'.join(failure) or '用户能看见的损坏'}\n- 证据：{chip}",
                    ),
                    difficulty=3,
                    rubric=Rubric(
                        required_points=[
                            RubricPoint(
                                id="chip_symbol",
                                description=t(
                                    f"Name {symbol}",
                                    f"点名 {symbol}",
                                ),
                                weight=0.4,
                                source_references=chip_ref,
                            ),
                            RubricPoint(
                                id="failure_path",
                                description=t(
                                    "Name the failure path the gate asks for",
                                    "写出过关要求的那条失败路径",
                                ),
                                weight=0.6,
                                source_references=chip_ref,
                            ),
                        ],
                        maximum_score=1.0,
                        contract={**contract_meta, "require_failure": True},
                    ),
                    source_references=chip_ref,
                )
            )
        return LearningItemGenerationResult(items=items[: self.max_items])

    @staticmethod
    def item_content_hash(item: LearningItemDraft) -> str:
        raw = f"{item.item_type}|{item.prompt}|{item.expected_answer_outline}"
        return hashlib.sha256(raw.encode()).hexdigest()[:24]
