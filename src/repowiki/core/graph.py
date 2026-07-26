"""dependency graph construction and PageRank ranking."""

from __future__ import annotations

import posixpath
import re
from pathlib import Path, PurePosixPath

import networkx as nx

from repowiki.core.models import ProjectContext
from repowiki.core.modules import group_into_modules, module_index

# import pattern regexes by language
_IMPORT_PATTERNS = {
    "python": [
        re.compile(r"^\s*import\s+([\w.]+)", re.MULTILINE),
        re.compile(r"^\s*from\s+([\w.]+)\s+import", re.MULTILINE),
    ],
    "javascript": [
        re.compile(r"""import\s+.*?\s+from\s+['"]([^'"]+)['"]""", re.MULTILINE),
        re.compile(r"""require\s*\(\s*['"]([^'"]+)['"]\s*\)""", re.MULTILINE),
    ],
    "typescript": [
        re.compile(r"""import\s+.*?\s+from\s+['"]([^'"]+)['"]""", re.MULTILINE),
        re.compile(r"""require\s*\(\s*['"]([^'"]+)['"]\s*\)""", re.MULTILINE),
    ],
    "go": [
        re.compile(r'"([^"]+)"', re.MULTILINE),
    ],
    "rust": [
        re.compile(r"^\s*use\s+([\w:]+)", re.MULTILINE),
        re.compile(r"^\s*mod\s+(\w+)", re.MULTILINE),
    ],
    "java": [
        re.compile(r"^\s*import\s+([\w.]+);", re.MULTILINE),
    ],
}

# also cover jsx/tsx/mjs etc
for alias in ("jsx", "tsx", "mjs", "cjs"):
    _IMPORT_PATTERNS[alias] = _IMPORT_PATTERNS["javascript"]


class DependencyGraph:
    """file dependency graph with PageRank scoring."""

    def __init__(self):
        self.graph = nx.DiGraph()
        self._file_paths: set[str] = set()
        # path -> module, from the same grouping the wiki writes pages for, so
        # an edge in the diagram always names a module the reader can open.
        self._module_of: dict[str, str] = {}

    @classmethod
    def build_from_project(cls, project: ProjectContext) -> DependencyGraph:
        dg = cls()
        path_set = {f.path for f in project.files}
        dg._file_paths = path_set
        dg._module_of = module_index(group_into_modules(project.files))

        # add all files as nodes
        for f in project.files:
            dg.graph.add_node(f.path, language=f.language, lines=f.lines)

        # parse imports and create edges
        for f in project.files:
            content = f.content or f.preview
            if not content:
                continue

            patterns = _IMPORT_PATTERNS.get(f.language, [])
            for pat in patterns:
                for match in pat.finditer(content):
                    import_path = match.group(1)
                    resolved = _resolve_import(import_path, f.path, f.language, path_set)
                    if resolved and resolved != f.path:
                        dg.graph.add_edge(f.path, resolved)

        return dg

    def rank_files(self) -> list[tuple[str, float]]:
        """return files ranked by PageRank (most important first)."""
        if not self.graph.nodes:
            return []
        try:
            scores = _pagerank_power_iteration(self.graph, alpha=0.85)
        except Exception:
            # fallback: uniform scores if PageRank fails (convergence, etc.)
            scores = {n: 1.0 / len(self.graph) for n in self.graph}
        return sorted(scores.items(), key=lambda x: -x[1])

    def get_core_files(self, top_n: int = 10) -> list[str]:
        """top N most important files by PageRank."""
        return [path for path, _ in self.rank_files()[:top_n]]

    def module_of(self, path: str) -> str:
        return self._module_of.get(path) or _get_module(path)

    def get_module_dependencies(self) -> dict[str, set[str]]:
        """edges between the modules the wiki documents."""
        deps: dict[str, set[str]] = {}
        for src, dst in self.graph.edges:
            src_mod = self.module_of(src)
            dst_mod = self.module_of(dst)
            if src_mod != dst_mod:
                deps.setdefault(src_mod, set()).add(dst_mod)
        return deps

    def module_neighbours(self, module: str) -> tuple[set[str], set[str]]:
        """Modules this one imports, and modules that import it."""
        out: set[str] = set()
        incoming: set[str] = set()
        for src, dst in self.graph.edges:
            src_mod = self.module_of(src)
            dst_mod = self.module_of(dst)
            if src_mod == dst_mod:
                continue
            if src_mod == module:
                out.add(dst_mod)
            elif dst_mod == module:
                incoming.add(src_mod)
        return out, incoming

    def module_mermaid(self, module: str) -> str:
        """Flowchart of one module's immediate neighbourhood.

        Scoped rather than whole-project: a reader on the page for one module
        needs its edges, and the full graph on every page is wallpaper.
        """
        out, incoming = self.module_neighbours(module)
        if not out and not incoming:
            return ""
        lines = ["graph LR"]
        me = _mermaid_id(module)
        for dep in sorted(incoming):
            lines.append(f"  {_mermaid_id(dep)}[{dep}] --> {me}[{module}]")
        for dep in sorted(out):
            lines.append(f"  {me}[{module}] --> {_mermaid_id(dep)}[{dep}]")
        return "\n".join(lines)

    def module_weights(self) -> dict[str, float]:
        """Total PageRank each module's files carry."""
        weights: dict[str, float] = {}
        for path, score in self.rank_files():
            weights[self.module_of(path)] = weights.get(self.module_of(path), 0.0) + score
        return weights

    def to_mermaid(self, max_modules: int = 12) -> str:
        """Mermaid flowchart of inter-module dependencies.

        Restricted to the heaviest modules by PageRank. A mid-sized repository
        produces fifty-odd edges, and a diagram that dense communicates less
        than the file list it was meant to summarise.
        """
        mod_deps = self.get_module_dependencies()
        if not mod_deps:
            return ""

        weights = self.module_weights()
        involved = set(mod_deps) | {d for ts in mod_deps.values() for d in ts}
        keep = set(sorted(involved, key=lambda m: -weights.get(m, 0.0))[:max_modules])

        lines = ["graph TD"]
        seen_edges = set()
        for src, targets in sorted(mod_deps.items()):
            if src not in keep:
                continue
            for dst in sorted(targets):
                edge = (src, dst)
                if dst not in keep or edge in seen_edges:
                    continue
                seen_edges.add(edge)
                # sanitize node names for Mermaid
                s = _mermaid_id(src)
                d = _mermaid_id(dst)
                lines.append(f"  {s}[{src}] --> {d}[{dst}]")

        if len(lines) == 1:
            return ""
        return "\n".join(lines)

    def get_entry_points(self) -> list[str]:
        """files with few incoming edges that still import other modules.

        These are likely top-level entry points: little or nothing in the
        project depends on them, yet they pull in other code. Files with no
        edges at all are not entry points -- see find_isolated_files().
        """
        entries = []
        for node in self.graph.nodes:
            if self.graph.in_degree(node) <= 1 and self.graph.out_degree(node) > 0:
                entries.append(node)
        return entries

    def find_isolated_files(self) -> list[str]:
        """files with no import edges in either direction -- likely dead code.

        An isolated file imports nothing in the project and is imported by
        nothing: a stray script, dead code, or a module that should be wired in
        but never was. Distinct from an entry point, which does pull in other
        modules. Deterministic.
        """
        isolated = [
            node
            for node in self.graph.nodes
            if self.graph.in_degree(node) == 0 and self.graph.out_degree(node) == 0
        ]
        return sorted(isolated)

    def find_circular_dependencies(self, limit: int = 10) -> list[list[str]]:
        """groups of files that import each other in a cycle.

        Circular dependencies make a codebase harder to read and refactor -- you
        can't fully understand one file without the others, and they invite
        import-time ordering bugs. Returns each strongly connected component of
        more than one file (a genuine cycle), largest first. Deterministic.
        """
        cycles = [
            sorted(scc) for scc in nx.strongly_connected_components(self.graph) if len(scc) > 1
        ]
        cycles.sort(key=lambda c: (-len(c), c[0]))
        return cycles[:limit]


def _pagerank_power_iteration(
    graph: nx.DiGraph,
    alpha: float = 0.85,
    max_iter: int = 100,
    tol: float = 1.0e-6,
) -> dict[str, float]:
    """PageRank via plain power iteration.

    networkx 3.6 moved its own implementation onto scipy, which RepoWiki does
    not depend on -- and pulling in scipy for one algorithm is a bad trade for
    a CLI install. This is the textbook iterative version, deterministic.
    """
    nodes = list(graph.nodes)
    n = len(nodes)
    if n == 0:
        return {}
    out_degree = {node: graph.out_degree(node) for node in nodes}
    scores = {node: 1.0 / n for node in nodes}
    for _ in range(max_iter):
        # dangling nodes (no out-edges) redistribute their share uniformly
        dangling = sum(scores[node] for node in nodes if out_degree[node] == 0)
        new_scores = {}
        for node in nodes:
            incoming = sum(
                scores[pred] / out_degree[pred]
                for pred in graph.predecessors(node)
                if out_degree[pred] > 0
            )
            new_scores[node] = (1 - alpha) / n + alpha * (incoming + dangling / n)
        if sum(abs(new_scores[node] - scores[node]) for node in nodes) < tol:
            scores = new_scores
            break
        scores = new_scores
    return scores


def _get_module(path: str) -> str:
    """Fallback for graphs built without a project to group against."""
    parts = Path(path).parts
    if len(parts) <= 1:
        return "root"
    mod = parts[0]
    if mod in ("src", "lib", "pkg", "internal", "app") and len(parts) > 2:
        return parts[1]
    return mod


def _mermaid_id(name: str) -> str:
    """make a valid Mermaid node ID from a module name."""
    return re.sub(r"[^a-zA-Z0-9_]", "_", name)


def _resolve_import(
    import_path: str,
    source_file: str,
    language: str,
    known_paths: set[str],
) -> str | None:
    """try to resolve an import string to an actual file path in the project."""
    if language in ("python", "pyi"):
        rel = _resolve_python_module(import_path, source_file)
        candidates = [
            f"{rel}.py",
            f"{rel}/__init__.py",
        ]
        if not rel.startswith("src/"):
            candidates.extend([f"src/{rel}.py", f"src/{rel}/__init__.py"])
    elif language in ("javascript", "typescript", "jsx", "tsx", "mjs", "cjs"):
        if import_path.startswith("."):
            base_dir = str(PurePosixPath(source_file).parent)
            rel = posixpath.normpath(posixpath.join(base_dir, import_path))
        else:
            rel = import_path
        candidates = [
            rel,
            f"{rel}.ts", f"{rel}.tsx", f"{rel}.js", f"{rel}.jsx",
            f"{rel}.mjs", f"{rel}.cjs",
            f"{rel}/index.ts", f"{rel}/index.tsx", f"{rel}/index.js",
            f"{rel}/index.jsx", f"{rel}/index.mjs", f"{rel}/index.cjs",
        ]
    elif language == "go":
        # go imports are package paths, hard to resolve without go.mod
        parts = import_path.split("/")
        if len(parts) >= 2:
            candidates = [f"{'/'.join(parts[-2:])}.go"]
        else:
            return None
    elif language == "rust":
        rel = import_path.split("::")[0].replace("::", "/")
        candidates = [f"src/{rel}.rs", f"src/{rel}/mod.rs", f"{rel}.rs"]
    elif language == "java":
        rel = import_path.replace(".", "/")
        candidates = [f"src/main/java/{rel}.java", f"{rel}.java"]
    else:
        return None

    for c in candidates:
        c = posixpath.normpath(c.replace("\\", "/"))
        if c in known_paths:
            return c

    return None


def _resolve_python_module(import_path: str, source_file: str) -> str:
    leading_dots = len(import_path) - len(import_path.lstrip("."))
    module = import_path[leading_dots:].replace(".", "/")
    if not leading_dots:
        return module

    source_dir = PurePosixPath(source_file.replace("\\", "/")).parent.parts
    keep = max(0, len(source_dir) - leading_dots + 1)
    parts = [*source_dir[:keep]]
    if module:
        parts.extend(module.split("/"))
    return "/".join(parts)
