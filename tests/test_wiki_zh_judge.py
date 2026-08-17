"""DeepSeek judge harness: heuristic works without a key."""

from __future__ import annotations

import json
from pathlib import Path

from recallstack.learning.wiki_judge import (
    LECTURE_MARKERS,
    heuristic_judge,
    judge_wiki_zh,
    load_bundled_references,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "wiki_judge"

_DUMP_STAMPS = (
    "你负责",
    "并签字",
    "缺了它哪条能力会断",
    "用户能察觉的行为会坏",
    "北极星",
    "复述标题不算过关",
    "本步要你干什么",
)


def _read(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_bundled_references_are_local_fixtures():
    refs = load_bundled_references(FIXTURES)
    assert "grok_build_overview.md" in refs
    assert "grok_build_tui_pager.md" in refs
    assert "deepwiki_overview.md" in refs
    assert "deepwiki_execution_environment.md" in refs
    assert "readme_zh.md" in refs
    assert "TUI Pager" in refs["grok_build_overview.md"]
    assert "xai-grok-pager" in refs["grok_build_tui_pager.md"]
    assert "Capability Seam" in refs["deepwiki_overview.md"]
    assert "ctx.fs" in refs["deepwiki_execution_environment.md"]
    assert "agent harness（智能体框架）" in refs["readme_zh.md"]
    assert "deepwiki.com" not in refs["grok_build_overview.md"]
    assert "deepwiki.com" not in refs["deepwiki_overview.md"]


def test_heuristic_detects_lecture_tone():
    verdict = heuristic_judge(_read("lecture_sample.md"), load_bundled_references(FIXTURES))
    assert "lecture_tone" in verdict["flags"]
    assert "stiff_translation" in verdict["flags"]
    assert verdict["scores"]["handbook_tone"] <= 2
    assert verdict["judge"] == "heuristic"
    assert "讲义腔" in verdict["comments"]
    payload = json.dumps(verdict, ensure_ascii=False)
    assert "handbook_tone" in payload


def test_heuristic_fails_grok_study_dump_stamps_without_key():
    """No API key: lecture fixtures must fail on the dump stamps themselves."""
    refs = load_bundled_references(FIXTURES)
    wiki = heuristic_judge(_read("lecture_sample.md"), refs)
    path = heuristic_judge(_read("lecture_path_sample.md"), refs)
    quiz = heuristic_judge(_read("lecture_quiz_sample.md"), refs)
    for verdict, name in ((wiki, "wiki"), (path, "path"), (quiz, "quiz")):
        assert verdict["judge"] == "heuristic", name
        assert "lecture_tone" in verdict["flags"], name
        assert verdict["scores"]["handbook_tone"] <= 2, name
        assert verdict["scores"]["naturalness"] <= 3, name
    assert "workbook" in path["flags"]
    assert any(stamp in _read("lecture_path_sample.md") for stamp in _DUMP_STAMPS)
    for stamp in (
        "你负责",
        "并签字",
        "缺了它哪条能力会断",
        "用户能察觉的行为会坏",
        "北极星",
    ):
        assert stamp in LECTURE_MARKERS


def test_heuristic_passes_handbook_sample():
    verdict = heuristic_judge(_read("handbook_sample.md"), load_bundled_references(FIXTURES))
    assert "lecture_tone" not in verdict["flags"]
    assert "workbook" not in verdict["flags"]
    assert "bad_translation" not in verdict["flags"]
    assert verdict["scores"]["handbook_tone"] >= 4
    assert verdict["scores"]["terminology"] >= 4
    assert verdict["scores"]["evidence"] >= 4
    assert verdict["scores"]["structure"] >= 4
    assert "手册口吻" in verdict["comments"]


def test_heuristic_passes_handbook_path_sample():
    verdict = heuristic_judge(_read("handbook_path_sample.md"), load_bundled_references(FIXTURES))
    assert "lecture_tone" not in verdict["flags"]
    assert "workbook" not in verdict["flags"]
    assert verdict["scores"]["handbook_tone"] >= 4
    assert "start_turn" in _read("handbook_path_sample.md")
    assert "你负责" not in _read("handbook_path_sample.md")
    assert "过关" not in _read("handbook_path_sample.md")


def test_heuristic_flags_translated_identifiers():
    page = "# 入口\n\n智能体客户端协议在 connect 之后把伪终端句柄交给开始回合。\n"
    verdict = heuristic_judge(page)
    assert "translated_identifier" in verdict["flags"]
    assert verdict["scores"]["terminology"] <= 3


def test_heuristic_keeps_english_identifiers():
    page = (
        "# ACP\n\n"
        "ACP 的 connect 之后，`PtyHandle` 仍由 runtime 持有。`start_turn` 推一轮。\n"
        "`crates/tui/src/app.rs:142 start_turn`\n"
    )
    verdict = heuristic_judge(page)
    assert "translated_identifier" not in verdict["flags"]
    assert verdict["scores"]["terminology"] >= 4


def test_heuristic_pairs_grok_build_overview_and_tui():
    refs = load_bundled_references(FIXTURES)
    overview = heuristic_judge(
        "# 概述\n\n## 概述\n\ngrok-build 的 TUI 与 Pager 是同一扇门。\n",
        refs,
    )
    assert any("overview ↔ 概述" in p for p in overview["pairs"])
    assert any("TUI pager ↔ TUI 与 Pager" in p for p in overview["pairs"])
    assert overview["scores"]["structure"] >= 4


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
    verdict = judge_wiki_zh(_read("lecture_path_sample.md"), load_bundled_references(FIXTURES))
    assert verdict["judge"] == "heuristic"
    assert "lecture_tone" in verdict["flags"]
    assert verdict["scores"]["handbook_tone"] <= 2


def test_judge_wiki_zh_uses_injected_llm():
    class _Fake:
        async def complete(self, messages, max_tokens=512, response_format=None):
            assert "handbook_tone" in messages[-1]["content"]
            assert "ACP" in messages[-1]["content"]
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
