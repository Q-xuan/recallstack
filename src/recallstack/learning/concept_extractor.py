"""Extract learning concepts from RepoWiki scan signals.

Primary path is deterministic (no LLM required). Optional LLM enrichment.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

from recallstack.domain.schemas import ConceptDraft, ConceptGenerationResult, SourceReference
from recallstack.learning.i18n import content_lang, t
from recallstack.learning.learning_contract import (
    bind_concept_source_references,
    definition_index_scope,
)
from recallstack.security import filter_source_references
from repowiki.core.graph import DependencyGraph
from repowiki.core.models import ProjectContext

_SLUG_RE = re.compile(r"[^a-z0-9]+")
_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
_HTML_BLOCK_RE = re.compile(
    r"<(picture|div|table|center)\b[^>]*>.*?</\1\s*>",
    re.I | re.S,
)
_SELF_CLOSING_RE = re.compile(r"<(img|br|hr|source|meta|link)\b[^>]*/?>", re.I)
_TAG_RE = re.compile(r"<[^>]+>")
_HTML_OPEN_RE = re.compile(
    r"</?(div|picture|source|img|table|thead|tbody|tr|td|th|center)\b",
    re.I,
)
_BLOCK_OPEN_RE = re.compile(r"<(div|picture|table|center)\b", re.I)
_BLOCK_CLOSE_RE = re.compile(r"</(div|picture|table|center)\s*>", re.I)
_BADGE_LINE_RE = re.compile(r"^\s*(\[!\[[^\]]*\]\([^)]+\)\]\([^)]+\)\s*)+$")
_LOGO_IMAGE_RE = re.compile(r"^!\[.*logo.*\]\(", re.I)


def slugify(text: str) -> str:
    s = _SLUG_RE.sub("-", text.lower()).strip("-")
    return s or "concept"


def readme_prose_excerpt(
    text: str,
    *,
    max_paragraphs: int = 3,
    max_chars: int = 1200,
) -> str:
    """First 1–3 prose markdown paragraphs from a README. Never returns HTML.

    Skips ``<picture>`` / centered logo / badge chrome. Headings like ``# Title``
    are kept. Empty string means “nothing usable” — callers should fall back to
    a generic one-liner rather than pasting raw README HTML.
    """
    if not (text or "").strip():
        return ""

    raw = text.replace("\r\n", "\n")
    raw = _HTML_COMMENT_RE.sub("", raw)
    prev = None
    while prev != raw:
        prev = raw
        raw = _HTML_BLOCK_RE.sub("\n", raw)
        raw = _SELF_CLOSING_RE.sub("", raw)

    kept_lines: list[str] = []
    skipping_html = False
    for line in raw.split("\n"):
        stripped = line.strip()
        low = stripped.lower()
        if skipping_html:
            if _BLOCK_CLOSE_RE.search(low):
                skipping_html = False
            elif stripped.startswith("#") and "<" not in stripped:
                skipping_html = False
                kept_lines.append(stripped)
            continue
        if (
            _HTML_OPEN_RE.search(stripped)
            or "srcset=" in low
            or 'align="center"' in low
            or "align='center'" in low
        ):
            if _BLOCK_OPEN_RE.search(stripped) and not _BLOCK_CLOSE_RE.search(low):
                skipping_html = True
            continue
        if _BADGE_LINE_RE.match(stripped) or (
            stripped.startswith("[![") and stripped.endswith(")")
        ):
            continue
        if _LOGO_IMAGE_RE.match(stripped):
            continue
        if stripped.startswith("<") and ">" in stripped and not stripped.startswith("<http"):
            continue
        cleaned = _TAG_RE.sub("", line).strip()
        if "<" in cleaned:
            continue
        kept_lines.append(cleaned)

    paragraphs: list[str] = []
    buf: list[str] = []

    def flush() -> None:
        if not buf:
            return
        para = " ".join(buf).strip()
        buf.clear()
        if para:
            paragraphs.append(para)

    for line in kept_lines:
        if not line:
            flush()
            continue
        buf.append(line)
    flush()

    usable: list[str] = []
    for para in paragraphs:
        if len(para) < 4:
            continue
        if para.startswith("[!"):
            continue
        if not re.search(r"[A-Za-z\u4e00-\u9fff]", para):
            continue
        usable.append(para)
        if len(usable) >= max_paragraphs:
            break

    excerpt = "\n\n".join(usable).strip()
    if len(excerpt) > max_chars:
        excerpt = excerpt[: max_chars - 1].rsplit(" ", 1)[0].rstrip() + "…"
    if "<" in excerpt:
        return ""
    if not re.search(r"[A-Za-z\u4e00-\u9fff]", excerpt):
        return ""
    return excerpt


def content_hash_for(parts: list[str]) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update(p.encode("utf-8", errors="ignore"))
        h.update(b"\0")
    return h.hexdigest()[:24]


class ConceptExtractor:
    def __init__(self, max_concepts: int = 20):
        self.max_concepts = max_concepts

    def extract(
        self,
        project: ProjectContext,
        graph: DependencyGraph,
        *,
        commit_sha: str = "",
        wiki_summary: str = "",
        topics=None,
    ) -> ConceptGenerationResult:
        ranked = graph.rank_files()
        files_by_path = {f.path: f for f in project.files}
        valid_paths = set(files_by_path)

        if topics is None:
            from repowiki.core.topics import build_deterministic_topics

            topics = build_deterministic_topics(
                project, graph, language=content_lang()
            )

        from recallstack.learning.topic_plan import topics_to_concepts

        store = {
            (f.path or "").replace("\\", "/"): (f.content or f.preview or "")
            for f in project.files
            if (f.content or f.preview)
        }
        with definition_index_scope(store):
            drafts = topics_to_concepts(
                topics,
                project,
                commit_sha=commit_sha,
                files_by_path=files_by_path,
                make_refs=self._refs,
            )
        goal = next((d for d in drafts if d.slug == "project-goal"), None)
        if goal:
            readme = self._find_readme(project)
            desc = self._project_goal_desc(project, readme)
            if desc:
                goal.description = desc
            if wiki_summary and len(desc) < 80:
                goal.description = wiki_summary[:1200]

        # validate source refs
        cleaned: list[ConceptDraft] = []
        for d in drafts[: self.max_concepts]:
            refs = filter_source_references(
                [r.model_dump() for r in d.source_references], valid_paths
            )
            if not refs and d.slug != "project-goal":
                continue
            cleaned.append(
                d.model_copy(
                    update={
                        "source_references": [SourceReference.model_validate(r) for r in refs]
                        if refs
                        else d.source_references
                    }
                )
            )

        if not cleaned:
            top = [p for p, _ in ranked[:3]] or [f.path for f in project.files[:3]]
            cleaned = [
                ConceptDraft(
                    slug="project-goal",
                    title=t("Project goal", "项目目标"),
                    description=t(
                        f"{project.name}: who it is for, what it solves, and what it does not do.",
                        f"{project.name}：给谁用、解决什么、明确不做什么。",
                    ),
                    difficulty=1,
                    importance=1.0,
                    why_learn=t(
                        "State the goal before reading any system page.",
                        "先讲清目标，再读各个系统页。",
                    ),
                    source_references=self._refs(top, files_by_path, commit_sha),
                    wiki_page_id="index",
                )
            ]

        for c in cleaned:
            c.prerequisites = [p for p in c.prerequisites if p != c.slug]

        return ConceptGenerationResult(concepts=cleaned)

    def remove_cyclic_prerequisites(
        self, concepts: list[ConceptDraft]
    ) -> list[ConceptDraft]:
        """Remove prerequisite edges that participate in cycles."""
        by_slug = {c.slug: c for c in concepts}
        graph: dict[str, set[str]] = {c.slug: set(c.prerequisites) for c in concepts}

        # Kahn-like: repeatedly remove edges that keep cycles
        def has_cycle(g: dict[str, set[str]]) -> list[str] | None:
            temp: set[str] = set()
            perm: set[str] = set()
            cycle_node: list[str] = []

            def visit(n: str) -> bool:
                if n in perm:
                    return False
                if n in temp:
                    cycle_node.append(n)
                    return True
                temp.add(n)
                for m in g.get(n, set()):
                    if m in g and visit(m):
                        return True
                temp.remove(n)
                perm.add(n)
                return False

            for node in list(g):
                if visit(node):
                    return cycle_node
            return None

        # remove edges until acyclic
        guard = 0
        while guard < 100:
            guard += 1
            cyc = has_cycle(graph)
            if not cyc:
                break
            # remove one edge from cycle node
            n = cyc[0]
            if graph[n]:
                graph[n].pop()
            else:
                break

        result = []
        for c in concepts:
            prereqs = [p for p in graph.get(c.slug, set()) if p in by_slug]
            result.append(c.model_copy(update={"prerequisites": prereqs}))
        return result

    def _module_name(self, path: str) -> str:
        parts = Path(path.replace("\\", "/")).parts
        if not parts:
            return "root"
        if parts[0] in {"src", "lib", "app", "pkg"} and len(parts) > 1:
            return parts[1]
        return parts[0]

    def _find_readme(self, project: ProjectContext) -> str | None:
        for f in project.files:
            name = Path(f.path).name.lower()
            if name in {"readme.md", "readme.rst", "readme.txt", "readme"}:
                return f.path
        return None

    def _project_goal_desc(self, project: ProjectContext, readme: str | None) -> str:
        fallback = t(
            f"{project.name}: who it is for, what it solves, and what it does not do.",
            f"{project.name}：给谁用、解决什么、明确不做什么。",
        )
        if not readme:
            return fallback
        for f in project.files:
            if f.path == readme and (f.preview or f.content):
                excerpt = readme_prose_excerpt(f.preview or f.content or "")
                return excerpt or fallback
        return fallback

    def _refs(
        self,
        paths: list[str],
        files_by_path: dict[str, Any],
        commit_sha: str,
        slug: str = "",
    ) -> list[SourceReference]:
        store = {
            (p or "").replace("\\", "/"): (getattr(f, "content", None) or getattr(f, "preview", None) or "")
            for p, f in (files_by_path or {}).items()
            if f and (getattr(f, "content", None) or getattr(f, "preview", None))
        }
        return bind_concept_source_references(
            paths, store, slug=slug, commit_sha=commit_sha
        )
