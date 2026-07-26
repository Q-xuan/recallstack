"""Deterministic full-text search over a generated wiki.

Search is the feature that turns a pile of generated pages into a wiki you can
actually use, so it must work without an LLM and without an index server. The
corpus is small (tens to low hundreds of pages held in one JSON column), so a
scan-and-score pass per query is fast enough and keeps the storage model simple.

Ranking is field-weighted: a hit in the title beats a hit in a heading, which
beats a hit in the body. Pages that match *every* query term are boosted above
pages that match only some, and an exact phrase hit outranks both.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

# Latin/number runs and CJK runs are tokenised separately: CJK text has no
# spaces, so whitespace splitting would collapse a whole sentence into one term.
_TOKEN_RE = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.\-]*|[一-鿿]+")
_CJK_RE = re.compile(r"[一-鿿]")
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*$", re.MULTILINE)
_CODE_FENCE_RE = re.compile(r"```[\s\S]*?```")

TITLE_WEIGHT = 14.0
HEADING_WEIGHT = 5.0
BODY_WEIGHT = 1.0
PATH_WEIGHT = 3.0
PHRASE_BONUS = 25.0
COVERAGE_BONUS = 18.0

# Reading order matters more than alphabetical order when scores tie: the
# overview should win a tie against a leaf concept page.
_KIND_PRIORITY = {
    "overview": 3.0,
    "architecture": 2.5,
    "guide": 2.0,
    "module": 1.0,
    "concept": 0.5,
    "page": 0.0,
}


@dataclass
class SearchDocument:
    """One searchable wiki page, pre-lowercased for repeated matching."""

    page_id: str
    title: str
    kind: str
    content: str
    paths: list[str] = field(default_factory=list)
    concept_id: str | None = None

    def __post_init__(self) -> None:
        body = _CODE_FENCE_RE.sub(" ", self.content)
        self._title_lc = self.title.lower()
        self._headings_lc = " \n".join(m.group(2) for m in _HEADING_RE.finditer(body)).lower()
        self._body_lc = body.lower()
        self._paths_lc = " ".join(self.paths).lower()


def tokenize(text: str) -> list[str]:
    """Split a query into match terms, expanding long CJK runs into bigrams.

    A user typing 依赖图构建 should still match a page containing 依赖图, so runs
    longer than two characters contribute their bigrams as additional terms.
    """
    terms: list[str] = []
    for raw in _TOKEN_RE.findall(text.lower()):
        if _CJK_RE.match(raw) and len(raw) > 2:
            terms.extend(raw[i : i + 2] for i in range(len(raw) - 1))
        else:
            terms.append(raw)
    # Preserve order while dropping duplicates so snippet selection stays stable.
    seen: set[str] = set()
    unique: list[str] = []
    for term in terms:
        if term not in seen:
            seen.add(term)
            unique.append(term)
    return unique


def classify_page(page_id: str) -> str:
    if page_id == "index":
        return "overview"
    if page_id == "architecture":
        return "architecture"
    if page_id in {"reading-guide", "dependencies"}:
        return "guide"
    if page_id.startswith("concepts/"):
        return "concept"
    if page_id.startswith("modules/"):
        return "module"
    return "page"


def _count(haystack: str, needle: str, cap: int) -> int:
    if not needle or not haystack:
        return 0
    return min(haystack.count(needle), cap)


def _score(doc: SearchDocument, terms: list[str], phrase: str) -> tuple[float, int]:
    score = 0.0
    matched = 0
    for term in terms:
        title_hits = _count(doc._title_lc, term, 3)
        heading_hits = _count(doc._headings_lc, term, 5)
        body_hits = _count(doc._body_lc, term, 8)
        path_hits = _count(doc._paths_lc, term, 4)
        if not (title_hits or heading_hits or body_hits or path_hits):
            continue
        matched += 1
        score += (
            TITLE_WEIGHT * title_hits
            + HEADING_WEIGHT * heading_hits
            + BODY_WEIGHT * body_hits
            + PATH_WEIGHT * path_hits
        )
    if not matched:
        return 0.0, 0
    if phrase and (phrase in doc._title_lc or phrase in doc._body_lc):
        score += PHRASE_BONUS
    if matched == len(terms) and len(terms) > 1:
        score += COVERAGE_BONUS
    return score + _KIND_PRIORITY.get(doc.kind, 0.0), matched


def _snippet(doc: SearchDocument, terms: list[str], width: int = 180) -> str:
    """Return a one-line excerpt centred on the earliest matching term."""
    plain = re.sub(r"[`*>#\[\]]", "", _CODE_FENCE_RE.sub(" ", doc.content))
    plain = re.sub(r"\s+", " ", plain).strip()
    if not plain:
        return ""
    lowered = plain.lower()
    positions = [pos for pos in (lowered.find(t) for t in terms) if pos >= 0]
    if not positions:
        return plain[:width].strip()
    start = max(0, min(positions) - width // 3)
    excerpt = plain[start : start + width].strip()
    prefix = "…" if start > 0 else ""
    suffix = "…" if start + width < len(plain) else ""
    return f"{prefix}{excerpt}{suffix}"


def build_documents(
    pages: list[dict[str, Any]],
    concept_paths: dict[str, list[str]] | None = None,
    concept_ids: dict[str, str] | None = None,
) -> list[SearchDocument]:
    """Turn stored wiki page dicts into search documents.

    ``concept_paths`` lets a concept page be found by the source files it cites,
    which is how someone searches for "scanner.py" and lands on the concept that
    explains it.
    """
    concept_paths = concept_paths or {}
    concept_ids = concept_ids or {}
    docs: list[SearchDocument] = []
    for page in pages:
        page_id = page.get("id") or ""
        if not page_id:
            continue
        slug = page_id.split("/", 1)[1] if page_id.startswith("concepts/") else ""
        docs.append(
            SearchDocument(
                page_id=page_id,
                title=page.get("title") or page_id,
                kind=classify_page(page_id),
                content=page.get("content") or "",
                paths=concept_paths.get(slug, []),
                concept_id=concept_ids.get(slug),
            )
        )
    return docs


def search(
    docs: list[SearchDocument], query: str, limit: int = 20
) -> list[dict[str, Any]]:
    """Rank ``docs`` against ``query``; returns serialisable result dicts."""
    query = (query or "").strip()
    if not query:
        return []
    terms = tokenize(query)
    if not terms:
        return []
    phrase = query.lower() if len(query) >= 3 else ""

    scored: list[tuple[float, int, SearchDocument]] = []
    for doc in docs:
        score, matched = _score(doc, terms, phrase)
        if score > 0:
            scored.append((score, matched, doc))

    scored.sort(key=lambda row: (-row[0], row[2].title.lower()))
    results = []
    for score, matched, doc in scored[:limit]:
        results.append(
            {
                "page_id": doc.page_id,
                "title": doc.title,
                "kind": doc.kind,
                "score": round(score, 2),
                "matched_terms": matched,
                "snippet": _snippet(doc, terms),
                "concept_id": doc.concept_id,
            }
        )
    return results
