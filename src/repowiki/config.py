"""configuration management for repowiki."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

_CONFIG_DIR = Path.home() / ".repowiki"
_CONFIG_FILE = _CONFIG_DIR / "config.json"

# shortcuts so users don't have to type full provider/model strings
MODEL_ALIASES = {
    "deepseek": "deepseek/deepseek-chat",
    "opus": "anthropic/claude-opus-4-6",
    "claude": "anthropic/claude-sonnet-4-6",
    "gpt": "gpt-5.4",
    "gpt-mini": "gpt-5.4-mini",
    "gemini": "gemini/gemini-3.1-pro-preview",
    "gemini-flash": "gemini/gemini-2.5-flash",
    "qwen": "openai/qwen3.5-plus",
    "kimi": "openai/kimi-k2.6",
    "glm": "openai/glm-5",
    "minimax": "openai/MiniMax-M2.7",
    "agnes": "agnes/agnes-2.0-flash",
    "agnes-2.5": "agnes/agnes-2.5-flash",
}

# Endpoints for hubs we can name, so configuring a key alone is enough to get
# running. Keyed by the provider prefix of the resolved model. The generic
# ``openai/`` prefix is deliberately absent: it names a wire format, not a host,
# and the aliases above route it at whatever hub the user points REPOWIKI_API_BASE at.
PROVIDER_API_BASES = {
    "agnes": "https://apihub.agnes-ai.com/v1",
    "deepseek": "https://api.deepseek.com/v1",
}

# Hub-specific key vars that also imply which model to talk to.
PROVIDER_KEY_ENVS = {
    "AGNES_API_KEY": "agnes",
    "DEEPSEEK_API_KEY": "deepseek",
}


def resolve_model(name: str) -> str:
    return MODEL_ALIASES.get(name, name)


def provider_of(model: str) -> str:
    return model.split("/", 1)[0] if "/" in model else ""


@dataclass
class Config:
    model: str = "deepseek/deepseek-chat"
    api_key: str = ""
    api_base: str = ""
    language: str = "en"
    max_file_size: int = 200 * 1024  # 200 KB
    max_files: int = 1000
    output_dir: str = "./wiki"
    concurrency: int = 5

    @classmethod
    def load(cls) -> Config:
        """Load config from file, then override with env vars."""
        data: dict = {}
        if _CONFIG_FILE.exists():
            try:
                data = json.loads(_CONFIG_FILE.read_text())
            except (json.JSONDecodeError, OSError):
                pass

        cfg = cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

        # env overrides
        model_chosen = bool(data.get("model"))
        if val := os.getenv("REPOWIKI_MODEL"):
            cfg.model = val
            model_chosen = True
        if val := os.getenv("REPOWIKI_API_KEY"):
            cfg.api_key = val
        if val := os.getenv("REPOWIKI_API_BASE"):
            cfg.api_base = val
        if val := os.getenv("REPOWIKI_LANG"):
            cfg.language = val

        # fall back to provider-specific keys; a hub key also selects its model
        # unless one was chosen explicitly, so setting AGNES_API_KEY alone works
        # instead of silently aiming an Agnes key at the DeepSeek default.
        hub_key = False
        if not cfg.api_key:
            for env_key, hub in PROVIDER_KEY_ENVS.items():
                if val := os.getenv(env_key):
                    cfg.api_key = val
                    hub_key = True
                    if not model_chosen:
                        cfg.model = hub
                    break
        if not cfg.api_key:
            for env_key in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
                if val := os.getenv(env_key):
                    cfg.api_key = val
                    break

        cfg.model = resolve_model(cfg.model)
        # Only supply an endpoint once the provider is actually established —
        # named in the model, or implied by its own key var. Pairing the default
        # model with an unrelated key is a mismatch to surface, not to route.
        if not cfg.api_base and (model_chosen or hub_key):
            cfg.api_base = PROVIDER_API_BASES.get(provider_of(cfg.model), "")
        return cfg

    def save(self) -> None:
        _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        data = {
            "model": self.model,
            "api_key": self.api_key,
            "api_base": self.api_base,
            "language": self.language,
        }
        # don't persist empty values
        data = {k: v for k, v in data.items() if v}
        _CONFIG_FILE.write_text(json.dumps(data, indent=2) + "\n")

    def to_dict(self) -> dict:
        return {k: getattr(self, k) for k in self.__dataclass_fields__}
