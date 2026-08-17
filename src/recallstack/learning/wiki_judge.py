"""DeepSeek-as-judge harness for Chinese wiki handbook voice.

Candidate: a RecallStack-generated zh wiki page.
References: DeepWiki English structure gold and/or official README.zh.

Uses the same LLM client as analyze (DeepSeek by default). Without a key,
a deterministic heuristic still flags lecture tone and passes handbook samples.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

DIMENSIONS = (
    "handbook_tone",
    "naturalness",
    "terminology",
    "evidence",
    "structure",
)

LECTURE_MARKERS = (
    "读完应能",
    "读完你应能",
    "读完你应该能",
    "读完本页，你要能",
    "缺了它哪条能力会断",
    "用户能察觉的行为会坏",
    "After reading you should",
)

LECTURE_HEADINGS = (
    "## 它是什么",
    "## 一次调用怎么走",
    "## 术语小贴士",
)

BAD_TERM_TRANSLATIONS = (
    "代理人",
    "插件系统",
)

EVIDENCE_PILL_RE = re.compile(
    r"`[A-Za-z0-9_./-]+\.[A-Za-z0-9]+(?::\d+(?:-\d+)?)?(?:\s+[A-Za-z_][A-Za-z0-9_]*)?`"
)
DIR_FIRST_RE = re.compile(
    r"(?m)^##\s*(目录|文件树|crate 清单|Heaviest modules|按目录罗列)"
)
CONCEPT_FIRST_RE = re.compile(
    r"(?m)^##\s*(概述|架构|关键类型|边界|Capability Seam|调用链)"
)


def _clamp(score: float) -> int:
    return max(0, min(5, int(round(score))))


def heuristic_judge(candidate: str, references: dict[str, str] | None = None) -> dict[str, Any]:
    """Score a page without calling the LLM. references are unused but kept for API parity."""
    del references
    text = candidate or ""
    flags: list[str] = []

    lecture_hits = [m for m in LECTURE_MARKERS if m in text]
    heading_hits = [h for h in LECTURE_HEADINGS if h in text]
    if lecture_hits or heading_hits:
        flags.append("lecture_tone")
    tone = 5.0
    tone -= 2.0 * len(lecture_hits)
    tone -= 1.0 * len(heading_hits)

    natural = 5.0
    if "您应能" in text or "阅读后" in text:
        natural -= 2.0
        flags.append("stiff_translation")
    if "这篇文档讲" in text:
        natural -= 1.0
    if re.search(r"leveraging|utilizing|comprehensive solution", text, re.I):
        natural -= 1.5

    terms = 5.0
    bad_terms = [
        w
        for w in BAD_TERM_TRANSLATIONS
        if w in text and not re.search(rf"(不是|不要|禁止|勿).{{0,16}}{re.escape(w)}", text)
    ]
    if bad_terms:
        terms -= 3.0
        flags.append("bad_translation")
    if re.search(r"\bAgent\b|plugin|harness|Capability Seam", text):
        terms = min(5.0, terms + 0.5)

    pills = EVIDENCE_PILL_RE.findall(text)
    evidence = 2.0
    if pills:
        evidence = 4.0 if len(pills) == 1 else 5.0
    elif len(text) > 400:
        evidence = 1.0
        flags.append("missing_evidence")
    else:
        evidence = 3.0

    structure = 3.0
    if CONCEPT_FIRST_RE.search(text):
        structure += 1.5
    if DIR_FIRST_RE.search(text):
        structure -= 2.0
        flags.append("directory_first")
    first_heading = next(
        (ln[3:].strip() for ln in text.splitlines() if ln.startswith("## ")),
        "",
    )
    if first_heading in {"概述", "架构", "Overview", "Architecture", "Capability Seam"}:
        structure = min(5.0, structure + 0.5)
    if first_heading in {"目录", "文件树", "crate 清单"}:
        flags.append("directory_first")
        structure = min(structure, 1.0)

    scores = {
        "handbook_tone": _clamp(tone),
        "naturalness": _clamp(natural),
        "terminology": _clamp(terms),
        "evidence": _clamp(evidence),
        "structure": _clamp(structure),
    }
    overall = _clamp(sum(scores.values()) / len(scores))
    comments = _heuristic_comment(flags, lecture_hits, heading_hits, bad_terms, pills)
    return {
        "scores": scores,
        "overall": overall,
        "flags": flags,
        "comments": comments,
        "judge": "heuristic",
    }


def _heuristic_comment(
    flags: list[str],
    lecture_hits: list[str],
    heading_hits: list[str],
    bad_terms: list[str],
    pills: list[str],
) -> str:
    parts: list[str] = []
    if "lecture_tone" in flags:
        shown = ", ".join([*lecture_hits, *heading_hits][:4]) or "讲义标记"
        parts.append(f"检测到讲义腔：{shown}。")
    else:
        parts.append("手册口吻：未见「读完应能」等讲义标记。")
    if "bad_translation" in flags:
        parts.append(f"术语乱译：{', '.join(bad_terms)}。")
    if pills:
        parts.append(f"证据芯片 {len(pills)} 处。")
    if "directory_first" in flags:
        parts.append("结构先堆目录，不像 DeepWiki 先讲概念/seam。")
    return " ".join(parts)


def _judge_messages(candidate: str, references: dict[str, str]) -> list[dict[str, str]]:
    ref_blocks = []
    for name, body in references.items():
        clipped = (body or "")[:4000]
        ref_blocks.append(f"## {name}\n{clipped}")
    refs = "\n\n".join(ref_blocks) or "(none)"
    return [
        {
            "role": "system",
            "content": (
                "You are a handbook editor judging a Chinese codebase wiki page. "
                "Gold language: DeepSeek Harness README.zh (direct, crisp; proper nouns stay English). "
                "Gold structure: DeepWiki (concepts/seams before directory trees; "
                "`path:line Symbol` chips next to claims). "
                "Output ONLY JSON."
            ),
        },
        {
            "role": "user",
            "content": (
                "Score the candidate 0-5 on each dimension:\n"
                "1. handbook_tone — handbook voice vs lecture/workbook (读完应能 / 它是什么)\n"
                "2. naturalness — like README.zh, not machine translation\n"
                "3. terminology — identifiers/type names stay English; "
                "Agent must not become 代理人; plugin may be 插件 but not 插件系统\n"
                "4. evidence — `path:line Symbol` sits next to the claim, DeepWiki-style\n"
                "5. structure — concepts/seams first, not a directory dump\n\n"
                "Return JSON:\n"
                "{\n"
                '  "scores": {"handbook_tone": 0, "naturalness": 0, "terminology": 0, '
                '"evidence": 0, "structure": 0},\n'
                '  "overall": 0,\n'
                '  "flags": ["lecture_tone"],\n'
                '  "comments": "two short sentences"\n'
                "}\n\n"
                f"## Candidate\n{candidate[:8000]}\n\n"
                f"## References\n{refs}\n"
            ),
        },
    ]


def _normalize_llm_verdict(data: dict[str, Any], *, fallback: dict[str, Any]) -> dict[str, Any]:
    raw_scores = data.get("scores") if isinstance(data.get("scores"), dict) else {}
    scores = {}
    for key in DIMENSIONS:
        try:
            scores[key] = _clamp(float(raw_scores.get(key, fallback["scores"][key])))
        except (TypeError, ValueError):
            scores[key] = fallback["scores"][key]
    try:
        overall = _clamp(float(data.get("overall")))
    except (TypeError, ValueError):
        overall = _clamp(sum(scores.values()) / len(scores))
    flags = [str(x) for x in (data.get("flags") or []) if str(x).strip()]
    comments = str(data.get("comments") or "").strip() or fallback["comments"]
    return {
        "scores": scores,
        "overall": overall,
        "flags": flags,
        "comments": comments,
        "judge": "llm",
        "heuristic": {
            "scores": fallback["scores"],
            "overall": fallback["overall"],
            "flags": fallback["flags"],
        },
    }


async def llm_judge(
    candidate: str,
    references: dict[str, str],
    *,
    llm: Any | None = None,
) -> dict[str, Any]:
    """Call the analyze LLM as judge. Raises if credentials or the call fail."""
    from repowiki.config import Config as RepoWikiConfig
    from repowiki.llm.client import LLMClient
    from repowiki.llm.prompts import extract_json

    client = llm
    if client is None:
        rw = RepoWikiConfig.load()
        if not rw.api_key or not rw.model:
            raise RuntimeError("LLM credentials not configured")
        client = LLMClient(model=rw.model, api_key=rw.api_key, api_base=rw.api_base or "")
    raw = await client.complete(
        _judge_messages(candidate, references),
        max_tokens=512,
        response_format={"type": "json_object"},
    )
    data = extract_json(raw)
    if not isinstance(data, dict):
        raise RuntimeError("judge returned no JSON")
    return _normalize_llm_verdict(data, fallback=heuristic_judge(candidate, references))


def judge_wiki_zh(
    candidate: str,
    references: dict[str, str] | None = None,
    *,
    llm: Any | None = None,
    use_llm: bool | None = None,
) -> dict[str, Any]:
    """Synchronous entry: heuristic always; LLM when a key (or client) is present."""
    refs = references or {}
    heuristic = heuristic_judge(candidate, refs)
    if use_llm is False:
        return heuristic
    if llm is None and use_llm is not True:
        from repowiki.config import Config as RepoWikiConfig

        rw = RepoWikiConfig.load()
        if not rw.api_key or not rw.model:
            return heuristic
    import asyncio

    try:
        return asyncio.run(llm_judge(candidate, refs, llm=llm))
    except Exception:
        return heuristic


def load_bundled_references(fixtures_dir: Path | None = None) -> dict[str, str]:
    if fixtures_dir is not None:
        root = fixtures_dir
    else:
        root = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "wiki_judge"
        if not root.is_dir():
            for parent in Path(__file__).resolve().parents:
                cand = parent / "tests" / "fixtures" / "wiki_judge"
                if cand.is_dir():
                    root = cand
                    break
    out: dict[str, str] = {}
    for name in (
        "deepwiki_overview.md",
        "deepwiki_execution_environment.md",
        "readme_zh.md",
    ):
        path = root / name
        if path.is_file():
            out[name] = path.read_text(encoding="utf-8")
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Judge a zh wiki page against DeepWiki / README.zh")
    parser.add_argument("--candidate", required=True, help="Markdown file to score")
    parser.add_argument(
        "--reference",
        action="append",
        default=[],
        help="Reference markdown (repeatable). Defaults to bundled fixtures.",
    )
    parser.add_argument("--heuristic-only", action="store_true")
    args = parser.parse_args(argv)
    candidate = Path(args.candidate).read_text(encoding="utf-8")
    if args.reference:
        refs = {Path(p).name: Path(p).read_text(encoding="utf-8") for p in args.reference}
    else:
        refs = load_bundled_references()
    verdict = judge_wiki_zh(candidate, refs, use_llm=False if args.heuristic_only else None)
    print(json.dumps(verdict, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
