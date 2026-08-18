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
from repowiki.core.module_handbook import (
    fallback_module_doc,
    is_canned_handbook_stub_text,
    topic_slug_is_pty_related,
)
from repowiki.core.path_class import (
    is_agent_memory_path,
    name_is_notes_product,
    repo_is_notes_primary,
    topic_paths_are_agent_memory,
)

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
    (
        "tool-system",
        "Tool System",
        "工具层",
        ("tool", "tools"),
    ),
    (
        "terminal-ui",
        "Terminal UI",
        "Terminal UI",
        ("tui", "ratatui", "crossterm", "pager"),
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
    ("acp-protocol", "ACP & Protocol", "协议 / ACP", ("acp", "protocol", "jsonrpc")),
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

# Grok-study / xai-org/grok-build product markers. Other repos must not
# inherit these crate names or the start_turn entry myth.
_GROK_PRODUCT_NEEDLES = (
    "xai-grok-pager",
    "xai-grok-agent",
    "xai-grok-tools",
    "/npm/grok/",
    "/bin/grok",
)
_GROK_SYSTEM_IDS = frozenset(
    {
        "agent-loop",
        "agent-runtime",
        "terminal-ui",
        "tui-pager",
        "system-prompt",
        "subagent-scheduling",
        "acp-protocol",
        "context-assembly",
        "pty-control",
        "headless-modes",
    }
)

# README / docs concepts (DeepWiki handbook IA), not a grok slug list.
_DOC_CONCEPTS: tuple[tuple[str, str, str, tuple[str, ...], tuple[str, ...]], ...] = (
    (
        "capability-seam",
        "Capability Seam",
        "Capability Seam",
        (
            "capability seam",
            "service definition",
            "service provider",
            "ctx.llm",
            "ctx.fs",
        ),
        ("docs/architecture.md", "packages/core", "packages/fs", "packages/llm"),
    ),
    (
        "plugin-architecture",
        "Plugin architecture",
        "Plugin 架构",
        (
            "everything-is-a-plugin",
            "everything is a plugin",
            "plugin-based",
            "is a plugin",
        ),
        ("packages/boot", "packages/bundle", "packages/core", "plugin"),
    ),
    (
        "cordis",
        "Cordis",
        "Cordis",
        ("cordis",),
        ("vendor/cordis", "packages/boot", "packages/core", "app-boot"),
    ),
)

# First-class dir match only — a helper file named prompt.rs must not become
# "System Prompt 模板" on an unrelated repo.
_FIRST_CLASS_ONLY_IDS = frozenset(
    {
        "agent-runtime",
        "system-prompt",
        "subagent-scheduling",
        "acp-protocol",
        "terminal-ui",
        "pty-control",
        "headless-modes",
        "codebase-graph",
        "codegen",
    }
)

TOPIC_PATH_CAP = 14
GETTING_STARTED_ID = "getting-started"
ENTRY_ID = "entry-and-boot"
CORE_ARCHITECTURE_ID = "core-architecture"


def slugify_topic(text: str) -> str:
    s = _SLUG_RE.sub("-", (text or "").lower()).strip("-")
    return s or "topic"


def is_generic_web_slug(slug: str) -> bool:
    return (slug or "") in _GENERIC_WEB_SLUGS


def web_system_names(slug: str) -> tuple[str, ...] | None:
    """Path-segment tokens that make a generic-web slug first-class, or None."""
    item = _OPTIONAL_WEB_BY_ID.get(slug or "")
    return item[3] if item else None


def repo_has_grok_product(paths) -> bool:
    """True when this tree actually contains grok-build / pager crates."""
    for raw in paths or []:
        low = (raw or "").replace("\\", "/").lower()
        if any(tok in low for tok in _GROK_PRODUCT_NEEDLES):
            return True
        parts = [p for p in low.split("/") if p]
        if parts and parts[0] == "bin" and "grok" in parts[-1]:
            return True
    return False


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


def omit_unusable_topic_stub(
    page_id: str, content: str, *, title: str = ""
) -> bool:
    """Drop persisted fallback stubs (PTY glossary on a non-PTY topic)."""
    pid = page_id or ""
    if not pid.startswith("topics/"):
        return False
    slug = pid.split("/", 1)[-1]
    if topic_slug_is_pty_related(slug, title):
        return False
    return is_canned_handbook_stub_text(content or "")


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
    all_paths = [f.path for f in project.files]
    grok_product = repo_has_grok_product(all_paths)
    notes_primary = repo_is_notes_primary(all_paths)

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

    boot = _pick_entry_boot_files(
        entry_paths,
        all_paths,
        rank_index,
        claimed,
    )
    if boot:
        topics.append(
            TopicOutline(
                id=ENTRY_ID,
                title="入口与启动" if zh else "Entry and boot",
                section="deep-dive",
                purpose=_purpose_for(
                    "入口与启动" if zh else "Entry and boot",
                    zh,
                    topic_id=ENTRY_ID,
                    paths=all_paths,
                ),
                key_files=boot,
                key_symbols=_harvest_topic_symbols(boot, files_by_path),
                depth="deep",
            )
        )
        claimed.update(boot)

    for topic in _doc_derived_topics(
        project, files_by_path, rank_index, claimed, zh
    ):
        topics.append(topic)
        claimed.update(topic.key_files)
        if len([t for t in topics if t.section == "deep-dive"]) >= TOPIC_PATH_CAP:
            break

    for topic_id, title_en, title_zh, names in _SYSTEMS:
        if topic_id in _GROK_SYSTEM_IDS and not grok_product:
            # Keep special file matchers (loop.rs / ToolBridge) but do not
            # mint grok sidebar slugs from a loose "agent" / "prompt" token.
            if topic_id not in {"agent-loop", "tool-system", "context-assembly"}:
                continue
            matched = [
                f.path
                for f in project.files
                if _file_matches_system(f.path, topic_id, names)
                and (notes_primary or not is_agent_memory_path(f.path))
            ]
            if not matched:
                continue
        else:
            matched = [
                f.path
                for f in project.files
                if _file_matches_system(f.path, topic_id, names)
                and (notes_primary or not is_agent_memory_path(f.path))
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
                purpose=_purpose_for(
                    title_zh if zh else title_en,
                    zh,
                    topic_id=topic_id,
                    paths=all_paths,
                ),
                key_files=key,
                key_symbols=_harvest_topic_symbols(key, files_by_path),
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
                    key_symbols=_harvest_topic_symbols(key, files_by_path),
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
            if is_agent_memory_path(path) and not notes_primary:
                continue
            if is_weak_topic_evidence_path(path):
                continue
            leaf = _system_leaf(path)
            if not leaf or (leaf.startswith(".") and not notes_primary):
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
                    key_symbols=_harvest_topic_symbols(key, files_by_path),
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
    evidence = pick_topic_callpath_evidence(topic)
    cite = f"`{evidence}`" if evidence else ""
    if topic.purpose:
        items.append(f"{topic.purpose} {cite}".strip())
    for path in topic.key_files[:3]:
        if is_weak_callpath_evidence_path(path):
            continue
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
        section = item.section if item.section in {"getting-started", "deep-dive"} else "deep-dive"
        if section != "getting-started":
            files = [p for p in files if not is_weak_callpath_evidence_path(p)]
        if not files:
            continue
        if not _keep_system_topic(topic_id, files, known):
            continue
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
        if not _keep_system_topic(item.id, list(item.key_files), known):
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
    _rebind_entry_and_boot(by_id, known, base)
    _rebind_doc_concepts(by_id, known, base, files_by_path=None)
    _drop_notes_sidebar_topics(by_id, known, base)
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


def _drop_notes_sidebar_topics(
    by_id: dict[str, TopicOutline],
    known: set[str],
    base: list[TopicOutline],
) -> None:
    """Keep getting-started as how-to-run; drop notes-only sidebar peers."""
    if repo_is_notes_primary(known):
        return
    zh = _topics_look_zh(list(by_id.values()) + list(base))
    getting = by_id.get(GETTING_STARTED_ID)
    if getting:
        getting.id = GETTING_STARTED_ID
        getting.section = "getting-started"
        getting.title = "快速开始" if zh else "Quick start"
        getting.purpose = (
            "从 README / 上手步骤跑起来，再进架构。"
            if zh
            else "Get a working run from the README, then read architecture."
        )
        readme = next(
            (p for p in getting.key_files if p.replace("\\", "/").lower() in {"readme.md", "readme"}),
            "",
        )
        if not readme:
            readme = next(
                (
                    p
                    for p in known
                    if p.replace("\\", "/").lower() in {"readme.md", "readme"}
                ),
                "",
            )
        if readme:
            getting.key_files = [readme]
    drop: list[str] = []
    for tid, item in by_id.items():
        if item.section == "getting-started" or item.id == GETTING_STARTED_ID:
            continue
        if topic_paths_are_agent_memory(item.key_files) or name_is_notes_product(
            item.title or item.id
        ):
            drop.append(tid)
    for tid in drop:
        by_id.pop(tid, None)


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


def _doc_and_readme_text(project: ProjectContext) -> str:
    chunks: list[str] = []
    for f in project.files:
        path = (f.path or "").replace("\\", "/").lower()
        name = path.rsplit("/", 1)[-1]
        if name in {"readme.md", "readme"} or path.startswith("docs/"):
            chunks.append(f.content or f.preview or "")
    return "\n".join(chunks).lower()


def _harvest_topic_symbols(
    paths: list[str], files_by_path: dict[str, FileInfo], *, limit: int = 4
) -> list[str]:
    from repowiki.core.context_pack import harvest_symbols

    names: list[str] = []
    seen: set[str] = set()
    for path in paths or []:
        info = files_by_path.get(path.replace("\\", "/")) or files_by_path.get(path)
        if not info:
            continue
        text = info.content or info.preview or ""
        for sym in harvest_symbols(text, limit=limit):
            name = (getattr(sym, "name", "") or "").strip()
            if not name or name in seen or "/" in name:
                continue
            seen.add(name)
            names.append(name)
            if len(names) >= limit:
                return names
    return names


def _topic_file_blob(
    paths: list[str], files_by_path: dict[str, FileInfo] | None
) -> str:
    if not files_by_path:
        return ""
    parts: list[str] = []
    for path in paths or []:
        info = files_by_path.get(path.replace("\\", "/")) or files_by_path.get(path)
        if info:
            parts.append(info.content or info.preview or "")
    return "\n".join(parts)


def _doc_derived_topics(
    project: ProjectContext,
    files_by_path: dict[str, FileInfo],
    rank_index: dict[str, int],
    claimed: set[str],
    zh: bool,
) -> list[TopicOutline]:
    """Mint plugin / Cordis / Capability Seam pages from README/docs evidence."""
    hay = _doc_and_readme_text(project)
    if not hay:
        return []
    known = [f.path.replace("\\", "/") for f in project.files]
    out: list[TopicOutline] = []
    used_ids: set[str] = set()
    for topic_id, title_en, title_zh, needles, path_needles in _DOC_CONCEPTS:
        if not any(n in hay for n in needles):
            continue
        matched = [
            p
            for p in known
            if any(tok in p.replace("\\", "/").lower() for tok in path_needles)
            and not is_weak_topic_evidence_path(p)
        ]
        if not matched:
            matched = [
                p
                for p in known
                if any(tok in p.replace("\\", "/").lower() for tok in path_needles)
                and p.replace("\\", "/").lower().endswith("docs/architecture.md")
            ]
        if not matched:
            continue
        key = _pick_doc_concept_files(
            topic_id, matched, files_by_path, rank_index, claimed, limit=6
        )
        if not key:
            key = _pick_doc_concept_files(
                topic_id, matched, files_by_path, rank_index, set(), limit=6
            )
        if not key:
            continue
        title = title_zh if zh else title_en
        out.append(
            TopicOutline(
                id=topic_id,
                title=title,
                section="deep-dive",
                purpose=_purpose_for(title, zh, topic_id=topic_id),
                key_files=key,
                key_symbols=_harvest_topic_symbols(key, files_by_path),
                depth="deep" if topic_id == "capability-seam" else "standard",
            )
        )
        used_ids.add(topic_id)
    if CORE_ARCHITECTURE_ID not in used_ids and "capability-seam" not in used_ids:
        arch_docs = [
            p
            for p in known
            if p.replace("\\", "/").lower().endswith("docs/architecture.md")
            or p.replace("\\", "/").lower() == "docs/architecture.md"
        ]
        if arch_docs:
            title = "核心架构" if zh else "Core architecture"
            out.append(
                TopicOutline(
                    id=CORE_ARCHITECTURE_ID,
                    title=title,
                    section="deep-dive",
                    purpose=_purpose_for(title, zh, topic_id=CORE_ARCHITECTURE_ID),
                    key_files=arch_docs[:4],
                    key_symbols=_harvest_topic_symbols(arch_docs, files_by_path),
                    depth="deep",
                )
            )
    return out


def _doc_concept_file_score(
    topic_id: str,
    path: str,
    files_by_path: dict[str, FileInfo] | None,
) -> int:
    """Prefer definition / assembly source over README, tsdown, or yaml presets."""
    low = _norm_topic_path(path)
    score = 0
    if low.endswith("docs/architecture.md") or low == "docs/architecture.md":
        score += 80
    if topic_id == "capability-seam":
        if any(tok in low for tok in ("packages/core", "packages/fs", "packages/llm")):
            score += 40
        blob = _topic_file_blob([path], files_by_path).lower()
        if "service definition" in blob or "capability seam" in blob:
            score += 50
        if "provider" in blob and "consumer" in blob:
            score += 30
        if "definestore" in blob or "zustand" in blob or "tsdown" in low:
            score -= 80
    elif topic_id == "plugin-architecture":
        if any(tok in low for tok in ("packages/boot", "packages/bundle", "/plugin")):
            score += 50
        if low.endswith("plugin.ts") or low.endswith("plugin.js"):
            score += 20
        if low.rsplit("/", 1)[-1] in {"readme.md", "readme"}:
            score -= 80
    elif topic_id == "cordis":
        if "vendor/cordis" in low:
            score += 60
        if "packages/boot" in low or "app-boot" in low:
            score += 50
        if "plugin" in low or low.endswith(("context.ts", "context.js", "ctx.ts")):
            score += 30
        if "packages/core" in low:
            score += 20
        if low.endswith((".yml", ".yaml")):
            score -= 80
    if is_weak_topic_evidence_path(path) and "architecture.md" not in low:
        score -= 60
    return score


def _pick_doc_concept_files(
    topic_id: str,
    paths: list[str],
    files_by_path: dict[str, FileInfo] | None,
    rank_index: dict[str, int],
    claimed: set[str],
    *,
    limit: int,
) -> list[str]:
    unused = [p for p in paths if p not in claimed] or list(paths)
    unused.sort(
        key=lambda p: (
            -_doc_concept_file_score(topic_id, p, files_by_path),
            _production_rank(p),
            rank_index.get(p, 10_000),
        )
    )
    return unused[:limit]


def _rebind_doc_concepts(
    by_id: dict[str, TopicOutline],
    known: set[str],
    base: list[TopicOutline],
    files_by_path: dict[str, FileInfo] | None = None,
) -> None:
    """Keep seam / plugin / cordis on definition and assembly files."""
    known_list = sorted(p.replace("\\", "/") for p in known)
    rank_index = {p: i for i, p in enumerate(known_list)}
    for topic_id, _en, _zh, _needles, path_needles in _DOC_CONCEPTS:
        item = by_id.get(topic_id)
        if item is None and topic_id == "cordis":
            item = next((t for t in by_id.values() if topic_looks_like_cordis(t)), None)
        if item is None:
            continue
        pool = [
            p
            for p in known_list
            if any(tok in p.replace("\\", "/").lower() for tok in path_needles)
        ]
        if not pool:
            continue
        kept = [
            p
            for p in item.key_files
            if p in known
            and (
                not is_weak_topic_evidence_path(p)
                or p.replace("\\", "/").lower().endswith("docs/architecture.md")
            )
        ]
        if topic_id == "capability-seam" and not any(
            "architecture.md" in p.replace("\\", "/").lower()
            or "packages/core" in p.replace("\\", "/").lower()
            for p in kept
        ):
            kept = []
        if topic_id == "plugin-architecture" and not any(
            tok in p.replace("\\", "/").lower()
            for p in kept
            for tok in ("packages/boot", "packages/bundle", "/plugin", "packages/core")
        ):
            kept = []
        if topic_id == "cordis":
            kept = [
                p
                for p in kept
                if not p.replace("\\", "/").lower().endswith((".yml", ".yaml"))
                and not is_weak_callpath_evidence_path(p)
            ]
            if not any(_is_cordis_runtime_path(p) for p in kept):
                kept = []
        if not kept:
            kept = _pick_doc_concept_files(
                topic_id, pool, files_by_path, rank_index, set(), limit=6
            )
        else:
            extra = _pick_doc_concept_files(
                topic_id, pool, files_by_path, rank_index, set(kept), limit=6
            )
            for path in extra:
                if path not in kept:
                    kept.append(path)
                if len(kept) >= 6:
                    break
        item.key_files = kept[:6]


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
}
_AGENT_CRATE_RE = re.compile(
    r"(?:^|/)(?:(?:xai-)?grok-agent|crates/agent|packages/agent)(?:/|$)",
    re.I,
)
_BOOT_SKIP_NEEDLES = (
    "worktree",
    "fast-worktree",
    "code-graph",
    "code_graph",
    "codegraph",
    "codebase-graph",
    "protoc",
    "protobuf",
    "dotslash",
    "/proto/",
    "protoc-gen",
)
_BOOT_TOOLCHAIN_STEMS = {
    "protoc",
    "protobuf",
    "buf",
    "flatc",
    "thrift",
    "capnpc",
    "grpc_cpp_plugin",
    "grpc_python_plugin",
}
_BOOT_NAME = {
    "main.rs",
    "main.py",
    "main.go",
    "main.ts",
    "main.js",
    "app.rs",
    "boot.rs",
}


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


_LOOP_SKIP_NEEDLES = (
    "/docs/",
    "docs/",
    "postmortem",
    "/e2e/",
    "/fixtures/",
    "/fixture/",
    "/tests/",
    "/test/",
    "/__tests__/",
    "tsdown",
    "webscaffold",
    "session.jsonl",
    ".e2e.",
    ".yml",
    ".yaml",
)
_TEST_FILE_SUFFIXES = (
    ".e2e.ts",
    ".e2e.tsx",
    ".e2e.js",
    ".e2e.jsx",
    ".spec.ts",
    ".spec.tsx",
    ".spec.js",
    ".test.ts",
    ".test.tsx",
    ".test.js",
)
_SCAFFOLD_TEXT_RE = re.compile(
    r"webscaffold|\.e2e\.(?:ts|tsx|js|jsx)\b|/e2e/|session\.jsonl",
    re.I,
)


def is_stub_file_path(path: str) -> bool:
    """Node module stubs / ``*-stub.ts`` — not a runtime container."""
    low = _norm_topic_path(path)
    leaf = low.rsplit("/", 1)[-1]
    stem = leaf.rsplit(".", 1)[0]
    if stem.endswith(("-stub", "_stub")) or stem == "stub":
        return True
    if "stub" in stem and ("module" in stem or "node" in stem):
        return True
    return False


def is_weak_topic_evidence_path(path: str) -> bool:
    """Docs / postmortem / e2e / tests / tsdown / yaml / stubs are not runtime evidence.

    ``apps/web/tests/foo.e2e.ts`` is a test file even though it is not under
    ``/e2e/``. ``WebScaffold`` / ``session.jsonl`` are harnesses, not the loop.
    ``node-module-stub.ts`` is a Node module shim, not Cordis / a plugin host.
    """
    low = _norm_topic_path(path)
    if low.endswith("docs/architecture.md") or low == "docs/architecture.md":
        return False
    if any(n in low for n in _LOOP_SKIP_NEEDLES):
        return True
    leaf = low.rsplit("/", 1)[-1]
    if leaf.endswith((".md", ".yml", ".yaml", ".json", ".jsonl")):
        return True
    if leaf.endswith(_TEST_FILE_SUFFIXES):
        return True
    if leaf in {"agents.md", "claude.md", "readme.md", "readme"}:
        return True
    compact = leaf.replace("-", "").replace("_", "")
    if "webscaffold" in compact:
        return True
    if is_stub_file_path(path):
        return True
    return False


def is_weak_entrypoint_path(path: str) -> bool:
    """Stub / fixture / e2e / tsdown — never the process start chip."""
    return is_weak_topic_evidence_path(path)


def is_weak_callpath_evidence_path(path: str) -> bool:
    """Stub / fixture / e2e / tsdown — never「接住链路上的一段工作」evidence."""
    return is_weak_entrypoint_path(path)


def _is_cordis_runtime_path(path: str) -> bool:
    """True when the file is vendored Cordis or a real plugin / ctx host."""
    low = _norm_topic_path(path)
    if is_weak_callpath_evidence_path(path):
        return False
    if "vendor/cordis" in low:
        return True
    if "packages/boot" in low or "app-boot" in low:
        return True
    if "plugin" in low and low.endswith((".ts", ".js", ".mjs", ".cjs")):
        return True
    leaf = low.rsplit("/", 1)[-1]
    if leaf in {"context.ts", "context.js", "ctx.ts", "ctx.js"}:
        return True
    return False


def topic_looks_like_cordis(topic: TopicOutline | None) -> bool:
    if topic is None:
        return False
    tid = (getattr(topic, "id", "") or getattr(topic, "name", "") or "").lower()
    title = getattr(topic, "title", "") or ""
    blob = f"{tid} {title}".lower()
    return "cordis" in blob or "插件容器" in title


_CALLPATH_TOPIC_FIRST = (
    "capability-seam",
    "plugin-architecture",
    "cordis",
    CORE_ARCHITECTURE_ID,
)


def _callpath_topic_rank(topic: TopicOutline) -> tuple[int, str]:
    tid = topic.id or ""
    if tid in _CALLPATH_TOPIC_FIRST or topic_looks_like_cordis(topic):
        return (0, tid)
    if tid == ENTRY_ID:
        return (2, tid)
    return (1, tid)


def callpath_topics_for_overview(topics: list[TopicOutline]) -> list[TopicOutline]:
    """Topics that can own a「接住链路上」bullet. Entry is already the start line."""
    out: list[TopicOutline] = []
    for topic in topics or []:
        if topic.section == "getting-started" or topic.id == GETTING_STARTED_ID:
            continue
        if topic.id == ENTRY_ID:
            continue
        out.append(topic)
    out.sort(key=_callpath_topic_rank)
    return out


def pick_topic_callpath_evidence(
    topic: TopicOutline,
    known_paths: list[str] | None = None,
) -> str | None:
    """First non-stub key_file. Cordis prefers vendor/cordis / boot / plugin."""
    files = [
        p
        for p in (topic.key_files or [])
        if p and not is_weak_callpath_evidence_path(p)
    ]
    if topic_looks_like_cordis(topic):
        preferred = [p for p in files if _is_cordis_runtime_path(p)]
        if preferred:
            preferred.sort(key=lambda p: -_doc_concept_file_score("cordis", p, None))
            return preferred[0]
        extra = [
            p
            for p in (known_paths or [])
            if _is_cordis_runtime_path(p)
        ]
        if extra:
            extra.sort(key=lambda p: -_doc_concept_file_score("cordis", p, None))
            return extra[0]
        return None
    source = [
        p
        for p in files
        if not p.replace("\\", "/").lower().endswith((".md", ".yml", ".yaml"))
    ]
    return (source or files)[0] if (source or files) else None


def text_cites_scaffold_evidence(text: str) -> bool:
    """True when prose names an e2e harness (WebScaffold / ``*.e2e.ts``)."""
    return bool(_SCAFFOLD_TEXT_RE.search(text or ""))


def _looks_like_process_entry(path: str) -> bool:
    if is_weak_entrypoint_path(path) or is_toolchain_boot_file(path):
        return False
    low = _norm_topic_path(path)
    name = low.rsplit("/", 1)[-1]
    stem = name.rsplit(".", 1)[0]
    if name not in _BOOT_NAME and stem not in {"main", "bin", "cli", "index", "boot", "app"}:
        return False
    if not name.endswith((".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".py", ".rs", ".go")):
        return False
    if low.startswith("apps/") or "/apps/" in f"/{low}/":
        return True
    if low.startswith(("src/", "bin/", "cmd/")) or "/src/bin/" in f"/{low}/":
        return True
    return False


def pick_process_entrypoint(paths: list[str] | None) -> str | None:
    """Best ``apps/*/src/{bin,main}.ts``-style entry. Never stub / e2e / tsdown."""
    picked = process_entrypoint_paths(list(paths or []))
    return picked[0] if picked else None


def process_entrypoint_paths(
    paths: list[str] | None = None,
    *,
    flagged: list[str] | None = None,
    graph_entries: list[str] | None = None,
) -> list[str]:
    """Real process entries for the overview start line."""
    ordered: list[str] = []
    for pool in (flagged, graph_entries, paths):
        for raw in pool or []:
            path = (raw or "").replace("\\", "/")
            if path and path not in ordered:
                ordered.append(path)
    picked = [
        p
        for p in ordered
        if not is_weak_entrypoint_path(p)
        and (is_entry_boot_file(p) or _looks_like_process_entry(p))
    ]
    return _prefer_boot(picked)


def is_agent_loop_file(path: str) -> bool:
    """Runtime loop (run / turn / tool dispatch), never conversation_util or postmortem."""
    if is_context_assembly_file(path) or is_weak_topic_evidence_path(path):
        return False
    low = _norm_topic_path(path)
    if not low.endswith((".ts", ".tsx", ".js", ".mjs", ".cjs", ".rs", ".py", ".go")):
        return False
    if _path_has_system(path, ("loop", "turn")):
        return True
    if not _AGENT_CRATE_RE.search(low):
        return False
    stem = low.rsplit("/", 1)[-1].rsplit(".", 1)[0]
    if stem in _LOOP_FILE_STEMS or "dispatch" in stem or stem.endswith("_loop"):
        return True
    return False


def is_tool_system_file(path: str) -> bool:
    """ToolBridge / tools crate — not worktree CLIs."""
    if is_agent_memory_path(path):
        return False
    low = _norm_topic_path(path)
    if any(n in low for n in _BOOT_SKIP_NEEDLES):
        return False
    compact = low.replace("_", "").replace("-", "")
    if "toolbridge" in compact:
        return True
    return _path_has_system(path, ("tool", "tools"))


def is_toolchain_boot_file(path: str) -> bool:
    """protoc / protobuf / dotslash / codegen CLIs — not the product process."""
    low = _norm_topic_path(path)
    if any(n in low for n in _BOOT_SKIP_NEEDLES):
        return True
    name = low.rsplit("/", 1)[-1]
    stem = name.rsplit(".", 1)[0]
    if stem in _BOOT_TOOLCHAIN_STEMS or name in _BOOT_TOOLCHAIN_STEMS:
        return True
    if stem.startswith("protoc-gen") or "protoc" in stem:
        return True
    return False


def is_entry_boot_file(path: str) -> bool:
    """grok / pager binary boot, not toolchain scripts or aux CLIs."""
    if is_toolchain_boot_file(path) or is_weak_entrypoint_path(path):
        return False
    low = _norm_topic_path(path)
    parts = [p for p in low.split("/") if p]
    name = parts[-1] if parts else ""
    stem = name.rsplit(".", 1)[0]
    product = any(
        tok in low for tok in ("grok", "pager", "xai-grok", "/tui/", "crates/tui")
    )
    if parts and parts[0] in {"bin", "cmd"}:
        return product or "grok" in stem or "pager" in stem
    if product and (
        name in _BOOT_NAME
        or name in {"lib.rs", "mod.rs"}
        or stem in {"grok", "pager"}
        or "pager" in stem
        or stem.startswith("grok")
    ):
        return True
    if name in {"main.rs", "main.py", "main.go", "main.ts", "main.js"}:
        if product or "/agent/" in f"/{low}/":
            return True
        if low.startswith("src/main.") or low.startswith("src/bin/"):
            return True
        if low.startswith("apps/") or "/apps/" in f"/{low}/":
            return True
    if stem in {"cli", "index", "bin"} and name.endswith((".ts", ".js", ".mjs", ".cjs")):
        if low.startswith("apps/") or "/apps/" in f"/{low}/":
            return True
    return False


def _system_names(topic_id: str) -> tuple[str, ...]:
    for tid, _en, _zh, names in _SYSTEMS:
        if tid == topic_id:
            return names
    return ()


def _keep_system_topic(topic_id: str, files: list[str], known: set[str] | list[str]) -> bool:
    """Drop grok sidebar slugs unless this tree actually has that system."""
    if topic_id not in _GROK_SYSTEM_IDS:
        return True
    names = _system_names(topic_id)
    if repo_has_grok_product(known):
        return True
    if topic_id in {"agent-loop", "tool-system", "context-assembly"}:
        return any(_file_matches_system(p, topic_id, names) for p in files or [])
    return any(first_class_system_dir(p, names) for p in files or []) if names else False


def _file_matches_system(path: str, topic_id: str, names: tuple[str, ...]) -> bool:
    if topic_id == "agent-loop":
        return is_agent_loop_file(path)
    if topic_id == "context-assembly":
        return is_context_assembly_file(path)
    if topic_id == "tool-system":
        return is_tool_system_file(path)
    if topic_id in _FIRST_CLASS_ONLY_IDS:
        return first_class_system_dir(path, names)
    return _path_has_system(path, names)


def _production_rank(path: str) -> int:
    low = _norm_topic_path(path)
    leaf = low.rsplit("/", 1)[-1]
    if is_agent_memory_path(path):
        return 8
    if is_weak_topic_evidence_path(path):
        return 6
    if (
        "/tests/" in f"/{low}/"
        or "/test/" in f"/{low}/"
        or low.startswith("tests/")
        or leaf.endswith("_test.rs")
        or leaf.startswith("test_")
    ):
        return 1
    if low.endswith("docs/architecture.md") or low == "docs/architecture.md":
        return 0
    return 0


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
        kept = [
            p
            for p in loop.key_files
            if not is_context_assembly_file(p) and not is_weak_topic_evidence_path(p)
        ]
        moved_assembly = [p for p in loop.key_files if is_context_assembly_file(p)]
        if not any(is_agent_loop_file(p) for p in kept) and loop_pool:
            kept = loop_pool[:6]
        else:
            for path in loop_pool:
                if path not in kept:
                    kept.append(path)
                if len(kept) >= 8:
                    break
        loop.key_files = _prefer_production(kept)[:8]
        if not loop.key_files:
            by_id.pop("agent-loop", None)
        elif not loop.purpose or "上下文装配" in (loop.purpose or ""):
            loop.purpose = _purpose_for(loop.title, zh, topic_id="agent-loop")

    assembly = by_id.get("context-assembly")
    assembly_files = list((assembly.key_files if assembly else []) or [])
    assembly_files = [p for p in assembly_files if not is_agent_loop_file(p)]
    for path in moved_assembly + assembly_pool:
        if path not in assembly_files:
            assembly_files.append(path)
    if not assembly_files:
        for item in base:
            if item.id == "context-assembly":
                assembly_files = [
                    p for p in item.key_files if is_context_assembly_file(p)
                ]
                break
    assembly_files = _prefer_production(assembly_files)[:8]
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


def _rebind_entry_and_boot(
    by_id: dict[str, TopicOutline],
    known: set[str],
    base: list[TopicOutline],
) -> None:
    """Keep entry-and-boot on grok/pager, not toolchain/worktree/code-graph CLIs."""
    zh = _topics_look_zh(list(by_id.values()) + list(base))
    known_list = sorted(p.replace("\\", "/") for p in known)
    boot_pool = _prefer_boot([p for p in known_list if is_entry_boot_file(p)])
    purpose = _purpose_for(
        "入口与启动" if zh else "Entry and boot",
        zh,
        topic_id=ENTRY_ID,
        paths=known_list,
    )
    entry = by_id.get(ENTRY_ID)
    if not entry:
        if not boot_pool:
            return
        title = "入口与启动" if zh else "Entry and boot"
        by_id[ENTRY_ID] = TopicOutline(
            id=ENTRY_ID,
            title=title,
            section="deep-dive",
            purpose=purpose,
            key_files=boot_pool[:6],
            depth="deep",
        )
        return
    kept = [p for p in entry.key_files if is_entry_boot_file(p)]
    if not kept:
        kept = boot_pool[:6]
    else:
        for path in boot_pool:
            if path not in kept:
                kept.append(path)
            if len(kept) >= 8:
                break
    entry.key_files = _prefer_boot(kept)[:8]
    blob = f"{entry.purpose or ''} {entry.title or ''}".lower()
    if (
        not entry.purpose
        or any(n in blob for n in ("protoc", "dotslash", "protobuf", "toolchain"))
    ):
        entry.purpose = purpose


def _boot_rank(path: str) -> int:
    """Lower is better: grok/pager/main ahead of leftover bin scripts."""
    if is_toolchain_boot_file(path):
        return 100
    low = _norm_topic_path(path)
    leaf = low.rsplit("/", 1)[-1]
    score = 0
    if "grok" in low:
        score -= 10
    if "pager" in low:
        score -= 8
    if leaf.startswith("main.") or leaf in {"main.rs", "app.rs", "boot.rs", "bin.ts", "bin.js"}:
        score -= 5
    if low.startswith("apps/") or "/apps/" in f"/{low}/":
        score -= 4
    if "/cli/" in f"/{low}/":
        score -= 2
    if low.startswith("bin/") or "/bin/" in f"/{low}/":
        score -= 2
    score += _production_rank(path) * 20
    return score


def _prefer_boot(paths: list[str]) -> list[str]:
    return sorted(paths, key=lambda p: (_boot_rank(p), p))


def _prefer_production(paths: list[str]) -> list[str]:
    return sorted(paths, key=lambda p: (_production_rank(p), p))


def _pick_entry_boot_files(
    entry_paths: list[str],
    all_paths: list[str],
    rank_index: dict[str, int],
    claimed: set[str],
) -> list[str]:
    candidates = [p for p in entry_paths if is_entry_boot_file(p)]
    if not candidates:
        candidates = [p for p in all_paths if is_entry_boot_file(p)]
    if not candidates:
        candidates = [
            p
            for p in entry_paths
            if not is_toolchain_boot_file(p)
            and not any(n in p.replace("\\", "/").lower() for n in _BOOT_SKIP_NEEDLES)
        ]
    candidates = _prefer_boot(candidates)
    key = _pick_keys(candidates, rank_index, claimed, limit=6)
    if not key:
        key = _pick_keys(candidates, rank_index, set(), limit=6)
    return _prefer_boot(key)


def _pick_keys(
    paths: list[str],
    rank_index: dict[str, int],
    claimed: set[str],
    *,
    limit: int,
) -> list[str]:
    unused = [p for p in paths if p not in claimed]
    unused.sort(key=lambda p: (_production_rank(p), rank_index.get(p, 10_000)))
    return unused[:limit]


def _system_leaf(path: str) -> str:
    if is_agent_memory_path(path):
        return ""
    parts = [p for p in path.replace("\\", "/").split("/") if p and p not in _SKIP_DIRS]
    if not parts:
        return ""
    if parts[0].startswith("."):
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
    named = {
        "core": ("Core", "核心"),
        "fs": ("fs", "fs"),
        "llm": ("LLM", "LLM"),
        "cordis": ("Cordis", "Cordis"),
        "plugin": ("Plugin", "Plugin"),
        "dsh": ("dsh CLI", "dsh CLI"),
    }
    if low in named:
        en, zh_title = named[low]
        return zh_title if zh else en
    # Keep crate identifiers readable; do not prefix 模块.
    return cleaned


def _purpose_for(
    title: str, zh: bool, topic_id: str = "", *, paths: list[str] | None = None
) -> str:
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
    if topic_id == ENTRY_ID:
        if repo_has_grok_product(paths):
            if zh:
                return "用户怎么把 grok 跑起来：二进制、pager、ACP server start。"
            return "How the user starts grok: binary, pager, ACP server start."
        if zh:
            return "用户怎么把进程跑起来：CLI / 二进制入口、装配、再进主循环。"
        return "How the user starts the process: CLI or binary, wiring, then the main loop."
    if topic_id == "capability-seam":
        if zh:
            return (
                "Capability Seam：Service Definition / Provider / Consumer 怎么把 "
                "`ctx.llm` / `ctx.fs` 这类能力接上，以及换 Provider 时谁跟着变。"
            )
        return (
            "Capability Seam: how Service Definition / Provider / Consumer wire "
            "`ctx.llm` / `ctx.fs`, and what changes when a provider is swapped."
        )
    if topic_id == "plugin-architecture":
        if zh:
            return "everything-is-a-plugin：组件如何被声明、装上、以及被配置替换。"
        return "everything-is-a-plugin: how a component is declared, loaded, and swapped."
    if topic_id == "cordis":
        if zh:
            return "vendored Cordis 如何装 plugin、暴露 ctx，以及和核心包怎么接。"
        return "How vendored Cordis loads plugins, exposes ctx, and joins the core package."
    if topic_id == CORE_ARCHITECTURE_ID:
        if zh:
            return "文档里的核心架构：一次调用经过哪些包，seam 落在哪。"
        return "Core architecture from the docs: which packages a call crosses, and where the seam sits."
    if zh:
        return f"{title} 在调用链上接住哪一段，以及和上下游怎么接。"
    return f"What `{title}` owns on the call path, and how it joins upstream and downstream."


_PACK_PURPOSE_HINTS: dict[str, tuple[str, str]] = {
    "cli": (
        "Parse argv and start the runner by profile.",
        "解析 argv 并按 profile 启动 runner。",
    ),
    "dsh": (
        "CLI entry that boots the harness by profile.",
        "CLI 入口，按 profile 启动 harness。",
    ),
    "web": (
        "Host the desktop/Web client UI.",
        "承载桌面/Web 客户端界面。",
    ),
    "docs": (
        "Architecture and usage notes.",
        "架构与使用说明。",
    ),
    "acp": (
        "ACP protocol adapter.",
        "ACP 协议适配。",
    ),
    "api": (
        "HTTP/RPC API surface.",
        "HTTP/RPC API 面。",
    ),
    "attachment": (
        "File and attachment delivery.",
        "附件与文件投递。",
    ),
    "boot": (
        "Stack bundle patches into the Cordis root.",
        "把 bundle patch 叠成 Cordis 根。",
    ),
    "bundle": (
        "Assemble and emit bundle patches.",
        "组装并下发 bundle patch。",
    ),
    "client": (
        "Client SDK talking to the host.",
        "客户端 SDK，和宿主通信。",
    ),
    "core": (
        "Product API spine and runtime types.",
        "产品 API 与运行时类型。",
    ),
    "fs": (
        "Local filesystem capability.",
        "本地文件系统能力。",
    ),
    "llm": (
        "Model-call capability.",
        "模型调用能力。",
    ),
}

_BOILERPLATE_PACK_PURPOSE_RE = re.compile(
    r"这一包在仓库里的职责边界|Responsibility boundary of",
    re.I,
)


def is_boilerplate_pack_purpose(text: str) -> bool:
    """True when the split-table purpose is the canned template, not a handbook line."""
    return bool(_BOILERPLATE_PACK_PURPOSE_RE.search(text or ""))


def purpose_for_pack(
    name: str,
    loc: str,
    project: ProjectContext | None,
    *,
    language: str = "zh",
) -> str:
    """One handbook sentence: package.json / README / entry comment / name hint."""
    zh = _is_zh(language)
    leaf = (name or loc.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1] or "").lower()
    hint = _PACK_PURPOSE_HINTS.get(leaf)
    extracted = _extract_pack_purpose(loc, project)
    if extracted and not is_boilerplate_pack_purpose(extracted):
        if zh and hint and re.fullmatch(r"[A-Za-z0-9 ,.'`/:+_-]+", extracted):
            return hint[1]
        return extracted.rstrip("。. ") + ("。" if zh else ".")
    if hint:
        return hint[1] if zh else hint[0]
    if loc.startswith("apps/"):
        return (
            f"应用入口 `{loc}`：解析启动参数并拉起进程。"
            if zh
            else f"App entry `{loc}`: parse launch args and start the process."
        )
    if loc.startswith("packages/") or loc.startswith("crates/"):
        return (
            f"`{loc}` 在一次调用里接住自己的那一段，再交给上下游。"
            if zh
            else f"`{loc}` owns one stretch of a call and hands off upstream/downstream."
        )
    return (
        f"`{loc}` 在仓库里实际干什么，以入口和 README 为准。"
        if zh
        else f"What `{loc}` actually does, from its entry and README."
    )


def _extract_pack_purpose(loc: str, project: ProjectContext | None) -> str:
    if not project or not loc:
        return ""
    prefix = loc.replace("\\", "/").rstrip("/") + "/"
    files_by_path = {f.path.replace("\\", "/"): f for f in project.files}
    pkg = files_by_path.get(f"{loc}/package.json")
    if pkg:
        desc = _package_json_description(pkg.content or pkg.preview or "")
        if desc:
            return desc
    for readme_name in ("README.md", "readme.md", "README"):
        readme = files_by_path.get(f"{loc}/{readme_name}")
        if readme:
            sentence = _first_handbook_sentence(readme.content or readme.preview or "")
            if sentence:
                return sentence
    entries: list[FileInfo] = []
    for path, info in files_by_path.items():
        if not path.startswith(prefix):
            continue
        leaf = path.rsplit("/", 1)[-1]
        if leaf in {"index.ts", "index.js", "bin.ts", "main.ts", "app-boot.ts"} or getattr(
            info, "is_entrypoint", False
        ):
            entries.append(info)
    for info in entries:
        sentence = _first_file_comment(info.content or info.preview or "")
        if sentence:
            return sentence
    return ""


def _package_json_description(raw: str) -> str:
    text = (raw or "").strip()
    if not text:
        return ""
    try:
        import json

        data = json.loads(text)
    except (TypeError, ValueError):
        match = re.search(r'"description"\s*:\s*"((?:[^"\\]|\\.)*)"', text)
        return (match.group(1).encode("utf-8").decode("unicode_escape") if match else "").strip()
    if isinstance(data, dict):
        return str(data.get("description") or "").strip()
    return ""


def _first_handbook_sentence(raw: str) -> str:
    lines: list[str] = []
    for line in (raw or "").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or s.startswith("```") or s.startswith("["):
            continue
        if s.startswith(">") :
            s = s.lstrip("> ").strip()
        if s:
            lines.append(s)
        if len(lines) >= 3:
            break
    blob = " ".join(lines).strip()
    if not blob or is_boilerplate_pack_purpose(blob):
        return ""
    match = re.split(r"(?<=[。.!])\s+", blob, maxsplit=1)
    sentence = (match[0] if match else blob).strip()
    return sentence[:160]


def _first_file_comment(raw: str) -> str:
    text = (raw or "").lstrip()
    if text.startswith("/**") or text.startswith("/*"):
        body = re.sub(r"^/\*+|\*+/$", "", text.split("*/", 1)[0], flags=re.S)
        body = re.sub(r"^\s*\*\s?", "", body, flags=re.M).strip()
        return _first_handbook_sentence(body)
    if text.startswith("//"):
        lines: list[str] = []
        for line in text.splitlines():
            if not line.strip().startswith("//"):
                break
            lines.append(line.strip().lstrip("/").strip())
        return _first_handbook_sentence("\n".join(lines))
    return ""


def fill_codebase_purposes(
    rows: list[CodebasePart],
    project: ProjectContext | None,
    *,
    language: str = "zh",
) -> list[CodebasePart]:
    """Replace empty / canned split-table purposes with handbook lines."""
    for row in rows or []:
        if not (row.purpose or "").strip() or is_boilerplate_pack_purpose(row.purpose):
            row.purpose = purpose_for_pack(
                row.name, row.location, project, language=language
            )
    return rows


def codebase_structure_for(
    project: ProjectContext, *, language: str = "zh", limit: int = 12
) -> list[CodebasePart]:
    """Crate / top-package rows for 代码如何拆分. Not a file dump."""
    from repowiki.core.grounding import is_doc_pack_row

    clusters: dict[str, str] = {}
    for f in project.files:
        parts = [p for p in f.path.replace("\\", "/").split("/") if p]
        if not parts or parts[0] in _SKIP_DIRS:
            continue
        if is_agent_memory_path(f.path) or parts[0].startswith("."):
            continue
        if parts[0] in {"crates", "packages", "apps"} and len(parts) > 1:
            name, loc = parts[1], f"{parts[0]}/{parts[1]}"
        elif len(parts) == 1:
            continue
        else:
            name, loc = parts[0], parts[0]
        if is_doc_pack_row(name, loc):
            continue
        clusters.setdefault(name, loc)
    rows: list[CodebasePart] = []
    for name, loc in list(clusters.items())[:limit]:
        rows.append(
            CodebasePart(
                name=name,
                location=loc,
                purpose=purpose_for_pack(name, loc, project, language=language),
            )
        )
    return rows


def subsystems_from_topics(topics: list[TopicOutline], *, limit: int = 8) -> list[Subsystem]:
    out: list[Subsystem] = []
    for topic in topics:
        if topic.section == "getting-started" or topic.id == GETTING_STARTED_ID:
            continue
        if topic_paths_are_agent_memory(topic.key_files) or name_is_notes_product(
            topic.title or topic.id
        ):
            continue
        evidence = pick_topic_callpath_evidence(topic)
        types = [
            KeyType(
                name=symbol,
                role="",
                path=evidence or "",
            )
            for symbol in (topic.key_symbols or [])[:4]
            if symbol and "/" not in symbol and not str(symbol).endswith(".rs")
        ]
        if not types:
            types = _fallback_key_types_for_topic(topic, files_by_path=None)
        types = [
            kt
            for kt in types
            if (kt.path or "").strip() and not is_weak_callpath_evidence_path(kt.path)
        ]
        title = topic.title or topic.id
        if "上下文装配" in title and "Agent Loop" in title:
            title = "Agent Loop"
        type_names = [kt.name for kt in types if (kt.name or "").strip()]
        mermaid = ""
        if len(type_names) >= 2:
            from repowiki.core.wiki_builder import flowchart_lr_from_types

            mermaid = flowchart_lr_from_types(type_names)
        out.append(
            Subsystem(
                name=title,
                role=topic.purpose,
                key_types=types,
                files=[
                    p
                    for p in topic.key_files[:6]
                    if not is_weak_callpath_evidence_path(p)
                ][:4],
                mermaid=mermaid,
            )
        )
        if len(out) >= limit:
            break
    return out


def _fallback_key_types_for_topic(
    topic: TopicOutline, files_by_path: dict[str, FileInfo] | None = None
) -> list[KeyType]:
    files = [
        p
        for p in (topic.key_files or [])
        if p and not is_weak_callpath_evidence_path(p)
    ]
    if topic_looks_like_cordis(topic):
        preferred = [p for p in files if _is_cordis_runtime_path(p)]
        files = preferred or files
    if not files:
        return []
    harvested = list(topic.key_symbols or [])
    if not harvested and files_by_path:
        harvested = _harvest_topic_symbols(files, files_by_path)
    blob = _topic_file_blob(files, files_by_path)
    hints: list[tuple[str, str]] = []
    tid = topic.id or ""
    if tid == "agent-loop" and "start_turn" in blob:
        hints = [
            ("start_turn", "pager dispatch / start_turn"),
            ("TurnRunning", "本轮运行中"),
        ]
    elif tid == "capability-seam" and (
        not blob
        or "definition" in blob.lower()
        or "provider" in blob.lower()
        or "capability seam" in blob.lower()
    ):
        hints = [
            ("Service Definition", "swappable capability contract"),
            ("Provider", "implements a definition"),
            ("Consumer", "uses ctx.llm / ctx.fs"),
        ]
    elif tid in {"terminal-ui", "tui-pager"} and re.search(r"\bPager\b", blob):
        hints = [("Pager", "TUI pager")]
    elif tid == "tool-system" and "ToolBridge" in blob:
        hints = [("ToolBridge", "执行模型 tool calls")]
    elif tid == ENTRY_ID:
        hints = [("main", "进程入口")]
    out: list[KeyType] = []
    seen: set[str] = set()
    prefer_hints_first = tid == "capability-seam" and hints
    harvest_iter = [] if prefer_hints_first else harvested
    hint_iter = hints + ([(n, "") for n in harvested] if prefer_hints_first else [])
    for i, name in enumerate(harvest_iter):
        if not name or name in seen or "/" in name:
            continue
        seen.add(name)
        path = files[min(i, len(files) - 1)]
        out.append(KeyType(name=name, role="", path=path, line=1))
        if len(out) >= 4:
            return out
    for i, (name, role) in enumerate(hint_iter if prefer_hints_first else hints):
        if name in seen or (
            blob and name not in blob and name != "main" and tid != "capability-seam"
        ):
            continue
        seen.add(name)
        path = files[min(i, len(files) - 1)]
        out.append(KeyType(name=name, role=role, path=path, line=1))
    if not out:
        leaf = files[0].replace("\\", "/").rsplit("/", 1)[-1]
        stem = leaf.rsplit(".", 1)[0]
        if stem not in {"lib", "mod", "main", "index"}:
            out.append(KeyType(name=stem, role="", path=files[0], line=1))
    return out[:4]


GROK_LOOP_SEQUENCE = (
    "sequenceDiagram\n"
    "  participant Pager\n"
    "  participant Turn as start_turn\n"
    "  participant Model\n"
    "  participant Bridge as ToolBridge\n"
    "  Pager->>Turn: dispatch\n"
    "  Turn->>Turn: TurnRunning\n"
    "  Turn->>Model: complete\n"
    "  Model-->>Turn: tool calls\n"
    "  Turn->>Bridge: execute\n"
    "  Bridge-->>Turn: write-back\n"
    "  Turn->>Turn: on_turn_done"
)


def sequence_tools_before_model(text: str) -> bool:
    """True when a sequence diagram runs tools before the model call."""
    if "sequencediagram" not in (text or "").lower().replace(" ", ""):
        return False
    tool_at: tuple[int, int] | None = None
    model_at: tuple[int, int] | None = None
    for i, line in enumerate((text or "").splitlines()):
        low = line.lower()
        if "->>" not in low and "-->>" not in low:
            continue
        tool_m = re.search(r"toolbridge|\btools?\b", low)
        model_m = re.search(r"\bmodel\b|\bcomplete\b|\bllm\b", low)
        if tool_m and tool_at is None:
            tool_at = (i, tool_m.start())
        if model_m and model_at is None:
            model_at = (i, model_m.start())
    if tool_at is None or model_at is None:
        return False
    return tool_at < model_at


def getting_started_call_path(
    project: ProjectContext,
    *,
    language: str = "zh",
) -> str:
    """How the user starts the process — not overview product copy."""
    zh = _is_zh(language)
    paths = [(f.path or "").replace("\\", "/") for f in project.files]
    flagged = [f.path for f in project.files if getattr(f, "is_entrypoint", False)]
    entries = process_entrypoint_paths(paths, flagged=flagged)
    args = [
        p
        for p in paths
        if p.rsplit("/", 1)[-1] in {"args.ts", "args.js", "args.py"}
        and not is_weak_callpath_evidence_path(p)
    ]
    readme = next((p for p in paths if p.lower() in {"readme.md", "readme"}), "")
    readme_text = ""
    if readme:
        info = next((f for f in project.files if (f.path or "").replace("\\", "/") == readme), None)
        readme_text = (info.content or info.preview or "") if info else ""
    has_pnpm = bool(
        re.search(r"\bpnpm\b", readme_text)
        or any(p.lower() in {"pnpm-workspace.yaml", "pnpm-lock.yaml"} for p in paths)
    )
    has_dsh_web = bool(re.search(r"\bdsh\s+web\b", readme_text))
    bits: list[str] = []
    if zh:
        if has_pnpm:
            bits.append("按 README 用 pnpm 在仓库根安装")
        else:
            bits.append("按 README 写的包管理器在仓库根安装")
        if has_dsh_web:
            bits.append("再用 `dsh web` 或 CLI 入口把进程拉起来")
        elif entries:
            bits.append(f"再从 `{entries[0]}` 把进程拉起来")
        else:
            bits.append("再按 README 的启动命令把进程拉起来")
        if args:
            bits.append(f"启动参数在 `{args[0]}`")
        elif entries and len(entries) > 1:
            bits.append(f"另一条入口是 `{entries[1]}`")
        text = "，".join(bits) + "。"
        if readme:
            text += f" 细节以 `{readme}` 为准。"
        return text
    if has_pnpm:
        bits.append("Install at the repo root with pnpm as the README says")
    else:
        bits.append("Install at the repo root with the package manager the README names")
    if has_dsh_web:
        bits.append("then start with `dsh web` or the CLI entry")
    elif entries:
        bits.append(f"then start from `{entries[0]}`")
    else:
        bits.append("then follow the README start command")
    if args:
        bits.append(f"launch flags live in `{args[0]}`")
    text = ", ".join(bits) + "."
    if readme:
        text += f" Cite `{readme}`."
    return text


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
    seen: set[str] = set()
    for path in entry_files or []:
        leaf = path.replace("\\", "/").rstrip("/").split("/")[-1]
        if leaf and leaf not in seen:
            nodes.append(leaf[:32])
            seen.add(leaf)
            break
    for topic in topics or []:
        section = getattr(topic, "section", "") or ""
        tid = getattr(topic, "id", "") or getattr(topic, "name", "")
        if section == "getting-started" or tid == GETTING_STARTED_ID:
            continue
        title = getattr(topic, "title", "") or tid
        label = re.sub(r'[\[\]{}"#\n]', " ", str(title))
        label = re.sub(r"\s+", " ", label).strip()[:32]
        if not label or label in seen:
            continue
        nodes.append(label)
        seen.add(label)
        if len(nodes) >= limit + 1:
            break
    if len(nodes) < 2:
        return ""
    lines = ["flowchart TD"]
    ids = [f"n{i}" for i in range(len(nodes))]
    for nid, lab in zip(ids, nodes, strict=True):
        lines.append(f'  {nid}["{lab}"]')
    for src, dst in zip(ids, ids[1:], strict=False):
        if src != dst:
            lines.append(f"  {src} --> {dst}")
    return "\n".join(lines)
