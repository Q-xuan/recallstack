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
    assert len(concept_list) >= 3

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
        assert "difficulty" not in page["content"].lower()
        assert "难度" not in page["content"]
        assert "本步要你干什么" not in page["content"]
        assert "## 过关" not in page["content"]

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
    assert r.json().get("annotations") == []


def test_source_preview_serves_scanned_text_without_working_copy(client: TestClient, monkeypatch):
    """GitHub/cloned repos have no local path; peek must use the analyze cache."""
    import shutil

    monkeypatch.setenv("RECALLSTACK_CONTENT_LANG", "zh")
    repo_id = _analyzed_repo(client)
    fixture = Path(client.fixture_repo)  # type: ignore[attr-defined]
    shutil.rmtree(fixture)

    r = client.get(
        "/api/recallstack/source",
        params={"repository_id": repo_id, "path": "README.md", "start_line": 1, "end_line": 2},
    )
    assert r.status_code == 200, r.text
    assert "Fixture" in r.json()["content"] or "Demo" in r.json()["content"]


def test_source_preview_github_repo_uses_scan_cache(client: TestClient, monkeypatch):
    from recallstack.db.models import Repository
    from recallstack.db.session import session_scope

    monkeypatch.setenv("RECALLSTACK_CONTENT_LANG", "zh")
    repo_id = _analyzed_repo(client)
    with session_scope() as session:
        row = session.get(Repository, repo_id)
        assert row is not None
        row.source_type = "github"
        row.source_location = "https://github.com/example/fixture"
        session.commit()

    r = client.get(
        "/api/recallstack/source",
        params={"repository_id": repo_id, "path": "README.md", "start_line": 1, "end_line": 48},
    )
    assert r.status_code == 200, r.text
    assert "Fixture" in r.json()["content"] or "Demo" in r.json()["content"]


def test_source_preview_missing_file_is_chinese_error(client: TestClient, monkeypatch):
    monkeypatch.setenv("RECALLSTACK_CONTENT_LANG", "zh")
    repo_id = _analyzed_repo(client)
    r = client.get(
        "/api/recallstack/source",
        params={"repository_id": repo_id, "path": "no-such-file.py"},
    )
    assert r.status_code == 404, r.text
    body = r.json()
    message = body.get("detail", {}).get("message") or body.get("detail") or ""
    assert "找不到工作副本里的这个文件" in str(message)


def test_source_preview_mini_repo_readme(client: TestClient, monkeypatch):
    monkeypatch.setenv("RECALLSTACK_CONTENT_LANG", "zh")
    mini = Path("fixtures/mini_repo").resolve()
    created = client.post(
        "/api/recallstack/repositories",
        json={"source_type": "local", "source_location": str(mini), "name": "mini"},
    )
    assert created.status_code == 200, created.text
    repo_id = created.json()["id"]
    analyzed = client.post(f"/api/recallstack/repositories/{repo_id}/analyze?wait=true")
    assert analyzed.status_code == 200, analyzed.text

    r = client.get(
        "/api/recallstack/source",
        params={"repository_id": repo_id, "path": "README.md", "start_line": 1, "end_line": 48},
    )
    assert r.status_code == 200, r.text
    assert "Mini Repo" in r.json()["content"]


def test_learning_path_api_omits_filler_and_states_mission(client: TestClient, monkeypatch):
    monkeypatch.setenv("RECALLSTACK_CONTENT_LANG", "zh")
    repo_id = _analyzed_repo(client)
    path = client.get(f"/api/recallstack/repositories/{repo_id}/learning-path")
    assert path.status_code == 200, path.text
    body = path.json()
    assert "先看进程怎么进" in body["description"] or "Walk the trunk" in body["description"]
    slugs = [n["concept"]["slug"] for n in body["nodes"] if n.get("concept")]
    titles = [n["concept"]["title"] for n in body["nodes"] if n.get("concept")]
    assert all(not s.startswith(("module-", "focus-", "file-")) for s in slugs)
    assert all("README.md" not in t and "Cargo.toml" not in t for t in titles)
    assert any(
        "指出" in (n.get("reason") or "") or "point" in (n.get("reason") or "").lower()
        for n in body["nodes"]
    )
    assert all(n.get("worksheet") for n in body["nodes"])
    worksheet = body["nodes"][0]["worksheet"]
    assert "## 本步要你干什么" in worksheet or "## What this step asks of you" in worksheet


def test_wiki_get_upgrades_legacy_concept_markdown(client: TestClient, monkeypatch):
    monkeypatch.setenv("RECALLSTACK_CONTENT_LANG", "zh")
    repo_id = _analyzed_repo(client)
    from sqlalchemy import select
    from sqlalchemy.orm.attributes import flag_modified

    from recallstack.db.models import RepositoryVersion
    from recallstack.db.session import session_scope

    old = (
        "# 项目目标\n\n"
        "> why-line\n\n"
        "## 为什么重要\n\n"
        "> why-line\n\n"
        "## 这份仓库做什么\n\n"
        "goal body\n\n"
        "## 源码证据\n\n"
        "- `README.md:1-48`\n\n"
        "## 自测\n\n"
        "1. x\n"
    )
    with session_scope() as session:
        version = session.scalars(
            select(RepositoryVersion)
            .where(RepositoryVersion.repository_id == repo_id)
            .order_by(RepositoryVersion.created_at.desc())
        ).first()
        assert version is not None
        payload = dict(version.wiki_pages or {})
        pages = []
        for page in payload.get("pages") or []:
            if page.get("id") == "concepts/project-goal":
                pages.append({**page, "content": old})
            else:
                pages.append(dict(page))
        payload["pages"] = pages
        version.wiki_pages = payload
        flag_modified(version, "wiki_pages")
        session.commit()

    wiki = client.get(f"/api/recallstack/repositories/{repo_id}/wiki")
    assert wiki.status_code == 200, wiki.text
    page = next(p for p in wiki.json()["pages"] if p["id"] == "concepts/project-goal")
    assert "## 本步要你干什么" not in page["content"]
    assert "用两句话写出这个仓库为谁" not in page["content"]
    assert "为什么重要" not in page["content"]
    assert "`README.md:1-48`" in page["content"]
    assert "点击展开" not in page["content"]
    assert "## 过关" not in page["content"]
    assert "## 它是什么" in page["content"]
    assert "## 先回到原理" not in page["content"]
    assert "goal body" in page["content"]


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


def test_progress_detail_is_published_and_localized(client, monkeypatch):
    """The LLM stage runs for minutes; the coarse status alone never moves.

    The analyzer already counted modules and threw the count away, so the UI
    had nothing to show between `llm_enriching` and `ready`.
    """
    monkeypatch.setenv("RECALLSTACK_CONTENT_LANG", "zh")

    from recallstack.application.analyze_repository import AnalyzeRepositoryService
    from recallstack.db.session import session_scope

    # Analyze synchronously: a background run would still be writing to this
    # version (and holding the SQLite write lock) while we publish below.
    repo_id = _analyzed_repo(client)

    version = client.get(f"/api/recallstack/repositories/{repo_id}/versions/latest").json()

    with session_scope() as session:
        AnalyzeRepositoryService(session)._publish_progress(version["id"], "Analyzed module 7/24")

    refreshed = client.get(f"/api/recallstack/repositories/{repo_id}/versions/latest").json()
    assert refreshed["progress_message"] == "已分析模块 7/24"


def test_unrecognized_progress_lines_pass_through():
    """A message added upstream should degrade to English, not vanish."""
    from recallstack.application.analyze_repository import AnalyzeRepositoryService

    assert AnalyzeRepositoryService._localize_progress("Something new") == "Something new"


def test_multipass_progress_lines_are_localized(monkeypatch):
    monkeypatch.setenv("RECALLSTACK_CONTENT_LANG", "zh")
    from recallstack.application.analyze_repository import AnalyzeRepositoryService

    loc = AnalyzeRepositoryService._localize_progress
    assert loc("Outlining wiki...") == "正在规划 Wiki 大纲"
    assert loc("Writing 4 modules...") == "正在撰写 4 个模块"
    assert loc("Wrote module 2/4") == "已撰写模块 2/4"
    assert loc("Verifying citations...") == "正在核验引用"


def test_starting_a_phase_clears_the_previous_detail():
    """Otherwise a stale module counter sits under the next phase's label."""
    from recallstack.application.analyze_repository import AnalyzeRepositoryService
    from recallstack.db.models import RepositoryVersion

    version = RepositoryVersion(status="scanning", progress_message="已分析模块 7/24")

    class _Session:
        def commit(self):
            pass

    service = AnalyzeRepositoryService.__new__(AnalyzeRepositoryService)
    service.session = _Session()
    service._set_status(version, "generating_wiki")

    assert version.status == "generating_wiki"
    assert version.progress_message is None


def test_interrupted_runs_are_failed_on_startup(client: TestClient):
    """A restart mid-analysis otherwise leaves a version the poller waits on forever."""
    from recallstack.db.models import RepositoryVersion
    from recallstack.db.session import session_scope

    repo_id = _analyzed_repo(client)
    version_id = client.get(f"/api/recallstack/repositories/{repo_id}/versions/latest").json()["id"]

    # simulate a process that died partway through the LLM stage
    with session_scope() as session:
        session.query(RepositoryVersion).filter(RepositoryVersion.id == version_id).update(
            {"status": "llm_enriching", "progress_message": "Analyzed module 3/24"}
        )

    init_recallstack()

    latest = client.get(f"/api/recallstack/repositories/{repo_id}/versions/latest").json()
    assert latest["status"] == "failed"
    assert latest["progress_message"] is None
    assert "interrupted" in (latest["error_message"] or "")


def test_startup_leaves_finished_runs_alone(client: TestClient):
    repo_id = _analyzed_repo(client)
    before = client.get(f"/api/recallstack/repositories/{repo_id}/versions/latest").json()
    assert before["status"] == "ready"

    init_recallstack()

    after = client.get(f"/api/recallstack/repositories/{repo_id}/versions/latest").json()
    assert after["status"] == "ready"
    assert after["error_message"] is None


def test_new_concepts_seed_the_review_queue(client: TestClient):
    """A fresh install has no mastery rows; review mode must still offer work."""
    _analyzed_repo(client)

    due = client.get("/api/recallstack/reviews/due").json()
    assert due, "queue should not be empty before any attempt"
    assert all(d["is_new"] for d in due)
    assert all(d["item_id"] for d in due)

    # And the session endpoint starts a run instead of 404ing.
    resp = client.get("/api/recallstack/sessions/review")
    assert resp.status_code == 200
    queue = resp.json()
    assert queue["mode"] == "review"
    assert queue["item_ids"]


def test_attempted_concept_leaves_the_new_queue(client: TestClient):
    _analyzed_repo(client)
    due = client.get("/api/recallstack/reviews/due").json()
    first = due[0]

    resp = client.post(
        f"/api/recallstack/items/{first['item_id']}/attempts?mode=review",
        json={"answer": "it scans the repository and builds the wiki", "confidence": 3},
    )
    assert resp.status_code == 200

    after = client.get("/api/recallstack/reviews/due").json()
    entry = next((d for d in after if d["concept_id"] == first["concept_id"]), None)
    # Either scheduled into the future (gone) or due again — never "new" again.
    assert entry is None or not entry["is_new"]


def test_ask_falls_back_to_search_without_llm(client: TestClient):
    """No API key in tests, so /ask must answer extractively with sources."""
    repo_id = _analyzed_repo(client)
    resp = client.post(
        f"/api/recallstack/repositories/{repo_id}/ask",
        json={"question": "boot 函数在哪里定义?"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["engine"] == "search"
    assert data["answer"]
    assert data["sources"], "fallback should still cite ranked pages"
    assert all(s["page_id"] for s in data["sources"])


def test_ask_before_analysis_is_409(client: TestClient):
    repo = client.post(
        "/api/recallstack/repositories",
        json={"source_type": "local", "source_location": client.fixture_repo},
    ).json()
    resp = client.post(
        f"/api/recallstack/repositories/{repo['id']}/ask",
        json={"question": "anything"},
    )
    assert resp.status_code == 409


def test_ask_unknown_repo_is_404(client: TestClient):
    resp = client.post(
        "/api/recallstack/repositories/nope/ask", json={"question": "hi"}
    )
    assert resp.status_code == 404
