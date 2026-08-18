"""Pass 1: structured wiki outline from graph signals, optionally LLM-enriched."""

from __future__ import annotations

from math import ceil

from repowiki.core.graph import DependencyGraph
from repowiki.core.models import (
    FileInfo,
    ModuleOutline,
    ProjectContext,
    WikiOutline,
)
from repowiki.core.path_class import (
    is_agent_memory_path,
    is_product_path,
    prose_treats_notes_as_product,
    repo_is_notes_primary,
)

# How many modules get the DeepWiki-style write prompt. A third of a 24-page
# wiki is eight longform pages; the rest stay standard/brief so token cost
# stays bounded.
_DEEP_FRACTION = 0.35
_MIN_DEEP = 1
_MAX_DEEP = 8

_DEEP_SECTIONS = [
    "purpose",
    "description",
    "implementation",
    "call_chains",
    "edge_cases",
    "files",
    "relationships",
]
_STANDARD_SECTIONS = ["purpose", "description", "files", "relationships"]
_BRIEF_SECTIONS = ["purpose", "files"]


def build_deterministic_outline(
    project: ProjectContext,
    modules: dict[str, list[FileInfo]],
    graph: DependencyGraph,
    *,
    language: str = "en",
) -> WikiOutline:
    """Plan pages from PageRank, entrypoints and config files. No LLM."""
    weights = graph.module_weights()
    ranked_files = graph.rank_files()
    rank_index = {path: i for i, (path, _) in enumerate(ranked_files)}

    names = sorted(modules, key=lambda n: _module_hub_key(n, modules, weights))
    n_deep = 0
    if names:
        n_deep = max(_MIN_DEEP, min(_MAX_DEEP, ceil(len(names) * _DEEP_FRACTION)))
        n_deep = min(n_deep, len(names))

    from repowiki.core.topics import process_entrypoint_paths

    flagged = [f.path for f in project.files if f.is_entrypoint]
    graph_entries = graph.get_entry_points()[:8]
    entry_paths = flagged or graph_entries
    start_paths = process_entrypoint_paths(
        [f.path for f in project.files],
        flagged=flagged,
        graph_entries=graph_entries,
    )
    entry_set = set(entry_paths)

    entry_modules: list[str] = []
    seen_entry_mod: set[str] = set()
    for path in entry_paths:
        mod = graph.module_of(path)
        if mod and mod in modules and mod not in seen_entry_mod:
            entry_modules.append(mod)
            seen_entry_mod.add(mod)

    reading_order: list[str] = list(entry_modules)
    for name in names:
        if name not in reading_order:
            reading_order.append(name)

    outlines: list[ModuleOutline] = []
    for i, name in enumerate(names):
        if i < n_deep:
            depth = "deep"
            priority = 3
            sections = list(_DEEP_SECTIONS)
        elif i < n_deep * 2 or n_deep == 0:
            depth = "standard"
            priority = 2
            sections = list(_STANDARD_SECTIONS)
        else:
            depth = "brief"
            priority = 1
            sections = list(_BRIEF_SECTIONS)

        files = modules[name]
        key_files = _key_files_for_module(files, entry_set, rank_index)
        outlines.append(
            ModuleOutline(
                name=name,
                priority=priority,
                depth=depth,
                sections=sections,
                key_files=key_files,
                key_symbols=[],
                notes=_module_notes(name, files, entry_set),
            )
        )

    top_mods = [
        n
        for n in names
        if not (
            modules.get(n)
            and all(is_agent_memory_path(f.path) for f in modules[n])
        )
    ][:6]
    if not top_mods:
        top_mods = names[: min(6, len(names))]
    zh = (language or "en").strip().lower().startswith(("zh", "cn"))
    hubs = ", ".join(f"`{n}`" for n in top_mods[:6]) if top_mods else ""
    entries = ", ".join(f"`{p}`" for p in (start_paths or entry_paths)[:6]) if (start_paths or entry_paths) else ""
    if zh:
        overview_bits = [
            f"{project.name} 的目标、一次真实调用经过谁、仓库怎么拆。"
        ]
        if entries:
            overview_bits.append(f"进程从 {entries} 进来，一次调用从这里进图。")
        if hubs:
            overview_bits.append(f"先看这些枢纽包：{hubs}。")
        arch_bits = [
            "仓库按一次调用真正经过的系统切页，而不是按目录罗列。"
        ]
        if entry_modules:
            arch_bits.append(
                "从 "
                + ", ".join(f"`{n}`" for n in entry_modules)
                + " 进链路。"
            )
        if hubs:
            arch_bits.append(f"核心包：{hubs}。")
    else:
        overview_bits = [
            f"{project.name}: the goal, who a real call passes through, and how the repo is split."
        ]
        if entries:
            overview_bits.append(
                "The process starts at "
                + entries
                + "; one call enters the graph here."
            )
        if hubs:
            overview_bits.append("Hub packages: " + hubs + ".")
        arch_bits = [
            "Split pages by the systems a real call crosses, not a file inventory."
        ]
        if entry_modules:
            arch_bits.append("Start from: " + ", ".join(f"`{n}`" for n in entry_modules) + ".")
        if hubs:
            arch_bits.append("Core packages: " + hubs + ".")

    emphasized = ["overview", "architecture"]
    emphasized.extend(names[:n_deep])

    from repowiki.core.topics import build_deterministic_topics

    topics = build_deterministic_topics(project, graph, language=language)

    return WikiOutline(
        overview_focus=" ".join(overview_bits),
        architecture_focus=" ".join(arch_bits),
        emphasized_pages=emphasized,
        reading_order=reading_order,
        modules=outlines,
        topics=topics,
    )


def merge_outline(
    base: WikiOutline,
    llm: WikiOutline,
    known_modules: set[str],
    known_paths: set[str],
) -> WikiOutline:
    """Overlay an LLM outline onto the deterministic plan.

    Unknown module names are dropped; missing modules keep the deterministic
    entry so every page still has a writing plan.
    """
    by_name = {item.name: item for item in base.modules}
    for item in llm.modules:
        if item.name not in known_modules:
            continue
        cleaned_files = [p for p in item.key_files if p in known_paths]
        depth = item.depth if item.depth in {"deep", "standard", "brief"} else "standard"
        priority = item.priority if item.priority else by_name[item.name].priority
        by_name[item.name] = ModuleOutline(
            name=item.name,
            priority=priority,
            depth=depth,
            sections=item.sections or by_name[item.name].sections,
            key_files=cleaned_files or by_name[item.name].key_files,
            key_symbols=item.key_symbols,
            notes=item.notes or by_name[item.name].notes,
        )

    reading = [n for n in llm.reading_order if n in known_modules]
    if not reading:
        reading = list(base.reading_order)
    for name in base.reading_order:
        if name not in reading:
            reading.append(name)

    emphasized = [p for p in llm.emphasized_pages if p in known_modules or p in {"overview", "architecture", "reading-guide"}]
    if not emphasized:
        emphasized = list(base.emphasized_pages)

    from repowiki.core.topics import merge_topics

    topics = merge_topics(list(base.topics), list(llm.topics or []), known_paths)

    overview_focus = llm.overview_focus or base.overview_focus
    architecture_focus = llm.architecture_focus or base.architecture_focus
    if not repo_is_notes_primary(known_paths):
        if prose_treats_notes_as_product(overview_focus):
            overview_focus = base.overview_focus
        if prose_treats_notes_as_product(architecture_focus):
            architecture_focus = base.architecture_focus

    return WikiOutline(
        overview_focus=overview_focus,
        architecture_focus=architecture_focus,
        emphasized_pages=emphasized,
        reading_order=reading,
        modules=[by_name[n] for n in by_name],
        topics=topics,
    )


def _module_hub_key(
    name: str,
    modules: dict[str, list[FileInfo]],
    weights: dict[str, float],
) -> tuple:
    """Product packages first; notes-only trees sort last even if numerous."""
    files = modules.get(name) or []
    notes_only = bool(files) and all(is_agent_memory_path(f.path) for f in files)
    has_entry = any(getattr(f, "is_entrypoint", False) for f in files)
    has_product = has_entry or any(is_product_path(f.path) for f in files)
    readme_only = bool(files) and all(
        (f.path or "").replace("\\", "/").lower() in {"readme.md", "readme"}
        or getattr(f, "is_config", False)
        for f in files
    )
    return (
        1 if notes_only else 0,
        0 if (has_product and not readme_only) or has_entry else 1,
        -weights.get(name, 0.0),
        name,
    )


def _key_files_for_module(
    files: list[FileInfo],
    entry_set: set[str],
    rank_index: dict[str, int],
    limit: int = 8,
) -> list[str]:
    scored: list[tuple[int, int, int, str]] = []
    for f in files:
        entry = 0 if (f.is_entrypoint or f.path in entry_set) else 1
        config = 0 if f.is_config else 1
        rank = rank_index.get(f.path, 10_000)
        scored.append((entry, config, rank, f.path))
    scored.sort()
    return [path for _, _, _, path in scored[:limit]]


def _module_notes(name: str, files: list[FileInfo], entry_set: set[str]) -> str:
    n = len(files)
    entries = [f.path for f in files if f.is_entrypoint or f.path in entry_set]
    if entries:
        return f"{n} files; entrypoints {', '.join(entries[:3])}."
    return f"{n} files."
