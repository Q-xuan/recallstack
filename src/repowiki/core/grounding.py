"""Hard constraint: wiki prose may only cite this version's tree.

Analyzer / LLM memory (grok-study ``xai-grok-pager``, ``start_turn``) is dropped
unless that path or symbol exists in ``version_files`` / the scan tree.
"""

from __future__ import annotations

import re
from typing import Any

from repowiki.core.cite_check import CiteIndex
from repowiki.core.models import (
    ArchitectureDiagram,
    CodebasePart,
    FileInfo,
    ProjectContext,
    ProjectOverview,
    WikiData,
)

# Bump when grounding rules change so the same content_hash is rescanned.
WIKI_GROUND_REVISION = 1

# Training-memory product tokens. Kept only when the tree actually has them.
_FOREIGN_PRODUCT_CRATES = (
    "xai-grok-pager",
    "xai-grok-agent",
    "xai-grok-tools",
    "xai-grok-auth",
    "xai-grok-code",
)
_FOREIGN_SYMBOLS = (
    "start_turn",
    "TuiPager",
    "TurnRunning",
    "on_turn_done",
    "AgentLoop",
    "PtyHandle",
    "ToolBridge",
    "Pager",
)
_CRATE_PATH_RE = re.compile(
    r"(?:packages|crates|apps|vendor|src)/[A-Za-z0-9_./@-]+",
    re.I,
)
_XAI_GROK_RE = re.compile(r"(?:packages/|crates/(?:codegen/)?)?xai-grok-[\w.-]+", re.I)
_SENTENCE_SPLIT = re.compile(r"(?<=[。！？.!?\n])")
_MERMAID_NODE = re.compile(
    r'([A-Za-z][\w-]*)\s*\[\s*"?([^"\]]+)"?\s*\]'
)
_MERMAID_PARTICIPANT = re.compile(
    r"^\s*participant\s+(\w+)(?:\s+as\s+(.+))?\s*$",
    re.I,
)
_MERMAID_FENCE_RE = re.compile(r"(?ms)^```mermaid\n(.*?)```")
_SAFE_MERMAID_LABELS = {
    "entry",
    "core",
    "seam",
    "model",
    "plugin",
    "ctx",
    "harness",
    "boot",
    "main",
    "llm",
    "fs",
    "provider",
    "consumer",
    "definition",
    "入口",
    "核心",
    "调用",
}


def cite_index_from_texts(file_texts: dict[str, str] | None) -> CiteIndex:
    """Build a CiteIndex from version_files / scan-tree text."""
    files: list[FileInfo] = []
    for path, text in (file_texts or {}).items():
        body = text or ""
        files.append(
            FileInfo(
                path=path,
                size=len(body),
                language="unknown",
                lines=body.count("\n") + 1,
                content=body,
                preview=body[:400],
            )
        )
    return CiteIndex.from_project(ProjectContext(name="", root=".", files=files))


def location_in_tree(index: CiteIndex, location: str) -> bool:
    """True when ``location`` is a version_files key or a directory prefix of one."""
    loc = (location or "").strip().replace("\\", "/")
    while loc.startswith("./"):
        loc = loc[2:]
    loc = loc.strip("/")
    if not loc:
        return False
    if index.resolve(loc):
        return True
    prefix = loc.rstrip("/") + "/"
    return any(p == loc or p.startswith(prefix) for p in index.paths)


def symbol_in_tree(index: CiteIndex, symbol: str) -> bool:
    name = (symbol or "").strip()
    if len(name) < 2:
        return False
    return index.has_term(name)


def _ungrounded_product_spans(text: str, index: CiteIndex) -> list[str]:
    """Crate / symbol / path mentions that are not in this tree."""
    hits: list[str] = []
    for match in _XAI_GROK_RE.finditer(text or ""):
        raw = match.group(0)
        leaf = raw.replace("\\", "/").rstrip("/").split("/")[-1]
        if not symbol_in_tree(index, leaf) and not location_in_tree(index, raw):
            hits.append(raw)
    for match in _CRATE_PATH_RE.finditer(text or ""):
        raw = match.group(0).rstrip(".,;:)")
        if not location_in_tree(index, raw):
            hits.append(raw)
    for name in _FOREIGN_SYMBOLS:
        if symbol_in_tree(index, name):
            continue
        if re.search(r"(?<![A-Za-z0-9_])" + re.escape(name) + r"(?![A-Za-z0-9_])", text or ""):
            hits.append(name)
    for name in _FOREIGN_PRODUCT_CRATES:
        if symbol_in_tree(index, name) or location_in_tree(index, name):
            continue
        if re.search(r"(?<![A-Za-z0-9_])" + re.escape(name) + r"(?![A-Za-z0-9_])", text or "", re.I):
            hits.append(name)
    return hits


def text_cites_foreign_tree(text: str, index: CiteIndex) -> bool:
    """True when prose/mermaid names a path or symbol missing from this tree."""
    return bool(_ungrounded_product_spans(text or "", index))


def scrub_ungrounded_prose(text: str, index: CiteIndex) -> str:
    """Drop sentences that name crates/symbols/paths not in version_files."""
    if not text:
        return text
    from repowiki.core.cite_check import sanitize_text

    cleaned = sanitize_text(text, index)
    parts = _SENTENCE_SPLIT.split(cleaned)
    kept: list[str] = []
    for part in parts:
        if text_cites_foreign_tree(part, index):
            continue
        kept.append(part)
    out = "".join(kept)
    out = re.sub(r"[ \t]{2,}", " ", out)
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out.strip()


def _label_is_grounded(label: str, index: CiteIndex) -> bool:
    raw = re.sub(r"\s+", " ", (label or "").strip())
    if not raw:
        return False
    low = raw.lower()
    if low in _SAFE_MERMAID_LABELS:
        return True
    if location_in_tree(index, raw) or symbol_in_tree(index, raw):
        return True
    if _XAI_GROK_RE.search(raw) or raw in _FOREIGN_SYMBOLS or raw in _FOREIGN_PRODUCT_CRATES:
        return False
    if _CRATE_PATH_RE.search(raw) and not location_in_tree(index, raw):
        return False
    # Short conceptual labels (Capability Seam / Cordis / Plugin) stay.
    if " " in raw or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", raw):
        return not text_cites_foreign_tree(raw, index)
    return symbol_in_tree(index, raw) or low in _SAFE_MERMAID_LABELS


def sanitize_mermaid_to_tree(source: str, index: CiteIndex) -> str:
    """Drop mermaid nodes whose labels are crates/symbols missing from the tree."""
    text = (source or "").strip()
    if not text:
        return text
    drop_ids: set[str] = set()
    drop_names: set[str] = set()
    for match in _MERMAID_NODE.finditer(text):
        nid, label = match.group(1), match.group(2)
        if not _label_is_grounded(label, index):
            drop_ids.add(nid)
            drop_names.add(re.sub(r"\s+", " ", label).strip())
    for match in _MERMAID_PARTICIPANT.finditer(text):
        alias = (match.group(2) or match.group(1) or "").strip()
        nid = match.group(1)
        if alias and not _label_is_grounded(alias, index):
            drop_ids.add(nid)
            drop_names.add(alias)
    if not drop_ids and not drop_names:
        if text_cites_foreign_tree(text, index):
            return ""
        return text
    out: list[str] = []
    for line in text.splitlines():
        node = _MERMAID_NODE.search(line)
        if node and node.group(1) in drop_ids:
            continue
        part = _MERMAID_PARTICIPANT.match(line)
        if part and part.group(1) in drop_ids:
            continue
        edge = re.match(
            r"^(\s*)([A-Za-z][\w-]*)\s*(?:-->|->>|-->>|-.)\s*([A-Za-z][\w-]*)",
            line,
        )
        if edge and (edge.group(2) in drop_ids or edge.group(3) in drop_ids):
            continue
        if any(re.search(r"(?<![A-Za-z0-9_])" + re.escape(n) + r"(?![A-Za-z0-9_])", line) for n in drop_names):
            continue
        out.append(line)
    kept_nodes = [ln for ln in out if _MERMAID_NODE.search(ln) or _MERMAID_PARTICIPANT.match(ln)]
    if len(kept_nodes) < 2:
        return ""
    return "\n".join(out).strip()


def _scrub_codebase_parts(rows: list[CodebasePart], index: CiteIndex) -> list[CodebasePart]:
    kept: list[CodebasePart] = []
    for row in rows or []:
        loc = (row.location or "").strip()
        name = (row.name or "").strip()
        if loc and not location_in_tree(index, loc):
            continue
        if name and not (
            symbol_in_tree(index, name) or location_in_tree(index, name) or location_in_tree(index, loc)
        ):
            continue
        row.purpose = scrub_ungrounded_prose(row.purpose, index)
        if text_cites_foreign_tree(f"{row.name} {row.location} {row.purpose}", index):
            continue
        kept.append(row)
    return kept


def ground_overview(overview: ProjectOverview, index: CiteIndex) -> ProjectOverview:
    """Strip overview fields that name paths/symbols missing from this tree."""
    overview.description = scrub_ungrounded_prose(overview.description, index)
    overview.one_liner = scrub_ungrounded_prose(overview.one_liner, index)
    overview.document_scope = scrub_ungrounded_prose(
        getattr(overview, "document_scope", "") or "", index
    )
    overview.runtime_flow = scrub_ungrounded_prose(
        getattr(overview, "runtime_flow", "") or "", index
    )
    overview.what_it_is = [
        s
        for s in (
            scrub_ungrounded_prose(item, index)
            for item in (getattr(overview, "what_it_is", None) or [])
        )
        if s
    ]
    overview.key_features = [
        s
        for s in (scrub_ungrounded_prose(item, index) for item in overview.key_features)
        if s
    ]
    overview.setup_instructions = [
        s
        for s in (scrub_ungrounded_prose(item, index) for item in overview.setup_instructions)
        if s
    ]
    overview.mermaid_component = sanitize_mermaid_to_tree(
        getattr(overview, "mermaid_component", "") or "", index
    )
    overview.codebase_structure = _scrub_codebase_parts(
        list(getattr(overview, "codebase_structure", None) or []), index
    )
    for sub in getattr(overview, "subsystems", None) or []:
        sub.role = scrub_ungrounded_prose(sub.role, index)
        sub.mermaid = sanitize_mermaid_to_tree(getattr(sub, "mermaid", "") or "", index)
        if text_cites_foreign_tree(sub.name or "", index):
            sub.name = ""
    overview.subsystems = [
        s
        for s in (getattr(overview, "subsystems", None) or [])
        if (s.name or "").strip() and not text_cites_foreign_tree(s.name, index)
    ]
    return overview


def ground_architecture(arch: ArchitectureDiagram, index: CiteIndex) -> ArchitectureDiagram:
    arch.description = scrub_ungrounded_prose(arch.description, index)
    arch.data_flow = scrub_ungrounded_prose(arch.data_flow, index)
    arch.mermaid_component = sanitize_mermaid_to_tree(arch.mermaid_component or "", index)
    arch.mermaid_sequence = sanitize_mermaid_to_tree(
        getattr(arch, "mermaid_sequence", "") or "", index
    )
    kept = []
    for comp in arch.components:
        if text_cites_foreign_tree(comp.name or "", index):
            continue
        comp.purpose = scrub_ungrounded_prose(comp.purpose, index)
        comp.role = scrub_ungrounded_prose(getattr(comp, "role", "") or "", index)
        kept.append(comp)
    arch.components = kept
    return arch


def ground_wiki_data(data: WikiData, index: CiteIndex) -> WikiData:
    data.overview = ground_overview(data.overview, index)
    data.architecture = ground_architecture(data.architecture, index)
    if data.outline:
        data.outline.overview_focus = scrub_ungrounded_prose(
            data.outline.overview_focus, index
        )
        data.outline.architecture_focus = scrub_ungrounded_prose(
            data.outline.architecture_focus, index
        )
    return data


def overview_cites_foreign_tree(overview: ProjectOverview, index: CiteIndex) -> bool:
    blob = "\n".join(
        [
            overview.description or "",
            overview.one_liner or "",
            getattr(overview, "document_scope", "") or "",
            getattr(overview, "runtime_flow", "") or "",
            getattr(overview, "mermaid_component", "") or "",
            " ".join(getattr(overview, "what_it_is", None) or []),
            " ".join(
                f"{p.name} {p.location} {p.purpose}"
                for p in (getattr(overview, "codebase_structure", None) or [])
            ),
        ]
    )
    return text_cites_foreign_tree(blob, index)


def architecture_cites_foreign_tree(arch: ArchitectureDiagram, index: CiteIndex) -> bool:
    blob = "\n".join(
        [
            arch.description or "",
            arch.data_flow or "",
            arch.mermaid_component or "",
            getattr(arch, "mermaid_sequence", "") or "",
            " ".join(c.name for c in arch.components),
            " ".join(" ".join(c.files) for c in arch.components),
        ]
    )
    return text_cites_foreign_tree(blob, index)


def wiki_payload_cites_foreign_tree(
    payload: dict[str, Any] | None, file_texts: dict[str, str] | None
) -> bool:
    """True when persisted overview/architecture names symbols missing from version_files."""
    if not isinstance(payload, dict):
        return False
    index = cite_index_from_texts(file_texts)
    for page in payload.get("pages") or []:
        if not isinstance(page, dict):
            continue
        pid = str(page.get("id") or "")
        if pid not in {"index", "architecture"}:
            continue
        if text_cites_foreign_tree(str(page.get("content") or ""), index):
            return True
    return False


def should_reuse_analyzed_wiki(
    payload: dict[str, Any] | None, file_texts: dict[str, str] | None
) -> bool:
    """Same content_hash may still need a rewrite when grounding rules moved."""
    if not isinstance(payload, dict) or not (payload.get("pages") or []):
        return False
    if int(payload.get("ground_revision") or 0) != WIKI_GROUND_REVISION:
        return False
    return not wiki_payload_cites_foreign_tree(payload, file_texts)


def scrub_wiki_page_content(content: str, index: CiteIndex) -> str:
    """GET/materialize: drop ungrounded mermaid nodes and sentences."""
    if not content:
        return content
    def fence_repl(match: re.Match[str]) -> str:
        body = sanitize_mermaid_to_tree(match.group(1), index)
        if not body:
            return ""
        return f"```mermaid\n{body}\n```"

    out = _MERMAID_FENCE_RE.sub(fence_repl, content)
    return scrub_ungrounded_prose(out, index)


def tree_has_grok_product(*blobs: str) -> bool:
    text = "\n".join(blobs).lower()
    return any(
        tok in text
        for tok in (
            "xai-grok-pager",
            "xai-grok-agent",
            "xai-grok-tools",
            "/bin/grok",
            "start_turn",
        )
    )
