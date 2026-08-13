"""Conceptual topic plan for the wiki IA (zread 入门指南 / 深入探索).

Directory modules are evidence, not the map. Topics are named as systems
this repository actually has — never a generic web-app syllabus.
"""

from __future__ import annotations

import re
from collections import defaultdict

from repowiki.core.graph import DependencyGraph
from repowiki.core.models import (
    CodebasePart,
    FileInfo,
    KeyType,
    ProjectContext,
    Subsystem,
    TopicDoc,
    TopicOutline,
)
from repowiki.core.module_handbook import fallback_module_doc

_SLUG_RE = re.compile(r"[^a-z0-9]+")
_SKIP_DIRS = {
    "",
    ".",
    "src",
    "lib",
    "root",
    "node_modules",
    "dist",
    "build",
    "vendor",
    "target",
    "tests",
    "test",
    ".cargo",
    ".github",
    ".git",
}

# First-class systems detected from path *segments* (crate/dir names), not
# substrings like "auth" inside "author".
_SYSTEMS: tuple[tuple[str, str, str, tuple[str, ...]], ...] = (
    ("agent-runtime", "Agent Runtime", "Agent Runtime", ("agent", "runtime", "session")),
    (
        "agent-loop",
        "Agent Loop & Context Assembly",
        "Agent Loop 与上下文装配",
        ("loop", "context", "assembly", "conversation"),
    ),
    (
        "system-prompt",
        "System Prompt Templating",
        "System Prompt 模板",
        ("prompt", "template", "system-prompt"),
    ),
    (
        "subagent-scheduling",
        "Sub-Agent Parallel Scheduling",
        "Sub-Agent 并行调度",
        ("subagent", "sub-agent", "scheduler"),
    ),
    ("tool-system", "Tool System", "工具层", ("tool", "tools")),
    ("acp-protocol", "ACP & Protocol", "协议 / ACP", ("acp", "protocol", "jsonrpc")),
    ("terminal-ui", "Terminal UI", "Terminal UI", ("tui", "ratatui", "crossterm")),
    ("pty-control", "PTY / Terminal Control", "PTY 控制", ("pty", "ptyctl")),
    ("headless-modes", "Headless & ACP Modes", "Headless 与 ACP 模式", ("headless",)),
    ("codegen", "Codegen", "代码生成", ("codegen",)),
)

# Only if the repo actually has a directory/crate of that name.
_OPTIONAL_WEB: tuple[tuple[str, str, str, tuple[str, ...]], ...] = (
    ("authentication", "Authentication", "身份认证", ("auth", "oauth", "jwt")),
    ("request-routing", "Request routing", "请求路由", ("router", "routes", "axum", "actix")),
    ("data-persistence", "Data persistence", "数据持久化", ("db", "database", "sqlite", "postgres")),
    ("caching", "Caching", "缓存", ("cache", "redis")),
)

_GENERIC_WEB_SLUGS = {item[0] for item in _OPTIONAL_WEB} | {
    "error-handling",
    "background-tasks",
}

TOPIC_PATH_CAP = 14
GETTING_STARTED_ID = "getting-started"
ENTRY_ID = "entry-and-boot"


def slugify_topic(text: str) -> str:
    s = _SLUG_RE.sub("-", (text or "").lower()).strip("-")
    return s or "topic"


def is_generic_web_slug(slug: str) -> bool:
    return (slug or "") in _GENERIC_WEB_SLUGS


def wiki_page_id_for_topic(topic_id: str) -> str:
    if topic_id in {"overview", "project-goal"}:
        return "index"
    if topic_id == GETTING_STARTED_ID:
        return GETTING_STARTED_ID
    return f"topics/{topic_id}"


def build_deterministic_topics(
    project: ProjectContext,
    graph: DependencyGraph,
    *,
    language: str = "zh",
) -> list[TopicOutline]:
    """Plan 入门 + 深入 topics from entrypoints, PageRank, and system names."""
    zh = _is_zh(language)
    files_by_path = {f.path.replace("\\", "/"): f for f in project.files}
    ranked = graph.rank_files()
    rank_index = {path: i for i, (path, _) in enumerate(ranked)}
    entry_paths = [f.path for f in project.files if f.is_entrypoint]
    if not entry_paths:
        entry_paths = graph.get_entry_points()[:8]

    claimed: set[str] = set()
    topics: list[TopicOutline] = []

    readme = _find_readme(project)
    if readme:
        topics.append(
            TopicOutline(
                id=GETTING_STARTED_ID,
                title="快速开始" if zh else "Quick start",
                section="getting-started",
                purpose=(
                    "从 README / 上手步骤跑起来，再进架构。"
                    if zh
                    else "Get a working run from the README, then read architecture."
                ),
                key_files=[readme],
                depth="brief",
            )
        )
        claimed.add(readme)

    if entry_paths:
        key = _pick_keys(entry_paths, rank_index, claimed, limit=6)
        topics.append(
            TopicOutline(
                id=ENTRY_ID,
                title="入口与启动" if zh else "Entry and boot",
                section="deep-dive",
                purpose=(
                    "进程从哪启动、启动后先装配什么。"
                    if zh
                    else "Where the process starts and what it wires first."
                ),
                key_files=key,
                depth="deep",
            )
        )
        claimed.update(key)

    for topic_id, title_en, title_zh, names in _SYSTEMS:
        matched = [
            f.path
            for f in project.files
            if _path_has_system(f.path, names)
        ]
        if not matched:
            continue
        key = _pick_keys(matched, rank_index, claimed, limit=6)
        if not key:
            # Sibling systems (Agent Runtime vs Agent Loop) may share a crate.
            unused = _pick_keys(matched, rank_index, set(), limit=6)
            key = unused
        if not key:
            continue
        topics.append(
            TopicOutline(
                id=topic_id,
                title=title_zh if zh else title_en,
                section="deep-dive",
                purpose=_purpose_for(title_zh if zh else title_en, zh),
                key_files=key,
                depth="deep" if topic_id in {"agent-runtime", "agent-loop", "tool-system"} else "standard",
            )
        )
        claimed.update(key)
        if len([t for t in topics if t.section == "deep-dive"]) >= TOPIC_PATH_CAP:
            break

    if len([t for t in topics if t.section == "deep-dive"]) < TOPIC_PATH_CAP:
        for topic_id, title_en, title_zh, names in _OPTIONAL_WEB:
            matched = [
                f.path
                for f in project.files
                if _path_has_system(f.path, names) and f.path not in claimed
            ]
            if len(matched) < 2 and not any(_path_has_system(p, names) and "/" in p for p in matched):
                # Need a real directory/crate, not one stray filename.
                if not matched:
                    continue
                dirs = {p.split("/")[0] for p in matched if "/" in p}
                if not dirs:
                    continue
            if not matched:
                continue
            key = _pick_keys(matched, rank_index, claimed, limit=5)
            if not key:
                continue
            topics.append(
                TopicOutline(
                    id=topic_id,
                    title=title_zh if zh else title_en,
                    section="deep-dive",
                    purpose=_purpose_for(title_zh if zh else title_en, zh),
                    key_files=key,
                    depth="standard",
                )
            )
            claimed.update(key)

    # Remaining hubs: name them as systems from crate/leaf, never "模块: path".
    if len([t for t in topics if t.section == "deep-dive"]) < 8:
        clusters: dict[str, list[str]] = defaultdict(list)
        for path, _ in ranked[:40]:
            if path in claimed or path not in files_by_path:
                continue
            leaf = _system_leaf(path)
            if not leaf:
                continue
            clusters[leaf].append(path)
        for leaf, paths in sorted(clusters.items(), key=lambda kv: -len(kv[1])):
            if len([t for t in topics if t.section == "deep-dive"]) >= TOPIC_PATH_CAP:
                break
            if any(t.id == slugify_topic(leaf) for t in topics):
                continue
            key = _pick_keys(paths, rank_index, claimed, limit=5)
            if not key:
                continue
            title = _human_system_title(leaf, zh)
            topics.append(
                TopicOutline(
                    id=slugify_topic(leaf),
                    title=title,
                    section="deep-dive",
                    purpose=_purpose_for(title, zh),
                    key_files=key,
                    depth="standard",
                )
            )
            claimed.update(key)

    return topics


def fallback_topic_doc(
    topic: TopicOutline,
    files: list[FileInfo],
    *,
    language: str = "zh",
    graph: DependencyGraph | None = None,
) -> TopicDoc:
    mod = fallback_module_doc(
        topic.title or topic.id,
        files,
        language=language,
        graph=graph,
        notes=topic.purpose,
    )
    return TopicDoc(
        name=topic.id,
        title=topic.title,
        section=topic.section,
        purpose=topic.purpose or mod.purpose,
        document_scope=topic.purpose or mod.purpose,
        description=mod.description,
        what_it_is=_topic_what_it_is(topic, language),
        key_types=[
            KeyType(
                name=symbol,
                role="",
                path=(topic.key_files[0] if topic.key_files else ""),
            )
            for symbol in (topic.key_symbols or [])[:4]
        ],
        implementation_details=mod.implementation_details,
        call_chains=mod.call_chains,
        mermaid=runtime_mermaid_for(
            entry_files=list(topic.key_files[:1]),
            topics=[topic],
        ),
        edge_cases=mod.edge_cases,
        files=mod.files,
        citations=mod.citations,
        term_tips=mod.term_tips,
    )


def _topic_what_it_is(topic: TopicOutline, language: str) -> list[str]:
    zh = _is_zh(language)
    items: list[str] = []
    cite = f"`{topic.key_files[0]}`" if topic.key_files else ""
    if topic.purpose:
        items.append(f"{topic.purpose} {cite}".strip())
    for path in topic.key_files[:3]:
        if zh:
            items.append(f"这条链路经过 `{path}`。")
        else:
            items.append(f"The call path runs through `{path}`.")
    return items[:4]


def merge_topics(
    base: list[TopicOutline],
    llm: list[TopicOutline],
    known_paths: set[str],
) -> list[TopicOutline]:
    """Prefer LLM titles/purpose; keep only real files; fill from deterministic."""
    if not llm:
        return list(base)
    known = {p.replace("\\", "/") for p in known_paths}
    by_id: dict[str, TopicOutline] = {}
    for item in llm:
        topic_id = slugify_topic(item.id or item.title)
        if not topic_id:
            continue
        files = [p for p in item.key_files if p.replace("\\", "/") in known]
        if not files:
            continue
        section = item.section if item.section in {"getting-started", "deep-dive"} else "deep-dive"
        depth = item.depth if item.depth in {"deep", "standard", "brief"} else "standard"
        title = (item.title or "").strip()
        if not title or title.startswith("模块") or title.lower().startswith("module:"):
            continue
        by_id[topic_id] = TopicOutline(
            id=topic_id,
            title=title,
            section=section,
            purpose=item.purpose or "",
            key_files=files[:8],
            key_symbols=[s for s in item.key_symbols if s][:5],
            depth=depth,
        )
    # Keep deterministic systems the LLM missed, if they still have unused files.
    used = {p for t in by_id.values() for p in t.key_files}
    for item in base:
        if item.id in by_id:
            continue
        files = [p for p in item.key_files if p not in used]
        if not files and item.section == "getting-started":
            files = list(item.key_files)
        if not files:
            continue
        by_id[item.id] = TopicOutline(
            id=item.id,
            title=item.title,
            section=item.section,
            purpose=item.purpose,
            key_files=files[:8],
            key_symbols=item.key_symbols,
            depth=item.depth,
        )
    getting = [t for t in by_id.values() if t.section == "getting-started"]
    deep = [t for t in by_id.values() if t.section != "getting-started"]
    # Preserve LLM order for deep-dive, then leftover deterministic.
    llm_order = [slugify_topic(t.id or t.title) for t in llm]
    ordered: list[TopicOutline] = []
    seen: set[str] = set()
    for tid in llm_order:
        item = by_id.get(tid)
        if item and item.id not in seen and item.section != "getting-started":
            ordered.append(item)
            seen.add(item.id)
    for item in deep:
        if item.id not in seen:
            ordered.append(item)
            seen.add(item.id)
    return (getting + ordered)[: TOPIC_PATH_CAP + 2]


def _is_zh(language: str) -> bool:
    code = (language or "en").strip().lower()
    return code.startswith("zh") or code.startswith("cn")


def find_readme(project: ProjectContext) -> str:
    return _find_readme(project)


def _find_readme(project: ProjectContext) -> str:
    for f in project.files:
        if f.path.lower() in {"readme.md", "readme"}:
            return f.path
    return ""


def _path_has_system(path: str, names: tuple[str, ...]) -> bool:
    parts = path.lower().replace("\\", "/").split("/")
    for part in parts:
        stem = part.rsplit(".", 1)[0]
        tokens = set(re.split(r"[-_]", stem))
        tokens.add(stem)
        tokens.add(part)
        if any(n in tokens for n in names):
            return True
    return False


def _pick_keys(
    paths: list[str],
    rank_index: dict[str, int],
    claimed: set[str],
    *,
    limit: int,
) -> list[str]:
    unused = [p for p in paths if p not in claimed]
    unused.sort(key=lambda p: rank_index.get(p, 10_000))
    return unused[:limit]


def _system_leaf(path: str) -> str:
    parts = [p for p in path.replace("\\", "/").split("/") if p and p not in _SKIP_DIRS]
    if not parts:
        return ""
    if len(parts) >= 2 and parts[0] in {"crates", "packages", "apps"}:
        return parts[1]
    return parts[0]


def _human_system_title(leaf: str, zh: bool) -> str:
    cleaned = leaf.replace("_", " ").replace("-", " ").strip()
    if not cleaned:
        return "核心系统" if zh else "Core system"
    # Keep crate identifiers readable; do not prefix 模块.
    return cleaned


def _purpose_for(title: str, zh: bool) -> str:
    if zh:
        return f"「{title}」在一次真实调用里做什么、缺了它哪条能力会断。"
    return f"What `{title}` does on one real call, and what breaks if it disappears."


def codebase_structure_for(
    project: ProjectContext, *, language: str = "zh", limit: int = 12
) -> list[CodebasePart]:
    """Crate / top-package rows for 代码如何拆分. Not a file dump."""
    zh = _is_zh(language)
    clusters: dict[str, str] = {}
    for f in project.files:
        parts = [p for p in f.path.replace("\\", "/").split("/") if p]
        if not parts or parts[0] in _SKIP_DIRS:
            continue
        if parts[0] in {"crates", "packages", "apps"} and len(parts) > 1:
            name, loc = parts[1], f"{parts[0]}/{parts[1]}"
        elif len(parts) == 1:
            continue
        else:
            name, loc = parts[0], parts[0]
        clusters.setdefault(name, loc)
    rows: list[CodebasePart] = []
    for name, loc in list(clusters.items())[:limit]:
        purpose = (
            f"`{loc}` 这一包在仓库里的职责边界。"
            if zh
            else f"Responsibility boundary of `{loc}`."
        )
        rows.append(CodebasePart(name=name, location=loc, purpose=purpose))
    return rows


def subsystems_from_topics(topics: list[TopicOutline], *, limit: int = 8) -> list[Subsystem]:
    out: list[Subsystem] = []
    for topic in topics:
        if topic.section == "getting-started" or topic.id == GETTING_STARTED_ID:
            continue
        types = [
            KeyType(
                name=symbol,
                role="",
                path=(topic.key_files[0] if topic.key_files else ""),
            )
            for symbol in (topic.key_symbols or [])[:4]
        ]
        out.append(
            Subsystem(
                name=topic.title or topic.id,
                role=topic.purpose,
                key_types=types,
                files=list(topic.key_files[:4]),
            )
        )
        if len(out) >= limit:
            break
    return out


def topic_wiki_links(topics: list[TopicOutline]) -> list[str]:
    links: list[str] = ["architecture"]
    for topic in topics:
        if topic.section == "getting-started" or topic.id == GETTING_STARTED_ID:
            continue
        links.append(wiki_page_id_for_topic(topic.id))
    return links[:12]


def runtime_mermaid_for(
    *,
    entry_files: list[str] | None = None,
    topics=None,
    limit: int = 6,
) -> str:
    """Tiny runtime flowchart when the import graph has no edges."""
    nodes: list[str] = []
    for path in entry_files or []:
        leaf = path.replace("\\", "/").rstrip("/").split("/")[-1]
        if leaf:
            nodes.append(leaf[:32])
            break
    for topic in topics or []:
        section = getattr(topic, "section", "") or ""
        tid = getattr(topic, "id", "") or getattr(topic, "name", "")
        if section == "getting-started" or tid == GETTING_STARTED_ID:
            continue
        title = getattr(topic, "title", "") or tid
        label = re.sub(r'[\[\]{}"#\n]', " ", str(title))
        label = re.sub(r"\s+", " ", label).strip()[:32]
        if label:
            nodes.append(label)
        if len(nodes) >= limit + 1:
            break
    if len(nodes) < 2:
        return ""
    lines = ["flowchart TD"]
    ids = [f"n{i}" for i in range(len(nodes))]
    for nid, lab in zip(ids, nodes, strict=True):
        lines.append(f'  {nid}["{lab}"]')
    for src, dst in zip(ids, ids[1:], strict=False):
        lines.append(f"  {src} --> {dst}")
    return "\n".join(lines)
