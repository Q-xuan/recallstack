"""assemble wiki pages from analysis results."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from repowiki.core.cite_check import format_citation
from repowiki.core.graph import DependencyGraph
from repowiki.core.models import ProjectContext, WikiData
from repowiki.core.modules import ROOT_NAME
from repowiki.core.topics import (
    GETTING_STARTED_ID,
    is_generic_web_slug,
    keep_generic_web_topic_nav,
    repo_has_web_system,
    wiki_page_id_for_topic,
)

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
    "what-is": {"en": "Overview", "zh": "概述", "ja": "概要", "ko": "개요"},
    "system-architecture": {"en": "System architecture", "zh": "系统架构", "ja": "システム構成", "ko": "시스템 아키텍처"},
    "codebase-split": {"en": "How the code is split", "zh": "代码如何拆分", "ja": "コードの分割", "ko": "코드가 나뉘는 방식"},
    "core-subsystems": {"en": "Core subsystems", "zh": "核心子系统", "ja": "中核サブシステム", "ko": "핵심 서브시스템"},
    "key-types": {"en": "Key types", "zh": "关键类型", "ja": "主要な型", "ko": "핵심 타입"},
    "see-also": {"en": "Read next", "zh": "继续读", "ja": "次に読む", "ko": "이어서 읽기"},
    "components": {"en": "Roles in the flow", "zh": "链路里的角色", "ja": "フロー上の役割", "ko": "흐름 속 역할"},
    "diagram": {"en": "Diagram", "zh": "结构图", "ja": "図", "ko": "다이어그램"},
    "data-flow": {"en": "Data Flow", "zh": "数据流", "ja": "データフロー", "ko": "데이터 흐름"},
    "tech-stack": {"en": "Tech Stack", "zh": "技术栈", "ja": "技術スタック", "ko": "기술 스택"},
    "key-features": {"en": "Key Features", "zh": "主要能力", "ja": "主な機能", "ko": "주요 기능"},
    "getting-started": {"en": "Getting Started", "zh": "入门指南", "ja": "入門", "ko": "시작하기"},
    "setup": {"en": "Setup", "zh": "上手", "ja": "セットアップ", "ko": "설정"},
    "quick-start": {"en": "Quick start", "zh": "快速开始", "ja": "クイックスタート", "ko": "빠른 시작"},
    "deep-dive": {"en": "Deep Dive", "zh": "深入探索", "ja": "深掘り", "ko": "심층 탐색"},
    "by-directory": {"en": "By directory", "zh": "按目录", "ja": "ディレクトリ別", "ko": "디렉터리별"},
    "files": {"en": "Files", "zh": "文件", "ja": "ファイル", "ko": "파일"},
    "related-source": {"en": "Related source", "zh": "相关源码", "ja": "関連ソース", "ko": "관련 소스"},
    "key-concepts": {"en": "Key Concepts", "zh": "关键概念", "ja": "重要概念", "ko": "핵심 개념"},
    "implementation": {"en": "Implementation", "zh": "实现", "ja": "実装", "ko": "구현"},
    "how-it-runs": {"en": "Implementation", "zh": "实现", "ja": "実装", "ko": "구현"},
    "call-chains": {"en": "Call path", "zh": "调用链", "ja": "呼び出し", "ko": "호출 체인"},
    "how-a-call-runs": {"en": "Call path", "zh": "调用链", "ja": "呼び出し", "ko": "호출 체인"},
    "edge-cases": {"en": "Boundaries", "zh": "边界", "ja": "境界", "ko": "경계"},
    "failures": {"en": "Boundaries", "zh": "边界", "ja": "境界", "ko": "경계"},
    "source-evidence": {"en": "Source Evidence", "zh": "源码证据", "ja": "ソース根拠", "ko": "소스 근거"},
    "relationships": {"en": "Internal Relationships", "zh": "内部关系", "ja": "内部関係", "ko": "내부 관계"},
    "term-tips": {"en": "Terms", "zh": "术语", "ja": "用語", "ko": "용어"},
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

        overview = wiki_data.overview
        from repowiki.core.path_class import prefer_product_overview

        prefer_product_overview(overview, project, language=lang)
        overview_md = self._build_overview_page(
            overview,
            project,
            lang,
            architecture=wiki_data.architecture,
            topics=wiki_data.topics,
        )
        overview_title = structural_title("overview", lang)
        pages.append(WikiPage(id="index", title=overview_title, content=overview_md, order=0))

        gs_topic = next(
            (t for t in (wiki_data.topics or []) if t.section == "getting-started" or t.name == "getting-started"),
            None,
        )
        has_readme = any(
            (f.path or "").replace("\\", "/").lower() in {"readme.md", "readme"}
            for f in project.files
        )
        if gs_topic and (overview.setup_instructions or gs_topic.files or overview.description):
            gs_title = structural_title("quick-start", lang)
            gs_md = self._build_getting_started_page(
                overview, gs_topic, lang, topics=wiki_data.topics, project=project
            )
            pages.append(WikiPage(id="getting-started", title=gs_title, content=gs_md, order=1))
        elif overview.setup_instructions or overview.description or has_readme:
            gs_title = structural_title("quick-start", lang)
            gs_md = self._build_getting_started_page(
                overview, None, lang, topics=wiki_data.topics, project=project
            )
            pages.append(WikiPage(id="getting-started", title=gs_title, content=gs_md, order=1))

        arch = wiki_data.architecture
        if (
            arch.architecture_type
            or (arch.mermaid_component or "").strip()
            or (arch.description or "").strip()
            or arch.components
        ):
            arch_title = structural_title("architecture", lang)
            arch_md = self._build_architecture_page(
                arch, lang, topics=wiki_data.topics
            )
            pages.append(WikiPage(id="architecture", title=arch_title, content=arch_md, order=2))

        project_paths = [f.path for f in project.files]
        topic_docs = [
            t
            for t in (wiki_data.topics or [])
            if t.section != "getting-started"
            and t.name != "getting-started"
            and _keep_built_topic(t, project_paths)
        ]
        for i, topic in enumerate(topic_docs):
            page_id = f"topics/{topic.name}"
            title = topic.title or topic.name
            if "上下文装配" in (title or "") and "Agent Loop" in (title or ""):
                title = "Agent Loop"
            topic_md = self._build_module_page(
                topic, graph, display_title=title, language=lang
            )
            pages.append(
                WikiPage(
                    id=page_id,
                    title=title,
                    content=topic_md,
                    parent_id="topics",
                    order=20 + i,
                )
            )

        # Directory modules still exist as pages (按目录), not default nav.
        for i, mod in enumerate(wiki_data.modules):
            mod_id = f"modules/{mod.name}"
            mod_title = module_display_title(mod.name, lang)
            mod_md = self._build_module_page(mod, graph, display_title=mod_title, language=lang)
            pages.append(WikiPage(
                id=mod_id, title=mod_title, content=mod_md,
                parent_id="modules", order=200 + i,
            ))

        guide = wiki_data.reading_guide
        if guide.steps:
            guide_title = structural_title("reading-guide", lang)
            guide_md = self._build_reading_guide_page(guide, lang)
            pages.append(WikiPage(id="reading-guide", title=guide_title, content=guide_md, order=300))

        mermaid = graph.to_mermaid()
        if mermaid:
            dep_title = structural_title("dependencies", lang)
            dep_md = self._build_dependency_page(graph, mermaid, lang)
            pages.append(WikiPage(id="dependencies", title=dep_title, content=dep_md, order=301))

        sidebar = self._topic_sidebar(pages, wiki_data, language=lang, graph=graph)
        known_ids = {p.id for p in pages}
        for page in pages:
            page.content = upgrade_wiki_page_content(
                page.content, known_ids, language=lang, page_id=page.id
            )
        return Wiki(pages=pages, sidebar=sidebar, project_name=project.name)

    def _build_overview_page(
        self,
        overview,
        project,
        language: str = "en",
        architecture=None,
        topics=None,
    ) -> str:
        from repowiki.core.path_class import product_display_name

        name = product_display_name(overview, project)
        lines = [f"# {name}\n"]

        chip_lines = _related_source_chip_lines(
            getattr(overview, "citations", None), language
        )
        lines.extend(chip_lines)

        scope = (getattr(overview, "document_scope", "") or "").strip()
        if language == "zh" and scope:
            scope = scope.replace("您", "你")
        lede = scope or _overview_lede(name, overview.one_liner, language)
        lines.append(f"> {lede}\n")
        if (
            not scope
            and overview.one_liner
            and overview.one_liner.strip() not in lede
        ):
            lines.append(f"{overview.one_liner}\n")

        from repowiki.core.grounding import is_fragment_claim, is_inventory_focus
        from repowiki.core.topics import (
            is_weak_callpath_evidence_path,
            is_weak_entrypoint_path,
            text_cites_scaffold_evidence,
        )

        def _keep_what(raw: str) -> bool:
            text = str(raw or "").strip()
            if not text or is_fragment_claim(text) or text_cites_scaffold_evidence(text):
                return False
            match = re.search(r"(?:进程从|The process starts at)\s*`([^`]+)`", text, re.I)
            if match:
                path = match.group(1).strip().split()[0].split(":")[0]
                if is_weak_entrypoint_path(path):
                    return False
            if "接住链路上的一段工作" in text or "owns one stretch" in text.lower():
                for chip in re.finditer(r"`([^`]+)`", text):
                    path = chip.group(1).strip().split()[0].split(":")[0]
                    if is_weak_callpath_evidence_path(path):
                        return False
            return True

        from repowiki.core.topics import pin_overview_claim_cites

        what = _dedupe_claim_lines(
            pin_overview_claim_cites(
                [
                    rewrite_lecture_claim(str(s))
                    for s in (getattr(overview, "what_it_is", None) or [])
                    if _keep_what(rewrite_lecture_claim(str(s)))
                ],
                project,
            )
        )
        lines.append(f"## {structural_title('what-is', language)}\n")
        if what:
            for item in what:
                lines.append(f"- {item}")
            lines.append("")
        elif overview.description and not _looks_like_readme_dump(overview.description):
            lines.append(f"{overview.description}\n")
        else:
            lines.append(f"{lede}\n")

        mermaid = (getattr(overview, "mermaid_component", "") or "").strip()
        if not mermaid and architecture:
            mermaid = (getattr(architecture, "mermaid_component", "") or "").strip()
        flow = (getattr(overview, "runtime_flow", "") or "").strip()
        if flow and is_inventory_focus(flow):
            flow = ""
        arch_type = getattr(architecture, "architecture_type", "") if architecture else ""
        arch_title = structural_title("architecture", language)
        if mermaid or flow or arch_type:
            lines.append(f"## {structural_title('system-architecture', language)}\n")
            _append_mermaid(lines, mermaid)
            if flow:
                lines.append(f"{flow}\n")
            elif arch_type:
                if language == "zh":
                    lines.append(f"架构见图 [{arch_title}](architecture)。\n")
                else:
                    lines.append(f"Architecture: see [{arch_title}](architecture).\n")

        from repowiki.core.topics import fill_codebase_purposes

        structure = fill_codebase_purposes(
            list(getattr(overview, "codebase_structure", None) or []),
            project,
            language=language,
        )
        subsystems = list(getattr(overview, "subsystems", None) or [])
        if structure:
            lines.append(f"## {structural_title('codebase-split', language)}\n")
            lines.extend(_codebase_structure_table(structure, language))
        elif not what and not subsystems:
            filtered = filter_tech_stack(overview.tech_stack, project)
            if filtered:
                lines.append(f"## {structural_title('tech-stack', language)}\n")
                lines.extend(_tech_stack_table(filtered, language))

        if subsystems:
            lines.append(f"## {structural_title('core-subsystems', language)}\n")
            lines.extend(_render_subsystems(subsystems, language))

        _append_term_tips(lines, getattr(overview, "term_tips", None), language)

        handbook = bool(what or structure or subsystems)
        if not handbook and overview.key_features:
            lines.append(f"## {structural_title('key-features', language)}\n")
            for feat in overview.key_features:
                lines.append(f"- {feat}")
            lines.append("")

        if not handbook and overview.setup_instructions:
            lines.append(f"## {structural_title('setup', language)}\n")
            for i, step in enumerate(overview.setup_instructions, 1):
                lines.append(f"{i}. {step}")
            lines.append("")

        see_lines = _see_also_lines(
            getattr(overview, "see_also", None) or [],
            topics or [],
            language,
            known_ids=_planned_page_ids(topics),
        )
        if see_lines:
            lines.append(f"## {structural_title('see-also', language)}\n")
            lines.extend(see_lines)

        return "\n".join(lines)

    def _build_getting_started_page(
        self, overview, topic, language: str = "en", topics=None, project=None
    ) -> str:
        title = structural_title("quick-start", language)
        lines = [f"# {title}\n"]
        next_name = _first_deep_topic_title(topics)
        if language == "zh":
            follow = f"再进架构和{next_name}。" if next_name else "再进架构。"
            lines.append(f"> 按 README 和仓库根上的启动说明把项目跑起来，{follow}\n")
        else:
            follow = (
                f"then read architecture and {next_name}."
                if next_name
                else "then read architecture."
            )
            lines.append(
                "> Follow the README and root setup notes to run the project, "
                f"{follow}\n"
            )
        one = (getattr(overview, "one_liner", "") or "").strip()
        from repowiki.core.path_class import prose_treats_notes_as_product

        if one and not prose_treats_notes_as_product(one):
            lines.append(f"{one}\n")
        if language == "zh":
            lines.append(f"## {structural_title('what-is', language)}\n")
            lines.append(
                "从 README 的 npm / pnpm / 源码 / Web UI 启动步骤把项目跑起来，再进架构。"
                "细节以 `README.md` 为准。\n"
            )
        else:
            lines.append(f"## {structural_title('what-is', language)}\n")
            lines.append(
                "Follow the README (npm / pnpm / source / Web UI) until the process starts, then read architecture. "
                "Cite `README.md`; do not paste the README into this section.\n"
            )
        from repowiki.core.grounding import (
            is_inventory_focus,
            is_overview_instruction_focus,
        )
        from repowiki.core.topics import getting_started_call_path

        flow = getting_started_call_path(project, language=language) if project else ""
        leftover = (getattr(overview, "runtime_flow", "") or "").strip()
        if leftover and (
            is_inventory_focus(leftover) or is_overview_instruction_focus(leftover)
        ):
            leftover = ""
        if not flow:
            flow = leftover
        if flow:
            lines.append(f"## {structural_title('how-a-call-runs', language)}\n")
            lines.append(f"{flow}\n")
        if overview.setup_instructions:
            lines.append(f"## {structural_title('setup', language)}\n")
            for i, step in enumerate(overview.setup_instructions, 1):
                lines.append(f"{i}. {step}")
            lines.append("")
        if language == "zh":
            lines.append("## 跑起来之后\n")
        else:
            lines.append("## After it runs\n")
        lines.append(f"- [{structural_title('architecture', language)}](architecture)")
        next_topic = _first_deep_topic_link(topics)
        if next_topic:
            lines.append(next_topic)
        lines.append("")
        paths: list[str] = []
        if topic is not None:
            for item in getattr(topic, "files", None) or []:
                path = getattr(item, "path", None) or (item if isinstance(item, str) else "")
                if path:
                    paths.append(path)
        if not paths:
            paths = ["README.md"]
        lines.append(f"## {structural_title('related-source', language)}\n")
        for path in paths[:8]:
            lines.append(f"- `{path}`")
        lines.append("")
        return "\n".join(lines)

    def _build_architecture_page(self, arch, language: str = "en", topics=None) -> str:
        title = structural_title("architecture", language)
        lines = [f"# {title}\n"]
        if language == "zh":
            kind = ""
            if arch.architecture_type and arch.architecture_type.lower() not in {
                "cli-tool",
                "library",
            }:
                kind = f"（{arch.architecture_type}）"
            lines.append(
                f"> 系统按一次真实调用串起来{kind}。各部分按链路上的角色说明，不按目录。\n"
            )
        else:
            kind = ""
            if arch.architecture_type and arch.architecture_type.lower() not in {
                "cli-tool",
                "library",
            }:
                kind = f" ({arch.architecture_type})"
            lines.append(
                f"> The system is wired along one real call{kind}. "
                "Parts are described as roles on that path, not as a folder tree.\n"
            )

        lines.extend(
            _related_source_chip_lines(getattr(arch, "citations", None), language)
        )

        mermaid = (arch.mermaid_component or "").strip()
        sequence = (getattr(arch, "mermaid_sequence", "") or "").strip()
        if mermaid or sequence or arch.description or arch.data_flow:
            lines.append(f"## {structural_title('system-architecture', language)}\n")
            _append_mermaid(lines, mermaid)
            _append_mermaid(lines, sequence)
            if arch.description:
                lines.append(f"{arch.description}\n")
            if arch.data_flow:
                lines.append(f"{arch.data_flow}\n")

        if arch.components:
            heading = (
                "core-subsystems"
                if any(getattr(c, "key_types", None) for c in arch.components)
                else "components"
            )
            lines.append(f"## {structural_title(heading, language)}\n")
            for c in arch.components:
                from repowiki.core.grounding import rewrite_lecture_claim

                role = rewrite_lecture_claim(
                    (getattr(c, "role", "") or "").strip() or (c.purpose or "").strip()
                )
                purpose = f" — {role}" if role else ""
                files = ""
                if c.files:
                    cites = ", ".join(f"`{f}`" for f in c.files[:3])
                    files = f"；证据：{cites}" if language == "zh" else f"; evidence: {cites}"
                lines.append(f"- **{c.name}**{purpose}{files}")
                for kt in getattr(c, "key_types", None) or []:
                    line = _key_type_line(kt)
                    if line:
                        lines.append(line)
            lines.append("")

        _append_term_tips(lines, getattr(arch, "term_tips", None), language)

        see_lines = _see_also_lines(
            [],
            topics or [],
            language,
            known_ids=_planned_page_ids(topics) - {"architecture"},
        )
        if see_lines:
            lines.append(f"## {structural_title('see-also', language)}\n")
            lines.extend(see_lines)

        return "\n".join(lines)

    def _build_module_sidebar(self, names: list[str], language: str = "en") -> SidebarItem:
        """Nest module entries by path so siblings sit under a shared parent.

        Module names are full repository paths; listed flat they are both wide
        and repetitive. The tree also gives a home to intermediate directories
        like ``src/`` that hold no files of their own and so have no page.
        Path segments stay as in the repo; only the group label and ``root``
        are localized.
        """
        root = SidebarItem(title=structural_title("by-directory", language), page_id="", children=[])
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

        for name in names:
            if is_directory_nav_noise(name):
                continue
            ensure(name).page_id = f"modules/{name}"
        return root

    def _topic_sidebar(
        self,
        pages: list[WikiPage],
        wiki_data: WikiData,
        language: str = "en",
        graph: DependencyGraph | None = None,
    ) -> list[SidebarItem]:
        """入门指南 / 深入探索 as the default nav; directory modules last."""
        lang = normalize_wiki_lang(language)
        page_ids = {p.id for p in pages}
        getting: list[SidebarItem] = []
        if "index" in page_ids:
            getting.append(
                SidebarItem(title=structural_title("overview", lang), page_id="index")
            )
        if "getting-started" in page_ids:
            getting.append(
                SidebarItem(
                    title=structural_title("quick-start", lang),
                    page_id="getting-started",
                )
            )
        if "reading-guide" in page_ids:
            getting.append(
                SidebarItem(
                    title=structural_title("reading-guide", lang),
                    page_id="reading-guide",
                )
            )
        deep: list[SidebarItem] = []
        if "architecture" in page_ids:
            deep.append(
                SidebarItem(
                    title=structural_title("architecture", lang),
                    page_id="architecture",
                )
            )
        for topic in wiki_data.topics or []:
            if topic.section == "getting-started" or topic.name == "getting-started":
                continue
            pid = f"topics/{topic.name}"
            if pid not in page_ids:
                continue
            if is_generic_web_slug(topic.name) and not keep_generic_web_topic_nav(
                pid, next((p.content for p in pages if p.id == pid), "")
            ):
                continue
            deep.append(SidebarItem(title=topic.title or topic.name, page_id=pid))
        items: list[SidebarItem] = []
        if getting:
            items.append(
                SidebarItem(
                    title=structural_title("getting-started", lang),
                    page_id="",
                    children=getting,
                )
            )
        if deep:
            items.append(
                SidebarItem(
                    title=structural_title("deep-dive", lang),
                    page_id="",
                    children=deep,
                )
            )
        module_names = [m.name for m in wiki_data.modules if f"modules/{m.name}" in page_ids]
        module_names = [n for n in module_names if not is_directory_nav_noise(n)]
        if module_names:
            blob = _importance_blob_from_pages(pages)
            ranks = _module_pagerank_scores(graph)
            module_names.sort(key=lambda n: _module_dir_sort_key(n, blob, ranks))
            items.append(self._build_module_sidebar(module_names, language=lang))
        return rank_and_cap_directory_sidebar(items, pages=pages, graph=graph)

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
        scope = (getattr(mod, "document_scope", "") or "").strip()
        lede = scope or (mod.purpose or "")
        if lede:
            lines.append(f"> {lede}\n")

        chip_lines = _related_source_chip_lines(getattr(mod, "citations", None), language)
        lines.extend(chip_lines)

        what = [s for s in (getattr(mod, "what_it_is", None) or []) if str(s).strip()]
        if what:
            lines.append(f"## {structural_title('what-is', language)}\n")
            for item in what:
                lines.append(f"- {item}")
            lines.append("")
        elif mod.description:
            lines.append(f"{mod.description}\n")

        _append_term_tips(lines, getattr(mod, "term_tips", None), language)

        chains = list(getattr(mod, "call_chains", None) or [])
        implementation = (getattr(mod, "implementation_details", "") or "").strip()
        walkthrough = _walkthrough_blob(mod)
        own_mermaid = (getattr(mod, "mermaid", "") or "").strip()

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
                    _append_mermaid(lines, diagram)
            if own_mermaid and not any(mermaid_from_call_chain(c) for c in chains):
                _append_mermaid(lines, own_mermaid)
        elif own_mermaid:
            lines.append(f"## {structural_title('how-a-call-runs', language)}\n")
            _append_mermaid(lines, own_mermaid)

        key_types = list(getattr(mod, "key_types", None) or [])
        type_lines = [line for kt in key_types if (line := _key_type_line(kt))]
        if type_lines:
            lines.append(f"## {structural_title('key-types', language)}\n")
            lines.extend(type_lines)
            lines.append("")

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

        if getattr(mod, "title", "") and getattr(mod, "section", "") not in {
            "",
            "getting-started",
        }:
            lines.append(f"## {structural_title('see-also', language)}\n")
            lines.append(
                f"- [{structural_title('overview', language)}](index)"
            )
            lines.append(
                f"- [{structural_title('architecture', language)}](architecture)"
            )
            lines.append("")

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


def _append_mermaid(lines: list[str], mermaid: str, *, max_lines: int = 40) -> None:
    text = normalize_mermaid_source(mermaid)
    if not text:
        return
    if text.count("\n") > max_lines:
        return
    lines.append("```mermaid")
    lines.append(text)
    lines.append("```\n")


def _key_type_line(kt) -> str:
    """Type — 职责 — `` `path:line Symbol` ``. Drop dummy lib.rs / folder symbols."""
    from repowiki.core.topics import is_weak_callpath_evidence_path

    name = (getattr(kt, "name", "") or "").strip()
    role = (getattr(kt, "role", "") or "").strip()
    path = (getattr(kt, "path", "") or "").strip()
    line = int(getattr(kt, "line", 0) or 0)
    if not path:
        return ""
    file_path, path_line = _split_path_line(path)
    if not file_path or is_weak_callpath_evidence_path(file_path):
        return ""
    loc_line = path_line or (str(line) if line else "")
    loc = f"{file_path}:{loc_line}" if loc_line else file_path
    symbol = "" if is_dummy_symbol(name) else name
    pill = f"`{loc} {symbol}`" if symbol else f"`{loc}`"
    if symbol and role:
        return f"- {symbol} — {role} — {pill}"
    if role:
        return f"- {pill} — {role}"
    if symbol:
        return f"- {symbol} — {pill}"
    return f"- {pill}"


_DUMMY_SYMBOL_RE = re.compile(
    r"^(lib\.rs|main\.rs|mod\.rs|index\.\w+|src|crates|packages|apps|root)$",
    re.I,
)


def is_dummy_symbol(name: str) -> bool:
    n = (name or "").strip().strip("`")
    if not n:
        return True
    if "/" in n or "\\" in n:
        return True
    if n.endswith((".rs", ".py", ".ts", ".js", ".go", ".toml", ".md")):
        return True
    return bool(_DUMMY_SYMBOL_RE.match(n))


def _split_path_line(path: str) -> tuple[str, str]:
    raw = (path or "").strip().strip("`").split()[0] if (path or "").strip() else ""
    match = re.match(r"^(.+?):(\d+)(?:-\d+)?$", raw)
    if match:
        return match.group(1), match.group(2)
    return raw, ""


def localize_split_table_markdown(content: str, *, language: str = "zh") -> str:
    """GET: rewrite 职责 cells that are `English |` or pasted package.json English."""
    if language != "zh" or not content or "代码如何拆分" not in content:
        return content
    from repowiki.core.topics import (
        is_english_pack_purpose,
        purpose_for_pack,
        should_rewrite_pack_purpose,
    )

    parts = re.split(r"(?m)(?=^## )", content)
    out: list[str] = []
    for part in parts:
        first, _, _rest = part.partition("\n")
        if not re.match(r"^##\s*代码如何拆分\s*$", first):
            out.append(part)
            continue
        rows = []
        for line in part.splitlines():
            if not line.startswith("|") or set(line.replace("|", "").strip()) <= {"-", " "}:
                rows.append(line)
                continue
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) < 3 or cells[0] in {"名称", "Name"}:
                rows.append(line)
                continue
            name, loc, purpose = cells[0], cells[1], " | ".join(cells[2:])
            purpose = purpose.replace("\\|", "|")
            if should_rewrite_pack_purpose(purpose, language="zh") or is_english_pack_purpose(purpose):
                purpose = purpose_for_pack(name, loc, None, language="zh")
            rows.append(
                "| "
                + " | ".join(
                    [
                        name.replace("|", "\\|"),
                        loc.replace("|", "\\|"),
                        purpose.replace("|", "\\|"),
                    ]
                )
                + " |"
            )
        out.append("\n".join(rows) + ("\n" if part.endswith("\n") else ""))
    return "".join(out)


def replace_subgraph_overview_mermaid(content: str, *, page_id: str = "") -> str:
    """GET: swap a packages/client-only overview diagram for the call-path stages."""
    if page_id not in {"index", "architecture", ""} or "```mermaid" not in (content or ""):
        return content
    from repowiki.core.topics import mermaid_is_local_package_subgraph

    fence = _MERMAID_FENCE_RE.search(content)
    if not fence or not mermaid_is_local_package_subgraph(fence.group(1)):
        return content
    stages: list[str] = []
    for token, label in (
        ("apps/cli", "CLI"),
        ("apps/dsh", "CLI"),
        ("packages/bundle", "Bundle"),
        ("packages/boot", "Boot/Cordis"),
        ("vendor/cordis", "Boot/Cordis"),
        ("packages/acp", "ACP"),
        ("packages/api", "API"),
        ("packages/client", "Client"),
        ("apps/web", "Web"),
    ):
        if token in content and label not in stages:
            stages.append(label)
    if len(stages) < 2:
        stages = ["CLI", "Bundle", "Boot/Cordis", "ACP", "API", "Client", "Web"]
    lines = ["flowchart LR"]
    ids = [f"s{i}" for i in range(len(stages))]
    for nid, lab in zip(ids, stages, strict=True):
        lines.append(f'  {nid}["{lab}"]')
    for src, dst in zip(ids, ids[1:], strict=False):
        lines.append(f"  {src} --> {dst}")
    diagram = "\n".join(lines)
    return content[: fence.start()] + f"```mermaid\n{diagram}\n```" + content[fence.end() :]


def upgrade_term_tip_markdown(content: str, *, language: str = "zh") -> str:
    """GET: fill or drop hollow「如 、」/「把 / 接上」term glosses."""
    if not content:
        return content
    from repowiki.core.grounding import repair_term_tip_markdown

    return repair_term_tip_markdown(content, language=language)


def _codebase_structure_table(rows, language: str = "en") -> list[str]:
    if language == "zh":
        headers = ["名称", "位置", "职责"]
    else:
        headers = ["Name", "Location", "Purpose"]
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        name = str(getattr(row, "name", "") or "").replace("|", "\\|")
        loc = str(getattr(row, "location", "") or "").replace("|", "\\|")
        purpose = str(getattr(row, "purpose", "") or "").replace("|", "\\|")
        lines.append(f"| {name} | {loc or '—'} | {purpose or '—'} |")
    lines.append("")
    return lines


def _render_subsystems(subsystems, language: str = "en") -> list[str]:
    lines: list[str] = []
    for sub in subsystems:
        name = _subsystem_display_name(getattr(sub, "name", "") or "")
        from repowiki.core.grounding import rewrite_lecture_claim

        role = rewrite_lecture_claim((getattr(sub, "role", "") or "").strip())
        types = list(getattr(sub, "key_types", None) or [])
        type_lines = [line for kt in types if (line := _key_type_line(kt))]
        mermaid = (getattr(sub, "mermaid", "") or "").strip()
        if not type_lines:
            continue
        lines.append(f"### {name}\n")
        if role:
            lines.append(f"{role}\n")
        _append_mermaid(lines, mermaid, max_lines=20)
        lines.extend(type_lines)
        lines.append("")
    return lines


def _subsystem_display_name(name: str) -> str:
    text = (name or "").strip()
    if "上下文装配" in text or "context assembly" in text.lower():
        if "Agent Loop" in text or text.lower().startswith("agent loop"):
            return "Agent Loop"
    return text


def _planned_page_ids(topics) -> set[str]:
    ids = {"index", "architecture", "getting-started", "reading-guide", "dependencies"}
    for topic in topics or []:
        tid = getattr(topic, "name", "") or getattr(topic, "id", "") or ""
        section = getattr(topic, "section", "") or ""
        if not tid or section == "getting-started" or tid == "getting-started":
            continue
        ids.add(f"topics/{tid}")
    return ids


def _keep_built_topic(topic, project_paths: list[str]) -> bool:
    from repowiki.core.path_class import (
        name_is_notes_product,
        repo_is_notes_primary,
        topic_paths_are_agent_memory,
    )

    slug = getattr(topic, "name", "") or ""
    title = getattr(topic, "title", "") or ""
    files = getattr(topic, "files", None) or []
    paths = [
        getattr(item, "path", None) or (item if isinstance(item, str) else "")
        for item in files
    ]
    paths = [p for p in paths if p]
    if not repo_is_notes_primary(project_paths) and (
        topic_paths_are_agent_memory(paths) or name_is_notes_product(title or slug)
    ):
        return False
    if not is_generic_web_slug(slug):
        return True
    return repo_has_web_system(project_paths, slug)


_MD_WIKI_LINK = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_DROP = "\0DROP\0"

# Hallucinated topic ids from earlier scans → real grok-study / zread ids.
_TOPIC_LINK_ALIASES: dict[str, tuple[str, ...]] = {
    "context-assembly": ("agent-loop",),
    "code-graph": ("codebase-graph", "codegen"),
    "pty-control": ("tui-pager", "terminal-ui", "pty-control"),
}


def _normalize_wiki_href(href: str) -> str:
    page_id = (href or "").split()[0].strip("<>").strip()
    if page_id.startswith("./"):
        page_id = page_id[2:]
    return page_id.rstrip("/")


def _rewrite_wiki_href(page_id: str, known_ids: set[str]) -> str | None:
    if page_id in known_ids:
        return page_id
    slug = page_id.split("/", 1)[-1] if page_id.startswith("topics/") else page_id
    for cand in _TOPIC_LINK_ALIASES.get(slug, ()):
        href = cand if cand in known_ids else f"topics/{cand}"
        if href in known_ids:
            return href
    return None


def filter_unknown_wiki_links(text: str, known_ids: set[str]) -> str:
    """Rewrite or drop markdown hrefs that are not planned wiki page ids."""
    if not text or not known_ids:
        return text

    def repl(match: re.Match[str]) -> str:
        label, href = match.group(1), (match.group(2) or "").strip()
        page_id = _normalize_wiki_href(href)
        if not page_id or page_id.startswith(("#", "http://", "https://", "mailto:")):
            return match.group(0)
        rewritten = _rewrite_wiki_href(page_id, known_ids)
        if rewritten:
            if rewritten == page_id:
                return match.group(0)
            return f"[{label}]({rewritten})"
        return _DROP

    text = _MD_WIKI_LINK.sub(repl, text)
    text = re.sub(r"(?m)^[ \t]*[-*][ \t]+\0DROP\0[ \t]*\n?", "", text)
    return text.replace(_DROP, "")


_LECTURE_CLAUSE_RE = re.compile(
    r"(?:阅读之后?[，,]?\s*[您你]?应?该?能|读完本页[，,]?你要能|读完[，,]?\s*[您你]?应?该?能)[^。\n]*。?"
)
_AFTER_READING_RE = re.compile(
    r"After (?:reading|this page) you should(?: be able to)? [^.?\n]+[.?]?",
    re.I,
)
_DOC_COVERS_PREFIX_RE = re.compile(r"这篇文档讲\s*")
_HANDBOOK_HEADING_REMAP = {
    "它是什么": "概述",
    "What it is": "Overview",
    "What is this": "Overview",
    "它在系统里的位置": "架构",
    "Where it sits": "Architecture",
    "一次调用怎么走": "调用链",
    "How a call runs": "Call path",
    "关键调用链": "调用链",
    "Key Call Chains": "Call path",
    "术语小贴士": "术语",
    "Term tips": "Terms",
    "关键类型在链路上的职责": "关键类型",
    "Key types and their roles": "Key types",
    "边界条件": "边界",
    "Boundary conditions": "Boundaries",
    "失败与边界": "边界",
    "Failures and edges": "Boundaries",
    "Edge Cases": "Boundaries",
    "这条链路怎么转": "实现",
    "How it actually runs": "Implementation",
    "实现要点": "实现",
    "Implementation details": "Implementation",
    "实现细节": "实现",
}


def upgrade_handbook_section_headings(content: str) -> str:
    """Map leftover workbook headings to handbook names (概述 / 架构 / 关键类型 / 边界)."""
    if not content or "## " not in content:
        return content

    def repl(match: re.Match[str]) -> str:
        title = match.group(1).strip()
        mapped = _HANDBOOK_HEADING_REMAP.get(title)
        return f"## {mapped}" if mapped else match.group(0)

    return re.sub(r"(?m)^## (.+?)\s*$", repl, content)


def rewrite_lecture_claim(text: str) -> str:
    from repowiki.core.grounding import rewrite_lecture_claim as _rewrite

    return _rewrite(text)


def upgrade_zh_handbook_voice(content: str) -> str:
    """Strip lecture clauses; keep 你 not 您. Do not rewrite into 读完应能."""
    if not content:
        return content
    from repowiki.core.grounding import rewrite_lecture_prose

    content = _LECTURE_CLAUSE_RE.sub("", content)
    content = _AFTER_READING_RE.sub("", content)
    content = _DOC_COVERS_PREFIX_RE.sub("", content)
    content = rewrite_lecture_prose(content)
    content = re.sub(r"[ \t]{2,}", " ", content)
    content = re.sub(r"。{2,}", "。", content)
    return content.replace("您", "你")


_PATHLESS_TYPE_BULLET_RE = re.compile(
    r"(?m)^[ \t]*[-*][ \t]+`([A-Za-z_][A-Za-z0-9_]*)`"
    r"(?:\s*[—–−-]\s+(?!`)[^\n`]*)?\s*$"
)


def strip_pathless_type_bullets(content: str) -> str:
    """Drop 核心子系统 bullets that are a Type name with no `path`."""
    if not content or "`" not in content:
        return content
    return _PATHLESS_TYPE_BULLET_RE.sub("", content)


def upgrade_codegraph_heading(content: str) -> str:
    """Overview 代码生成 that cites a code-graph crate → 代码图谱."""
    if not content or "代码生成" not in content:
        return content
    if not re.search(r"code-graph|codebase-graph|codegraph", content, re.I):
        return content
    chunks = re.split(r"(?m)(?=^#{2,3} )", content)
    out: list[str] = []
    for chunk in chunks:
        first, _, _rest = chunk.partition("\n")
        if re.match(r"^#{2,3} 代码生成\s*$", first) and re.search(
            r"code-graph|codebase-graph|codegraph", chunk, re.I
        ):
            chunk = re.sub(r"^#{2,3} 代码生成", lambda m: m.group(0).replace("代码生成", "代码图谱"), chunk, count=1)
        out.append(chunk)
    return "".join(out)


def upgrade_wiki_page_content(
    content: str,
    known_ids: set[str],
    *,
    language: str = "zh",
    page_id: str = "",
) -> str:
    """GET/build pass: chips, dead links, 您, pathless types, 代码图谱."""
    if not content:
        return content
    content = upgrade_source_chip_markdown(content)
    content = upgrade_key_type_chip_markdown(content)
    content = fill_key_type_chip_lines(content)
    content = upgrade_mermaid_fences(content)
    content = thicken_subsystem_diagrams(content)
    content = replace_subgraph_overview_mermaid(content, page_id=page_id)
    content = shorten_mermaid_node_labels(content)
    content = strip_reading_wiki_homework(content, page_id=page_id)
    content = upgrade_architecture_loop_wording(content)
    content = filter_unknown_wiki_links(content, known_ids)
    if language == "zh" or "您" in content or "阅读后" in content or "读完" in content:
        content = upgrade_zh_handbook_voice(content)
    content = localize_split_table_markdown(content, language=language)
    content = upgrade_term_tip_markdown(content, language=language)
    content = upgrade_handbook_section_headings(content)
    content = strip_pathless_type_bullets(content)
    content = upgrade_codegraph_heading(content)
    if page_id == "getting-started":
        content = thicken_getting_started(content, known_ids, language=language)
    content = rewrite_start_claim_helper_symbols(content)
    return content


def rewrite_start_claim_helper_symbols(content: str) -> str:
    """Drop helper exports (readVersion) from 进程从 `path:line Symbol` chips."""
    if not content:
        return content
    from repowiki.core.topics import is_entry_chip_symbol

    def repl(match: re.Match[str]) -> str:
        prefix, inner = match.group(1), match.group(2)
        bits = inner.strip().split()
        if len(bits) < 2:
            return match.group(0)
        path, symbol = bits[0], bits[1]
        if is_entry_chip_symbol(symbol):
            return match.group(0)
        loc = path.split(":")[0]
        return f"{prefix}`{loc}`"

    return re.sub(
        r"(?i)((?:进程从|The process starts at)\s*)`([^`]+)`",
        repl,
        content,
    )


def _see_also_lines(
    see_also,
    topics,
    language: str = "en",
    *,
    known_ids: set[str] | None = None,
) -> list[str]:
    titles = {
        (getattr(t, "name", "") or getattr(t, "id", "") or ""): (
            getattr(t, "title", "") or getattr(t, "name", "") or getattr(t, "id", "")
        )
        for t in topics or []
    }
    planned = known_ids if known_ids is not None else _planned_page_ids(topics)
    arch_title = structural_title("architecture", language)
    items: list[str] = []
    seen: set[str] = set()
    raw = list(see_also or [])
    if not raw and topics:
        raw = ["architecture"]
        for t in topics:
            if getattr(t, "section", "") == "getting-started":
                continue
            tid = getattr(t, "name", "") or getattr(t, "id", "") or ""
            if tid:
                raw.append(f"topics/{tid}")
    for item in raw:
        text = str(item or "").strip()
        if not text:
            continue
        href = ""
        label = text
        md = _MD_WIKI_LINK.search(text)
        if md:
            label, href = md.group(1), md.group(2).split()[0].strip("<>")
        elif text in {"architecture", "架构概览"}:
            href, label = "architecture", arch_title
        elif text in {"index", "overview", "概述"}:
            href, label = "index", structural_title("overview", language)
        elif text.startswith("topics/"):
            href = text.split()[0]
            tid = href.split("/", 1)[-1]
            label = titles.get(tid) or tid
        elif text in planned:
            href = text
        elif f"topics/{text}" in planned:
            href = f"topics/{text}"
            label = titles.get(text) or text
        if not href or href not in planned or href in seen:
            continue
        seen.add(href)
        items.append(f"- [{label}]({href})")
    return items + ([""] if items else [])


def _append_term_tips(lines: list[str], tips, language: str = "en") -> None:
    from repowiki.core.grounding import fill_hollow_term_tip, is_hollow_tip

    items = []
    for tip in tips or []:
        term = getattr(tip, "term", "") or ""
        if not term:
            continue
        text = fill_hollow_term_tip(
            term, getattr(tip, "tip", "") or "", language=language
        )
        if not text or is_hollow_tip(text):
            continue
        items.append((term, text))
    if not items:
        return
    lines.append(f"## {structural_title('term-tips', language)}\n")
    for term, text in items:
        lines.append(f"> **{term}** — {text}")
    lines.append("")


def _append_citations(lines: list[str], citations, language: str = "en") -> None:
    if not citations:
        return

    lines.append(f"## {structural_title('source-evidence', language)}\n")
    for cite in citations:
        loc = format_citation(cite)
        symbol = (getattr(cite, "symbol", "") or "").strip()
        if is_dummy_symbol(symbol):
            symbol = ""
        pill = f"{loc} {symbol}".strip() if symbol else loc
        note = (getattr(cite, "note", "") or "").strip()
        if note:
            lines.append(f"- `{pill}` — {note}")
        else:
            lines.append(f"- `{pill}`")
    lines.append("")


def _related_source_chip_lines(citations, language: str = "en") -> list[str]:
    items = list(citations or [])
    if not items:
        return []
    chips: list[str] = []
    for cite in items[:8]:
        loc = format_citation(cite)
        symbol = (getattr(cite, "symbol", "") or "").strip()
        if is_dummy_symbol(symbol):
            symbol = ""
        pill = f"{loc} {symbol}".strip() if symbol else loc
        chips.append(f"`{pill}`")
    label = structural_title("related-source", language)
    return [f"**{label}:** " + " ".join(chips), ""]


_CHIP_HEADING_RE = re.compile(
    r"(?m)^([ \t]*\*\*(?:相关源码|Related source):\*\*[ \t]*)(.*)$"
)
# Symbol may be `mod channel` (spaces). Use [ \t] never \s so the match cannot
# swallow the next list line.
_CHIP_ITEM_RE = re.compile(
    r"`([^`]+)`(?:[ \t]*[—–−-][ \t]*"
    r"`([A-Za-z_][A-Za-z0-9_]*(?:[ \t]+[A-Za-z_][A-Za-z0-9_]*)*)`)?"
)
_EVIDENCE_SPLIT_RE = re.compile(
    r"(?m)^([ \t]*[-*][ \t]*)`([^`]+)`[ \t]*[—–−-][ \t]*"
    r"`([A-Za-z_][A-Za-z0-9_]*(?:[ \t]+[A-Za-z_][A-Za-z0-9_]*)*)`"
    r"([ \t]*[—–−-][ \t]*[^\n]*)?[ \t]*$"
)


def upgrade_source_chip_markdown(content: str) -> str:
    """Rewrite persisted `` `path` — `Sym` `` chips into `` `path Sym` `` pills.

    Covers ``**相关源码:**`` rows and 源码证据 list items
    (`` `path:line` — `Symbol` — comment ``). Applied on wiki GET so a
    refresh fixes grok-study without a re-scan.
    """
    if not content:
        return content

    def heading_repl(match: re.Match[str]) -> str:
        prefix, rest = match.group(1), match.group(2)
        pills: list[str] = []
        for item in _CHIP_ITEM_RE.finditer(rest):
            path = (item.group(1) or "").strip()
            symbol = (item.group(2) or "").strip()
            if not path:
                continue
            if is_dummy_symbol(symbol):
                symbol = ""
            pills.append(f"`{path} {symbol}`" if symbol else f"`{path}`")
        if not pills:
            return match.group(0)
        return prefix + " ".join(pills)

    def evidence_repl(match: re.Match[str]) -> str:
        prefix, path, symbol, note = match.group(1), match.group(2), match.group(3), match.group(4)
        path = (path or "").strip()
        symbol = (symbol or "").strip()
        if is_dummy_symbol(symbol):
            symbol = ""
        pill = f"`{path} {symbol}`" if symbol else f"`{path}`"
        tail = (note or "").rstrip()
        return f"{prefix}{pill}{tail}"

    content = _CHIP_HEADING_RE.sub(heading_repl, content)
    return _EVIDENCE_SPLIT_RE.sub(evidence_repl, content)


# `` `Type` — duty — `path` `` (关键类型 / 核心子系统). Symbol may have spaces.
_KEY_TYPE_TRIPLE_RE = re.compile(
    r"(?m)^([ \t]*[-*][ \t]*)`([^`]+)`"
    r"[ \t]*[—–−-][ \t]*([^\n`]+?)[ \t]*[—–−-][ \t]*`([^`]+)`[ \t]*$"
)


def upgrade_key_type_chip_markdown(content: str) -> str:
    """Rewrite `` `Type` — duty — `path` `` into Type — duty — `` `path Symbol` ``."""
    if not content or "`" not in content:
        return content

    def repl(match: re.Match[str]) -> str:
        prefix, symbol, role, path = match.group(1), match.group(2), match.group(3), match.group(4)
        symbol = (symbol or "").strip()
        role = (role or "").strip()
        path = (path or "").strip()
        if is_dummy_symbol(symbol):
            return ""
        if "/" in symbol:
            return match.group(0)
        loc, line = _split_path_line(path)
        loc = loc or path
        chip_loc = f"{loc}:{line}" if line else loc
        pill = f"`{chip_loc} {symbol}`" if symbol else f"`{chip_loc}`"
        if role:
            return f"{prefix}{symbol} — {role} — {pill}"
        return f"{prefix}{pill}"

    return _KEY_TYPE_TRIPLE_RE.sub(repl, content)


_FILE_PILL_RE = re.compile(
    r"^([A-Za-z0-9_./\-]+?\.[A-Za-z0-9]+)(?::(\d+)(?:-\d+)?)?(?:[ \t]+(.+))?$"
)
_KEY_TYPE_HEADING_RE = re.compile(
    r"(?im)^#{2,3}[ \t]+(关键类型|核心子系统|Key types|Core subsystems)\b"
)
_READING_HOMEWORK_HEADINGS = {
    "本步要你干什么",
    "What this step asks of you",
    "过关",
    "Pass",
    "自测",
    "Self-check",
    "可练习概念",
    "Practice concept",
    "Practice concepts",
}
_MERMAID_FENCE_RE = re.compile(r"(?ms)^```mermaid\n(.*?)```")
_MERMAID_NODE_RE = re.compile(
    r'(?P<pre>\b[A-Za-z][\w-]*\s*)(?P<open>\[(?:")?)(?P<label>[^\]"\n]+)(?P<close>"?\])'
)
_INCOMPLETE_TRAIL_RE = re.compile(r"(然后|后将|并把|并将|为|把|从)$")
_MERMAID_TRAIL_JUNK = re.compile(
    r"(?:、-|、$|--$|-$|（[A-Za-z0-9_./-]+$|\([A-Za-z0-9_./-]+$)"
)
_MERMAID_TYPE_RE = re.compile(
    r"^(?:flowchart|graph|sequenceDiagram|classDiagram|stateDiagram(?:-v2)?|"
    r"erDiagram|gantt|pie|gitGraph|mindmap|timeline)\b",
    re.I,
)
_UNICODE_ARROW_RE = re.compile(r"[→⟶⇒➔➜➝➞⟹]")


def _parse_file_pill(inner: str) -> tuple[str, str, str]:
    """Return (path, line, symbol) from a chip pill body."""
    text = (inner or "").strip()
    match = _FILE_PILL_RE.match(text)
    if not match:
        return "", "", ""
    return (
        (match.group(1) or "").strip(),
        (match.group(2) or "").strip(),
        (match.group(3) or "").strip(),
    )


def _collect_pill_lines(content: str) -> dict[tuple[str, str], str]:
    """Map (path, symbol) and (path, '') to a cited line number on this page."""
    known: dict[tuple[str, str], str] = {}
    for match in re.finditer(r"`([^`]+)`", content or ""):
        path, line, symbol = _parse_file_pill(match.group(1))
        if not path or not line:
            continue
        known.setdefault((path, symbol), line)
        known.setdefault((path, ""), line)
    return known


def fill_key_type_chip_lines(content: str) -> str:
    """GET: add `:line` to 关键类型 `` `path Symbol` `` pills when the page already cites it.

    Does not invent `:1` unless that line is already cited for the same symbol.
    """
    if not content or "`" not in content:
        return content
    known = _collect_pill_lines(content)
    if not known:
        return content

    def rewrite_section(section: str) -> str:
        def pill_repl(match: re.Match[str]) -> str:
            inner = match.group(1)
            path, line, symbol = _parse_file_pill(inner)
            if not path or line or not symbol:
                return match.group(0)
            found = known.get((path, symbol))
            if not found:
                found = known.get((path, ""))
                if found == "1":
                    found = ""
            if not found:
                return match.group(0)
            return f"`{path}:{found} {symbol}`"

        return re.sub(r"`([^`]+)`", pill_repl, section)

    parts = re.split(r"(?m)(?=^## )", content)
    out: list[str] = []
    for part in parts:
        first, _, _rest = part.partition("\n")
        if _KEY_TYPE_HEADING_RE.match(first):
            out.append(rewrite_section(part))
        else:
            out.append(part)
    return "".join(out)


def _mostly_cjk(text: str) -> bool:
    if not text:
        return False
    cjk = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
    return cjk * 2 >= len(text)


def _strip_incomplete_mermaid_trail(text: str) -> str:
    cleaned = (text or "").strip()
    cleaned = _MERMAID_TRAIL_JUNK.sub("", cleaned).rstrip()
    while cleaned and _INCOMPLETE_TRAIL_RE.search(cleaned):
        cleaned = _INCOMPLETE_TRAIL_RE.sub("", cleaned).rstrip()
    if cleaned.count("（") > cleaned.count("）"):
        cleaned = cleaned.rsplit("（", 1)[0].rstrip()
    if cleaned.count("(") > cleaned.count(")"):
        cleaned = cleaned.rsplit("(", 1)[0].rstrip()
    return cleaned.rstrip("、，,;:（(-")


def normalize_mermaid_source(code: str) -> str:
    """Make a mermaid fence body parseable: ASCII arrows + a diagram type.

    Bare ``A --> B`` / ``A → B`` has no type; Mermaid then fails with
    ``No diagram type detected``. Wrap those as ``flowchart LR`` unless the
    first real line is already a known type keyword.
    """
    text = (code or "").replace("\r\n", "\n").strip()
    if not text:
        return text
    text = _UNICODE_ARROW_RE.sub("-->", text)
    first_real = ""
    for line in text.split("\n"):
        stripped = line.strip()
        if not stripped or stripped.startswith("%%"):
            continue
        first_real = stripped
        break
    if first_real and _MERMAID_TYPE_RE.match(first_real):
        return text
    return f"flowchart LR\n{text}"


def upgrade_mermaid_fences(content: str) -> str:
    """GET: rewrite typeless ```mermaid fences so persisted overview diagrams render."""
    if not content or "```mermaid" not in content:
        return content

    def fence_repl(match: re.Match[str]) -> str:
        body = normalize_mermaid_source(match.group(1))
        if not body:
            return match.group(0)
        return f"```mermaid\n{body}\n```"

    return _MERMAID_FENCE_RE.sub(fence_repl, content)


_TYPE_NAME_BULLET_RE = re.compile(
    r"^[-*][ \t]+`?([A-Za-z_][A-Za-z0-9_]*)`?[ \t]+—"
)
_PILL_SYMBOL_RE = re.compile(r"`[^`]+[ \t]+([A-Za-z_][A-Za-z0-9_]*)`")


def mermaid_is_toy(source: str) -> bool:
    """True when a subsystem diagram is missing, one-edge, or has fewer than 3 types."""
    text = normalize_mermaid_source(source)
    if not text:
        return True
    low = text.lstrip().lower()
    if low.startswith("sequencediagram"):
        return len(re.findall(r"(?i)\bparticipant\b", text)) < 3
    nodes = _MERMAID_NODE_RE.findall(text)
    edges = len(re.findall(r"-->", text))
    return len(nodes) < 3 or edges < 2


def flowchart_lr_from_types(names: list[str]) -> str:
    """Typed flowchart LR from on-page types. Does not invent names."""
    labels: list[str] = []
    seen: set[str] = set()
    for raw in names:
        name = (raw or "").strip()
        if not name or is_dummy_symbol(name) or name in seen:
            continue
        seen.add(name)
        labels.append(clip_mermaid_label(name) or name)
        if len(labels) >= 6:
            break
    if len(labels) < 2:
        return ""
    lines = ["flowchart LR"]
    ids = [chr(ord("A") + i) for i in range(len(labels))]
    for nid, lab in zip(ids, labels, strict=True):
        lines.append(f'  {nid}["{lab}"]')
    for src, dst, a, b in zip(ids, ids[1:], labels, labels[1:], strict=False):
        if a == b:
            continue
        lines.append(f"  {src} --> {dst}")
    return "\n".join(lines)


def _types_in_subsystem_chunk(chunk: str) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for line in (chunk or "").splitlines():
        match = _TYPE_NAME_BULLET_RE.match(line.strip())
        if match and match.group(1) not in seen and not is_dummy_symbol(match.group(1)):
            seen.add(match.group(1))
            names.append(match.group(1))
    for match in _PILL_SYMBOL_RE.finditer(chunk or ""):
        name = match.group(1)
        if name not in seen and not is_dummy_symbol(name):
            seen.add(name)
            names.append(name)
    return names


def _thicken_one_subsystem(chunk: str) -> str:
    if not chunk.startswith("###"):
        return chunk
    types = _types_in_subsystem_chunk(chunk)
    diagram = flowchart_lr_from_types(types)
    if not diagram:
        return chunk
    fence = _MERMAID_FENCE_RE.search(chunk)
    if fence:
        if not mermaid_is_toy(fence.group(1)):
            return chunk
        return chunk[: fence.start()] + f"```mermaid\n{diagram}\n```" + chunk[fence.end() :]
    lines = chunk.splitlines(keepends=True)
    insert_at = 1
    while insert_at < len(lines) and not lines[insert_at].strip():
        insert_at += 1
    if insert_at < len(lines) and not lines[insert_at].lstrip().startswith(("#", "-", "*", "```")):
        insert_at += 1
        while insert_at < len(lines) and not lines[insert_at].strip():
            insert_at += 1
    injection = "```mermaid\n" + diagram + "\n```\n\n"
    return "".join(lines[:insert_at]) + injection + "".join(lines[insert_at:])


def thicken_subsystem_diagrams(content: str) -> str:
    """Replace toy 核心子系统 mermaids with typed flowchart LR from on-page types."""
    if not content:
        return content
    if "## 核心子系统" not in content and "## Core subsystems" not in content:
        return content
    parts = re.split(r"(?m)(?=^## )", content)
    out: list[str] = []
    for part in parts:
        first, _, _rest = part.partition("\n")
        if re.match(r"(?im)^##[ \t]+(核心子系统|Core subsystems)\b", first):
            chunks = re.split(r"(?m)(?=^### )", part)
            out.append("".join(_thicken_one_subsystem(chunk) for chunk in chunks))
        else:
            out.append(part)
    return "".join(out)


def _topic_lookup(pages: list[dict]) -> dict[str, dict]:
    found: dict[str, dict] = {}
    for page in pages:
        pid = str(page.get("id") or "")
        if not pid.startswith("topics/"):
            continue
        slug = pid.split("/", 1)[-1]
        found[slug] = page
        found[slug.replace("-", " ")] = page
        title = str(page.get("title") or "").strip()
        if title:
            found[title] = page
            found[title.lower()] = page
    return found


def _match_topic_page(name: str, topics: dict[str, dict]) -> dict | None:
    raw = (name or "").strip()
    if not raw:
        return None
    for key in (raw, raw.lower(), raw.replace(" ", "-").lower()):
        if key in topics:
            return topics[key]
    for key, page in topics.items():
        if raw.lower() in key.lower() or key.lower() in raw.lower():
            return page
    return None


def _topic_type_lines(content: str) -> list[str]:
    lines: list[str] = []
    in_types = False
    for line in (content or "").splitlines():
        if re.match(r"(?im)^##[ \t]+(关键类型|Key types)\b", line):
            in_types = True
            continue
        if in_types and re.match(r"(?m)^## ", line):
            break
        if in_types and line.strip().startswith(("-", "*")):
            lines.append(line.rstrip())
    return lines


def _topic_mermaid(content: str) -> str:
    match = _MERMAID_FENCE_RE.search(content or "")
    if not match:
        return ""
    body = normalize_mermaid_source(match.group(1))
    return body if body and not mermaid_is_toy(body) else ""


def enrich_overview_from_topic_pages(pages: list[dict]) -> None:
    """Copy real diagrams / type-as-role lines from existing topic pages.

    Does not invent topics. Overview 核心子系统 headings must already exist.
    """
    topics = _topic_lookup(pages)
    if not topics:
        return
    for page in pages:
        if str(page.get("id") or "") != "index":
            continue
        content = page.get("content") or ""
        if "## 核心子系统" not in content and "## Core subsystems" not in content:
            continue
        parts = re.split(r"(?m)(?=^## )", content)
        out: list[str] = []
        for part in parts:
            first, _, _rest = part.partition("\n")
            if not re.match(r"(?im)^##[ \t]+(核心子系统|Core subsystems)\b", first):
                out.append(part)
                continue
            chunks = re.split(r"(?m)(?=^### )", part)
            rebuilt: list[str] = []
            for chunk in chunks:
                if not chunk.startswith("###"):
                    rebuilt.append(chunk)
                    continue
                heading = chunk.split("\n", 1)[0]
                name = re.sub(r"^###\s+", "", heading).strip()
                topic = _match_topic_page(name, topics)
                if topic is None:
                    rebuilt.append(_thicken_one_subsystem(chunk))
                    continue
                topic_md = str(topic.get("content") or "")
                diagram = _topic_mermaid(topic_md)
                type_lines = _topic_type_lines(topic_md)
                chunk = _thicken_one_subsystem(chunk)
                if diagram and mermaid_is_toy(
                    (m.group(1) if (m := _MERMAID_FENCE_RE.search(chunk)) else "")
                ):
                    if _MERMAID_FENCE_RE.search(chunk):
                        chunk = _MERMAID_FENCE_RE.sub(
                            f"```mermaid\n{diagram}\n```", chunk, count=1
                        )
                    else:
                        chunk = _thicken_one_subsystem(
                            chunk.rstrip() + "\n\n```mermaid\n" + diagram + "\n```\n"
                        )
                if type_lines and not _types_in_subsystem_chunk(chunk):
                    chunk = chunk.rstrip() + "\n\n" + "\n".join(type_lines) + "\n"
                    chunk = _thicken_one_subsystem(chunk)
                rebuilt.append(chunk)
            out.append("".join(rebuilt))
        page["content"] = "".join(out)


def clip_mermaid_label(text: str) -> str:
    """Keep mermaid node text short and complete (GET + generate)."""
    cleaned = _MERMAID_LABEL_RE.sub(" ", text or "")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if not cleaned:
        return ""
    cap = 12 if _mostly_cjk(cleaned) else 28
    parts = re.findall(r"`[^`]+`|\S+", cleaned)
    if not parts:
        return _strip_incomplete_mermaid_trail(cleaned)
    if len(cleaned) > cap:
        acc: list[str] = []
        length = 0
        for part in parts:
            add = (1 if acc else 0) + len(part)
            if acc and length + add > cap:
                break
            if not acc and len(part) > cap and not part.startswith("`"):
                chunk = part[:cap]
                cut = -1
                for sep in (" ", "、", "，", "；"):
                    idx = chunk.rfind(sep)
                    if idx >= max(2, cap // 3):
                        cut = max(cut, idx)
                part = chunk[:cut].rstrip() if cut > 0 else chunk
                acc.append(part)
                break
            acc.append(part)
            length += add
        cleaned = " ".join(acc) if acc else parts[0]
    if cleaned.count("`") % 2:
        cleaned = cleaned.rsplit("`", 1)[0].rstrip()
    cleaned = re.sub(
        r"\b(?:undefine|constructo|functio|retur|writeDefaultPrese)\b",
        "",
        cleaned,
        flags=re.I,
    )
    return _strip_incomplete_mermaid_trail(cleaned.strip())


def shorten_mermaid_node_labels(content: str) -> str:
    """GET: clip mermaid node labels so they are not cut mid-verb."""
    if not content or "```mermaid" not in content:
        return content

    def fence_repl(match: re.Match[str]) -> str:
        body = match.group(1)

        def node_repl(node: re.Match[str]) -> str:
            label = clip_mermaid_label(node.group("label"))
            if not label:
                return node.group(0)
            return f'{node.group("pre")}{node.group("open")}{label}{node.group("close")}'

        body = _MERMAID_NODE_RE.sub(node_repl, body)
        return f"```mermaid\n{body}```"

    return _MERMAID_FENCE_RE.sub(fence_repl, content)


def strip_reading_wiki_homework(content: str, *, page_id: str = "") -> str:
    """Drop homework headings / 可练习概念 from reading wiki. Learning path keeps them."""
    if not content:
        return content
    lead, sections = _split_markdown_sections(content)
    kept: list[tuple[str, str]] = []
    for heading, body in sections:
        title = heading.strip()
        if title in _READING_HOMEWORK_HEADINGS or title.startswith("可练习"):
            continue
        kept.append((heading, body))
    if len(kept) != len(sections):
        parts = [lead.rstrip()]
        for heading, body in kept:
            parts.append(f"## {heading}\n{body}".rstrip())
        content = "\n\n".join(p for p in parts if p).rstrip() + "\n"
    if page_id == "reading-guide" or "可练习概念" in content or "practice concept" in content.lower():
        content = content.replace(
            "每一步对应一个可练习概念：先读证据，再做回忆。",
            "每一步对应一个系统：先读证据，再跟一次调用。",
        )
        content = content.replace(
            "Each step maps to a practice concept: read evidence, then recall.",
            "Each step maps to a system: read evidence, then follow one call.",
        )
        content = content.replace("可练习概念", "系统")
        content = re.sub(
            r"(?i)practice concepts?",
            "system",
            content,
        )
    return content


def upgrade_architecture_loop_wording(content: str) -> str:
    """GET: invented AgentLoop / cli-tool lede / leftover assembly title."""
    if not content:
        return content
    content = content.replace("Agent Loop 与上下文装配", "Agent Loop")
    content = content.replace("Agent Loop & Context Assembly", "Agent Loop")
    content = _rewrite_agentloop_token(content)
    content = re.sub(r"（cli-tool）", "", content)
    content = re.sub(r"\(cli-tool\)", "", content)
    return content


def _page_has_grok_loop(content: str) -> bool:
    """True when this page already names the grok runtime (do not invent it)."""
    return bool(
        re.search(r"\bstart_turn\b", content or "")
        or re.search(r"xai-grok-(?:pager|agent)", content or "", re.I)
    )


def _rewrite_agentloop_token(content: str) -> str:
    """Map invented AgentLoop to start_turn only when this page already has that loop."""
    grok = _page_has_grok_loop(content)
    replacement = "start_turn" if grok else "Agent Loop"

    def mermaid_repl(match: re.Match[str]) -> str:
        body = match.group(1)
        if grok and re.search(r"\bstart_turn\b", body):
            body = re.sub(r"\bAgentLoop\b", "start_turn", body)
        elif grok:
            body = re.sub(r"\bAgentLoop\b", "start_turn", body)
        else:
            body = re.sub(r"\bAgentLoop\b", "Agent Loop", body)
        return f"```mermaid\n{collapse_repeated_mermaid_labels(body)}\n```"

    content = re.sub(r"```mermaid\n(.*?)```", mermaid_repl, content, flags=re.S)
    return re.sub(r"\bAgentLoop\b", replacement, content)


def collapse_repeated_mermaid_labels(source: str) -> str:
    """Drop edges whose two ends share a label (Pager → start_turn → start_turn)."""
    text = (source or "").strip()
    if not text:
        return text
    node_labels: dict[str, str] = {}
    for match in re.finditer(
        r'([A-Za-z][\w-]*)\s*\[\s*"?([^"\]]+)"?\s*\]', text
    ):
        node_labels[match.group(1)] = re.sub(r"\s+", " ", match.group(2)).strip()
    if not node_labels:
        return text
    out: list[str] = []
    for line in text.splitlines():
        edge = re.match(r"^(\s*)([A-Za-z][\w-]*)\s*-->\s*([A-Za-z][\w-]*)", line)
        if edge:
            src, dst = edge.group(2), edge.group(3)
            if src == dst or node_labels.get(src) == node_labels.get(dst):
                continue
        out.append(line)
    return "\n".join(out)


def _first_deep_topic(topics) -> tuple[str, str] | None:
    for item in topics or []:
        tid = getattr(item, "id", None) or getattr(item, "name", "") or ""
        section = getattr(item, "section", "") or ""
        if not tid or section == "getting-started" or tid == GETTING_STARTED_ID:
            continue
        if tid in {"overview", "project-goal", "architecture"}:
            continue
        title = (getattr(item, "title", "") or tid).strip()
        return wiki_page_id_for_topic(tid), title
    return None


def _first_deep_topic_title(topics) -> str:
    hit = _first_deep_topic(topics)
    return hit[1] if hit else ""


def _first_deep_topic_link(topics) -> str:
    hit = _first_deep_topic(topics)
    if not hit:
        return ""
    page_id, title = hit
    return f"- [{title}]({page_id})"


def thicken_getting_started(
    content: str, known_ids: set[str], *, language: str = "zh"
) -> str:
    """If 快速开始 is a stub, append 跑起来之后 links (GET refresh)."""
    if not content or len(content) >= 800:
        return content
    if "跑起来之后" in content or "After it runs" in content:
        return content
    links: list[str] = []
    if "architecture" in known_ids:
        title = structural_title("architecture", language)
        links.append(f"- [{title}](architecture)")
    for pid in known_ids:
        if pid.startswith("topics/") and pid != "topics/getting-started":
            title = pid.split("/", 1)[-1]
            if title == "agent-loop":
                links.append("- [Agent Loop](topics/agent-loop)")
            elif title == "entry-and-boot":
                links.append("- [入口与启动](topics/entry-and-boot)" if language == "zh" else "- [Entry and boot](topics/entry-and-boot)")
            elif title in {"capability-seam", "plugin-architecture", "cordis", "core-architecture"}:
                shown = {
                    "capability-seam": "Capability Seam",
                    "plugin-architecture": "Plugin 架构" if language == "zh" else "Plugin architecture",
                    "cordis": "Cordis",
                    "core-architecture": "核心架构" if language == "zh" else "Core architecture",
                }[title]
                links.append(f"- [{shown}]({pid})")
            if len(links) >= 2:
                break
    if not links:
        return content
    heading = "## 跑起来之后" if language == "zh" else "## After it runs"
    return content.rstrip() + "\n\n" + heading + "\n\n" + "\n".join(links) + "\n"


def _looks_like_readme_dump(text: str) -> bool:
    """True when overview.description is a pasted README, not a handbook lede."""
    raw = (text or "").strip()
    if not raw:
        return False
    if raw.startswith("# "):
        return True
    if "\n# " in raw or "\n## " in raw:
        return True
    return len(raw) > 600 and raw.count("\n") > 8


def _dedupe_claim_lines(items) -> list[str]:
    """Drop repeated '启动，一次调用从这里进图' bullets that only differ by a broken chip."""
    seen: set[str] = set()
    out: list[str] = []
    for raw in items:
        text = str(raw or "").strip()
        if not text:
            continue
        key = re.sub(r"`[^`]+`", "", text)
        key = re.sub(r"\s+", " ", key).strip()
        if key in seen:
            continue
        seen.add(key)
        out.append(text)
    return out


def _overview_lede(name: str, one_liner: str, language: str) -> str:
    if language == "zh":
        extra = f"（{one_liner.rstrip('。')}）" if one_liner else ""
        return (
            f"{name} 解决什么问题、给谁用，以及主要能力落在哪{extra}。"
            "目标与边界以 README 和入口为准，不以目录名为准。"
        )
    extra = f" {one_liner}" if one_liner else ""
    return (
        f"{name} states what problem it solves, who it is for, and where the "
        f"main capabilities sit.{extra} The goal lives in the README and "
        "entrypoints, not the folder tree."
    )


_LANG_ALIASES = {
    "python": "python",
    "javascript": "javascript",
    "js": "javascript",
    "typescript": "typescript",
    "ts": "typescript",
    "java": "java",
    "go": "go",
    "golang": "go",
    "rust": "rust",
    "ruby": "ruby",
    "php": "php",
    "c++": "cpp",
    "cpp": "cpp",
    "c#": "csharp",
    "csharp": "csharp",
    "kotlin": "kotlin",
    "swift": "swift",
}
_UNSPECIFIED = {"未指定", "unspecified", "unknown", "n/a", "none", "-", "n.a."}


def filter_tech_stack(items, project) -> list:
    """Drop invented languages (Python/JavaScript 未指定 on a Rust repo)."""
    langs = {
        (getattr(f, "language", "") or "").strip().lower()
        for f in (getattr(project, "files", None) or [])
        if (getattr(f, "language", "") or "").strip()
        and getattr(f, "language", "") != "unknown"
    }
    out = []
    for item in items or []:
        name = (getattr(item, "name", "") or "").strip()
        cat = (getattr(item, "category", "") or "").strip().lower()
        ver = (getattr(item, "version", "") or "").strip()
        if ver.lower() in _UNSPECIFIED:
            try:
                item.version = ""
            except Exception:
                pass
        key = _LANG_ALIASES.get(name.lower())
        is_lang = cat == "language" or key is not None
        if is_lang and langs:
            token = key or name.lower()
            if token not in langs and not any(token in lang or lang in token for lang in langs):
                continue
        out.append(item)
    return out


def _tech_stack_table(items, language: str = "en") -> list[str]:
    has_cat = any(getattr(t, "category", "") for t in items)
    has_ver = any(getattr(t, "version", "") for t in items)
    if language == "zh":
        headers = ["技术"]
        if has_cat:
            headers.append("类别")
        if has_ver:
            headers.append("版本")
    else:
        headers = ["Tech"]
        if has_cat:
            headers.append("Category")
        if has_ver:
            headers.append("Version")
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for item in items:
        row = [item.name]
        if has_cat:
            row.append(item.category or "—")
        if has_ver:
            row.append(item.version or "—")
        lines.append("| " + " | ".join(row) + " |")
    lines.append("")
    return lines


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
    "term-tips": ("术语", "术语小贴士", "Terms", "Term tips"),
    "how-a-call-runs": (
        "调用链",
        "一次调用怎么走",
        "Call path",
        "How a call runs",
        "关键调用链",
        "Key Call Chains",
    ),
    "how-it-runs": (
        "实现",
        "这条链路怎么转",
        "How it actually runs",
        "实现细节",
        "实现要点",
        "Implementation",
        "Implementation details",
    ),
    "failures": (
        "边界",
        "失败与边界",
        "Boundaries",
        "Failures and edges",
        "边界条件",
        "Edge Cases",
    ),
    "dependencies": ("依赖", "Dependencies"),
    "related-source": ("相关源码", "Related source", "文件", "Files"),
    "key-concepts": ("关键概念", "Key Concepts"),
    "relationships": ("内部关系", "Internal Relationships"),
    "source-evidence": ("源码证据", "Source Evidence"),
}
_MODULE_SECTION_CANON = {
    "how-a-call-runs": {"zh": "调用链", "en": "Call path"},
    "how-it-runs": {"zh": "实现", "en": "Implementation"},
    "failures": {"zh": "边界", "en": "Boundaries"},
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
    cleaned = clip_mermaid_label(text)
    if not cleaned:
        return ""
    if _mostly_cjk(cleaned):
        return cleaned if len(cleaned) >= 2 else ""
    return cleaned if len(cleaned) >= 4 else ""


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


_TOPIC_GROUP_TITLES = {
    "getting-started",
    "getting started",
    "入门指南",
    "deep-dive",
    "deep dive",
    "深入探索",
}
_MODULE_GROUP_TITLES = {"modules", "模块", "by directory", "按目录"}
DIR_SIDEBAR_LEAF_CAP = 8
_DIR_NAV_SKIP_ROOTS = {
    ".cargo",
    ".github",
    ".git",
    "target",
    "node_modules",
    "vendor",
    "scripts",
    "third_party",
}
_DIR_PRODUCT_TOKS = ("xai-grok", "grok", "pager")


def is_directory_nav_noise(module_name: str) -> bool:
    """`.cargo` / toolchain `bin` do not belong in the 8-leaf crate listing."""
    raw = (module_name or "").replace("\\", "/")
    if raw.startswith("modules/"):
        raw = raw[len("modules/") :]
    parts = [p for p in raw.split("/") if p]
    if not parts:
        return True
    root = parts[0]
    if root.startswith(".") or root in _DIR_NAV_SKIP_ROOTS:
        return True
    if root == "bin":
        return True
    return False


def _page_id_of(item) -> str:
    if isinstance(item, dict):
        return str(item.get("page_id") or "")
    return str(getattr(item, "page_id", "") or "")


def _importance_blob_from_pages(pages) -> str:
    parts: list[str] = []
    for page in pages or []:
        if isinstance(page, dict):
            pid = str(page.get("id") or "")
            content = str(page.get("content") or "")
        else:
            pid = str(getattr(page, "id", "") or "")
            content = str(getattr(page, "content", "") or "")
        if pid in {"index", "architecture"} or pid.startswith("topics/"):
            parts.append(content)
            parts.append(pid)
    return "\n".join(parts).lower()


def _module_pagerank_scores(graph: DependencyGraph | None) -> dict[str, float]:
    if graph is None:
        return {}
    scores: dict[str, float] = {}
    try:
        ranked = graph.rank_files()
    except Exception:
        return {}
    for path, score in ranked:
        parts = [p for p in path.replace("\\", "/").split("/") if p]
        for i in range(len(parts)):
            prefix = "/".join(parts[: i + 1])
            scores[prefix] = max(scores.get(prefix, 0.0), float(score))
    return scores


def _module_dir_sort_key(
    name: str,
    blob: str,
    ranks: dict[str, float] | None = None,
) -> tuple:
    """Lower is better: cited / product crates ahead of alphabetical codegen."""
    path = (name or "").replace("\\", "/").removeprefix("modules/")
    leaf = path.rsplit("/", 1)[-1] if path else ""
    low = path.lower()
    cited = blob or ""
    hits = cited.count(low) * 3 + cited.count(leaf.lower())
    product = 0
    if any(tok in low for tok in _DIR_PRODUCT_TOKS):
        product = 8
    if "pager" in low:
        product = max(product, 12)
    if "grok-agent" in low or low.rstrip("/").endswith("xai-grok-agent"):
        product = max(product, 11)
    pr = (ranks or {}).get(path, 0.0)
    return (-hits, -product, -pr, path)


def _dir_item_path(item) -> str:
    pid = _page_id_of(item)
    if pid.startswith("modules/"):
        return pid[len("modules/") :]
    title = _sidebar_title(item)
    return title


def _dir_item_sort_key(item, blob: str, ranks: dict[str, float]) -> tuple:
    kids = _sidebar_children(item)
    if kids:
        return min(_dir_item_sort_key(child, blob, ranks) for child in kids)
    return _module_dir_sort_key(_dir_item_path(item), blob, ranks)


def _filter_directory_children(children: list) -> list:
    kept: list = []
    for child in children:
        path = _dir_item_path(child)
        kids = _sidebar_children(child)
        if kids:
            inner = _filter_directory_children(kids)
            if not inner:
                continue
            _set_sidebar_children(child, inner)
            kept.append(child)
            continue
        if is_directory_nav_noise(path):
            continue
        kept.append(child)
    return kept


def _rank_directory_children(
    children: list, blob: str, ranks: dict[str, float]
) -> list:
    ranked = []
    for child in children:
        kids = _sidebar_children(child)
        if kids:
            _set_sidebar_children(child, _rank_directory_children(kids, blob, ranks))
        ranked.append(child)
    ranked.sort(key=lambda item: _dir_item_sort_key(item, blob, ranks))
    return ranked


def rank_and_cap_directory_sidebar(
    sidebar: list,
    *,
    pages=None,
    graph: DependencyGraph | None = None,
    cap: int = DIR_SIDEBAR_LEAF_CAP,
) -> list:
    """Exclude toolchain dirs, rank remaining crates, then cap to `cap` leaves."""
    blob = _importance_blob_from_pages(pages)
    ranks = _module_pagerank_scores(graph)
    labels = {t.lower() for t in _MODULE_GROUP_TITLES}
    for item in sidebar or []:
        title = _sidebar_title(item).strip().lower()
        if title not in labels:
            continue
        kids = _filter_directory_children(_sidebar_children(item))
        kids = _rank_directory_children(kids, blob, ranks)
        _set_sidebar_children(item, kids)
    return cap_directory_sidebar(sidebar, cap=cap)


def prune_sidebar_missing_pages(sidebar: list, page_ids: set[str]) -> list:
    """Drop leaves whose page was omitted (failed stub, generic web, …)."""
    out: list = []
    for item in sidebar or []:
        if not isinstance(item, dict):
            out.append(item)
            continue
        pid = str(item.get("page_id") or "")
        children = prune_sidebar_missing_pages(item.get("children") or [], page_ids)
        if pid and pid not in page_ids and pid.startswith(("topics/", "concepts/")):
            continue
        new_item = dict(item)
        new_item["children"] = children
        out.append(new_item)
    return out


def _sidebar_title(item) -> str:
    if isinstance(item, dict):
        return str(item.get("title") or "")
    return str(getattr(item, "title", "") or "")


def _sidebar_children(item):
    if isinstance(item, dict):
        return list(item.get("children") or [])
    return list(getattr(item, "children", None) or [])


def _set_sidebar_children(item, children) -> None:
    if isinstance(item, dict):
        item["children"] = children
    else:
        item.children = children


def _count_sidebar_leaves(item) -> int:
    kids = _sidebar_children(item)
    if not kids:
        return 1
    return sum(_count_sidebar_leaves(child) for child in kids)


def _cap_sidebar_children(children: list, cap: int) -> list:
    kept: list = []
    leaves = 0
    for child in children:
        n = _count_sidebar_leaves(child)
        if leaves + n <= cap:
            kept.append(child)
            leaves += n
        elif n > 1:
            inner = _cap_sidebar_children(_sidebar_children(child), cap - leaves)
            if inner:
                _set_sidebar_children(child, inner)
                kept.append(child)
                leaves += sum(_count_sidebar_leaves(c) for c in inner)
        if leaves >= cap:
            break
    return kept


def cap_directory_sidebar(sidebar: list, *, cap: int = DIR_SIDEBAR_LEAF_CAP) -> list:
    """Keep 按目录 to a handful of crate roots so topics stay the main nav."""
    out: list = []
    labels = {t.lower() for t in _MODULE_GROUP_TITLES}
    for item in sidebar or []:
        title = _sidebar_title(item).strip().lower()
        if title in labels:
            kids = _cap_sidebar_children(_sidebar_children(item), cap)
            if not kids:
                continue
            _set_sidebar_children(item, kids)
        out.append(item)
    return out


_GENERIC_WEB_PAGE_SLUGS = {
    "caching",
    "authentication",
    "request-routing",
    "data-persistence",
    "error-handling",
    "background-tasks",
}
_CONCEPT_NAV_SKIP = {"module-inventory", "file-inventory"}


def is_concept_nav_slug(slug: str) -> bool:
    raw = (slug or "").strip()
    if not raw or raw in _CONCEPT_NAV_SKIP or raw in _GENERIC_WEB_PAGE_SLUGS:
        return False
    if raw.startswith(("module-", "file-", "focus-")):
        return False
    from repowiki.core.topics import is_config_file_concept

    if is_config_file_concept(raw):
        return False
    return True


def _concept_nav_leaves(pages: list[dict], titles: dict[str, str]) -> list[dict]:
    leaves: list[dict] = []
    for page in pages:
        pid = str(page.get("id") or "")
        if not pid.startswith("concepts/"):
            continue
        slug = pid.split("/", 1)[-1]
        if not is_concept_nav_slug(slug):
            continue
        leaves.append({
            "title": titles.get(pid) or str(page.get("title") or slug),
            "page_id": pid,
            "children": [],
        })
    return leaves


def ensure_reading_ia_sidebar(
    sidebar: list,
    pages: list[dict],
    *,
    language: str = "zh",
) -> list:
    """Put 导读 in 入门指南 and 词条 in 深入探索 without reshuffling topics."""
    lang = normalize_wiki_lang(language)
    page_ids = {str(p.get("id") or "") for p in pages}
    titles = {
        str(p.get("id") or ""): str(p.get("title") or p.get("id") or "")
        for p in pages
    }

    def leaf(page_id: str, title: str | None = None) -> dict:
        return {
            "title": title or titles.get(page_id, page_id),
            "page_id": page_id,
            "children": [],
        }

    items = [dict(item) if isinstance(item, dict) else item for item in (sidebar or [])]
    getting_title = structural_title("getting-started", lang)
    deep_title = structural_title("deep-dive", lang)
    guide_title = structural_title("reading-guide", lang)
    concepts_title = structural_title("concepts", lang)

    def find_group(title: str) -> dict | None:
        for item in items:
            if isinstance(item, dict) and str(item.get("title") or "") == title:
                return item
        return None

    getting = find_group(getting_title)
    if getting is None and ("index" in page_ids or "getting-started" in page_ids or "reading-guide" in page_ids):
        getting = {"title": getting_title, "page_id": "", "children": []}
        items.insert(0, getting)
    if getting is not None:
        kids = list(getting.get("children") or [])
        have = {str(c.get("page_id") or "") for c in kids if isinstance(c, dict)}
        if "reading-guide" in page_ids and "reading-guide" not in have:
            kids.append(leaf("reading-guide", guide_title))
        getting["children"] = kids

    glossary = _concept_nav_leaves(pages, titles)
    if glossary:
        deep = find_group(deep_title)
        if deep is None:
            deep = {"title": deep_title, "page_id": "", "children": []}
            items.append(deep)
        kids = list(deep.get("children") or [])
        existing_group = next(
            (
                c
                for c in kids
                if isinstance(c, dict)
                and not c.get("page_id")
                and str(c.get("title") or "") == concepts_title
            ),
            None,
        )
        have_ids = {str(c.get("page_id") or "") for c in kids if isinstance(c, dict)}
        if existing_group is not None:
            nested = list(existing_group.get("children") or [])
            nested_ids = {str(c.get("page_id") or "") for c in nested if isinstance(c, dict)}
            for item in glossary:
                if item["page_id"] not in nested_ids:
                    nested.append(item)
            existing_group["children"] = nested
        else:
            missing = [item for item in glossary if item["page_id"] not in have_ids]
            if missing:
                kids.append({
                    "title": concepts_title,
                    "page_id": "",
                    "children": missing,
                })
        deep["children"] = kids
    return items


def rebuild_topic_sidebar(
    pages: list[dict],
    *,
    language: str = "zh",
) -> list[dict]:
    """Rebuild 入门指南 / 深入探索 from persisted pages (GET upgrade)."""
    lang = normalize_wiki_lang(language)
    page_ids = {str(p.get("id") or "") for p in pages}
    titles = {
        str(p.get("id") or ""): str(p.get("title") or p.get("id") or "")
        for p in pages
    }

    def leaf(page_id: str, title: str | None = None) -> dict:
        return {
            "title": title or titles.get(page_id, page_id),
            "page_id": page_id,
            "children": [],
        }

    getting: list[dict] = []
    if "index" in page_ids:
        getting.append(leaf("index", structural_title("overview", lang)))
    if "getting-started" in page_ids:
        getting.append(leaf("getting-started", structural_title("quick-start", lang)))
    if "reading-guide" in page_ids:
        getting.append(leaf("reading-guide", structural_title("reading-guide", lang)))

    deep: list[dict] = []
    if "architecture" in page_ids:
        deep.append(leaf("architecture", structural_title("architecture", lang)))
    topic_pages = sorted(
        (p for p in pages if str(p.get("id") or "").startswith("topics/")),
        key=lambda p: str(p.get("id") or ""),
    )
    kept_topics = 0
    for page in topic_pages:
        pid = str(page.get("id") or "")
        if not keep_generic_web_topic_nav(pid, str(page.get("content") or "")):
            continue
        deep.append(leaf(pid))
        kept_topics += 1
    glossary = _concept_nav_leaves(pages, titles)
    if glossary:
        if kept_topics:
            deep.append({
                "title": structural_title("concepts", lang),
                "page_id": "",
                "children": glossary,
            })
        else:
            deep.extend(glossary)

    items: list[dict] = []
    if getting:
        items.append({
            "title": structural_title("getting-started", lang),
            "page_id": "",
            "children": getting,
        })
    if deep:
        items.append({
            "title": structural_title("deep-dive", lang),
            "page_id": "",
            "children": deep,
        })
    module_children: list[dict] = []
    for page in pages:
        pid = str(page.get("id") or "")
        if pid.startswith("modules/"):
            module_children.append(leaf(pid))
    if module_children:
        items.append({
            "title": structural_title("by-directory", lang),
            "page_id": "",
            "children": module_children,
        })
    return rank_and_cap_directory_sidebar(items, pages=pages)


def prune_generic_web_sidebar(sidebar: list, content_by_id: dict[str, str]) -> list:
    """Drop thin caching/request-routing topic leaves from an existing nav."""
    out: list = []
    for item in sidebar or []:
        if not isinstance(item, dict):
            out.append(item)
            continue
        pid = str(item.get("page_id") or "")
        children = prune_generic_web_sidebar(item.get("children") or [], content_by_id)
        if pid.startswith(("topics/", "concepts/")) and not keep_generic_web_topic_nav(
            pid, content_by_id.get(pid, "")
        ):
            continue
        new_item = dict(item)
        new_item["children"] = children
        out.append(new_item)
    return out


def sidebar_has_topic_groups(sidebar: list) -> bool:
    """True when the nav already uses 入门指南 / 深入探索 (skip GET rebuild)."""
    titles = {
        str(item.get("title") or "").strip().lower()
        for item in sidebar or []
        if isinstance(item, dict)
    }
    return bool(titles & {t.lower() for t in _TOPIC_GROUP_TITLES})


def sidebar_looks_like_module_tree(sidebar: list) -> bool:
    """True when the persisted nav is still RepoWiki's directory clustering."""
    if not sidebar:
        return False
    titles = [str(item.get("title") or "").strip() for item in sidebar if isinstance(item, dict)]
    lowered = {t.lower() for t in titles}
    if lowered & _TOPIC_GROUP_TITLES:
        return False
    if any(t in ("入门指南", "深入探索") for t in titles):
        return False
    if any(t in ("模块", "Modules") for t in titles):
        return True
    # Flat old nav: Overview, Architecture, then crate paths / Modules.
    if titles and titles[0] in {"Overview", "概述", "Architecture", "架构概览"}:
        for item in sidebar:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or "")
            iid = str(item.get("page_id") or item.get("id") or "")
            if title in ("模块", "Modules") or iid == "modules":
                return True
            children = item.get("children") or []
            for child in children:
                if not isinstance(child, dict):
                    continue
                ctitle = str(child.get("title") or "")
                cid = str(child.get("page_id") or child.get("id") or "")
                if cid.startswith("modules/") or ctitle.startswith(".") or "/" in ctitle:
                    return True
    return False
