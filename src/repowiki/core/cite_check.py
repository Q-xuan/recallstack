"""Pass 3: drop or rewrite hallucinated file citations before wiki render."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from repowiki.core.models import (
    ArchitectureDiagram,
    CallChain,
    Citation,
    FileDoc,
    FileInfo,
    ModuleDoc,
    ProjectContext,
    ProjectOverview,
    ReadingGuide,
    Relationship,
    WikiData,
)

# Backtick cites the frontend SourcePeek already understands:
# `path/to/file.py`, `path/to/file.py:12`, `path/to/file.py:12-40`
_BACKTICK_CITE = re.compile(
    r"`((?:[A-Za-z0-9_.@-]+/)*[A-Za-z0-9_.@-]+\.[A-Za-z0-9]+)(?::(\d+)(?:-(\d+))?)?`"
)
_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_CAMEL = re.compile(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+|[0-9]+")
_JUNK_TIP = re.compile(
    r"未直接使用|仅用于文档生成|not (directly |actually )?used( in (this )?repo)?",
    re.I,
)


@dataclass
class CiteIndex:
    """Resolved project paths, per-file line counts, and identifier tokens."""

    paths: set[str]
    lines: dict[str, int]
    tokens: set[str] = field(default_factory=set)
    blob: str = ""

    @classmethod
    def from_project(cls, project: ProjectContext) -> CiteIndex:
        paths: set[str] = set()
        lines: dict[str, int] = {}
        tokens: set[str] = set()
        blobs: list[str] = []
        for f in project.files:
            path = _normalize_path(f.path)
            paths.add(path)
            lines[path] = _line_count(f)
            _add_path_tokens(tokens, path)
            text = f.content or f.preview or ""
            if text:
                blobs.append(text)
                _add_ident_tokens(tokens, text)
        return cls(
            paths=paths,
            lines=lines,
            tokens=tokens,
            blob="\n".join(blobs).lower(),
        )

    def resolve(self, path: str) -> str | None:
        """Exact match, then unique suffix (``main.py`` → ``app/main.py``)."""
        cand = _normalize_path(path)
        if not cand:
            return None
        if cand in self.paths:
            return cand
        matches = [p for p in self.paths if p.endswith("/" + cand) or p == cand]
        if len(matches) == 1:
            return matches[0]
        return None

    def clamp_line(self, path: str, line: int) -> int:
        if line <= 0:
            return 0
        limit = self.lines.get(path, 0)
        if not limit or line <= limit:
            return line
        return 0

    def has_term(self, term: str) -> bool:
        """True when ``term`` appears as an identifier or path token in this repo."""
        raw = (term or "").strip()
        if len(raw) < 2:
            return False
        key = raw.lower()
        if key in self.tokens:
            return True
        if " " in key and key in self.blob:
            return True
        return False


@dataclass
class CiteReport:
    dropped: list[str] = field(default_factory=list)
    rewritten: list[str] = field(default_factory=list)
    kept: int = 0

    def failed_count(self) -> int:
        return len(self.dropped)


def verify_wiki_data(data: WikiData, project: ProjectContext) -> WikiData:
    """Strip impossible paths from structured fields and prose. No LLM."""
    index = CiteIndex.from_project(project)
    data.overview = verify_overview(data.overview, index)
    data.architecture = verify_architecture(data.architecture, index)
    data.reading_guide = verify_reading_guide(data.reading_guide, index)
    data.modules = [verify_module(m, index) for m in data.modules]
    if data.topics:
        from repowiki.core.topics import is_generic_web_slug, repo_has_web_system

        kept = []
        for mod in data.topics:
            verified = verify_module(mod, index)
            slug = getattr(verified, "name", "") or ""
            if is_generic_web_slug(slug) and not repo_has_web_system(index.paths, slug):
                continue
            kept.append(verified)
        data.topics = kept
    if data.file_index:
        cleaned: dict[str, FileDoc] = {}
        for path, doc in data.file_index.items():
            resolved = index.resolve(path)
            if not resolved:
                continue
            verified, ok = _verify_file_doc(doc, index)
            if ok and verified is not None:
                cleaned[resolved] = verified
        data.file_index = cleaned
    return data


def verify_module(mod: ModuleDoc, index: CiteIndex) -> ModuleDoc:
    files: list[FileDoc] = []
    for doc in mod.files:
        cleaned, ok = _verify_file_doc(doc, index)
        if ok and cleaned is not None:
            files.append(cleaned)
    mod.files = files

    rels: list[Relationship] = []
    for rel in mod.relationships:
        src = index.resolve(rel.source)
        dst = index.resolve(rel.target)
        if not src or not dst:
            continue
        rel.source = src
        rel.target = dst
        rel.description = sanitize_text(rel.description, index)
        rels.append(rel)
    mod.relationships = rels

    chains: list[CallChain] = []
    for chain in mod.call_chains:
        chain.files = [p for p in (index.resolve(x) for x in chain.files) if p]
        chain.description = sanitize_text(chain.description, index)
        chain.steps = [sanitize_text(s, index) for s in chain.steps]
        chains.append(chain)
    mod.call_chains = chains

    mod.citations = [_clamp_citation(c, index) for c in mod.citations]
    mod.citations = [c for c in mod.citations if c is not None]
    mod.purpose = sanitize_text(mod.purpose, index)
    mod.description = sanitize_text(mod.description, index)
    mod.implementation_details = sanitize_text(mod.implementation_details, index)
    mod.edge_cases = [sanitize_text(s, index) for s in mod.edge_cases]
    mod.document_scope = sanitize_text(getattr(mod, "document_scope", "") or "", index)
    mod.what_it_is = [
        sanitize_text(s, index) for s in (getattr(mod, "what_it_is", None) or [])
    ]
    mod.key_types = _sanitize_key_types(getattr(mod, "key_types", None) or [], index)
    for concept in mod.key_concepts:
        concept.explanation = sanitize_text(concept.explanation, index)
    mod.term_tips = _sanitize_term_tips(getattr(mod, "term_tips", None), index)
    return mod


def verify_overview(overview: ProjectOverview, index: CiteIndex) -> ProjectOverview:
    overview.description = sanitize_text(overview.description, index)
    overview.one_liner = sanitize_text(overview.one_liner, index)
    overview.document_scope = sanitize_text(
        getattr(overview, "document_scope", "") or "", index
    )
    overview.runtime_flow = sanitize_text(
        getattr(overview, "runtime_flow", "") or "", index
    )
    overview.what_it_is = [
        sanitize_text(s, index) for s in (getattr(overview, "what_it_is", None) or [])
    ]
    overview.citations = [c for c in (_clamp_citation(c, index) for c in overview.citations) if c]
    overview.key_features = [sanitize_text(s, index) for s in overview.key_features]
    overview.setup_instructions = [sanitize_text(s, index) for s in overview.setup_instructions]
    overview.term_tips = _sanitize_term_tips(getattr(overview, "term_tips", None), index)
    for part in getattr(overview, "codebase_structure", None) or []:
        part.purpose = sanitize_text(part.purpose, index)
    for sub in getattr(overview, "subsystems", None) or []:
        sub.role = sanitize_text(sub.role, index)
        sub.files = [p for p in (index.resolve(x) for x in sub.files) if p]
        sub.key_types = _sanitize_key_types(sub.key_types, index)
    return overview


def verify_architecture(arch: ArchitectureDiagram, index: CiteIndex) -> ArchitectureDiagram:
    arch.description = sanitize_text(arch.description, index)
    arch.data_flow = sanitize_text(arch.data_flow, index)
    arch.citations = [c for c in (_clamp_citation(c, index) for c in arch.citations) if c]
    for comp in arch.components:
        comp.files = [p for p in (index.resolve(x) for x in comp.files) if p]
        comp.purpose = sanitize_text(comp.purpose, index)
        comp.role = sanitize_text(getattr(comp, "role", "") or "", index)
        comp.key_types = _sanitize_key_types(
            getattr(comp, "key_types", None) or [], index
        )
    arch.term_tips = _sanitize_term_tips(getattr(arch, "term_tips", None), index)
    return arch


def verify_reading_guide(guide: ReadingGuide, index: CiteIndex) -> ReadingGuide:
    guide.introduction = sanitize_text(guide.introduction, index)
    for step in guide.steps:
        step.files = [p for p in (index.resolve(x) for x in step.files) if p]
        step.explanation = sanitize_text(step.explanation, index)
    guide.tips = [sanitize_text(s, index) for s in guide.tips]
    return guide


def sanitize_text(text: str, index: CiteIndex) -> str:
    """Rewrite backtick path cites; drop ones that cannot be resolved."""
    if not text:
        return text

    def repl(match: re.Match[str]) -> str:
        path, start_s, end_s = match.group(1), match.group(2), match.group(3)
        resolved = index.resolve(path)
        if not resolved:
            return path.split("/")[-1]
        start = int(start_s) if start_s else 0
        end = int(end_s) if end_s else 0
        start = index.clamp_line(resolved, start)
        end = index.clamp_line(resolved, end)
        if start and end and end < start:
            end = 0
        loc = resolved
        if start:
            loc += f":{start}"
            if end and end != start:
                loc += f"-{end}"
        return f"`{loc}`"

    return _BACKTICK_CITE.sub(repl, text)


def _sanitize_term_tips(tips, index: CiteIndex):
    if not tips:
        return []
    kept = []
    for tip in tips:
        term = (getattr(tip, "term", "") or "").strip()
        text = getattr(tip, "tip", "") or ""
        if not term or not index.has_term(term):
            continue
        if _JUNK_TIP.search(text):
            continue
        tip.tip = sanitize_text(text, index)
        kept.append(tip)
    return kept


def _sanitize_key_types(types, index: CiteIndex) -> list:
    """Drop types with no path, or whose path is not in the repo."""
    kept = []
    for kt in types or []:
        path = (getattr(kt, "path", "") or "").strip()
        if not path:
            continue
        resolved = index.resolve(path)
        if not resolved:
            continue
        kt.path = resolved
        kt.role = sanitize_text(getattr(kt, "role", "") or "", index)
        kept.append(kt)
    return kept


def collect_invalid_paths(mod: ModuleDoc, index: CiteIndex) -> list[str]:
    """Paths the write pass claimed that do not exist in the project."""
    claimed: list[str] = []
    claimed.extend(f.path for f in mod.files)
    claimed.extend(r.source for r in mod.relationships)
    claimed.extend(r.target for r in mod.relationships)
    claimed.extend(c.path for c in mod.citations)
    for chain in mod.call_chains:
        claimed.extend(chain.files)
    invalid: list[str] = []
    seen: set[str] = set()
    for path in claimed:
        if path in seen:
            continue
        seen.add(path)
        if index.resolve(path) is None:
            invalid.append(path)
    return invalid


def parse_citation_string(raw: str) -> Citation | None:
    """Parse ``path:12-40`` / ``path:12`` / ``path`` into a Citation."""
    raw = (raw or "").strip().strip("`")
    if not raw:
        return None
    match = re.match(
        r"^(.+?)(?::(\d+)(?:-(\d+))?)?$",
        raw,
    )
    if not match:
        return None
    path = _normalize_path(match.group(1))
    if not path:
        return None
    start = int(match.group(2)) if match.group(2) else 0
    end = int(match.group(3)) if match.group(3) else 0
    return Citation(path=path, start_line=start, end_line=end)


def format_citation(cite: Citation) -> str:
    loc = cite.path.replace("\\", "/")
    if cite.start_line:
        loc += f":{cite.start_line}"
        if cite.end_line and cite.end_line != cite.start_line:
            loc += f"-{cite.end_line}"
    return loc


def _verify_file_doc(doc: FileDoc, index: CiteIndex) -> tuple[FileDoc | None, bool]:
    resolved = index.resolve(doc.path)
    if not resolved:
        return None, False
    doc.path = resolved
    for symbol in doc.key_symbols:
        if symbol.line:
            symbol.line = index.clamp_line(resolved, symbol.line)
        if symbol.description:
            symbol.description = sanitize_text(symbol.description, index)
    doc.purpose = sanitize_text(doc.purpose, index)
    return doc, True


def _clamp_citation(cite: Citation, index: CiteIndex) -> Citation | None:
    resolved = index.resolve(cite.path)
    if not resolved:
        return None
    cite.path = resolved
    cite.start_line = index.clamp_line(resolved, cite.start_line)
    cite.end_line = index.clamp_line(resolved, cite.end_line)
    if cite.end_line and cite.start_line and cite.end_line < cite.start_line:
        cite.end_line = 0
    cite.note = sanitize_text(cite.note, index)
    return cite


def _normalize_path(path: str) -> str:
    path = (path or "").strip().replace("\\", "/")
    while path.startswith("./"):
        path = path[2:]
    return path.strip("/")


def _line_count(f: FileInfo) -> int:
    if f.lines:
        return f.lines
    text = f.content or f.preview or ""
    if not text:
        return 0
    return text.count("\n") + 1


def _add_path_tokens(tokens: set[str], path: str) -> None:
    for part in path.replace("\\", "/").split("/"):
        if not part:
            continue
        stem = part.rsplit(".", 1)[0].lower()
        tokens.add(stem)
        tokens.add(part.lower())
        for bit in re.split(r"[-_]", stem):
            if len(bit) >= 2:
                tokens.add(bit)
    if "crates" in tokens:
        tokens.add("crate")


def _add_ident_tokens(tokens: set[str], text: str) -> None:
    for ident in _IDENT.findall(text or ""):
        low = ident.lower()
        tokens.add(low)
        for part in _CAMEL.findall(ident):
            if len(part) >= 2:
                tokens.add(part.lower())
