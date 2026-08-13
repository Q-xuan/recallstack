"""assemble wiki pages from analysis results."""

from __future__ import annotations

from dataclasses import dataclass, field

from repowiki.core.cite_check import format_citation
from repowiki.core.graph import DependencyGraph
from repowiki.core.models import ProjectContext, WikiData


@dataclass
class WikiPage:
    id: str
    title: str
    content: str
    parent_id: str = ""
    order: int = 0


@dataclass
class SidebarItem:
    title: str
    page_id: str
    children: list[SidebarItem] = field(default_factory=list)


@dataclass
class Wiki:
    pages: list[WikiPage] = field(default_factory=list)
    sidebar: list[SidebarItem] = field(default_factory=list)
    project_name: str = ""

    def get_page(self, page_id: str) -> WikiPage | None:
        for p in self.pages:
            if p.id == page_id:
                return p
        return None


class WikiBuilder:
    """constructs a Wiki from analysis results."""

    def build(
        self,
        project: ProjectContext,
        wiki_data: WikiData,
        graph: DependencyGraph,
    ) -> Wiki:
        pages: list[WikiPage] = []
        sidebar: list[SidebarItem] = []

        # 1. index / overview page
        overview = wiki_data.overview
        overview_md = self._build_overview_page(overview, project)
        pages.append(WikiPage(id="index", title="Overview", content=overview_md, order=0))
        sidebar.append(SidebarItem(title="Overview", page_id="index"))

        # 2. architecture page
        arch = wiki_data.architecture
        if arch.architecture_type:
            arch_md = self._build_architecture_page(arch)
            pages.append(WikiPage(id="architecture", title="Architecture", content=arch_md, order=1))
            sidebar.append(SidebarItem(title="Architecture", page_id="architecture"))

        # 3. module pages
        for i, mod in enumerate(wiki_data.modules):
            mod_id = f"modules/{mod.name}"
            mod_md = self._build_module_page(mod, graph)
            pages.append(WikiPage(
                id=mod_id, title=mod.name, content=mod_md,
                parent_id="modules", order=i,
            ))
        module_sidebar = self._build_module_sidebar([m.name for m in wiki_data.modules])
        if module_sidebar.children:
            sidebar.append(module_sidebar)

        # 4. reading guide
        guide = wiki_data.reading_guide
        if guide.steps:
            guide_md = self._build_reading_guide_page(guide)
            pages.append(WikiPage(id="reading-guide", title="Reading Guide", content=guide_md, order=10))
            sidebar.append(SidebarItem(title="Reading Guide", page_id="reading-guide"))

        # 5. dependency graph
        mermaid = graph.to_mermaid()
        if mermaid:
            dep_md = self._build_dependency_page(graph, mermaid)
            pages.append(WikiPage(id="dependencies", title="Dependencies", content=dep_md, order=11))
            sidebar.append(SidebarItem(title="Dependencies", page_id="dependencies"))

        return Wiki(pages=pages, sidebar=sidebar, project_name=project.name)

    def _build_overview_page(self, overview, project) -> str:
        lines = [f"# {overview.name or project.name}\n"]
        if overview.one_liner:
            lines.append(f"> {overview.one_liner}\n")
        if overview.description:
            lines.append(f"{overview.description}\n")

        if overview.tech_stack:
            lines.append("## Tech Stack\n")
            for t in overview.tech_stack:
                ver = f" {t.version}" if t.version else ""
                cat = f" ({t.category})" if t.category else ""
                lines.append(f"- **{t.name}**{ver}{cat}")
            lines.append("")

        if overview.key_features:
            lines.append("## Key Features\n")
            for feat in overview.key_features:
                lines.append(f"- {feat}")
            lines.append("")

        if overview.setup_instructions:
            lines.append("## Getting Started\n")
            for i, step in enumerate(overview.setup_instructions, 1):
                lines.append(f"{i}. {step}")
            lines.append("")

        _append_citations(lines, getattr(overview, "citations", None))

        return "\n".join(lines)

    def _build_architecture_page(self, arch) -> str:
        lines = ["# Architecture\n"]
        if arch.architecture_type:
            lines.append(f"**Type:** {arch.architecture_type}\n")
        if arch.description:
            lines.append(f"{arch.description}\n")

        if arch.components:
            lines.append("## Components\n")
            for c in arch.components:
                purpose = f" — {c.purpose}" if c.purpose else ""
                lines.append(f"- **{c.name}**{purpose}")
                if c.files:
                    files = ", ".join(f"`{f}`" for f in c.files[:8])
                    lines.append(f"  - Files: {files}")
            lines.append("")

        if arch.mermaid_component:
            lines.append("## Diagram\n")
            lines.append("```mermaid")
            lines.append(arch.mermaid_component.strip())
            lines.append("```\n")

        if arch.data_flow:
            lines.append("## Data Flow\n")
            lines.append(f"{arch.data_flow}\n")

        _append_citations(lines, getattr(arch, "citations", None))

        return "\n".join(lines)

    def _build_module_sidebar(self, names: list[str]) -> SidebarItem:
        """Nest module entries by path so siblings sit under a shared parent.

        Module names are full repository paths; listed flat they are both wide
        and repetitive. The tree also gives a home to intermediate directories
        like ``src/`` that hold no files of their own and so have no page.
        """
        root = SidebarItem(title="Modules", page_id="", children=[])
        nodes: dict[str, SidebarItem] = {}

        def ensure(prefix: str) -> SidebarItem:
            if prefix in nodes:
                return nodes[prefix]
            parent_key, _, leaf = prefix.rpartition("/")
            parent = ensure(parent_key) if parent_key else root
            item = SidebarItem(title=leaf or prefix, page_id="", children=[])
            parent.children.append(item)
            nodes[prefix] = item
            return item

        for name in sorted(names):
            ensure(name).page_id = f"modules/{name}"
        return root

    def _build_module_page(self, mod, graph: DependencyGraph | None = None) -> str:
        lines = [f"# {mod.name}\n"]
        if mod.purpose:
            lines.append(f"> {mod.purpose}\n")
        if mod.description:
            lines.append(f"{mod.description}\n")

        implementation = getattr(mod, "implementation_details", "") or ""
        if implementation:
            lines.append("## Implementation\n")
            lines.append(f"{implementation}\n")

        chains = getattr(mod, "call_chains", None) or []
        if chains:
            lines.append("## Key Call Chains\n")
            for chain in chains:
                lines.append(f"### {chain.name}\n")
                if chain.description:
                    lines.append(f"{chain.description}\n")
                for i, step in enumerate(chain.steps, 1):
                    lines.append(f"{i}. {step}")
                if chain.steps:
                    lines.append("")
                if chain.files:
                    files = ", ".join(f"`{p}`" for p in chain.files)
                    lines.append(f"**Files:** {files}\n")

        edge_cases = getattr(mod, "edge_cases", None) or []
        if edge_cases:
            lines.append("## Edge Cases\n")
            for case in edge_cases:
                lines.append(f"- {case}")
            lines.append("")

        if graph is not None:
            neighbourhood = graph.module_mermaid(mod.name)
            if neighbourhood:
                lines.append("## Dependencies\n")
                lines.append("```mermaid\n" + neighbourhood + "\n```\n")

        if mod.files:
            lines.append("## Files\n")
            for f in mod.files:
                purpose = f" — {f.purpose}" if f.purpose else ""
                lines.append(f"- `{f.path}`{purpose}")
                if f.key_symbols:
                    for s in f.key_symbols[:8]:
                        desc = f" - {s.description}" if s.description else ""
                        lines.append(f"  - `{s.name}` ({s.kind}){desc}")
            lines.append("")

        if mod.key_concepts:
            lines.append("## Key Concepts\n")
            for c in mod.key_concepts:
                lines.append(f"- **{c.name}**: {c.explanation}")
            lines.append("")

        if mod.relationships:
            lines.append("## Internal Relationships\n")
            for r in mod.relationships:
                lines.append(f"- `{r.source}` → `{r.target}`: {r.description}")
            lines.append("")

        _append_citations(lines, getattr(mod, "citations", None))

        return "\n".join(lines)

    def _build_reading_guide_page(self, guide) -> str:
        lines = ["# Reading Guide\n"]
        if guide.introduction:
            lines.append(f"{guide.introduction}\n")

        for step in guide.steps:
            time_est = f" (~{step.time_estimate})" if step.time_estimate else ""
            lines.append(f"## Step {step.order}: {step.title}{time_est}\n")
            if step.files:
                lines.append("**Files:** " + ", ".join(f"`{f}`" for f in step.files) + "\n")
            if step.explanation:
                lines.append(f"{step.explanation}\n")

        if guide.tips:
            lines.append("## Tips\n")
            for tip in guide.tips:
                lines.append(f"- {tip}")
            lines.append("")

        return "\n".join(lines)

    def _build_dependency_page(self, graph: DependencyGraph, mermaid: str) -> str:
        lines = ["# Module Dependencies\n"]
        lines.append("```mermaid\n" + mermaid + "\n```\n")

        # core files
        core = graph.get_core_files(10)
        if core:
            lines.append("## Core Files (by PageRank)\n")
            for i, path in enumerate(core, 1):
                lines.append(f"{i}. `{path}`")
            lines.append("")

        # entry points
        entries = graph.get_entry_points()
        if entries:
            lines.append("## Likely Entry Points\n")
            for e in entries[:10]:
                lines.append(f"- `{e}`")
            lines.append("")

        # circular dependencies (an architectural smell worth surfacing)
        cycles = graph.find_circular_dependencies()
        if cycles:
            lines.append("## Circular Dependencies\n")
            lines.append(
                "These groups of files import each other in a cycle, so you can't "
                "fully understand one without the others; consider breaking the loop "
                "to reduce coupling.\n"
            )
            for cycle in cycles:
                files = ", ".join(f"`{p}`" for p in cycle)
                lines.append(f"- {files}")
            lines.append("")

        # isolated files (likely dead code worth surfacing)
        isolated = graph.find_isolated_files()
        if isolated:
            lines.append("## Isolated Files\n")
            lines.append(
                "These files import nothing in the project and are imported by "
                "nothing -- likely dead code, stray scripts, or modules that were "
                "never wired in.\n"
            )
            for f in isolated[:15]:
                lines.append(f"- `{f}`")
            lines.append("")

        return "\n".join(lines)


def _append_citations(lines: list[str], citations) -> None:
    if not citations:
        return

    lines.append("## Source Evidence\n")
    for cite in citations:
        loc = format_citation(cite)
        extra = ""
        if cite.symbol:
            extra += f" — `{cite.symbol}`"
        if cite.note:
            extra += f" — {cite.note}"
        lines.append(f"- `{loc}`{extra}")
    lines.append("")
