"""Classify repo paths: product code vs agent notes / nav metadata.

`.agents/notes` and `.i18n.yaml` are real files and may stay in version_files.
They must not win overview / getting-started / sidebar IA when packages/apps
exist — that is decision-log volume, not the product.
"""

from __future__ import annotations

import re

_AGENT_ROOTS = frozenset(
    {".agents", ".claude", ".cursor", ".codex", ".windsurf", ".gemini"}
)
_METADATA_LEAVES = frozenset({".i18n.yaml", ".i18n.yml"})
_PRODUCT_ROOTS = frozenset(
    {"packages", "apps", "app", "crates", "src", "lib", "docs", "vendor", "bin"}
)
_PRODUCT_LEAVES = frozenset(
    {
        "readme.md",
        "readme",
        "package.json",
        "pnpm-workspace.yaml",
        "yarn.lock",
        "pnpm-lock.yaml",
        "cargo.toml",
        "go.mod",
        "pyproject.toml",
    }
)

_NOTES_AS_PRODUCT_RE = re.compile(
    r"决策日志仓库|架构记忆库|"
    r"不是.{0,24}(?:源码|实现)|"
    r"只是(?:决策日志|架构记忆)|"
    r"notes 目录层级|"
    r"not (?:the |an? )?(?:source(?: code)?(?: implementation)?|implementation)"
    r"|only (?:a |the )?decision[- ]logs?"
    r"|decision[- ]log (?:repo|warehouse|memory)",
    re.I,
)
_NOTES_NAME_RE = re.compile(
    r"决策日志|记忆库|\.agents|notes 目录|i18n 元数据|archived",
    re.I,
)


def norm_path(path: str) -> str:
    return (path or "").replace("\\", "/").strip("/")


def path_parts(path: str) -> list[str]:
    return [p for p in norm_path(path).split("/") if p]


def is_agent_memory_path(path: str) -> bool:
    """Decision logs, agent notes, archived notes, or i18n nav metadata."""
    parts = path_parts(path)
    if not parts:
        return False
    leaf = parts[-1].lower()
    if leaf in _METADATA_LEAVES or leaf.startswith(".i18n."):
        return True
    root = parts[0].lower()
    if root in _AGENT_ROOTS:
        return True
    if root == "notes" and any(p.lower() == "archived" for p in parts):
        return True
    return False


def is_product_path(path: str) -> bool:
    """packages / apps / crates / docs / README — the product tree."""
    if is_agent_memory_path(path):
        return False
    parts = path_parts(path)
    if not parts:
        return False
    if parts[-1].lower() in _PRODUCT_LEAVES:
        return True
    return parts[0].lower() in _PRODUCT_ROOTS


def repo_is_notes_primary(paths) -> bool:
    """True when the tree has no product code — notes *are* the repo."""
    all_paths = [p for p in (paths or []) if p]
    if not all_paths:
        return False
    product = sum(1 for p in all_paths if is_product_path(p))
    notes = sum(1 for p in all_paths if is_agent_memory_path(p))
    return product == 0 and notes >= 3


def product_rank(path: str) -> int:
    """Lower is better for hubs, file-tree truncation, and scan walk order."""
    if is_agent_memory_path(path):
        return 80
    low = norm_path(path).lower()
    leaf = low.rsplit("/", 1)[-1]
    if leaf in {"readme.md", "readme"} or low.startswith("docs/"):
        return 0
    if low.startswith(("packages/", "apps/", "crates/")):
        return 1
    if low.startswith("vendor/"):
        return 2
    if is_product_path(path):
        return 3
    return 20


def walk_dir_priority(dirname: str) -> tuple:
    """os.walk sibling order: product dirs before `.agents` / notes."""
    low = (dirname or "").lower()
    if low in {"packages", "apps", "app", "crates", "src", "lib", "docs"}:
        return (0, low)
    if low in {"vendor", "bin"}:
        return (1, low)
    if low.startswith(".") or low in {"notes", "archived"}:
        return (3, low)
    return (2, low)


def prose_treats_notes_as_product(text: str) -> bool:
    """True when copy claims the repo is a decision-log, not the product."""
    return bool(_NOTES_AS_PRODUCT_RE.search(text or ""))


def name_is_notes_product(name: str) -> bool:
    """True when an overview/page title is a notes-tree nickname."""
    text = name or ""
    if not text.strip():
        return False
    if _NOTES_NAME_RE.search(text):
        return True
    return False


def topic_paths_are_agent_memory(paths) -> bool:
    items = [p for p in (paths or []) if p]
    return bool(items) and all(is_agent_memory_path(p) for p in items)


_PLACEHOLDER_TITLES = frozenset(
    {
        "typename",
        "type name",
        "project name",
        "name",
        "untitled",
        "overview",
        "概述",
        "symbol",
        "filename",
        "path",
        "line",
    }
)
_PLACEHOLDER_EXACT = frozenset({"TypeName", "FileName", "Symbol", "Type"})


def is_placeholder_title(name: str) -> bool:
    """True for schema leftovers (TypeName) or an empty identifier."""
    raw = (name or "").strip().strip("`")
    if not raw:
        return True
    if raw in _PLACEHOLDER_EXACT:
        return True
    if raw.lower() in _PLACEHOLDER_TITLES:
        return True
    if re.fullmatch(r"src/file\.\w+", raw, re.I):
        return True
    return False


def readme_product_title(project) -> str:
    """First README H1, e.g. ``# DeepSeek Harness`` → DeepSeek Harness."""
    for item in getattr(project, "files", None) or []:
        path = (getattr(item, "path", "") or "").replace("\\", "/").lower()
        if path not in {"readme.md", "readme"}:
            continue
        text = getattr(item, "content", "") or getattr(item, "preview", "") or ""
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("# ") and not stripped.startswith("## "):
                title = re.sub(r"\s*\(.*\)$", "", stripped[2:].strip().strip("`")).strip()
                if title and not is_placeholder_title(title):
                    return title
    return ""


def product_display_name(overview, project) -> str:
    """Handbook H1: product title, never TypeName or an empty identifier."""
    overview_name = (getattr(overview, "name", "") or "").strip()
    if name_is_notes_product(overview_name):
        overview_name = ""
    project_name = (getattr(project, "name", "") or "").strip()
    readme_title = readme_product_title(project)

    def _slug(value: str) -> str:
        return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")

    if overview_name and not is_placeholder_title(overview_name):
        if readme_title and _slug(overview_name) == _slug(project_name):
            return readme_title
        return overview_name
    if readme_title:
        return readme_title
    if project_name and not is_placeholder_title(project_name):
        return project_name
    return readme_title or "Overview"


def prefer_product_overview(overview, project, *, language: str = "zh") -> None:
    """Rewrite notes-as-product overview fields back to the harness product."""
    paths = [getattr(f, "path", "") for f in (getattr(project, "files", None) or [])]
    if repo_is_notes_primary(paths):
        return
    overview.name = product_display_name(overview, project)
    zh = (language or "zh").startswith("zh") or (language or "").startswith("cn")
    product = overview.name or getattr(project, "name", "") or "this repo"
    if prose_treats_notes_as_product(getattr(overview, "document_scope", "") or ""):
        overview.document_scope = (
            f"{product} 的目标、一次真实调用经过谁、仓库怎么拆。"
            "关键类型保持英文 identifier，证据用 path:line Symbol 贴在断言旁边。"
            if zh
            else (
                f"{product}: the goal, who a real call passes through, "
                "and how the repo is split. Key types stay English identifiers; "
                "evidence is path:line Symbol next to the claim."
            )
        )
    if prose_treats_notes_as_product(getattr(overview, "one_liner", "") or ""):
        overview.one_liner = (
            f"{product}：一次真实调用里这个仓库怎么串起来"
            if zh
            else f"{product}: how this repo is wired on one real call"
        )
    if prose_treats_notes_as_product(getattr(overview, "description", "") or ""):
        readme = next(
            (
                f
                for f in (getattr(project, "files", None) or [])
                if (getattr(f, "path", "") or "").lower() in {"readme.md", "readme"}
            ),
            None,
        )
        text = ""
        if readme:
            text = (getattr(readme, "content", "") or getattr(readme, "preview", "") or "").strip()
        overview.description = text[:800] if text else ""
    if prose_treats_notes_as_product(getattr(overview, "runtime_flow", "") or ""):
        overview.runtime_flow = ""
