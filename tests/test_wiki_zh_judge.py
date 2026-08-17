"""DeepSeek judge harness: heuristic works without a key."""

from __future__ import annotations

import json
from pathlib import Path

from recallstack.learning.wiki_judge import (
    heuristic_judge,
    judge_wiki_zh,
    load_bundled_references,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "wiki_judge"


def _read(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_bundled_references_are_local_fixtures():
    refs = load_bundled_references(FIXTURES)
    assert "deepwiki_overview.md" in refs
    assert "deepwiki_execution_environment.md" in refs
    assert "readme_zh.md" in refs
    assert "Capability Seam" in refs["deepwiki_overview.md"]
    assert "ctx.fs" in refs["deepwiki_execution_environment.md"]
    assert "agent harness（智能体框架）" in refs["readme_zh.md"]
    assert "deepwiki.com" not in refs["deepwiki_overview.md"]


def test_heuristic_detects_lecture_tone():
    verdict = heuristic_judge(_read("lecture_sample.md"), load_bundled_references(FIXTURES))
    assert "lecture_tone" in verdict["flags"]
    assert verdict["scores"]["handbook_tone"] <= 2
    assert verdict["judge"] == "heuristic"
    assert "讲义腔" in verdict["comments"]
    payload = json.dumps(verdict, ensure_ascii=False)
    assert "handbook_tone" in payload


def test_heuristic_passes_handbook_sample():
    verdict = heuristic_judge(_read("handbook_sample.md"), load_bundled_references(FIXTURES))
    assert "lecture_tone" not in verdict["flags"]
    assert "bad_translation" not in verdict["flags"]
    assert verdict["scores"]["handbook_tone"] >= 4
    assert verdict["scores"]["terminology"] >= 4
    assert verdict["scores"]["evidence"] >= 4
    assert verdict["scores"]["structure"] >= 4
    assert "手册口吻" in verdict["comments"]


def test_heuristic_flags_agent_as_dailiren():
    page = "# Agent\n\n这个代理人调度 plugin，把循环跑完。\n"
    verdict = heuristic_judge(page)
    assert "bad_translation" in verdict["flags"]
    assert verdict["scores"]["terminology"] <= 2


def test_judge_wiki_zh_skips_llm_without_key(monkeypatch):
    monkeypatch.delenv("REPOWIKI_API_KEY", raising=False)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("AGNES_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    verdict = judge_wiki_zh(_read("lecture_sample.md"), load_bundled_references(FIXTURES))
    assert verdict["judge"] == "heuristic"
    assert "lecture_tone" in verdict["flags"]


def test_judge_wiki_zh_uses_injected_llm():
    class _Fake:
        async def complete(self, messages, max_tokens=512, response_format=None):
            assert "handbook_tone" in messages[-1]["content"]
            return json.dumps(
                {
                    "scores": {
                        "handbook_tone": 5,
                        "naturalness": 5,
                        "terminology": 5,
                        "evidence": 4,
                        "structure": 5,
                    },
                    "overall": 5,
                    "flags": [],
                    "comments": "手册口吻，术语保持英文。",
                }
            )

    verdict = judge_wiki_zh(_read("handbook_sample.md"), load_bundled_references(FIXTURES), llm=_Fake())
    assert verdict["judge"] == "llm"
    assert verdict["scores"]["handbook_tone"] == 5
    assert verdict["comments"].startswith("手册口吻")
