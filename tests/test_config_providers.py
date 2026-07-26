"""Provider resolution: model alias, endpoint default, and key precedence."""

from __future__ import annotations

import pytest

from repowiki.config import Config
from repowiki.llm.prompts import build_overview_prompt

# Every var Config.load reads, cleared so a developer's own .env or shell does
# not leak into the assertions below.
_LLM_ENV = (
    "REPOWIKI_MODEL",
    "REPOWIKI_API_KEY",
    "REPOWIKI_API_BASE",
    "REPOWIKI_LANG",
    "AGNES_API_KEY",
    "DEEPSEEK_API_KEY",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
)


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch, tmp_path):
    for name in _LLM_ENV:
        monkeypatch.delenv(name, raising=False)
    # Config.load also merges ~/.repowiki/config.json; point it at an empty dir.
    monkeypatch.setattr("repowiki.config._CONFIG_FILE", tmp_path / "config.json")
    return monkeypatch


def test_agnes_key_alone_selects_model_and_endpoint(clean_env):
    clean_env.setenv("AGNES_API_KEY", "sk-agnes")

    cfg = Config.load()

    assert cfg.api_key == "sk-agnes"
    assert cfg.model == "agnes/agnes-2.0-flash"
    assert cfg.api_base == "https://apihub.agnes-ai.com/v1"


def test_explicit_model_survives_a_hub_key(clean_env):
    clean_env.setenv("AGNES_API_KEY", "sk-agnes")
    clean_env.setenv("REPOWIKI_MODEL", "deepseek/deepseek-chat")

    cfg = Config.load()

    assert cfg.model == "deepseek/deepseek-chat"
    assert cfg.api_base == "https://api.deepseek.com/v1"


def test_explicit_api_base_wins_over_the_default(clean_env):
    clean_env.setenv("AGNES_API_KEY", "sk-agnes")
    clean_env.setenv("REPOWIKI_API_BASE", "http://localhost:1234/v1")

    assert Config.load().api_base == "http://localhost:1234/v1"


def test_generic_key_leaves_the_endpoint_unset(clean_env):
    # OPENAI_API_KEY names a wire format more than a host here, so guessing an
    # endpoint from it would point compatible hubs at the wrong server.
    clean_env.setenv("OPENAI_API_KEY", "sk-openai")

    cfg = Config.load()

    assert cfg.api_key == "sk-openai"
    assert cfg.api_base == ""


def test_agnes_alias_resolves(clean_env):
    clean_env.setenv("REPOWIKI_MODEL", "agnes")
    clean_env.setenv("REPOWIKI_API_KEY", "sk-x")

    assert Config.load().model == "agnes/agnes-2.0-flash"


@pytest.mark.parametrize("language", ["zh", "ja", "ko"])
def test_non_english_prompts_restate_the_output_language(language):
    # The schema in each prompt uses English placeholder values; without a
    # restatement next to it, smaller models answer in the schema's language.
    closing = build_overview_prompt("tree", "files", language)[-1]["content"]

    assert "LANGUAGE:" in closing
    assert "do not copy their language" in closing


def test_english_prompts_carry_no_language_clause():
    closing = build_overview_prompt("tree", "files", "en")[-1]["content"]

    assert "LANGUAGE:" not in closing
