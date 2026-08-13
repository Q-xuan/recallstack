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
    # Loop before runtime so xai-grok-agent agent.rs/turn/run is not stolen by
    # the "agent" token, and before context-assembly so conversation_util cannot
    # become the Agent Loop evidence pack.
    (
        "agent-loop",
        "Agent Loop",
        "Agent Loop",
        ("loop", "turn"),
    ),
    (
        "context-assembly",
        "Context assembly",
        "上下文装配",
        ("conversation", "chat-state", "prompt-context", "system-head"),
    ),
    ("agent-runtime", "Agent Runtime", "Agent Runtime", ("agent", "runtime", "session")),
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
    (
        "codebase-graph",
        "Codebase graph",
        "代码图谱",
        ("code-graph", "codebase-graph", "codegraph"),
    ),
    ("codegen", "Codegen", "代码生成", ("codegen",)),
)

# Only if the repo actually has a directory/crate of that name.
_OPTIONAL_WEB: tuple[tuple[str, str, str, tuple[str, ...]], ...] = (
    ("authentication", "Authentication", "身份认证", ("auth", "oauth", "jwt")),
    ("request-routing", "Request routing", "请求路由", ("router", "routes", "axum", "actix")),
    ("data-persistence", "Data persistence", "数据持久化", ("db", "database", "sqlite", "postgres")),
    ("caching", "Caching", "缓存", ("cache", "redis")),
)

_OPTIONAL_WEB_BY_ID = {item[0]: item for item in _OPTIONAL_WEB}

_GENERIC_WEB_SLUGS = {item[0] for item in _OPTIONAL_WEB} | {
    "error-handling",
    "background-tasks",
}

_PKG_ROOTS = {"crates", "packages", "apps"}

TOPIC_PATH_CAP = 14
GETTING_STARTED_ID = "getting-started"
ENTRY_ID = "entry-and-boot"


def slugify_topic(text: str) -> str:
    s = _SLUG_RE.sub("-", (text or "").lower()).strip("-")
    return s or "topic"


def is_generic_web_slug(slug: str) -> bool:
    return (slug or "") in _GENERIC_WEB_SLUGS


def web_system_names(slug: str) -> tuple[str, ...] | None:
    """Path-segment tokens that make a generic-web slug first-class, or None."""
    item = _OPTIONAL_WEB_BY_ID.get(slug or "")
    return item[3] if item else None


def first_class_system_dir(path: str, names: tuple[str, ...]) -> bool:
    """True when a crate/directory name (not a leaf file) matches ``names``.

    ``crates/xai-grok-auth/src/lib.rs`` counts for authentication; a helper
    ``crates/agent/src/auth.rs`` does not.
    """
    if not path or not names:
        return False
    parts = [p for p in path.replace("\\", "/").split("/") if p]
    if not parts:
        return False
    dirs = parts[:-1] if "." in parts[-1] else parts
    wanted = {n.lower() for n in names}
    candidates: list[str] = [d for d in dirs if d.lower() not in _SKIP_DIRS]
    if parts[0].lower() in _PKG_ROOTS:
        for d in parts[1:]:
            if "." in d:
                break
            if d.lower() in _SKIP_DIRS:
                continue
            candidates.append(d)
    for cand in candidates:
        stem = cand.rsplit(".", 1)[0].lower()
        tokens = set(re.split(r"[-_]", stem))
        tokens.add(stem)
        if tokens & wanted:
            return True
    return False


def repo_has_web_system(paths, slug: str) -> bool:
    """Generic web slug is allowed only when a matching crate/dir exists."""
    names = web_system_names(slug)
    if not names:
        return False
    return any(first_class_system_dir(p, names) for p in paths or [])


def content_cites_first_class_system(content: str, names: tuple[str, ...]) -> bool:
    for match in re.finditer(r"`([^`]+)`", content or ""):
        path = match.group(1).split()[0].split(":")[0]
        if first_class_system_dir(path, names):
            return True
    return False


def keep_generic_web_topic_nav(page_id: str, content: str) -> bool:
    """GET/sidebar: drop caching-style pages unless the body cites a real crate."""
    pid = page_id or ""
    if pid.startswith("topics/") or pid.startswith("concepts/"):
        slug = pid.split("/", 1)[-1]
    else:
        return True
    if not is_generic_web_slug(slug):
        return True
    names = web_system_names(slug)
    if not names:
        return False
    return content_cites_first_class_system(content, names)


def omit_generic_web_wiki_page(page_id: str, content: str) -> bool:
    """True when a stub caching/routing concept or topic must leave wiki GET."""
    return not keep_generic_web_topic_nav(page_id, content) and (
        (page_id or "").startswith("topics/") or (page_id or "").startswith("concepts/")
    )


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
            if _file_matches_system(f.path, topic_id, names)
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
                purpose=_purpose_for(title_zh if zh else title_en, zh, topic_id=topic_id),
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
                if first_class_system_dir(f.path, names)
            ]
            if not matched:
                continue
            key = _pick_keys(matched, rank_index, claimed, limit=5)
            if not key:
                # Nested crates (codegen/xai-grok-auth) may already be claimed
                # by a parent system name; still emit the first-class topic.
                key = _pick_keys(matched, rank_index, set(), limit=5)
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
        if is_generic_web_slug(topic_id) and not repo_has_web_system(known, topic_id):
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
        if is_generic_web_slug(item.id) and not repo_has_web_system(known, item.id):
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
    _rebind_loop_and_assembly(by_id, known, base)
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


_ASSEMBLY_NEEDLES = (
    "conversation_util",
    "prompt_context",
    "promptcontext",
    "chat-state",
    "chat_state",
    "system_head",
    "replace_or_insert",
)
_LOOP_FILE_STEMS = {
    "agent",
    "loop",
    "turn",
    "run",
    "dispatch",
    "tool_dispatch",
    "tool_call",
    "tools",
    "tool",
}
_AGENT_CRATE_RE = re.compile(
    r"(?:^|/)(?:(?:xai-)?grok-agent|crates/agent|packages/agent)(?:/|$)",
    re.I,
)


def _norm_topic_path(path: str) -> str:
    return (path or "").replace("\\", "/").lower()


def is_context_assembly_file(path: str) -> bool:
    """System-head / PromptContext / chat-state — not the runtime agent loop."""
    low = _norm_topic_path(path)
    if any(needle in low for needle in _ASSEMBLY_NEEDLES):
        return True
    return _path_has_system(
        path, ("conversation", "chat-state", "prompt-context", "system-head")
    )


def is_agent_loop_file(path: str) -> bool:
    """Runtime loop (run / turn / tool dispatch), never conversation_util."""
    if is_context_assembly_file(path):
        return False
    if _path_has_system(path, ("loop", "turn")):
        return True
    low = _norm_topic_path(path)
    if not _AGENT_CRATE_RE.search(low):
        return False
    stem = low.rsplit("/", 1)[-1].rsplit(".", 1)[0]
    if stem in _LOOP_FILE_STEMS or "dispatch" in stem or stem.endswith("_loop"):
        return True
    return False


def _file_matches_system(path: str, topic_id: str, names: tuple[str, ...]) -> bool:
    if topic_id == "agent-loop":
        return is_agent_loop_file(path)
    if topic_id == "context-assembly":
        return is_context_assembly_file(path)
    return _path_has_system(path, names)


def _topics_look_zh(topics: list[TopicOutline]) -> bool:
    for item in topics:
        for ch in item.title or "":
            if "\u4e00" <= ch <= "\u9fff":
                return True
    return False


def _system_title(topic_id: str, zh: bool) -> str:
    for tid, title_en, title_zh, _names in _SYSTEMS:
        if tid == topic_id:
            return title_zh if zh else title_en
    return topic_id


def _rebind_loop_and_assembly(
    by_id: dict[str, TopicOutline],
    known: set[str],
    base: list[TopicOutline],
) -> None:
    """Keep agent-loop on the runtime crate; move conversation_util off it."""
    zh = _topics_look_zh(list(by_id.values()) + list(base))
    known_list = sorted(p.replace("\\", "/") for p in known)
    loop_pool = [p for p in known_list if is_agent_loop_file(p)]
    assembly_pool = [p for p in known_list if is_context_assembly_file(p)]

    loop = by_id.get("agent-loop")
    moved_assembly: list[str] = []
    if loop:
        title = loop.title or ""
        if "上下文装配" in title or "context assembly" in title.lower():
            loop.title = _system_title("agent-loop", zh)
            loop.purpose = _purpose_for(loop.title, zh, topic_id="agent-loop")
        kept = [p for p in loop.key_files if not is_context_assembly_file(p)]
        moved_assembly = [p for p in loop.key_files if is_context_assembly_file(p)]
        if not any(is_agent_loop_file(p) for p in kept) and loop_pool:
            kept = loop_pool[:6]
        else:
            for path in loop_pool:
                if path not in kept:
                    kept.append(path)
                if len(kept) >= 8:
                    break
        loop.key_files = kept[:8]
        if not loop.purpose or "上下文装配" in (loop.purpose or ""):
            loop.purpose = _purpose_for(loop.title, zh, topic_id="agent-loop")

    assembly = by_id.get("context-assembly")
    assembly_files = list((assembly.key_files if assembly else []) or [])
    assembly_files = [p for p in assembly_files if not is_agent_loop_file(p)]
    for path in moved_assembly + assembly_pool:
        if path not in assembly_files:
            assembly_files.append(path)
    assembly_files = assembly_files[:8]
    if assembly:
        assembly.key_files = assembly_files
        if not assembly.key_files:
            by_id.pop("context-assembly", None)
        else:
            if "Agent Loop" in (assembly.title or "") and "装配" not in (assembly.title or ""):
                assembly.title = _system_title("context-assembly", zh)
            if not assembly.purpose:
                assembly.purpose = _purpose_for(
                    assembly.title, zh, topic_id="context-assembly"
                )
    elif assembly_files:
        title = _system_title("context-assembly", zh)
        by_id["context-assembly"] = TopicOutline(
            id="context-assembly",
            title=title,
            section="deep-dive",
            purpose=_purpose_for(title, zh, topic_id="context-assembly"),
            key_files=assembly_files,
            depth="standard",
        )


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
    low = leaf.lower().replace("_", "-")
    if low in {"code-graph", "codebase-graph", "codegraph"}:
        return "代码图谱" if zh else "Codebase graph"
    # Keep crate identifiers readable; do not prefix 模块.
    return cleaned


def _purpose_for(title: str, zh: bool, topic_id: str = "") -> str:
    if topic_id == "agent-loop":
        if zh:
            return (
                "一次会话怎么从用户输入走到组 prompt、调模型、解析并执行工具、"
                "把结果写回、再进入下一轮或结束。"
            )
        return (
            "How one session walks user input → prompt → model call → tool → "
            "write-back → next turn or stop."
        )
    if topic_id == "context-assembly":
        if zh:
            return (
                "会话历史里 System 头和 PromptContext 怎么对齐；这不是 Agent Loop 本身。"
            )
        return (
            "How System head / PromptContext is assembled — not the agent loop."
        )
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
