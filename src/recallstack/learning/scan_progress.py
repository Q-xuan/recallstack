"""Compact scan-phase mapping for the repository header strip.

Keep in sync with ``frontend/src/lib/scanProgress.ts``. The API already
sends ``status`` + ``progress_message``; this only parses those strings.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

ScanPhase = Literal["scan", "outline", "write", "cite", "polish"]

_FRACTION = re.compile(r"(\d+)\s*/\s*(\d+)")

# Write 7/16 lands near 55% — the in-flight example Jake asked for.
_PHASE_START: dict[ScanPhase, int] = {
    "scan": 0,
    "outline": 12,
    "write": 32,
    "cite": 84,
    "polish": 92,
}
_PHASE_SPAN: dict[ScanPhase, int] = {
    "scan": 12,
    "outline": 20,
    "write": 52,
    "cite": 8,
    "polish": 8,
}


@dataclass(frozen=True)
class ScanProgress:
    phase: ScanPhase | None
    current: int | None
    total: int | None
    determinate: bool
    percent: int | None


def _phase_from_message(message: str) -> ScanPhase | None:
    if re.search(r"核验|verifying citations|citation", message, re.I):
        return "cite"
    if re.search(r"大纲|outlining", message, re.I):
        return "outline"
    if re.search(r"wrote topic|wrote module|已撰写|撰写专题|writing\s*\d+", message, re.I):
        return "write"
    if re.search(r"润色|enrich", message, re.I):
        return "polish"
    if re.search(
        r"analyzed module|已分析|preparing file|analyzing\s*\d+|扫描|正在分析|ingesting",
        message,
        re.I,
    ):
        return "scan"
    if re.search(r"概览|overview|规划", message, re.I):
        return "outline"
    if re.search(r"架构|architecture|阅读指南|reading guide", message, re.I):
        return "write"
    return None


def _phase_from_status(status: str) -> ScanPhase | None:
    if status in {"queued", "pending", "scanning"}:
        return "scan"
    if status == "generating_concepts":
        return "outline"
    if status == "generating_wiki":
        return "write"
    if status == "llm_enriching":
        return "polish"
    return None


def parse_scan_progress(status: str | None, message: str | None) -> ScanProgress:
    st = (status or "").strip()
    msg = (message or "").strip()

    if st == "ready":
        return ScanProgress(None, None, None, False, None)

    current: int | None = None
    total: int | None = None
    frac = _FRACTION.search(msg)
    if frac:
        current = int(frac.group(1))
        total = int(frac.group(2))
        if total <= 0:
            current = None
            total = None

    phase = (_phase_from_message(msg) if msg else None) or _phase_from_status(st)
    queued_unknown = st in {"queued", "pending", ""} and not msg

    if not phase or queued_unknown:
        return ScanProgress(
            phase or ("scan" if queued_unknown else None),
            current,
            total,
            False,
            None,
        )

    start = _PHASE_START[phase]
    span = _PHASE_SPAN[phase]
    ratio = min(1.0, max(0.0, current / total)) if current is not None and total else 0.4
    return ScanProgress(phase, current, total, True, round(start + span * ratio))
