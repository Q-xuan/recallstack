"""RecallStack API routes mounted under /api/recallstack."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy.orm import Session

from recallstack import __version__
from recallstack.api.dependencies import ensure_user, get_config, get_db_session
from recallstack.api.errors import api_error
from recallstack.api.serializers import (
    attempt_out,
    concept_out,
    edge_out,
    item_out,
    path_out,
    repo_out,
    version_out,
    wiki_out,
)
from recallstack.application.analyze_repository import AnalyzeRepositoryService
from recallstack.application.evaluate_attempt import EvaluateAttemptService
from recallstack.application.session_queue import SessionQueueService
from recallstack.config import RecallStackConfig
from recallstack.db.repositories import RepositoryStore
from recallstack.domain.schemas import (
    AttemptCreate,
    AttemptOut,
    ConceptGraphOut,
    ConceptOut,
    DashboardOut,
    DueReviewOut,
    HintRequest,
    HintResponse,
    LearningItemOut,
    LearningPathOut,
    RepositoryCreate,
    RepositoryOut,
    SessionQueueOut,
    VersionOut,
    WikiAskIn,
    WikiAskOut,
    WikiOut,
    WikiPageOut,
    WikiSearchOut,
)
from recallstack.jobs import get_job_runner
from recallstack.learning.code_loader import (
    enrich_file_texts_from_working_copy,
    load_version_file_texts,
)
from recallstack.learning.wiki_serve import (
    materialize_path_resolved,
    materialize_wiki_payload,
    path_is_materialized,
    persist_path_resolved,
    persist_wiki_payload,
    sync_path_contract_items,
    wiki_is_materialized,
)
from recallstack.security import SecurityError

router = APIRouter(prefix="/recallstack", tags=["recallstack"])


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "recallstack", "version": __version__}


@router.get("/fs/roots")
def list_fs_roots() -> dict[str, Any]:
    """List browseable local roots (drives on Windows, home/cwd elsewhere)."""
    import os
    import string
    from pathlib import Path

    roots: list[dict[str, str]] = []
    if os.name == "nt":
        for letter in string.ascii_uppercase:
            drive = Path(f"{letter}:/")
            if drive.exists():
                roots.append({"name": f"{letter}:", "path": str(drive.resolve())})
    home = Path.home()
    roots.append({"name": "Home", "path": str(home.resolve())})
    cwd = Path.cwd().resolve()
    if not any(r["path"] == str(cwd) for r in roots):
        roots.append({"name": "Workspace", "path": str(cwd)})
    # de-dupe while preserving order
    seen: set[str] = set()
    unique: list[dict[str, str]] = []
    for r in roots:
        key = r["path"].lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(r)
    return {"roots": unique}


@router.get("/fs/list")
def list_fs_directory(path: str | None = None) -> dict[str, Any]:
    """List immediate children of a local directory for the folder picker."""
    import os
    from pathlib import Path

    if not path or not str(path).strip():
        # default landing
        current = Path.cwd().resolve()
    else:
        try:
            current = Path(path).expanduser().resolve()
        except OSError as exc:
            raise api_error(400, "invalid_path", "Invalid path") from exc

    if not current.exists() or not current.is_dir():
        raise api_error(404, "path_not_found", "Directory not found")

    # basic safety: must be under an existing drive/root
    try:
        entries = list(current.iterdir())
    except PermissionError as exc:
        raise api_error(403, "permission_denied", "Cannot read this directory") from exc

    dirs: list[dict[str, Any]] = []
    files: list[dict[str, Any]] = []
    skip_names = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build"}
    for entry in sorted(entries, key=lambda p: (not p.is_dir(), p.name.lower())):
        name = entry.name
        if name in skip_names or name.startswith("."):
            # still show dotfiles that are useful? skip heavy/hidden by default
            if name not in {".github"}:
                continue
        try:
            is_dir = entry.is_dir()
        except OSError:
            continue
        item = {
            "name": name,
            "path": str(entry.resolve()),
            "is_dir": is_dir,
        }
        if is_dir:
            dirs.append(item)
        else:
            files.append(item)

    parent = current.parent
    parent_path = str(parent.resolve()) if parent != current else None
    # on Windows drive root, parent may equal self
    if parent_path and parent_path.lower() == str(current).lower():
        parent_path = None

    return {
        "path": str(current),
        "parent": parent_path,
        "directories": dirs[:300],
        "files": files[:100],
        "is_windows": os.name == "nt",
    }



@router.post("/repositories", response_model=RepositoryOut)
def create_repository(
    body: RepositoryCreate,
    db: Session = Depends(get_db_session),
    config: RecallStackConfig = Depends(get_config),
) -> RepositoryOut:
    ensure_user(db, config.default_user_id)
    svc = AnalyzeRepositoryService(db, config)
    try:
        repo = svc.create_repository(
            source_type=body.source_type,
            source_location=body.source_location,
            name=body.name,
            default_branch=body.default_branch,
        )
        db.commit()
        db.refresh(repo)
        return repo_out(repo)
    except SecurityError as exc:
        raise api_error(400, exc.code, exc.message) from exc
    except FileNotFoundError as exc:
        raise api_error(400, "path_not_found", str(exc)) from exc


@router.get("/repositories", response_model=list[RepositoryOut])
def list_repositories(db: Session = Depends(get_db_session)) -> list[RepositoryOut]:
    store = RepositoryStore(db)
    return [repo_out(r) for r in store.list_repositories()]


@router.get("/repositories/{repository_id}", response_model=RepositoryOut)
def get_repository(repository_id: str, db: Session = Depends(get_db_session)) -> RepositoryOut:
    store = RepositoryStore(db)
    repo = store.get_repository(repository_id)
    if not repo:
        raise api_error(404, "repository_not_found", "Repository not found")
    return repo_out(repo)


def _run_analyze(repository_id: str) -> None:
    from recallstack.db.session import session_scope

    with session_scope() as session:
        svc = AnalyzeRepositoryService(session)
        svc.analyze(repository_id)


@router.post("/repositories/{repository_id}/analyze", response_model=VersionOut)
def analyze_repository(
    repository_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db_session),
    config: RecallStackConfig = Depends(get_config),
    wait: bool = False,
) -> VersionOut:
    store = RepositoryStore(db)
    repo = store.get_repository(repository_id)
    if not repo:
        raise api_error(404, "repository_not_found", "Repository not found")

    if wait:
        try:
            svc = AnalyzeRepositoryService(db, config)
            version = svc.analyze(repository_id)
            return version_out(version)
        except SecurityError as exc:
            raise api_error(400, exc.code, exc.message) from exc
        except Exception as exc:  # noqa: BLE001
            raise api_error(500, "analyze_failed", "Analysis failed", {"error": str(exc)[:500]}) from exc

    # Background path. Flip the existing version to "queued" *before* enqueuing so
    # a poller never sees a stale "ready" and concludes the rescan already finished.
    latest = store.get_latest_version(repository_id)
    if latest:
        latest.status = "queued"
        latest.error_message = None
        db.commit()
        db.refresh(latest)

    runner = get_job_runner()
    runner.enqueue("analyze", _run_analyze, repository_id)
    if latest:
        return version_out(latest)

    # ensure a pending version exists for UI polling
    from recallstack.db.models import RepositoryVersion

    pending = RepositoryVersion(
        repository_id=repository_id,
        commit_sha="pending",
        content_hash="",
        status="pending",
    )
    db.add(pending)
    db.commit()
    db.refresh(pending)
    return version_out(pending)


@router.get("/repositories/{repository_id}/versions/latest", response_model=VersionOut)
def latest_version(repository_id: str, db: Session = Depends(get_db_session)) -> VersionOut:
    store = RepositoryStore(db)
    if not store.get_repository(repository_id):
        raise api_error(404, "repository_not_found", "Repository not found")
    version = store.get_latest_version(repository_id)
    if not version:
        raise api_error(404, "version_not_found", "No analysis version yet")
    return version_out(version)


@router.get("/repositories/{repository_id}/concepts", response_model=ConceptGraphOut)
def list_concepts(
    repository_id: str,
    db: Session = Depends(get_db_session),
    config: RecallStackConfig = Depends(get_config),
) -> ConceptGraphOut:
    store = RepositoryStore(db)
    repo = store.get_repository(repository_id)
    if not repo:
        raise api_error(404, "repository_not_found", "Repository not found")
    version = store.get_latest_version(repository_id)
    if not version:
        return ConceptGraphOut(concepts=[], edges=[])
    user_id = ensure_user(db, config.default_user_id)
    concepts = store.list_concepts(repository_id, version.id)
    edges = store.list_edges_for_concepts([c.id for c in concepts])
    outs = []
    for c in concepts:
        m = store.get_mastery(user_id, c.id)
        outs.append(
            concept_out(
                c,
                mastery_score=m.mastery_score if m else None,
                next_review_at=m.next_review_at if m else None,
            )
        )
    return ConceptGraphOut(concepts=outs, edges=[edge_out(e) for e in edges])


@router.get("/repositories/{repository_id}/wiki", response_model=WikiOut)
def get_repository_wiki(
    repository_id: str, db: Session = Depends(get_db_session)
) -> WikiOut:
    """Return the real wiki generated by the same analyze pipeline as learning."""
    store = RepositoryStore(db)
    if not store.get_repository(repository_id):
        raise api_error(404, "repository_not_found", "Repository not found")
    version = store.get_latest_version(repository_id)
    if not version:
        raise api_error(404, "version_not_found", "No analysis version yet")
    if not version.wiki_pages or not (version.wiki_pages or {}).get("pages"):
        raise api_error(404, "wiki_not_found", "Wiki not generated yet — re-analyze repository")
    concepts = store.list_concepts(repository_id, version.id)
    payload = version.wiki_pages or {}
    if not wiki_is_materialized(payload):
        repo = store.get_repository(repository_id)
        file_texts = enrich_file_texts_from_working_copy(
            load_version_file_texts(str(version.id)),
            source_type=getattr(repo, "source_type", "") or "",
            source_location=getattr(repo, "source_location", "") or "",
        )
        payload = materialize_wiki_payload(payload, concepts, file_texts)
        persist_wiki_payload(db, version, payload)
        version.wiki_pages = payload
    return wiki_out(repository_id, version, concepts)


@router.get("/repositories/{repository_id}/wiki/search", response_model=WikiSearchOut)
def search_repository_wiki(
    repository_id: str,
    q: str,
    limit: int = 20,
    db: Session = Depends(get_db_session),
) -> WikiSearchOut:
    """Rank wiki pages against a free-text query.

    Deterministic and LLM-free: search has to work on a freshly scanned repo
    with no API key configured.
    """
    from recallstack.learning.wiki_search import search

    store = RepositoryStore(db)
    if not store.get_repository(repository_id):
        raise api_error(404, "repository_not_found", "Repository not found")
    docs = _wiki_documents(store, repository_id)
    results = search(docs, q, limit=max(1, min(limit, 50)))
    return WikiSearchOut(query=q, total=len(results), results=results)


def _wiki_documents(store: RepositoryStore, repository_id: str):
    """Searchable documents for the latest wiki, or [] before analysis."""
    from recallstack.learning.wiki_search import build_documents

    version = store.get_latest_version(repository_id)
    if not version or not (version.wiki_pages or {}).get("pages"):
        return []
    concepts = store.list_concepts(repository_id, version.id)
    concept_paths = {
        c.slug: [str(ref.get("path", "")) for ref in (c.source_references or [])]
        for c in concepts
    }
    concept_ids = {c.slug: c.id for c in concepts}
    return build_documents(
        (version.wiki_pages or {}).get("pages") or [],
        concept_paths=concept_paths,
        concept_ids=concept_ids,
    )


def _qa_llm_client(config: RecallStackConfig):
    """The raw completion client for Q&A, or None to use the search fallback."""
    if not config.llm_enabled:
        return None
    try:
        from repowiki.config import Config as RepoWikiConfig
        from repowiki.llm.client import LLMClient
    except Exception:  # noqa: BLE001
        return None
    rw = RepoWikiConfig.load()
    if not rw.api_key or not rw.model:
        return None
    return LLMClient(model=rw.model, api_key=rw.api_key, api_base=rw.api_base or "")


@router.post("/repositories/{repository_id}/ask", response_model=WikiAskOut)
async def ask_repository_wiki(
    repository_id: str,
    body: WikiAskIn,
    db: Session = Depends(get_db_session),
    config: RecallStackConfig = Depends(get_config),
) -> WikiAskOut:
    """Answer a question about the repository, grounded in its wiki pages.

    Falls back to an extractive search answer when no LLM is configured or the
    call fails — the feature degrades, it never errors out.
    """
    from recallstack.learning.wiki_qa import answer_question

    store = RepositoryStore(db)
    repo = store.get_repository(repository_id)
    if not repo:
        raise api_error(404, "repository_not_found", "Repository not found")
    docs = _wiki_documents(store, repository_id)
    if not docs:
        raise api_error(409, "wiki_not_ready", "Analyze the repository first")

    result = await answer_question(
        body.question.strip(),
        docs,
        project_name=repo.name,
        llm=_qa_llm_client(config),
        history=[{"question": t.question, "answer": t.answer} for t in body.history],
    )
    return WikiAskOut(
        question=body.question.strip(),
        answer=result["answer"],
        engine=result["engine"],
        sources=result["sources"],
    )


@router.get("/repositories/{repository_id}/wiki/pages/{page_id:path}", response_model=WikiPageOut)
def get_repository_wiki_page(
    repository_id: str, page_id: str, db: Session = Depends(get_db_session)
) -> WikiPageOut:
    wiki = get_repository_wiki(repository_id, db)
    for page in wiki.pages:
        if page.id == page_id:
            return page
    raise api_error(404, "page_not_found", "Wiki page not found")


@router.get("/repositories/{repository_id}/learning-path", response_model=LearningPathOut)
def get_learning_path(
    repository_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db_session),
) -> LearningPathOut:
    store = RepositoryStore(db)
    if not store.get_repository(repository_id):
        raise api_error(404, "repository_not_found", "Repository not found")
    version = store.get_latest_version(repository_id)
    if not version:
        raise api_error(404, "version_not_found", "No analysis version yet")
    path = store.get_learning_path(version.id)
    if not path:
        raise api_error(404, "path_not_found", "Learning path not found")
    if path_is_materialized(getattr(path, "resolved", None)):
        out = path_out(path)
        _schedule_path_annotation_prefetch(background_tasks, str(version.id), out, {})
        return out
    repo = store.get_repository(repository_id)
    file_texts = enrich_file_texts_from_working_copy(
        load_version_file_texts(str(version.id)),
        source_type=getattr(repo, "source_type", "") or "",
        source_location=getattr(repo, "source_location", "") or "",
    )
    resolved = materialize_path_resolved(path, file_texts)
    persist_path_resolved(db, path, resolved)
    path.resolved = resolved
    sync_path_contract_items(db, path, file_texts)
    try:
        db.commit()
    except Exception:  # noqa: BLE001
        db.rollback()
    out = path_out(path, file_texts=file_texts)
    _schedule_path_annotation_prefetch(background_tasks, str(version.id), out, file_texts)
    return out


@router.get("/concepts/{concept_id}", response_model=ConceptOut)
def get_concept(
    concept_id: str,
    db: Session = Depends(get_db_session),
    config: RecallStackConfig = Depends(get_config),
) -> ConceptOut:
    store = RepositoryStore(db)
    concept = store.get_concept(concept_id)
    if not concept:
        raise api_error(404, "concept_not_found", "Concept not found")
    user_id = ensure_user(db, config.default_user_id)
    m = store.get_mastery(user_id, concept.id)
    return concept_out(
        concept,
        mastery_score=m.mastery_score if m else None,
        next_review_at=m.next_review_at if m else None,
    )


@router.get("/concepts/{concept_id}/items", response_model=list[LearningItemOut])
def list_items(concept_id: str, db: Session = Depends(get_db_session)) -> list[LearningItemOut]:
    store = RepositoryStore(db)
    if not store.get_concept(concept_id):
        raise api_error(404, "concept_not_found", "Concept not found")
    return [item_out(i) for i in store.list_items(concept_id)]


@router.get("/items/{item_id}", response_model=LearningItemOut)
def get_item(item_id: str, db: Session = Depends(get_db_session)) -> LearningItemOut:
    store = RepositoryStore(db)
    item = store.get_item(item_id)
    if not item:
        raise api_error(404, "item_not_found", "Learning item not found")
    snippets = EvaluateAttemptService(db).evidence_snippets_for_item(item)
    return item_out(item, evidence_snippets=snippets)


def _session_queue_out(
    payload: dict[str, Any],
    *,
    db: Session,
    include_current: bool = True,
) -> SessionQueueOut:
    current_item = None
    if include_current:
        store = RepositoryStore(db)
        item = store.get_item(payload["current_item_id"])
        if item:
            snippets = EvaluateAttemptService(db).evidence_snippets_for_item(item)
            current_item = item_out(item, evidence_snippets=snippets)
    return SessionQueueOut(
        mode=payload["mode"],
        concept_id=payload["concept_id"],
        concept_title=payload["concept_title"],
        repository_id=payload["repository_id"],
        item_ids=payload["item_ids"],
        position=payload["position"],
        total=payload["total"],
        current_item_id=payload["current_item_id"],
        next_item_id=payload.get("next_item_id"),
        prev_item_id=payload.get("prev_item_id"),
        remaining_count=payload.get("remaining_count", 0),
        completed_count=payload.get("completed_count", 0),
        items=payload.get("items") or [],
        current_item=current_item,
    )


@router.get("/sessions/concept/{concept_id}", response_model=SessionQueueOut)
def concept_session(
    concept_id: str,
    db: Session = Depends(get_db_session),
    config: RecallStackConfig = Depends(get_config),
) -> SessionQueueOut:
    user_id = ensure_user(db, config.default_user_id)
    try:
        payload = SessionQueueService(db, config).concept_queue(concept_id, user_id=user_id)
    except KeyError as exc:
        code = str(exc.args[0]) if exc.args else "not_found"
        raise api_error(404, code, code.replace("_", " ")) from None
    return _session_queue_out(payload, db=db)


@router.get("/sessions/review", response_model=SessionQueueOut)
def review_session(
    concept_id: str | None = None,
    db: Session = Depends(get_db_session),
    config: RecallStackConfig = Depends(get_config),
) -> SessionQueueOut:
    user_id = ensure_user(db, config.default_user_id)
    try:
        payload = SessionQueueService(db, config).review_queue(user_id, concept_id=concept_id)
    except KeyError as exc:
        code = str(exc.args[0]) if exc.args else "not_found"
        raise api_error(404, code, code.replace("_", " ")) from None
    return _session_queue_out(payload, db=db)


@router.get("/sessions/item/{item_id}", response_model=SessionQueueOut)
def item_session(
    item_id: str,
    mode: str = "concept",
    db: Session = Depends(get_db_session),
    config: RecallStackConfig = Depends(get_config),
) -> SessionQueueOut:
    user_id = ensure_user(db, config.default_user_id)
    session_mode = "review" if mode == "review" else "concept"
    try:
        payload = SessionQueueService(db, config).queue_for_item(
            item_id, mode=session_mode, user_id=user_id
        )
    except KeyError as exc:
        code = str(exc.args[0]) if exc.args else "not_found"
        raise api_error(404, code, code.replace("_", " ")) from None
    return _session_queue_out(payload, db=db)


@router.post("/items/{item_id}/hint", response_model=HintResponse)
def get_hint(
    item_id: str,
    body: HintRequest,
    db: Session = Depends(get_db_session),
) -> HintResponse:
    svc = EvaluateAttemptService(db)
    try:
        result = svc.request_hint(
            item_id,
            current_level=body.current_level,
            hints_used=body.hints_used,
            reveal_answer=False,
        )
        return HintResponse(
            level=int(result["level"]),
            content=str(result["content"]),
            revealed_answer=bool(result.get("revealed_answer")),
        )
    except KeyError:
        raise api_error(404, "item_not_found", "Learning item not found") from None
    except ValueError as exc:
        raise api_error(400, "invalid_hint_progression", str(exc)) from exc


@router.post("/items/{item_id}/reveal", response_model=HintResponse)
def reveal_answer(
    item_id: str,
    body: HintRequest,
    db: Session = Depends(get_db_session),
) -> HintResponse:
    svc = EvaluateAttemptService(db)
    try:
        result = svc.request_hint(
            item_id,
            current_level=body.current_level,
            hints_used=body.hints_used,
            reveal_answer=True,
        )
        return HintResponse(
            level=int(result["level"]),
            content=str(result["content"]),
            revealed_answer=True,
        )
    except KeyError:
        raise api_error(404, "item_not_found", "Learning item not found") from None


@router.post("/items/{item_id}/attempts", response_model=AttemptOut)
def submit_attempt(
    item_id: str,
    body: AttemptCreate,
    db: Session = Depends(get_db_session),
    config: RecallStackConfig = Depends(get_config),
    mode: str = "concept",
) -> AttemptOut:
    user_id = ensure_user(db, config.default_user_id)
    svc = EvaluateAttemptService(db, config)
    try:
        result = svc.submit_attempt(
            item_id,
            user_id=user_id,
            answer=body.answer,
            confidence=body.confidence,
            hints_used=body.hints_used,
            duration_seconds=body.duration_seconds,
            revealed_answer=body.revealed_answer,
        )
        session_mode = "review" if mode == "review" else "concept"
        queue = SessionQueueService(db, config).queue_for_item(
            item_id, mode=session_mode, user_id=user_id
        )
        # current item is now attempted; expose next in sequence
        next_item_id = queue.get("next_item_id")
        session_out = _session_queue_out(queue, db=db, include_current=False)
        db.commit()
        return attempt_out(
            result["attempt"],
            mastery_score=result["mastery_score"],
            next_review_at=result["next_review_at"],
            expected_answer_outline=result.get("expected_answer_outline"),
            evaluation_source=result.get("evaluation_source"),
            concept_id=result.get("concept_id"),
            next_item_id=next_item_id,
            session=session_out,
        )
    except KeyError:
        raise api_error(404, "item_not_found", "Learning item not found") from None
    except ValueError as exc:
        raise api_error(400, "invalid_attempt", str(exc)) from exc


@router.get("/reviews/due", response_model=list[DueReviewOut])
def due_reviews(
    db: Session = Depends(get_db_session),
    config: RecallStackConfig = Depends(get_config),
) -> list[DueReviewOut]:
    user_id = ensure_user(db, config.default_user_id)
    store = RepositoryStore(db)
    now = datetime.now(timezone.utc)
    due = store.due_masteries(user_id, now)
    out: list[DueReviewOut] = []
    for m in due:
        concept = store.get_concept(m.concept_id)
        if not concept:
            continue
        items = store.list_items(concept.id)
        out.append(
            DueReviewOut(
                concept_id=concept.id,
                title=concept.title,
                mastery_score=m.mastery_score,
                next_review_at=m.next_review_at,
                stale=bool(concept.stale),
                item_id=items[0].id if items else None,
            )
        )
    # Anki-style: never-attempted concepts count as due for their first pass.
    # Without this a fresh install has no mastery rows and the queue is empty
    # forever — review mode only becomes reachable after the user stumbles into
    # a self-test elsewhere.
    for concept in store.unlearned_concepts(user_id, limit=10):
        items = store.list_items(concept.id)
        if not items:
            continue
        out.append(
            DueReviewOut(
                concept_id=concept.id,
                title=concept.title,
                mastery_score=0.0,
                next_review_at=None,
                stale=bool(concept.stale),
                item_id=items[0].id,
                is_new=True,
            )
        )
    return out


@router.post("/reviews/{concept_id}", response_model=AttemptOut)
def submit_review(
    concept_id: str,
    body: AttemptCreate,
    db: Session = Depends(get_db_session),
    config: RecallStackConfig = Depends(get_config),
) -> AttemptOut:
    store = RepositoryStore(db)
    concept = store.get_concept(concept_id)
    if not concept:
        raise api_error(404, "concept_not_found", "Concept not found")
    items = store.list_items(concept_id)
    if not items:
        raise api_error(404, "item_not_found", "No learning items for concept")
    return submit_attempt(items[0].id, body, db, config)


@router.get("/dashboard", response_model=DashboardOut)
def dashboard(
    db: Session = Depends(get_db_session),
    config: RecallStackConfig = Depends(get_config),
) -> DashboardOut:
    user_id = ensure_user(db, config.default_user_id)
    store = RepositoryStore(db)
    repos = store.list_repositories()
    current = repos[0] if repos else None
    due = due_reviews(db, config)

    recent_concepts: list[ConceptOut] = []
    weak_concepts: list[ConceptOut] = []
    learning_count = 0
    code_trace_count = 0
    progress = 0.0

    if current:
        version = store.get_latest_version(current.id)
        concepts = store.list_concepts(current.id, version.id if version else None)
        learning_count = len(concepts)
        mastered = 0
        for c in concepts:
            items = store.list_items(c.id)
            code_trace_count += sum(1 for i in items if i.item_type == "code_trace")
            m = store.get_mastery(user_id, c.id)
            co = concept_out(
                c,
                mastery_score=m.mastery_score if m else 0.0,
                next_review_at=m.next_review_at if m else None,
            )
            if m and m.mastery_score >= 0.7:
                mastered += 1
            if m and m.mastery_score < 0.5 and m.attempts_count > 0:
                weak_concepts.append(co)
            if m and m.last_reviewed_at:
                recent_concepts.append(co)
        recent_concepts = sorted(
            recent_concepts,
            key=lambda x: x.next_review_at or datetime.min.replace(tzinfo=timezone.utc),
            reverse=True,
        )[:5]
        weak_concepts = weak_concepts[:5]
        progress = (mastered / learning_count * 100.0) if learning_count else 0.0

    return DashboardOut(
        due_review_count=len(due),
        learning_concept_count=learning_count,
        interval_review_count=len(due),
        code_trace_count=code_trace_count,
        current_repository=repo_out(current) if current else None,
        recent_concepts=recent_concepts,
        weak_concepts=weak_concepts,
        due_reviews=due,
        progress_percent=round(progress, 1),
    )


def _schedule_path_annotation_prefetch(
    background_tasks: BackgroundTasks,
    version_id: str,
    out: LearningPathOut,
    file_texts: dict[str, str],
) -> None:
    """Warm the first 过关 chip so the first peek is instant. Never blocks GET."""
    from recallstack.learning.code_loader import slice_lines
    from recallstack.learning.peek_annotations import (
        build_annotate_llm,
        parse_evidence_chip,
        prefetch_annotations_sync,
    )

    if build_annotate_llm() is None:
        return
    for node in out.nodes or []:
        chip = getattr(node, "evidence_chip", None) or ""
        parsed = parse_evidence_chip(chip)
        if not parsed:
            continue
        rel, start = parsed
        text = file_texts.get(rel) or ""
        if not text:
            continue
        snippet, s, e = slice_lines(text, start, None)
        slug = ""
        concept = getattr(node, "concept", None)
        if concept is not None:
            slug = getattr(concept, "slug", "") or ""
        background_tasks.add_task(
            prefetch_annotations_sync,
            version_id=version_id,
            path=rel,
            start_line=s,
            end_line=e,
            snippet=snippet,
            slug=slug,
        )
        return


@router.get("/source")
async def get_source_snippet(
    path: str,
    repository_id: str,
    start_line: int | None = None,
    end_line: int | None = None,
    slug: str | None = None,
    db: Session = Depends(get_db_session),
) -> dict[str, Any]:
    """Return a short source snippet for a repository-relative path.

    Uses scanned file text from the last analyze (so GitHub clones work), then
    the local working copy / clone cache. Blocked files are never served.
    Teaching annotations are generated lazily on first peek and cached.
    """
    store = RepositoryStore(db)
    repo = store.get_repository(repository_id)
    if not repo:
        raise api_error(404, "repository_not_found", "Repository not found")

    from recallstack.learning.code_loader import (
        missing_working_copy_message,
        resolve_file_text,
        slice_lines,
    )
    from recallstack.learning.peek_annotations import annotations_for_snippet
    from recallstack.security import is_blocked_filename, normalize_repo_path

    rel = normalize_repo_path(path)
    if not rel or ".." in rel.split("/") or rel.startswith("/"):
        raise api_error(400, "path_escape", "Invalid path")
    if is_blocked_filename(rel):
        raise api_error(403, "blocked_file", "This file cannot be previewed")

    version = store.get_latest_version(repository_id)
    text = resolve_file_text(
        source_type=repo.source_type,
        source_location=repo.source_location,
        rel_path=rel,
        version_id=version.id if version else None,
    )
    if text is None:
        raise api_error(404, "file_not_found", missing_working_copy_message())
    snippet, s, e = slice_lines(text, start_line, end_line)
    notes: list[dict[str, Any]] = []
    if snippet.strip():
        notes = await annotations_for_snippet(
            version_id=str(version.id) if version else "",
            path=rel,
            start_line=s,
            end_line=e,
            snippet=snippet,
            slug=(slug or "").strip(),
        )
    return {
        "path": rel,
        "start_line": s,
        "end_line": e,
        "content": snippet,
        "annotations": notes,
    }
