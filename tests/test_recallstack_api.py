"""API tests for RecallStack endpoints."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from recallstack.bootstrap import init_recallstack
from recallstack.db.session import reset_engine


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("RECALLSTACK_DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    # Keep API tests deterministic: never call external LLMs.
    monkeypatch.setenv("RECALLSTACK_LLM_ENABLED", "0")
    monkeypatch.setenv("RECALLSTACK_LLM_EVALUATION", "0")
    reset_engine()
    init_recallstack(f"sqlite:///{db_path.as_posix()}")

    # tiny fixture repo
    repo = tmp_path / "fixture_repo"
    repo.mkdir()
    (repo / "README.md").write_text("# Fixture\nDemo learning repo\n", encoding="utf-8")
    (repo / "app").mkdir()
    (repo / "app" / "main.py").write_text(
        "from app.core import boot\n\ndef main():\n    return boot()\n",
        encoding="utf-8",
    )
    (repo / "app" / "core.py").write_text(
        "def boot():\n    return 'ok'\n",
        encoding="utf-8",
    )
    (repo / "app" / "__init__.py").write_text("", encoding="utf-8")

    from repowiki.server.app import create_app

    app = create_app()
    with TestClient(app) as c:
        c.fixture_repo = str(repo)  # type: ignore[attr-defined]
        yield c
    reset_engine()


def test_health(client: TestClient):
    r = client.get("/api/recallstack/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_create_repository_and_analyze_and_attempt(client: TestClient):
    repo_path = client.fixture_repo  # type: ignore[attr-defined]

    created = client.post(
        "/api/recallstack/repositories",
        json={"source_type": "local", "source_location": repo_path, "name": "fixture"},
    )
    assert created.status_code == 200, created.text
    repo_id = created.json()["id"]

    analyzed = client.post(f"/api/recallstack/repositories/{repo_id}/analyze?wait=true")
    assert analyzed.status_code == 200, analyzed.text
    body = analyzed.json()
    assert body["status"] == "ready"
    assert body["commit_sha"]

    # idempotent re-run
    again = client.post(f"/api/recallstack/repositories/{repo_id}/analyze?wait=true")
    assert again.status_code == 200
    assert again.json()["id"] == body["id"] or again.json()["status"] == "ready"

    concepts = client.get(f"/api/recallstack/repositories/{repo_id}/concepts")
    assert concepts.status_code == 200
    concept_list = concepts.json()["concepts"]
    assert len(concept_list) >= 5

    path = client.get(f"/api/recallstack/repositories/{repo_id}/learning-path")
    assert path.status_code == 200
    assert path.json()["nodes"]

    concept_id = concept_list[0]["id"]
    items = client.get(f"/api/recallstack/concepts/{concept_id}/items")
    assert items.status_code == 200
    item_list = items.json()
    assert item_list
    item_id = item_list[0]["id"]

    # ensure answer outline not leaked on list endpoint
    assert "expected_answer_outline" not in item_list[0]

    hint = client.post(
        f"/api/recallstack/items/{item_id}/hint",
        json={"current_level": 0, "hints_used": []},
    )
    assert hint.status_code == 200
    assert hint.json()["level"] == 1

    session = client.get(f"/api/recallstack/sessions/concept/{concept_id}")
    assert session.status_code == 200, session.text
    session_body = session.json()
    assert session_body["total"] >= 1
    assert session_body["current_item_id"]
    assert session_body["current_item"]["id"] == session_body["current_item_id"]

    item_session = client.get(f"/api/recallstack/sessions/item/{item_id}?mode=concept")
    assert item_session.status_code == 200
    assert item_session.json()["concept_id"] == concept_id

    attempt = client.post(
        f"/api/recallstack/items/{item_id}/attempts?mode=concept",
        json={
            "answer": "这个模块负责应用入口与核心启动流程，见 app/main.py 与 boot",
            "confidence": 4,
            "hints_used": [{"level": 1, "content": hint.json()["content"]}],
            "duration_seconds": 40,
            "revealed_answer": False,
        },
    )
    assert attempt.status_code == 200, attempt.text
    data = attempt.json()
    assert 0.0 <= data["score"] <= 1.0
    assert data["fsrs_rating"] in {1, 2, 3, 4}
    assert data["next_review_at"]
    assert data["evaluation"]["feedback"]
    assert data["evaluation_source"] in {"deterministic", "llm"}
    assert data["concept_id"] == concept_id
    assert data["session"] is not None
    assert data["session"]["total"] >= 1
    # with multi-item concepts, next_item_id should be present or null for last item
    assert "next_item_id" in data

    detail = client.get(f"/api/recallstack/items/{item_id}")
    assert detail.status_code == 200
    assert "evidence_snippets" in detail.json()

    dash = client.get("/api/recallstack/dashboard")
    assert dash.status_code == 200
    assert dash.json()["current_repository"]["id"] == repo_id


def test_reject_bad_git_url(client: TestClient):
    r = client.post(
        "/api/recallstack/repositories",
        json={"source_type": "github", "source_location": "ssh://git@github.com/a/b.git"},
    )
    assert r.status_code == 400


def _analyzed_repo(client: TestClient) -> str:
    created = client.post(
        "/api/recallstack/repositories",
        json={
            "source_type": "local",
            "source_location": client.fixture_repo,  # type: ignore[attr-defined]
            "name": "fixture",
        },
    )
    assert created.status_code == 200, created.text
    repo_id = created.json()["id"]
    analyzed = client.post(f"/api/recallstack/repositories/{repo_id}/analyze?wait=true")
    assert analyzed.status_code == 200, analyzed.text
    return repo_id


def test_wiki_search_ranks_pages(client: TestClient):
    repo_id = _analyzed_repo(client)

    r = client.get(f"/api/recallstack/repositories/{repo_id}/wiki/search", params={"q": "app"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["query"] == "app"
    assert body["total"] == len(body["results"]) > 0
    top = body["results"][0]
    assert top["page_id"] and top["title"] and top["kind"]
    assert top["score"] > 0

    # Searching a source file name reaches the concept that cites it.
    by_file = client.get(
        f"/api/recallstack/repositories/{repo_id}/wiki/search", params={"q": "main.py"}
    )
    assert by_file.status_code == 200
    assert by_file.json()["results"]

    # An empty query is not an error — it just has no results.
    blank = client.get(f"/api/recallstack/repositories/{repo_id}/wiki/search", params={"q": ""})
    assert blank.status_code == 200
    assert blank.json()["results"] == []


def test_wiki_search_on_unanalyzed_repo_is_empty_not_404(client: TestClient):
    created = client.post(
        "/api/recallstack/repositories",
        json={
            "source_type": "local",
            "source_location": client.fixture_repo,  # type: ignore[attr-defined]
        },
    )
    repo_id = created.json()["id"]
    r = client.get(f"/api/recallstack/repositories/{repo_id}/wiki/search", params={"q": "app"})
    assert r.status_code == 200
    assert r.json()["results"] == []


def test_wiki_search_unknown_repo_is_404(client: TestClient):
    r = client.get("/api/recallstack/repositories/does-not-exist/wiki/search", params={"q": "app"})
    assert r.status_code == 404


def test_concept_pages_cross_link_and_cite_evidence(client: TestClient):
    repo_id = _analyzed_repo(client)
    wiki = client.get(f"/api/recallstack/repositories/{repo_id}/wiki")
    assert wiki.status_code == 200, wiki.text
    pages = {p["id"]: p for p in wiki.json()["pages"]}

    concept_pages = [p for pid, p in pages.items() if pid.startswith("concepts/")]
    assert concept_pages, "analyze should emit concept pages"
    for page in concept_pages:
        assert page["concept_id"], "concept pages must resolve back to their concept row"
        assert "difficulty" in page["content"].lower() or "难度" in page["content"]

    # At least one concept cites a source location in `path:line` form, which is
    # what the reader turns into an inline snippet.
    assert any(
        re.search(r"`[\w./\-]+\.\w+:\d+", p["content"]) for p in concept_pages
    ), "expected at least one path:line source citation"

    # Reading Guide steps link to the concept pages they describe.
    guide = pages.get("reading-guide")
    if guide:
        assert "](concepts/" in guide["content"]


def test_background_analyze_marks_version_queued(client: TestClient):
    repo_id = _analyzed_repo(client)
    r = client.post(f"/api/recallstack/repositories/{repo_id}/analyze?wait=false")
    assert r.status_code == 200, r.text
    # A poller must not see a stale "ready" and think the rescan already finished.
    assert r.json()["status"] in {"queued", "pending", "scanning"}


def test_source_preview_reads_a_nested_file(client: TestClient):
    repo_id = _analyzed_repo(client)

    r = client.get(
        "/api/recallstack/source",
        params={"repository_id": repo_id, "path": "app/main.py", "start_line": 1, "end_line": 2},
    )

    assert r.status_code == 200, r.text
    assert "def main" in r.json()["content"] or "boot" in r.json()["content"]


def test_source_preview_refuses_secret_files(client: TestClient):
    # `path` is caller-supplied, so the endpoint cannot rely on concepts having
    # filtered it. It previously served any file inside the repository root.
    repo_path = Path(client.fixture_repo)  # type: ignore[attr-defined]
    (repo_path / ".env").write_text("OPENAI_API_KEY=sk-should-never-be-served\n", encoding="utf-8")
    repo_id = _analyzed_repo(client)

    r = client.get(
        "/api/recallstack/source",
        params={"repository_id": repo_id, "path": ".env"},
    )

    assert r.status_code == 403, r.text
    assert "sk-should-never-be-served" not in r.text
