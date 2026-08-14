"""Materialize wiki markdown and path chips once; GET stays a cheap read.

Serve-time used to re-upgrade every page and walk the full scan store on each
GET. Persist the result (analyze, or first successful upgrade) under
``serve_revision`` so later requests skip the store.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm.attributes import flag_modified

from recallstack.learning.i18n import content_lang
from recallstack.learning.learning_contract import (
    CORE_PATH_CAP,
    definition_index_scope,
    drop_duplicate_entry_slug,
    fill_wiki_key_type_lines,
    is_filler_slug_title,
    is_shallow_path_leaf,
    is_web_filler_path_slug,
    path_evidence_chip,
    path_rank,
    upgrade_legacy_concept_markdown,
    wiki_prose_excerpt,
)
from recallstack.learning.wiki_generator import link_reading_guide_markdown
from repowiki.core.topics import (
    is_generic_web_slug,
    omit_generic_web_wiki_page,
    omit_unusable_topic_stub,
)
from repowiki.core.wiki_builder import (
    enrich_overview_from_topic_pages,
    ensure_reading_ia_sidebar,
    prune_generic_web_sidebar,
    prune_sidebar_missing_pages,
    rank_and_cap_directory_sidebar,
    rebuild_topic_sidebar,
    sidebar_has_topic_groups,
    upgrade_legacy_module_markdown,
    upgrade_wiki_page_content,
)

logger = logging.getLogger(__name__)

# Bump when materialize logic changes so stale persisted pages re-upgrade once.
WIKI_SERVE_REVISION = 1
PATH_SERVE_REVISION = 1


def wiki_is_materialized(payload: dict[str, Any] | None) -> bool:
    return isinstance(payload, dict) and payload.get("serve_revision") == WIKI_SERVE_REVISION


def path_is_materialized(resolved: dict[str, Any] | None) -> bool:
    return isinstance(resolved, dict) and resolved.get("serve_revision") == PATH_SERVE_REVISION


def kept_wiki_pages(raw_pages: list[Any]) -> list[dict[str, Any]]:
    kept: list[dict[str, Any]] = []
    for item in raw_pages or []:
        if not isinstance(item, dict):
            continue
        page_id = str(item.get("id") or "")
        content = str(item.get("content") or "")
        if omit_generic_web_wiki_page(page_id, content):
            continue
        if omit_unusable_topic_stub(
            page_id, content, title=str(item.get("title") or "")
        ):
            continue
        kept.append(item)
    return kept


def materialize_wiki_payload(
    payload: dict[str, Any] | None,
    concepts: list[Any] | None,
    file_texts: dict[str, str] | None,
) -> dict[str, Any]:
    """Upgrade pages + sidebar once. Safe to call again (idempotent)."""
    src = dict(payload or {})
    concept_list = list(concepts or [])
    concept_by_slug = {getattr(c, "slug", ""): c for c in concept_list if getattr(c, "slug", None)}
    raw_pages = src.get("pages") or []
    kept_pages = kept_wiki_pages(raw_pages)
    page_ids = {item.get("id") for item in kept_pages}
    known_ids = {str(i) for i in page_ids if i}
    lang = content_lang()
    overview_excerpt = wiki_prose_excerpt(
        next(
            (item.get("content") or "" for item in kept_pages if item.get("id") == "index"),
            "",
        )
    )
    store = file_texts or {}
    upgraded: list[dict[str, Any]] = []
    with definition_index_scope(store):
        for p in kept_pages:
            page_id = str(p.get("id") or "")
            content = p.get("content") or ""
            if page_id.startswith("concepts/"):
                slug = page_id.split("/", 1)[1]
                concept = concept_by_slug.get(slug)
                content = upgrade_legacy_concept_markdown(
                    content,
                    slug=slug,
                    title=(getattr(concept, "title", None) if concept else p.get("title")) or "",
                    has_overview="index" in page_ids,
                    has_architecture="architecture" in page_ids,
                    overview_excerpt=overview_excerpt if slug == "project-goal" else "",
                )
            elif page_id.startswith("modules/"):
                content = upgrade_legacy_module_markdown(content, language=lang)
            content = upgrade_wiki_page_content(
                content, known_ids, language=lang, page_id=page_id
            )
            if page_id == "reading-guide":
                content = link_reading_guide_markdown(content, concept_list)
            if store:
                content = fill_wiki_key_type_lines(content, store)
            upgraded.append(
                {
                    "id": page_id,
                    "title": p.get("title") or page_id,
                    "content": content,
                    "parent_id": p.get("parent_id") or "",
                    "order": int(p.get("order") or 0),
                }
            )
        enrich_overview_from_topic_pages(upgraded)
        if store:
            for item in upgraded:
                if item.get("id") == "index":
                    item["content"] = fill_wiki_key_type_lines(
                        item.get("content") or "", store
                    )
                    break

    content_by_id = {item.get("id") or "": item.get("content") or "" for item in upgraded}
    page_id_set = {str(item.get("id") or "") for item in upgraded if item.get("id")}
    raw_sidebar = src.get("sidebar") or []
    if not sidebar_has_topic_groups(raw_sidebar):
        ranked = rebuild_topic_sidebar(upgraded, language=lang)
    else:
        ranked = raw_sidebar
    ranked = ensure_reading_ia_sidebar(ranked, upgraded, language=lang)
    ranked = rank_and_cap_directory_sidebar(
        prune_sidebar_missing_pages(
            prune_generic_web_sidebar(ranked, content_by_id),
            page_id_set,
        ),
        pages=upgraded,
    )
    out = dict(src)
    out["pages"] = upgraded
    out["sidebar"] = ranked
    out["serve_revision"] = WIKI_SERVE_REVISION
    return out


def materialize_path_resolved(
    path: Any,
    file_texts: dict[str, str] | None,
) -> dict[str, Any]:
    """Resolve evidence chips once. Templates stay live on GET."""
    store = file_texts or {}
    candidates: list[tuple[int, str, object, object]] = []
    for n in getattr(path, "nodes", None) or []:
        concept = getattr(n, "concept", None)
        slug = concept.slug if concept else ""
        title = concept.title if concept else ""
        wiki_id = getattr(concept, "wiki_page_id", None) if concept else None
        if is_filler_slug_title(slug, title):
            continue
        if is_web_filler_path_slug(slug, wiki_id) or (
            is_generic_web_slug(slug) and not (wiki_id or "").startswith("topics/")
        ):
            continue
        if is_shallow_path_leaf(slug):
            continue
        candidates.append((path_rank(slug), slug or "", n, concept))
    selected_slugs = {item[1] for item in candidates}
    candidates = [
        item for item in candidates if not drop_duplicate_entry_slug(item[1], selected_slugs)
    ]
    candidates.sort(key=lambda item: (item[0], item[1]))
    chips: dict[str, str] = {}
    with definition_index_scope(store):
        for _rank, _slug, n, concept in candidates[:CORE_PATH_CAP]:
            cid = str(getattr(n, "concept_id", "") or getattr(concept, "id", "") or "")
            if not cid or not concept:
                continue
            chip = path_evidence_chip(concept, file_texts=store)
            if chip:
                chips[cid] = chip
    return {"serve_revision": PATH_SERVE_REVISION, "chips": chips}


def persist_wiki_payload(session: Any, version: Any, payload: dict[str, Any]) -> None:
    version.wiki_pages = payload
    flag_modified(version, "wiki_pages")
    try:
        session.add(version)
        session.commit()
    except Exception:  # noqa: BLE001
        session.rollback()
        logger.exception("wiki materialize persist failed")


def persist_path_resolved(session: Any, path: Any, resolved: dict[str, Any]) -> None:
    path.resolved = resolved
    flag_modified(path, "resolved")
    try:
        session.add(path)
        session.commit()
    except Exception:  # noqa: BLE001
        session.rollback()
        logger.exception("path chip persist failed")


def materialize_analyzed_version(
    session: Any,
    version: Any,
    concepts: list[Any],
    file_texts: dict[str, str],
) -> None:
    """Analyze-time write of upgraded wiki + resolved chips."""
    version.wiki_pages = materialize_wiki_payload(version.wiki_pages or {}, concepts, file_texts)
    flag_modified(version, "wiki_pages")
    try:
        from recallstack.db.repositories import RepositoryStore

        path = RepositoryStore(session).get_learning_path(str(version.id))
    except Exception:  # noqa: BLE001
        path = None
    if path is not None:
        path.resolved = materialize_path_resolved(path, file_texts)
        flag_modified(path, "resolved")
