"""assemble wiki pages from analysis results."""

from __future__ import annotations

import re
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
    "related-source": {"en": "Related source", "zh": "相关源码", "ja": "関連ソース", "ko": "관련 소스"},
    "key-concepts": {"en": "Key Concepts", "zh": "关键概念", "ja": "重要概念", "ko": "핵심 개념"},
    "implementation": {"en": "Implementation", "zh": "实现细节", "ja": "実装", "ko": "구현"},
    "how-it-runs": {"en": "How it actually runs", "zh": "这条链路怎么转", "ja": "実際の動き", "ko": "실제 동작"},
    "call-chains": {"en": "Key Call Chains", "zh": "关键调用链", "ja": "主要な呼び出し", "ko": "주요 호출 체인"},
    "how-a-call-runs": {"en": "How a call runs", "zh": "一次调用怎么走", "ja": "呼び出しの流れ", "ko": "호출이 흐르는 방식"},
    "edge-cases": {"en": "Edge Cases", "zh": "边界条件", "ja": "エッジケース", "ko": "예외 상황"},
    "failures": {"en": "Failures and edges", "zh": "失败与边界", "ja": "失敗と境界", "ko": "실패와 경계"},
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

        chains = list(getattr(mod, "call_chains", None) or [])
        implementation = (getattr(mod, "implementation_details", "") or "").strip()
        walkthrough = _walkthrough_blob(mod)

        if chains:
            lines.append(f"## {structural_title('how-a-call-runs', language)}\n")
            for chain in chains:
                lines.append(f"### {chain.name}\n")
                if chain.description:
                    lines.append(f"{chain.description}\n")
                for i, step in enumerate(chain.steps, 1):
                    lines.append(f"{i}. {step}")
                if chain.steps:
                    lines.append("")
                diagram = mermaid_from_call_chain(chain)
                if diagram:
                    lines.append("```mermaid")
                    lines.append(diagram)
                    lines.append("```\n")

        if implementation and not _duplicates_chain_prose(implementation, chains):
            lines.append(f"## {structural_title('how-it-runs', language)}\n")
            lines.append(f"{implementation}\n")

        edge_cases = getattr(mod, "edge_cases", None) or []
        if edge_cases:
            lines.append(f"## {structural_title('failures', language)}\n")
            for case in edge_cases:
                lines.append(f"- {case}")
            lines.append("")

        if graph is not None:
            neighbourhood = graph.module_mermaid(mod.name)
            if neighbourhood:
                lines.append(f"## {structural_title('dependencies', language)}\n")
                lines.append("```mermaid\n" + neighbourhood + "\n```\n")

        load_bearing = list(mod.files or [])[:6]
        if load_bearing:
            lines.append(f"## {structural_title('related-source', language)}\n")
            for f in load_bearing:
                purpose = f" — {f.purpose}" if f.purpose else ""
                lines.append(f"- `{f.path}`{purpose}")
            lines.append("")

        extra_concepts = [
            c
            for c in (mod.key_concepts or [])
            if _adds_new_fact(f"{c.name} {c.explanation}", walkthrough)
        ]
        if extra_concepts:
            lines.append(f"## {structural_title('key-concepts', language)}\n")
            for c in extra_concepts:
                lines.append(f"- **{c.name}**: {c.explanation}")
            lines.append("")

        extra_rels = [
            r
            for r in (mod.relationships or [])
            if _adds_new_fact(f"{r.source} {r.target} {r.description}", walkthrough)
        ]
        if extra_rels:
            lines.append(f"## {structural_title('relationships', language)}\n")
            for r in extra_rels:
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


_TICK_OR_PATH = re.compile(r"`([^`]+)`|([A-Za-z0-9_./-]+\.[A-Za-z0-9]+)")
_INVENTORY_PROSE_RE = re.compile(
    r"(?i)(the entry point is\b|submodules are\b|heaviest modules|"
    r"入口是\s*`?lib\.rs|子模块是)"
)
_SYMBOL_DUMP_RE = re.compile(
    r"(?m)^[ \t]+- `[A-Za-z_][A-Za-z0-9_]*` \((function|class|method|struct|enum|trait|type)\)[^\n]*\n"
)
_MERMAID_LABEL_RE = re.compile(r'[\[\]{}"#\n]')
_MODULE_SECTION_ALIASES: dict[str, tuple[str, ...]] = {
    "term-tips": ("术语小贴士", "Term tips"),
    "how-a-call-runs": ("一次调用怎么走", "How a call runs", "关键调用链", "Key Call Chains"),
    "how-it-runs": ("这条链路怎么转", "How it actually runs", "实现细节", "Implementation"),
    "failures": ("失败与边界", "Failures and edges", "边界条件", "Edge Cases"),
    "dependencies": ("依赖", "Dependencies"),
    "related-source": ("相关源码", "Related source", "文件", "Files"),
    "key-concepts": ("关键概念", "Key Concepts"),
    "relationships": ("内部关系", "Internal Relationships"),
    "source-evidence": ("源码证据", "Source Evidence"),
}
_MODULE_SECTION_CANON = {
    "how-a-call-runs": {"zh": "一次调用怎么走", "en": "How a call runs"},
    "how-it-runs": {"zh": "这条链路怎么转", "en": "How it actually runs"},
    "failures": {"zh": "失败与边界", "en": "Failures and edges"},
    "related-source": {"zh": "相关源码", "en": "Related source"},
}
_MODULE_SECTION_ORDER = (
    "term-tips",
    "how-a-call-runs",
    "how-it-runs",
    "failures",
    "dependencies",
    "related-source",
    "key-concepts",
    "relationships",
    "source-evidence",
)


def mermaid_from_call_chain(chain) -> str:
    """Flowchart from ≥3 call-chain steps. Empty if labels would be garbage."""
    steps = [str(s).strip() for s in (getattr(chain, "steps", None) or []) if str(s).strip()]
    if len(steps) < 3:
        return ""
    labels: list[str] = []
    for step in steps[:8]:
        label = _safe_mermaid_label(step)
        if not label:
            return ""
        labels.append(label)
    if len(labels) < 3:
        return ""
    lines = ["flowchart TD"]
    ids = [f"s{i}" for i in range(1, len(labels) + 1)]
    for nid, lab in zip(ids, labels, strict=True):
        lines.append(f'  {nid}["{lab}"]')
    for src, dst in zip(ids, ids[1:], strict=False):
        lines.append(f"  {src} --> {dst}")
    return "\n".join(lines)


def _safe_mermaid_label(text: str) -> str:
    cleaned = _MERMAID_LABEL_RE.sub(" ", text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()[:48]
    if len(cleaned) < 8:
        return ""
    return cleaned


def _walkthrough_blob(mod) -> str:
    parts = [
        getattr(mod, "purpose", "") or "",
        getattr(mod, "description", "") or "",
        getattr(mod, "implementation_details", "") or "",
    ]
    for chain in getattr(mod, "call_chains", None) or []:
        parts.append(getattr(chain, "name", "") or "")
        parts.append(getattr(chain, "description", "") or "")
        parts.extend(getattr(chain, "steps", None) or [])
    return "\n".join(parts)


def _cited_tokens(text: str) -> set[str]:
    out: set[str] = set()
    for match in _TICK_OR_PATH.finditer(text or ""):
        token = (match.group(1) or match.group(2) or "").strip()
        if token:
            out.add(token.split(":")[0])
    return out


def _adds_new_fact(text: str, walkthrough: str) -> bool:
    extra = _cited_tokens(text) - _cited_tokens(walkthrough)
    return bool(extra)


def _strip_inventory_prose(text: str) -> str:
    kept: list[str] = []
    for line in text.splitlines():
        if _INVENTORY_PROSE_RE.search(line):
            continue
        kept.append(line)
    return "\n".join(kept)


def _norm_prose(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _duplicates_chain_prose(implementation: str, chains) -> bool:
    impl = _norm_prose(implementation)
    if not impl or not chains:
        return False
    blob = _norm_prose(
        " ".join(
            " ".join(
                [
                    getattr(c, "description", "") or "",
                    *list(getattr(c, "steps", None) or []),
                ]
            )
            for c in chains
        )
    )
    if not blob:
        return False
    if impl in blob or blob in impl:
        return True
    impl_tokens = set(impl.split())
    if not impl_tokens:
        return True
    return len(impl_tokens & set(blob.split())) / len(impl_tokens) >= 0.75


def upgrade_legacy_module_markdown(content: str, language: str = "zh") -> str:
    """Rewrite persisted module pages: strip JavaDoc dumps, put the flow first."""
    if not content or "## " not in content:
        return content
    text = _SYMBOL_DUMP_RE.sub("", content)
    lead, sections = _split_markdown_sections(text)
    lead = _strip_inventory_prose(lead)
    if not sections:
        return (lead.rstrip() + "\n") if lead.strip() else content

    lang = "zh" if normalize_wiki_lang(language) == "zh" else "en"
    grouped: dict[str, list[tuple[str, str]]] = {key: [] for key in _MODULE_SECTION_ORDER}
    other: list[tuple[str, str]] = []
    for title, body in sections:
        key = _module_section_key(title)
        if key:
            grouped[key].append((title, body))
        else:
            other.append((title, body))

    chain_blob = " ".join(body for _, body in grouped["how-a-call-runs"])
    kept_impl: list[tuple[str, str]] = []
    for title, body in grouped["how-it-runs"]:
        cleaned = _strip_inventory_prose(body)
        if not cleaned.strip():
            continue
        if _duplicates_chain_prose(cleaned, [_SimpleChain(chain_blob)]):
            continue
        kept_impl.append((title, cleaned))
    grouped["how-it-runs"] = kept_impl

    out = [lead.rstrip()]
    for key in _MODULE_SECTION_ORDER:
        canon = _MODULE_SECTION_CANON.get(key, {}).get(lang)
        for title, body in grouped[key]:
            heading = canon or title
            chunk = f"## {heading}"
            if body.strip():
                chunk += "\n" + body.strip("\n")
            out.append(chunk)
    for title, body in other:
        chunk = f"## {title}"
        if body.strip():
            chunk += "\n" + body.strip("\n")
        out.append(chunk)
    return "\n\n".join(part for part in out if part.strip()).rstrip() + "\n"


class _SimpleChain:
    def __init__(self, blob: str):
        self.description = blob
        self.steps: list[str] = []


def _module_section_key(title: str) -> str | None:
    stripped = title.strip()
    for key, aliases in _MODULE_SECTION_ALIASES.items():
        if stripped in aliases:
            return key
    return None


def _split_markdown_sections(content: str) -> tuple[str, list[tuple[str, str]]]:
    parts = re.split(r"(?m)^## ", content)
    lead = parts[0]
    sections: list[tuple[str, str]] = []
    for part in parts[1:]:
        title, _, rest = part.partition("\n")
        sections.append((title.strip(), rest))
    return lead, sections
