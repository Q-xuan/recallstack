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
) -> WikiOutline:
    """Plan pages from PageRank, entrypoints and config files. No LLM."""
    weights = graph.module_weights()
    ranked_files = graph.rank_files()
    rank_index = {path: i for i, (path, _) in enumerate(ranked_files)}

    names = sorted(modules, key=lambda n: (-weights.get(n, 0.0), n))
    n_deep = 0
    if names:
        n_deep = max(_MIN_DEEP, min(_MAX_DEEP, ceil(len(names) * _DEEP_FRACTION)))
        n_deep = min(n_deep, len(names))

    entry_paths = [f.path for f in project.files if f.is_entrypoint]
    if not entry_paths:
        entry_paths = graph.get_entry_points()[:8]
    entry_set = set(entry_paths)
    config_paths = [f.path for f in project.files if f.is_config]

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

    top_mods = names[: min(6, len(names))]
    overview_bits = [f"Project {project.name} ({len(project.files)} files)."]
    if entry_paths:
        overview_bits.append("Entrypoints: " + ", ".join(entry_paths[:6]) + ".")
    if config_paths:
        overview_bits.append("Config: " + ", ".join(config_paths[:6]) + ".")
    if top_mods:
        overview_bits.append("Core modules: " + ", ".join(top_mods) + ".")

    arch_bits = []
    if top_mods:
        arch_bits.append("Heaviest modules by PageRank: " + ", ".join(top_mods) + ".")
    if entry_modules:
        arch_bits.append("Start from: " + ", ".join(entry_modules) + ".")

    emphasized = ["overview", "architecture"]
    emphasized.extend(names[:n_deep])

    return WikiOutline(
        overview_focus=" ".join(overview_bits),
        architecture_focus=" ".join(arch_bits),
        emphasized_pages=emphasized,
        reading_order=reading_order,
        modules=outlines,
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

    return WikiOutline(
        overview_focus=llm.overview_focus or base.overview_focus,
        architecture_focus=llm.architecture_focus or base.architecture_focus,
        emphasized_pages=emphasized,
        reading_order=reading,
        modules=[by_name[n] for n in by_name],
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
