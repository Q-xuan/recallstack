"""assemble wiki pages from analysis results."""

from __future__ import annotations

from dataclasses import dataclass, field

from repowiki.core.cite_check import format_citation
from repowiki.core.graph import DependencyGraph
from repowiki.core.models import ProjectContext, WikiData
from repowiki.core.modules import ROOT_NAME

# Sidebar / page chrome labels. Path segments (crates, bin, .cargo) stay as
# they are in the repo; only these structural names are translated.
_STRUCTURAL_TITLES: dict[str, dict[str, str]] = {
    "overview": {"en": "Overview", "zh": "概述", "ja": "概要", "ko": "개요"},
    "architecture": {"en": "Architecture", "zh": "架构概览", "ja": "アーキテクチャ", "ko": "아키텍처"},
    "modules": {"en": "Modules", "zh": "模块", "ja": "モジュール", "ko": "모듈"},
    "reading-guide": {"en": "Reading Guide", "zh": "导读", "ja": "ガイド", "ko": "가이드"},
    "dependencies": {"en": "Dependencies", "zh": "依赖", "ja": "依存関係", "ko": "의존성"},
    "root": {"en": "Root", "zh": "根目录", "ja": "ルート", "ko": "루트"},
    "concepts": {"en": "Concepts", "zh": "词条", "ja": "用語", "ko": "개념"},
    "type": {"en": "Type", "zh": "类型", "ja": "種類", "ko": "유형"},
    "components": {"en": "Components", "zh": "组成", "ja": "コンポーネント", "ko": "구성"},
    "diagram": {"en": "Diagram", "zh": "结构图", "ja": "図", "ko": "다이어그램"},
    "data-flow": {"en": "Data Flow", "zh": "数据流", "ja": "データフロー", "ko": "데이터 흐름"},
    "tech-stack": {"en": "Tech Stack", "zh": "技术栈", "ja": "技術スタック", "ko": "기술 스택"},
    "key-features": {"en": "Key Features", "zh": "主要能力", "ja": "主な機能", "ko": "주요 기능"},
    "getting-started": {"en": "Getting Started", "zh": "上手", "ja": "はじめに", "ko": "시작하기"},
    "files": {"en": "Files", "zh": "文件", "ja": "ファイル", "ko": "파일"},
    "key-concepts": {"en": "Key Concepts", "zh": "关键概念", "ja": "重要概念", "ko": "핵심 개념"},
    "implementation": {"en": "Implementation", "zh": "实现细节", "ja": "実装", "ko": "구현"},
    "call-chains": {"en": "Key Call Chains", "zh": "关键调用链", "ja": "主要な呼び出し", "ko": "주요 호출 체인"},
    "edge-cases": {"en": "Edge Cases", "zh": "边界条件", "ja": "エッジケース", "ko": "예외 상황"},
    "source-evidence": {"en": "Source Evidence", "zh": "源码证据", "ja": "ソース根拠", "ko": "소스 근거"},
    "relationships": {"en": "Internal Relationships", "zh": "内部关系", "ja": "内部関係", "ko": "내부 관계"},
    "term-tips": {"en": "Term tips", "zh": "术语小贴士", "ja": "用語メモ", "ko": "용어 팁"},
    "tips": {"en": "Tips", "zh": "提示", "ja": "ヒント", "ko": "팁"},
    "step": {"en": "Step", "zh": "步骤", "ja": "ステップ", "ko": "단계"},
    "core-files": {"en": "Core Files (by PageRank)", "zh": "核心文件（按 PageRank）", "ja": "中核ファイル（PageRank）", "ko": "핵심 파일 (PageRank)"},
    "entry-points": {"en": "Likely Entry Points", "zh": "可能的入口", "ja": "想定エントリポイント", "ko": "예상 진입점"},
    "circular": {"en": "Circular Dependencies", "zh": "循环依赖", "ja": "循環依存", "ko": "순환 의존"},
    "isolated": {"en": "Isolated Files", "zh": "孤立文件", "ja": "孤立ファイル", "ko": "고립 파일"},
}


def normalize_wiki_lang(language: str | None) -> str:
    code = (language or "en").strip().lower().replace("_", "-")
    primary = code.split("-", 1)[0]
    if primary in {"zh", "cn"}:
        return "zh"
    if primary in {"ja", "jp"}:
        return "ja"
    if primary in {"ko", "kr"}:
        return "ko"
    return "en"


def structural_title(key: str, language: str = "en") -> str:
    """Localized label for a structural wiki page or sidebar group."""
    table = _STRUCTURAL_TITLES[key]
    lang = normalize_wiki_lang(language)
    return table.get(lang) or table["en"]


def module_display_title(name: str, language: str = "en") -> str:
    """Sidebar/page title for a module. Only ``root`` is localized; paths stay."""
    if name == ROOT_NAME:
        return structural_title("root", language)
    return name


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

    def __init__(self, language: str = "en"):
        self.language = language

    def build(
        self,
        project: ProjectContext,
        wiki_data: WikiData,
        graph: DependencyGraph,
        *,
        language: str | None = None,
    ) -> Wiki:
        lang = normalize_wiki_lang(self.language if language is None else language)
        pages: list[WikiPage] = []
        sidebar: list[SidebarItem] = []

        # 1. index / overview page
        overview = wiki_data.overview
        overview_md = self._build_overview_page(overview, project, lang)
        overview_title = structural_title("overview", lang)
        pages.append(WikiPage(id="index", title=overview_title, content=overview_md, order=0))
        sidebar.append(SidebarItem(title=overview_title, page_id="index"))

        # 2. architecture page
        arch = wiki_data.architecture
        if arch.architecture_type:
            arch_title = structural_title("architecture", lang)
            arch_md = self._build_architecture_page(arch, lang)
            pages.append(WikiPage(id="architecture", title=arch_title, content=arch_md, order=1))
            sidebar.append(SidebarItem(title=arch_title, page_id="architecture"))

        # 3. module pages
        for i, mod in enumerate(wiki_data.modules):
            mod_id = f"modules/{mod.name}"
            mod_title = module_display_title(mod.name, lang)
            mod_md = self._build_module_page(mod, graph, display_title=mod_title, language=lang)
            pages.append(WikiPage(
                id=mod_id, title=mod_title, content=mod_md,
                parent_id="modules", order=i,
            ))
        module_sidebar = self._build_module_sidebar(
            [m.name for m in wiki_data.modules], language=lang
        )
        if module_sidebar.children:
            sidebar.append(module_sidebar)

        # 4. reading guide
        guide = wiki_data.reading_guide
        if guide.steps:
            guide_title = structural_title("reading-guide", lang)
            guide_md = self._build_reading_guide_page(guide, lang)
            pages.append(WikiPage(id="reading-guide", title=guide_title, content=guide_md, order=10))
            sidebar.append(SidebarItem(title=guide_title, page_id="reading-guide"))

        # 5. dependency graph
        mermaid = graph.to_mermaid()
        if mermaid:
            dep_title = structural_title("dependencies", lang)
            dep_md = self._build_dependency_page(graph, mermaid, lang)
            pages.append(WikiPage(id="dependencies", title=dep_title, content=dep_md, order=11))
            sidebar.append(SidebarItem(title=dep_title, page_id="dependencies"))

        return Wiki(pages=pages, sidebar=sidebar, project_name=project.name)

    def _build_overview_page(self, overview, project, language: str = "en") -> str:
        lines = [f"# {overview.name or project.name}\n"]
        if overview.one_liner:
            lines.append(f"> {overview.one_liner}\n")
        if overview.description:
            lines.append(f"{overview.description}\n")

        _append_term_tips(lines, getattr(overview, "term_tips", None), language)

        if overview.tech_stack:
            lines.append(f"## {structural_title('tech-stack', language)}\n")
            for t in overview.tech_stack:
                ver = f" {t.version}" if t.version else ""
                cat = f" ({t.category})" if t.category else ""
                lines.append(f"- **{t.name}**{ver}{cat}")
            lines.append("")

        if overview.key_features:
            lines.append(f"## {structural_title('key-features', language)}\n")
            for feat in overview.key_features:
                lines.append(f"- {feat}")
            lines.append("")

        if overview.setup_instructions:
            lines.append(f"## {structural_title('getting-started', language)}\n")
            for i, step in enumerate(overview.setup_instructions, 1):
                lines.append(f"{i}. {step}")
            lines.append("")

        _append_citations(lines, getattr(overview, "citations", None), language)

        return "\n".join(lines)

    def _build_architecture_page(self, arch, language: str = "en") -> str:
        lines = [f"# {structural_title('architecture', language)}\n"]
        if arch.architecture_type:
            lines.append(f"**{structural_title('type', language)}:** {arch.architecture_type}\n")
        if arch.description:
            lines.append(f"{arch.description}\n")

        _append_term_tips(lines, getattr(arch, "term_tips", None), language)

        if arch.components:
            lines.append(f"## {structural_title('components', language)}\n")
            for c in arch.components:
                purpose = f" — {c.purpose}" if c.purpose else ""
                lines.append(f"- **{c.name}**{purpose}")
                if c.files:
                    files = ", ".join(f"`{f}`" for f in c.files[:8])
                    lines.append(f"  - {structural_title('files', language)}: {files}")
            lines.append("")

        if arch.mermaid_component:
            lines.append(f"## {structural_title('diagram', language)}\n")
            lines.append("```mermaid")
            lines.append(arch.mermaid_component.strip())
            lines.append("```\n")

        if arch.data_flow:
            lines.append(f"## {structural_title('data-flow', language)}\n")
            lines.append(f"{arch.data_flow}\n")

        _append_citations(lines, getattr(arch, "citations", None), language)

        return "\n".join(lines)

    def _build_module_sidebar(self, names: list[str], language: str = "en") -> SidebarItem:
        """Nest module entries by path so siblings sit under a shared parent.

        Module names are full repository paths; listed flat they are both wide
        and repetitive. The tree also gives a home to intermediate directories
        like ``src/`` that hold no files of their own and so have no page.
        Path segments stay as in the repo; only the group label and ``root``
        are localized.
        """
        root = SidebarItem(title=structural_title("modules", language), page_id="", children=[])
        nodes: dict[str, SidebarItem] = {}

        def ensure(prefix: str) -> SidebarItem:
            if prefix in nodes:
                return nodes[prefix]
            parent_key, _, leaf = prefix.rpartition("/")
            parent = ensure(parent_key) if parent_key else root
            item = SidebarItem(
                title=module_display_title(leaf or prefix, language),
                page_id="",
                children=[],
            )
            parent.children.append(item)
            nodes[prefix] = item
            return item

        for name in sorted(names):
            ensure(name).page_id = f"modules/{name}"
        return root

    def _build_module_page(
        self,
        mod,
        graph: DependencyGraph | None = None,
        *,
        display_title: str | None = None,
        language: str = "en",
    ) -> str:
        heading = display_title or mod.name
        lines = [f"# {heading}\n"]
        if mod.purpose:
            lines.append(f"> {mod.purpose}\n")
        if mod.description:
            lines.append(f"{mod.description}\n")

        _append_term_tips(lines, getattr(mod, "term_tips", None), language)

        implementation = getattr(mod, "implementation_details", "") or ""
        if implementation:
            lines.append(f"## {structural_title('implementation', language)}\n")
            lines.append(f"{implementation}\n")

        chains = getattr(mod, "call_chains", None) or []
        if chains:
            lines.append(f"## {structural_title('call-chains', language)}\n")
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
                    lines.append(f"**{structural_title('files', language)}:** {files}\n")

        edge_cases = getattr(mod, "edge_cases", None) or []
        if edge_cases:
            lines.append(f"## {structural_title('edge-cases', language)}\n")
            for case in edge_cases:
                lines.append(f"- {case}")
            lines.append("")

        if graph is not None:
            neighbourhood = graph.module_mermaid(mod.name)
            if neighbourhood:
                lines.append(f"## {structural_title('dependencies', language)}\n")
                lines.append("```mermaid\n" + neighbourhood + "\n```\n")

        if mod.files:
            lines.append(f"## {structural_title('files', language)}\n")
            for f in mod.files:
                purpose = f" — {f.purpose}" if f.purpose else ""
                lines.append(f"- `{f.path}`{purpose}")
                if f.key_symbols:
                    for s in f.key_symbols[:8]:
                        desc = f" - {s.description}" if s.description else ""
                        lines.append(f"  - `{s.name}` ({s.kind}){desc}")
            lines.append("")

        if mod.key_concepts:
            lines.append(f"## {structural_title('key-concepts', language)}\n")
            for c in mod.key_concepts:
                lines.append(f"- **{c.name}**: {c.explanation}")
            lines.append("")

        if mod.relationships:
            lines.append(f"## {structural_title('relationships', language)}\n")
            for r in mod.relationships:
                lines.append(f"- `{r.source}` → `{r.target}`: {r.description}")
            lines.append("")

        _append_citations(lines, getattr(mod, "citations", None), language)

        return "\n".join(lines)

    def _build_reading_guide_page(self, guide, language: str = "en") -> str:
        lines = [f"# {structural_title('reading-guide', language)}\n"]
        if guide.introduction:
            lines.append(f"{guide.introduction}\n")

        for step in guide.steps:
            time_est = f" (~{step.time_estimate})" if step.time_estimate else ""
            lines.append(
                f"## {structural_title('step', language)} {step.order}: {step.title}{time_est}\n"
            )
            if step.files:
                files_label = structural_title("files", language)
                lines.append(f"**{files_label}:** " + ", ".join(f"`{f}`" for f in step.files) + "\n")
            if step.explanation:
                lines.append(f"{step.explanation}\n")

        if guide.tips:
            lines.append(f"## {structural_title('tips', language)}\n")
            for tip in guide.tips:
                lines.append(f"- {tip}")
            lines.append("")

        return "\n".join(lines)

    def _build_dependency_page(
        self, graph: DependencyGraph, mermaid: str, language: str = "en"
    ) -> str:
        lines = [f"# {structural_title('dependencies', language)}\n"]
        lines.append("```mermaid\n" + mermaid + "\n```\n")

        # core files
        core = graph.get_core_files(10)
        if core:
            lines.append(f"## {structural_title('core-files', language)}\n")
            for i, path in enumerate(core, 1):
                lines.append(f"{i}. `{path}`")
            lines.append("")

        # entry points
        entries = graph.get_entry_points()
        if entries:
            lines.append(f"## {structural_title('entry-points', language)}\n")
            for e in entries[:10]:
                lines.append(f"- `{e}`")
            lines.append("")

        # circular dependencies (an architectural smell worth surfacing)
        cycles = graph.find_circular_dependencies()
        if cycles:
            lines.append(f"## {structural_title('circular', language)}\n")
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
            lines.append(f"## {structural_title('isolated', language)}\n")
            lines.append(
                "These files import nothing in the project and are imported by "
                "nothing -- likely dead code, stray scripts, or modules that were "
                "never wired in.\n"
            )
            for f in isolated[:15]:
                lines.append(f"- `{f}`")
            lines.append("")

        return "\n".join(lines)


def _append_term_tips(lines: list[str], tips, language: str = "en") -> None:
    items = [tip for tip in (tips or []) if getattr(tip, "term", "")]
    if not items:
        return
    lines.append(f"## {structural_title('term-tips', language)}\n")
    for tip in items:
        text = getattr(tip, "tip", "") or ""
        if text:
            lines.append(f"> **{tip.term}** — {text}")
        else:
            lines.append(f"> **{tip.term}**")
    lines.append("")


def _append_citations(lines: list[str], citations, language: str = "en") -> None:
    if not citations:
        return

    lines.append(f"## {structural_title('source-evidence', language)}\n")
    for cite in citations:
        loc = format_citation(cite)
        extra = ""
        if cite.symbol:
            extra += f" — `{cite.symbol}`"
        if cite.note:
            extra += f" — {cite.note}"
        lines.append(f"- `{loc}`{extra}")
    lines.append("")
