"""data models for repowiki analysis pipeline."""

from __future__ import annotations

from pydantic import BaseModel, Field


class FileInfo(BaseModel):
    """metadata about a single file in the project."""

    path: str
    size: int
    language: str = "unknown"
    lines: int = 0
    preview: str = ""
    content: str = ""
    is_config: bool = False
    is_entrypoint: bool = False


class ProjectContext(BaseModel):
    """everything we know about a project before LLM analysis."""

    name: str
    root: str
    files: list[FileInfo] = Field(default_factory=list)
    file_tree: str = ""

    @property
    def total_lines(self) -> int:
        return sum(f.lines for f in self.files)


# --- LLM analysis output models ---


class Citation(BaseModel):
    """A source claim: path, optional line range, optional symbol.

    Rendered as ``path:start-end`` so the wiki UI can open an inline peek.
    Invalid paths are stripped in the citation-verification pass.
    """

    path: str
    start_line: int = 0
    end_line: int = 0
    symbol: str = ""
    note: str = ""


class CallChain(BaseModel):
    """A named runtime/read-order path through the module."""

    name: str
    description: str = ""
    steps: list[str] = Field(default_factory=list)
    files: list[str] = Field(default_factory=list)


class TermTip(BaseModel):
    """Repo-specific jargon note rendered as 术语小贴士 / Term tips.

    ``term`` stays the identifier as it appears in code (PageRank, ACP, crate).
    Older cached JSON without this field still parses as an empty list.
    """

    term: str
    tip: str = ""


class TechItem(BaseModel):
    name: str
    category: str = ""  # language, framework, database, etc.
    version: str = ""


class KeyType(BaseModel):
    """A type/function named as a role on a call path, not a method dump."""

    name: str
    role: str = ""
    path: str = ""


class CodebasePart(BaseModel):
    """One row in 代码如何拆分: crate or top-level package."""

    name: str
    location: str = ""
    purpose: str = ""


class Subsystem(BaseModel):
    """One DeepWiki 核心子系统 block."""

    name: str
    role: str = ""
    key_types: list[KeyType] = Field(default_factory=list)
    files: list[str] = Field(default_factory=list)
    mermaid: str = ""


class ProjectOverview(BaseModel):
    name: str = ""
    one_liner: str = ""
    description: str = ""
    tech_stack: list[TechItem] = Field(default_factory=list)
    setup_instructions: list[str] = Field(default_factory=list)
    key_features: list[str] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
    term_tips: list[TermTip] = Field(default_factory=list)
    # DeepWiki handbook fields. Older cached JSON without them still parses.
    document_scope: str = ""
    what_it_is: list[str] = Field(default_factory=list)
    runtime_flow: str = ""
    codebase_structure: list[CodebasePart] = Field(default_factory=list)
    subsystems: list[Subsystem] = Field(default_factory=list)
    mermaid_component: str = ""
    see_also: list[str] = Field(default_factory=list)


class Symbol(BaseModel):
    name: str
    kind: str = ""  # function, class, variable, constant
    line: int = 0
    description: str = ""


class FileDoc(BaseModel):
    path: str
    purpose: str = ""
    key_symbols: list[Symbol] = Field(default_factory=list)


class Relationship(BaseModel):
    source: str
    target: str
    description: str = ""


class Concept(BaseModel):
    name: str
    explanation: str = ""


class ModuleDoc(BaseModel):
    name: str
    purpose: str = ""
    description: str = ""
    files: list[FileDoc] = Field(default_factory=list)
    relationships: list[Relationship] = Field(default_factory=list)
    key_concepts: list[Concept] = Field(default_factory=list)
    # Optional DeepWiki-style longform. Older cached JSON without these
    # fields still parses; the wiki builder omits empty sections.
    implementation_details: str = ""
    call_chains: list[CallChain] = Field(default_factory=list)
    edge_cases: list[str] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
    term_tips: list[TermTip] = Field(default_factory=list)
    document_scope: str = ""
    what_it_is: list[str] = Field(default_factory=list)
    key_types: list[KeyType] = Field(default_factory=list)
    mermaid: str = ""


class ModuleOutline(BaseModel):
    """Per-module writing plan produced by the outline pass."""

    name: str
    priority: int = 0  # higher = write deeper
    depth: str = "standard"  # deep | standard | brief
    sections: list[str] = Field(default_factory=list)
    key_files: list[str] = Field(default_factory=list)
    key_symbols: list[str] = Field(default_factory=list)
    notes: str = ""


class TopicOutline(BaseModel):
    """Conceptual system page (zread 深入探索), not a directory module."""

    id: str
    title: str
    section: str = "deep-dive"  # getting-started | deep-dive
    purpose: str = ""
    key_files: list[str] = Field(default_factory=list)
    key_symbols: list[str] = Field(default_factory=list)
    depth: str = "standard"


class TopicDoc(ModuleDoc):
    """Handbook page for one conceptual topic. ``name`` is the topic id."""

    title: str = ""
    section: str = "deep-dive"


class WikiOutline(BaseModel):
    """Structured wiki plan: what to emphasize and in what order."""

    overview_focus: str = ""
    architecture_focus: str = ""
    emphasized_pages: list[str] = Field(default_factory=list)
    reading_order: list[str] = Field(default_factory=list)
    modules: list[ModuleOutline] = Field(default_factory=list)
    topics: list[TopicOutline] = Field(default_factory=list)

    def module_for(self, name: str) -> ModuleOutline | None:
        for item in self.modules:
            if item.name == name:
                return item
        return None

    def depth_for(self, name: str) -> str:
        item = self.module_for(name)
        return item.depth if item else "standard"

    def topic_for(self, topic_id: str) -> TopicOutline | None:
        for item in self.topics:
            if item.id == topic_id:
                return item
        return None


class Component(BaseModel):
    name: str
    purpose: str = ""
    role: str = ""
    files: list[str] = Field(default_factory=list)
    key_types: list[KeyType] = Field(default_factory=list)


class ArchitectureDiagram(BaseModel):
    architecture_type: str = ""  # monolith, client-server, microservices, etc.
    description: str = ""
    components: list[Component] = Field(default_factory=list)
    mermaid_component: str = ""
    mermaid_sequence: str = ""
    data_flow: str = ""
    citations: list[Citation] = Field(default_factory=list)
    term_tips: list[TermTip] = Field(default_factory=list)


class ReadingStep(BaseModel):
    order: int
    title: str
    files: list[str] = Field(default_factory=list)
    explanation: str = ""
    time_estimate: str = ""


class ReadingGuide(BaseModel):
    introduction: str = ""
    steps: list[ReadingStep] = Field(default_factory=list)
    tips: list[str] = Field(default_factory=list)


class WikiData(BaseModel):
    """complete wiki analysis output."""

    overview: ProjectOverview = Field(default_factory=ProjectOverview)
    modules: list[ModuleDoc] = Field(default_factory=list)
    topics: list[TopicDoc] = Field(default_factory=list)
    architecture: ArchitectureDiagram = Field(default_factory=ArchitectureDiagram)
    reading_guide: ReadingGuide = Field(default_factory=ReadingGuide)
    file_index: dict[str, FileDoc] = Field(default_factory=dict)
    outline: WikiOutline | None = None
