"""Pack file text into LLM prompts without naive per-file 4k truncation.

Entrypoints, configs, and high-PageRank files go first. Large files are
reduced to a head slice plus windows around symbol definitions so the write
pass still sees call-chain evidence.
"""

from __future__ import annotations

import re

from repowiki.core.graph import DependencyGraph
from repowiki.core.models import FileInfo, ModuleOutline, ProjectContext, Symbol

MODULE_BUDGET = {
    "deep": 14_000,
    "standard": 9_000,
    "brief": 5_000,
}
FILE_CAP = {
    "deep": 3_500,
    "standard": 2_500,
    "brief": 1_800,
}
KEY_FILES_BUDGET = 12_000
KEY_FILE_CAP = 2_500
NEIGHBOURHOOD_BUDGET = 3_000
NEIGHBOUR_FILE_CAP = 900

_HEAD_LINES = 40
_WINDOW = 14

_SYMBOL_LINE = re.compile(
    r"^\s*(?:"
    r"(?:async\s+)?def\s+\w+"
    r"|class\s+\w+"
    r"|(?:export\s+)?(?:async\s+)?function\s+\w+"
    r"|(?:pub\s+)?(?:async\s+)?fn\s+\w+"
    r"|func\s+\w+"
    r"|(?:public|private|protected)\s+(?:static\s+)?(?:class|interface|void|fun)\s+\w+"
    r")",
    re.MULTILINE,
)


def pack_key_files(project: ProjectContext, budget: int = KEY_FILES_BUDGET) -> str:
    """Config + entrypoint context for overview/architecture prompts."""
    preferred = [f for f in project.files if f.is_config or f.is_entrypoint]
    if not preferred:
        preferred = list(project.files[:8])
    return _pack_file_list(preferred, budget=budget, per_file=KEY_FILE_CAP)


def pack_module_context(
    files: list[FileInfo],
    *,
    depth: str = "standard",
    outline: ModuleOutline | None = None,
    graph: DependencyGraph | None = None,
    project: ProjectContext | None = None,
) -> str:
    """Order and slice a module's files for the write prompt."""
    depth = depth if depth in MODULE_BUDGET else "standard"
    ordered = _order_module_files(files, outline)
    body = _pack_file_list(ordered, budget=MODULE_BUDGET[depth], per_file=FILE_CAP[depth])
    if depth != "deep" or graph is None or project is None:
        return body
    extra = pack_neighbourhood(files, graph, project)
    if not extra:
        return body
    return body + "\n\n## Imported neighbourhood (outside this module)\n" + extra


def pack_neighbourhood(
    files: list[FileInfo],
    graph: DependencyGraph,
    project: ProjectContext,
    budget: int = NEIGHBOURHOOD_BUDGET,
) -> str:
    """Short slices of files this module imports, for cross-module call chains."""
    in_module = {f.path for f in files}
    by_path = {f.path: f for f in project.files}
    imported: list[FileInfo] = []
    seen: set[str] = set()
    for f in files:
        if f.path not in graph.graph:
            continue
        for dst in graph.graph.successors(f.path):
            if dst in in_module or dst in seen or dst not in by_path:
                continue
            seen.add(dst)
            imported.append(by_path[dst])
    return _pack_file_list(imported, budget=budget, per_file=NEIGHBOUR_FILE_CAP)


def harvest_symbols(content: str, limit: int = 8) -> list[Symbol]:
    """Cheap regex harvest used by the no-LLM module fallback."""
    found: list[Symbol] = []
    for i, line in enumerate(content.splitlines(), start=1):
        match = _SYMBOL_LINE.match(line)
        if not match:
            continue
        token = match.group(0).strip()
        name = token.split()[-1]
        kind = "class" if "class" in token else "function"
        found.append(Symbol(name=name, kind=kind, line=i))
        if len(found) >= limit:
            break
    return found


def slice_file(content: str, max_chars: int) -> str:
    """Keep the file head plus windows around symbol definitions."""
    if len(content) <= max_chars:
        return content
    lines = content.splitlines()
    if not lines:
        return content[:max_chars]

    keep: set[int] = set(range(min(_HEAD_LINES, len(lines))))
    for i, line in enumerate(lines):
        if _SYMBOL_LINE.match(line):
            start = max(0, i)
            end = min(len(lines), i + _WINDOW)
            keep.update(range(start, end))

    parts: list[str] = []
    prev = -2
    used = 0
    for i in sorted(keep):
        if used >= max_chars:
            break
        if i != prev + 1 and parts:
            parts.append("...")
        parts.append(lines[i])
        used += len(lines[i]) + 1
        prev = i

    text = "\n".join(parts)
    if len(text) > max_chars:
        text = text[:max_chars] + "\n... (truncated)"
    elif len(keep) < len(lines):
        text += "\n... (truncated)"
    return text


def _order_module_files(
    files: list[FileInfo],
    outline: ModuleOutline | None,
) -> list[FileInfo]:
    key_set = set(outline.key_files) if outline else set()
    rank = {path: i for i, path in enumerate(outline.key_files)} if outline else {}

    def score(f: FileInfo) -> tuple[int, int, int, int, str]:
        outlined = 0 if f.path in key_set else 1
        entry = 0 if f.is_entrypoint else 1
        config = 0 if f.is_config else 1
        return (outlined, entry, config, rank.get(f.path, 10_000), f.path)

    return sorted(files, key=score)


def _pack_file_list(files: list[FileInfo], *, budget: int, per_file: int) -> str:
    parts: list[str] = []
    used = 0
    for f in files:
        remaining = budget - used
        if remaining < 200:
            parts.append(f"### {f.path} ({f.language})\n... (omitted to fit context budget)")
            continue
        raw = f.content if f.content else f.preview
        sliced = slice_file(raw, min(per_file, remaining))
        block = f"### {f.path} ({f.language})\n```{f.language}\n{sliced}\n```"
        parts.append(block)
        used += len(block)
    return "\n\n".join(parts)
