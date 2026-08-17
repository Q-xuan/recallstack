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
    chip_needs_restamp,
    concept_refs_need_rebind,
    deepen_concept_markdown,
    definition_index_scope,
    drop_duplicate_entry_slug,
    fill_wiki_key_type_lines,
    is_filler_slug_title,
    is_shallow_path_leaf,
    is_web_filler_path_slug,
    path_evidence_chip,
    path_rank,
    path_step_contract,
    source_refs_from_chip,
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
WIKI_SERVE_REVISION = 4
PATH_SERVE_REVISION = 2
# Bump when leftover chip rules change so store-backed persist restamps once.
PATH_CHIP_RESTAMP = 2


def wiki_is_materialized(payload: dict[str, Any] | None) -> bool:
    return isinstance(payload, dict) and payload.get("serve_revision") == WIKI_SERVE_REVISION


def path_chips_ready(resolved: dict[str, Any] | None) -> bool:
    """True when a prior write already persisted chips — later GETs must not walk the store."""
    if not isinstance(resolved, dict):
        return False
    chips = resolved.get("chips")
    return isinstance(chips, dict) and bool(chips)


def path_is_materialized(resolved: dict[str, Any] | None) -> bool:
    """Chips on disk are enough. Revision bumps upgrade in memory, not via store walk."""
    return path_chips_ready(resolved)


def path_needs_chip_restamp(path: Any, resolved: dict[str, Any] | None) -> bool:
    """True when any persisted chip is still junk / not a definition line."""
    if not isinstance(resolved, dict) or not path_chips_ready(resolved):
        return False
    if int(resolved.get("chip_restamp") or 0) >= PATH_CHIP_RESTAMP:
        return False
    chips = resolved.get("chips") or {}
    if not isinstance(chips, dict):
        return False
    for n in getattr(path, "nodes", None) or []:
        concept = getattr(n, "concept", None)
        slug = getattr(concept, "slug", "") or ""
        cid = str(getattr(n, "concept_id", "") or getattr(concept, "id", "") or "")
        if not cid or not chip_needs_restamp(slug, str(chips.get(cid) or "")):
            continue
        return True
    return False


def restamp_weak_path_chips(
    path: Any,
    resolved: dict[str, Any],
    file_texts: dict[str, str] | None,
) -> dict[str, Any]:
    """Rewrite only leftover chips, then persist. Later GETs stay cheap."""
    chips = dict(resolved.get("chips") or {})
    nodes = dict(resolved.get("nodes") or {}) if isinstance(resolved.get("nodes"), dict) else {}
    store = file_texts or {}
    with definition_index_scope(store):
        for n in getattr(path, "nodes", None) or []:
            concept = getattr(n, "concept", None)
            slug = getattr(concept, "slug", "") or ""
            cid = str(getattr(n, "concept_id", "") or getattr(concept, "id", "") or "")
            if not cid or not concept:
                continue
            if not chip_needs_restamp(slug, str(chips.get(cid) or "")):
                continue
            chip = path_evidence_chip(concept, file_texts=store)
            if not chip:
                continue
            chips[cid] = chip
            nodes[cid] = path_step_contract(concept, chip=chip, file_texts=store)
    return {
        "serve_revision": PATH_SERVE_REVISION,
        "chip_restamp": PATH_CHIP_RESTAMP,
        "chips": chips,
        "nodes": nodes,
    }


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
                if store and concept is not None:
                    content = deepen_concept_markdown(content, concept, store)
            elif page_id.startswith("modules/"):
                content = upgrade_legacy_module_markdown(content, language=lang)
            content = upgrade_wiki_page_content(
                content, known_ids, language=lang, page_id=page_id
            )
            if page_id == "reading-guide":
                content = link_reading_guide_markdown(content, concept_list)
            if store:
                content = fill_wiki_key_type_lines(content, store)
                if page_id in {"index", "architecture"}:
                    from repowiki.core.grounding import (
                        cite_index_from_texts,
                        scrub_wiki_page_content,
                    )

                    content = scrub_wiki_page_content(
                        content, cite_index_from_texts(store)
                    )
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
    nodes: dict[str, dict[str, Any]] = {}
    with definition_index_scope(store):
        for _rank, _slug, n, concept in candidates[:CORE_PATH_CAP]:
            cid = str(getattr(n, "concept_id", "") or getattr(concept, "id", "") or "")
            if not cid or not concept:
                continue
            chip = path_evidence_chip(concept, file_texts=store)
            if chip:
                chips[cid] = chip
            nodes[cid] = path_step_contract(concept, chip=chip, file_texts=store)
    return {
        "serve_revision": PATH_SERVE_REVISION,
        "chip_restamp": PATH_CHIP_RESTAMP,
        "chips": chips,
        "nodes": nodes,
    }


def cheap_upgrade_path_resolved(path: Any, persisted: dict[str, Any]) -> dict[str, Any]:
    """Fill missing node contracts from existing chips. Never walks the scan store."""
    chips = persisted.get("chips") if isinstance(persisted.get("chips"), dict) else {}
    nodes_in = persisted.get("nodes") if isinstance(persisted.get("nodes"), dict) else {}
    nodes: dict[str, dict[str, Any]] = dict(nodes_in)
    for n in getattr(path, "nodes", None) or []:
        concept = getattr(n, "concept", None)
        cid = str(getattr(n, "concept_id", "") or getattr(concept, "id", "") or "")
        if not cid or not concept:
            continue
        existing = nodes.get(cid)
        if isinstance(existing, dict) and (existing.get("chip") or existing.get("symbol")):
            continue
        chip = chips.get(cid)
        if not chip:
            continue
        nodes[cid] = path_step_contract(concept, chip=chip, file_texts=None)
    out = {
        "serve_revision": PATH_SERVE_REVISION,
        "chips": chips,
        "nodes": nodes,
    }
    if persisted.get("chip_restamp"):
        out["chip_restamp"] = persisted["chip_restamp"]
    return out


def sync_concept_refs_from_chips(
    session: Any,
    path: Any,
    resolved: dict[str, Any] | None = None,
) -> bool:
    """Rewrite junk concept ``source_references`` from persisted chips. No store walk."""
    payload = resolved if isinstance(resolved, dict) else getattr(path, "resolved", None)
    chips = payload.get("chips") if isinstance(payload, dict) else None
    if not isinstance(chips, dict) or not chips:
        return False
    changed = False
    for n in getattr(path, "nodes", None) or []:
        concept = getattr(n, "concept", None)
        cid = str(getattr(n, "concept_id", "") or getattr(concept, "id", "") or "")
        if not concept or not cid:
            continue
        slug = getattr(concept, "slug", "") or ""
        chip = str(chips.get(cid) or "")
        if not chip or chip_needs_restamp(slug, chip):
            continue
        refs = getattr(concept, "source_references", None) or []
        if not concept_refs_need_rebind(refs, slug, chip):
            continue
        new_refs = [ref.model_dump() for ref in source_refs_from_chip(chip)]
        if not new_refs:
            continue
        concept.source_references = new_refs
        try:
            flag_modified(concept, "source_references")
        except Exception:  # noqa: BLE001
            pass
        add = getattr(session, "add", None) if session is not None else None
        if callable(add):
            add(concept)
        changed = True
    return changed


def persist_path_from_loaded_store(
    session: Any,
    path: Any,
    file_texts: dict[str, str] | None,
) -> None:
    """While the store is already in memory (wiki materialize), persist path chips too."""
    if path is None:
        return
    resolved = getattr(path, "resolved", None)
    if path_chips_ready(resolved):
        if path_needs_chip_restamp(path, resolved):
            upgraded = restamp_weak_path_chips(path, resolved or {}, file_texts)
            persist_path_resolved(session, path, upgraded)
            path.resolved = upgraded
            sync_path_contract_items(session, path, file_texts)
            sync_concept_refs_from_chips(session, path, upgraded)
            try:
                session.commit()
            except Exception:  # noqa: BLE001
                session.rollback()
                logger.exception("path leftover chip restamp after store-backed persist failed")
            return
        if sync_concept_refs_from_chips(session, path, resolved):
            try:
                session.commit()
            except Exception:  # noqa: BLE001
                session.rollback()
                logger.exception("concept ref chip sync after store-backed persist failed")
        return
    resolved = materialize_path_resolved(path, file_texts)
    persist_path_resolved(session, path, resolved)
    path.resolved = resolved
    sync_path_contract_items(session, path, file_texts)
    sync_concept_refs_from_chips(session, path, resolved)
    try:
        session.commit()
    except Exception:  # noqa: BLE001
        session.rollback()
        logger.exception("path contract sync after store-backed persist failed")


def persist_wiki_payload(session: Any, version: Any, payload: dict[str, Any]) -> None:
    version.wiki_pages = payload
    flag_modified(version, "wiki_pages")
    try:
        session.add(version)
        session.commit()
    except Exception:  # noqa: BLE001
        session.rollback()
        logger.exception("wiki materialize persist failed")


def _item_has_contract(item: Any) -> bool:
    rubric = getattr(item, "rubric", None) or {}
    if not isinstance(rubric, dict):
        return False
    contract = rubric.get("contract")
    return isinstance(contract, dict) and bool(contract.get("symbol") or contract.get("chip"))


def _item_matches_contract(item: Any, contract: dict[str, Any]) -> bool:
    """Skip rewrite only when the persisted item already locks the new chip + line."""
    if not _item_has_contract(item):
        return False
    rubric = getattr(item, "rubric", None) or {}
    existing = rubric.get("contract") if isinstance(rubric, dict) else None
    if not isinstance(existing, dict):
        return False
    new_chip = (contract.get("chip") or "").strip()
    old_chip = (existing.get("chip") or "").strip()
    if new_chip and old_chip != new_chip:
        return False
    if int(contract.get("line") or 0) < 1:
        return False
    refs = getattr(item, "source_references", None) or []
    if refs:
        first = refs[0] if isinstance(refs[0], dict) else None
        if first is not None and not first.get("start_line"):
            return False
    return True


def sync_path_contract_items(
    session: Any,
    path: Any,
    file_texts: dict[str, str] | None,
) -> None:
    """Replace path-step practice items with contract-locked drafts.

    Off-path concepts keep the generic triad. Existing item rows are updated
    in place so attempt FKs stay valid.
    """
    from sqlalchemy import select

    from recallstack.db.models import LearningItem
    from recallstack.learning.question_generator import QuestionGenerator

    resolved = getattr(path, "resolved", None) or {}
    nodes = resolved.get("nodes") if isinstance(resolved, dict) else {}
    nodes = nodes if isinstance(nodes, dict) else {}
    chips = resolved.get("chips") if isinstance(resolved, dict) else {}
    chips = chips if isinstance(chips, dict) else {}
    qgen = QuestionGenerator()
    for n in getattr(path, "nodes", None) or []:
        concept = getattr(n, "concept", None)
        cid = str(getattr(n, "concept_id", "") or "")
        if not concept or not cid:
            continue
        contract = nodes.get(cid)
        if not isinstance(contract, dict) or not (contract.get("chip") or contract.get("symbol")):
            contract = path_step_contract(
                concept, chip=chips.get(cid), file_texts=file_texts
            )
        if not contract.get("chip") and not contract.get("symbol"):
            continue
        drafts = qgen.generate_from_contract(
            title=getattr(concept, "title", "") or "",
            contract=contract,
            concept=concept,
            file_texts=file_texts,
        ).items
        existing = list(
            session.scalars(
                select(LearningItem)
                .where(LearningItem.concept_id == cid)
                .order_by(LearningItem.created_at.asc())
            )
        )
        if existing and all(_item_matches_contract(item, contract) for item in existing):
            continue
        for item, draft in zip(existing, drafts, strict=False):
            item.item_type = draft.item_type
            item.prompt = draft.prompt
            item.rubric = draft.rubric.model_dump()
            item.expected_answer_outline = draft.expected_answer_outline
            item.source_references = [r.model_dump() for r in draft.source_references]
            item.difficulty = draft.difficulty
            item.content_hash = qgen.item_content_hash(draft)
            item.stale = False
            flag_modified(item, "rubric")
            flag_modified(item, "source_references")
        if len(existing) < len(drafts):
            for draft in drafts[len(existing) :]:
                session.add(
                    LearningItem(
                        concept_id=cid,
                        item_type=draft.item_type,
                        prompt=draft.prompt,
                        rubric=draft.rubric.model_dump(),
                        expected_answer_outline=draft.expected_answer_outline,
                        source_references=[r.model_dump() for r in draft.source_references],
                        difficulty=draft.difficulty,
                        content_hash=qgen.item_content_hash(draft),
                        stale=False,
                    )
                )


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
        sync_path_contract_items(session, path, file_texts)
        sync_concept_refs_from_chips(session, path, path.resolved)
