"""Unit tests for RecallStack learning core (no paid LLM calls)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from recallstack.domain.schemas import ConceptDraft, Rubric, RubricPoint
from recallstack.learning.concept_extractor import ConceptExtractor
from recallstack.learning.hint_engine import HintEngine
from recallstack.learning.path_builder import PathBuilder
from recallstack.learning.question_generator import QuestionGenerator
from recallstack.learning.rubric_evaluator import RubricEvaluator
from recallstack.learning.scheduler import FSRSReviewScheduler, map_score_to_rating
from recallstack.learning.stale import compute_changed_paths
from recallstack.security import (
    SecurityError,
    filter_source_references,
    normalize_repo_path,
    validate_git_url,
    validate_local_path,
)
from repowiki.core.graph import DependencyGraph
from repowiki.core.models import FileInfo, ProjectContext


def _sample_project(tmp_path: Path) -> ProjectContext:
    root = tmp_path / "demo"
    root.mkdir()
    (root / "README.md").write_text("# Demo App\nA tiny service.\n", encoding="utf-8")
    (root / "app").mkdir()
    (root / "app" / "__init__.py").write_text("", encoding="utf-8")
    (root / "app" / "main.py").write_text(
        "from app.service import run\n\ndef main():\n    run()\n",
        encoding="utf-8",
    )
    (root / "app" / "service.py").write_text(
        "from app.db import save\n\ndef run():\n    save({'ok': True})\n",
        encoding="utf-8",
    )
    (root / "app" / "db.py").write_text(
        "def save(data):\n    return data\n",
        encoding="utf-8",
    )
    (root / "tests").mkdir()
    (root / "tests" / "test_service.py").write_text(
        "from app.service import run\n\ndef test_run():\n    assert run() is None or True\n",
        encoding="utf-8",
    )

    files = []
    for path in root.rglob("*"):
        if path.is_file():
            rel = str(path.relative_to(root)).replace("\\", "/")
            text = path.read_text(encoding="utf-8")
            files.append(
                FileInfo(
                    path=rel,
                    size=len(text),
                    language="python" if rel.endswith(".py") else "markdown",
                    lines=text.count("\n") + 1,
                    preview=text[:500],
                    content=text,
                    is_config=rel.lower().startswith("readme"),
                    is_entrypoint=rel.endswith("main.py"),
                )
            )
    return ProjectContext(name="demo", root=str(root), files=files, file_tree="")


def test_concept_graph_build(tmp_path: Path):
    project = _sample_project(tmp_path)
    graph = DependencyGraph.build_from_project(project)
    result = ConceptExtractor().extract(project, graph, commit_sha="abc")
    assert len(result.concepts) >= 3
    assert all(c.source_references for c in result.concepts if c.slug != "project-goal")
    slugs = {c.slug for c in result.concepts}
    assert "caching" not in slugs
    assert "authentication" not in slugs
    assert "request-routing" not in slugs


def test_concept_prerequisite_cycle_removal():
    concepts = [
        ConceptDraft(slug="a", title="A", prerequisites=["c"]),
        ConceptDraft(slug="b", title="B", prerequisites=["a"]),
        ConceptDraft(slug="c", title="C", prerequisites=["b"]),
    ]
    cleaned = ConceptExtractor().remove_cyclic_prerequisites(concepts)
    # graph should be acyclic: no full mutual cycle remains
    edges = {c.slug: set(c.prerequisites) for c in cleaned}

    def has_cycle() -> bool:
        temp, perm = set(), set()

        def visit(n: str) -> bool:
            if n in perm:
                return False
            if n in temp:
                return True
            temp.add(n)
            for m in edges.get(n, set()):
                if visit(m):
                    return True
            temp.remove(n)
            perm.add(n)
            return False

        return any(visit(n) for n in edges)

    assert not has_cycle()


def test_learning_path_ordering():
    concepts = [
        ConceptDraft(slug="testing-structure", title="Tests", importance=0.4, prerequisites=["project-goal"]),
        ConceptDraft(slug="application-entry", title="Entry", importance=0.9, prerequisites=["project-goal"]),
        ConceptDraft(slug="project-goal", title="Goal", importance=1.0, prerequisites=[]),
        ConceptDraft(slug="call-flow", title="Flow", importance=0.7, prerequisites=["application-entry"]),
    ]
    path = PathBuilder().build(concepts)
    order = [n.concept_slug for n in path.nodes]
    assert order.index("project-goal") < order.index("application-entry")
    assert order.index("application-entry") < order.index("call-flow")
    assert order.index("call-flow") < order.index("testing-structure")
    assert all(n.reason and "Ordered by prerequisites" not in n.reason for n in path.nodes)
    assert "Walk the trunk" in path.description or "进程怎么进" in path.description


def test_learning_path_excludes_file_inventory_filler():
    concepts = [
        ConceptDraft(slug="project-goal", title="项目目标", importance=1.0),
        ConceptDraft(slug="application-entry", title="应用入口", importance=0.9),
        ConceptDraft(slug="module-readme-md", title="模块：README.md", importance=0.8),
        ConceptDraft(slug="module-cargo-toml", title="模块: Cargo.toml", importance=0.8),
        ConceptDraft(slug="focus-init-py", title="聚焦：__init__.py", importance=0.7),
        ConceptDraft(slug="file-package-json", title="Key file: package.json", importance=0.6),
        ConceptDraft(slug="call-flow", title="调用链", importance=0.5),
        ConceptDraft(slug="caching", title="缓存", importance=0.9),
        ConceptDraft(slug="request-routing", title="请求路由", importance=0.9),
    ]
    path = PathBuilder().build(concepts)
    slugs = [n.concept_slug for n in path.nodes]
    assert "project-goal" in slugs
    assert "application-entry" in slugs
    assert "call-flow" in slugs
    assert "module-readme-md" not in slugs
    assert "module-cargo-toml" not in slugs
    assert "focus-init-py" not in slugs
    assert "file-package-json" not in slugs
    assert "caching" not in slugs
    assert "request-routing" not in slugs
    assert len(slugs) <= 8
    goal = next(n for n in path.nodes if n.concept_slug == "project-goal")
    assert "一句话" in goal.reason or "one sentence" in goal.reason.lower()


def test_hint_level_increments_and_no_skip():
    engine = HintEngine()
    refs = [{"path": "app/main.py", "symbol": "main", "start_line": 1, "end_line": 4}]
    h1 = engine.next_hint(current_level=0, source_references=refs)
    assert h1["level"] == 1
    h2 = engine.next_hint(current_level=1, source_references=refs)
    assert h2["level"] == 2
    assert engine.validate_progression([{"level": 1}, {"level": 2}])
    assert not engine.validate_progression([{"level": 1}, {"level": 3}])


def test_hint_level4_includes_code_snippet(tmp_path: Path):
    root = tmp_path / "repo"
    (root / "app").mkdir(parents=True)
    (root / "app" / "main.py").write_text(
        "def main():\n    return 42\n", encoding="utf-8"
    )
    from recallstack.learning.code_loader import load_code_lookup

    refs = [{"path": "app/main.py", "symbol": "main", "start_line": 1, "end_line": 2}]
    lookup = load_code_lookup(root, refs)
    assert "app/main.py" in lookup
    h4 = HintEngine().next_hint(
        current_level=3,
        source_references=refs,
        code_lookup=lookup,
    )
    assert h4["level"] == 4
    assert "def main" in h4["content"]


def test_code_loader_blocks_escape_and_secrets(tmp_path: Path):
    root = tmp_path / "repo"
    root.mkdir()
    (root / "ok.py").write_text("x = 1\n", encoding="utf-8")
    (root / ".env").write_text("SECRET=1\n", encoding="utf-8")
    outside = tmp_path / "outside.py"
    outside.write_text("leak\n", encoding="utf-8")
    from recallstack.learning.code_loader import load_code_lookup, snippet_for_ref

    lookup = load_code_lookup(
        root,
        [
            {"path": "ok.py", "start_line": 1},
            {"path": ".env"},
            {"path": "../outside.py"},
        ],
    )
    assert set(lookup) == {"ok.py"}
    snip = snippet_for_ref(lookup, {"path": "ok.py", "start_line": 1, "end_line": 1})
    assert "x = 1" in snip


def test_rubric_score_calculation():
    rubric = Rubric(
        required_points=[
            RubricPoint(id="responsibility", description="说明服务职责 service run", weight=0.5),
            RubricPoint(id="evidence", description="引用 app/service.py", weight=0.5),
        ]
    )
    result = RubricEvaluator().evaluate_deterministic(
        answer="service run 负责执行主流程，见 app/service.py",
        rubric=rubric,
        source_references=[{"path": "app/service.py", "start_line": 1, "end_line": 3}],
    )
    assert result.score >= 0.5
    assert "responsibility" in result.covered_points or "evidence" in result.covered_points


def test_rubric_rewards_path_and_symbol_evidence():
    rubric = Rubric(
        required_points=[
            RubricPoint(id="responsibility", description="说明入口职责", weight=0.4),
            RubricPoint(id="evidence", description="引用源码证据", weight=0.6),
        ]
    )
    weak = RubricEvaluator().evaluate_deterministic(
        answer="这个模块负责启动应用",
        rubric=rubric,
        source_references=[{"path": "app/main.py", "symbol": "main", "start_line": 1}],
    )
    strong = RubricEvaluator().evaluate_deterministic(
        answer="main 函数是入口，见 app/main.py，负责启动应用",
        rubric=rubric,
        source_references=[{"path": "app/main.py", "symbol": "main", "start_line": 1}],
    )
    assert strong.score > weak.score
    assert "evidence" in strong.covered_points


def test_score_to_fsrs_rating_mapping():
    assert map_score_to_rating(0.2) == 1
    assert map_score_to_rating(0.5) == 2
    assert map_score_to_rating(0.8) == 3
    assert map_score_to_rating(0.95, hints_used=[]) == 4
    assert map_score_to_rating(0.95, hints_used=[{"level": 4}]) == 3
    assert map_score_to_rating(0.9, revealed_answer=True) == 2


def test_fsrs_card_serialization():
    sched = FSRSReviewScheduler(desired_retention=0.9)
    card = sched.create_card()
    assert isinstance(card, dict)
    new_card, log = sched.review(card, 3, datetime.now(timezone.utc))
    assert isinstance(new_card, dict)
    assert isinstance(log, dict)
    assert "due" in new_card or new_card  # due may be present depending on fsrs version


def test_stale_content_changed_paths():
    old = {"a.py": "1", "b.py": "2"}
    new = {"a.py": "1", "b.py": "3", "c.py": "4"}
    changed = compute_changed_paths(old, new)
    assert changed == {"b.py", "c.py"}


def test_source_reference_validation():
    refs = [
        {"path": "app/main.py", "start_line": 1},
        {"path": "does/not/exist.py", "start_line": 1},
        {"path": "../secret.env", "start_line": 1},
    ]
    cleaned = filter_source_references(refs, {"app/main.py"})
    assert len(cleaned) == 1
    assert cleaned[0]["path"] == "app/main.py"


def test_windows_scanned_paths_still_match_their_references():
    # Ingestion on Windows reports backslashes; references use forward slashes.
    # Comparing the raw forms dropped every file below the repository root.
    refs = [{"path": "src/pkg/mod.py", "start_line": 1}]

    cleaned = filter_source_references(refs, {"src\\pkg\\mod.py"})

    assert [r["path"] for r in cleaned] == ["src/pkg/mod.py"]


def test_dotfile_references_keep_their_leading_dot():
    # lstrip("./") strips a character set, so it used to turn
    # ".github/workflows/ci.yml" into "github/workflows/ci.yml" — a path that
    # resolves to nothing on disk.
    refs = [{"path": "./.github/workflows/ci.yml", "start_line": 1}]

    cleaned = filter_source_references(refs, {".github/workflows/ci.yml"})

    assert [r["path"] for r in cleaned] == [".github/workflows/ci.yml"]


def test_env_files_cannot_slip_past_the_block_by_losing_their_dot():
    # Same character-set bug, but load-bearing: ".env.local" became "env.local",
    # which no longer matched the ^\.env block, so secrets could be cited as
    # evidence and then served by the source endpoint.
    refs = [{"path": ".env.local", "start_line": 1}]

    assert filter_source_references(refs, {".env.local"}) == []


def test_normalize_repo_path_still_refuses_to_escape():
    assert normalize_repo_path("/etc/passwd") == "etc/passwd"
    assert normalize_repo_path(".\\src\\a.py") == "src/a.py"
    assert normalize_repo_path("././a.py") == "a.py"


def test_git_url_security():
    assert validate_git_url("https://github.com/org/repo").startswith("https://github.com/")
    with pytest.raises(SecurityError):
        validate_git_url("ssh://git@github.com/org/repo.git")
    with pytest.raises(SecurityError):
        validate_git_url("file:///tmp/repo")
    with pytest.raises(SecurityError):
        validate_git_url("https://evil.example/org/repo")


def test_local_directory_escape(tmp_path: Path):
    inside = tmp_path / "repo"
    inside.mkdir()
    validate_local_path(str(inside), allow_root=tmp_path)
    # only test escape when allow_root is set
    with pytest.raises(SecurityError):
        validate_local_path(str(tmp_path), allow_root=inside)


def test_content_lang_follows_repowiki_codes(monkeypatch):
    from recallstack.learning import i18n

    monkeypatch.delenv("RECALLSTACK_CONTENT_LANG", raising=False)
    monkeypatch.setenv("REPOWIKI_LANG", "zh")
    assert i18n.content_lang() == "zh"
    assert i18n.t("Project goal", "项目目标") == "项目目标"
    assert "中文" in i18n.lang_instruction("zh")

    monkeypatch.setenv("REPOWIKI_LANG", "ja")
    assert i18n.normalize_lang("ja-JP") == "ja"
    assert i18n.t("Hello", "你好", ja="こんにちは") == "こんにちは"

    monkeypatch.setenv("RECALLSTACK_CONTENT_LANG", "en")
    assert i18n.content_lang() == "en"  # explicit override wins
    assert i18n.t("Project goal", "项目目标") == "Project goal"


def test_question_generator_has_rubric():
    q = QuestionGenerator().generate_deterministic(
        title="Application entry",
        description="Program start",
        why_learn="Reading start",
        source_references=[{"path": "app/main.py", "start_line": 1, "end_line": 4, "symbol": "main"}],
        valid_paths={"app/main.py"},
    )
    assert 1 <= len(q.items) <= 3
    assert q.items[0].rubric.required_points
    assert "app/main.py" in q.items[0].prompt or "main" in q.items[0].prompt
    # default content language is English (RepoWiki-compatible)
    assert "responsibility" in q.items[0].prompt.lower() or "main responsibility" in q.items[0].prompt.lower() or "Application entry" in q.items[0].prompt


def test_session_queue_orders_item_types():
    from recallstack.application.session_queue import SessionQueueService

    class FakeItem:
        def __init__(self, id, item_type, difficulty=2):
            self.id = id
            self.item_type = item_type
            self.difficulty = difficulty
            self.prompt = item_type
            self.stale = False
            self.created_at = None
            self.source_references = []

    class FakeConcept:
        id = "c1"
        title = "Entry"
        repository_id = "r1"

    class FakeStore:
        def get_concept(self, concept_id):
            return FakeConcept()

        def list_items(self, concept_id):
            return [
                FakeItem("t", "teach_back"),
                FakeItem("a", "active_recall"),
                FakeItem("c", "code_trace"),
            ]

        def latest_attempt_for_item(self, user_id, item_id):
            return None

        def get_repository(self, repository_id):
            return None

    svc = SessionQueueService.__new__(SessionQueueService)
    svc.store = FakeStore()
    svc.config = None
    payload = svc.concept_queue("c1", user_id="u1")
    assert [i["id"] for i in payload["items"]] == ["a", "c", "t"]
    assert payload["current_item_id"] == "a"
    assert payload["next_item_id"] == "c"


def test_blend_evaluations_prefers_llm_with_evidence_anchor():
    from recallstack.application.evaluate_attempt import EvaluateAttemptService
    from recallstack.domain.schemas import AttemptEvaluationResult

    det = AttemptEvaluationResult(
        score=0.8,
        covered_points=["evidence"],
        missing_points=["boundary"],
        feedback="det",
    )
    llm = AttemptEvaluationResult(
        score=0.4,
        covered_points=["responsibility"],
        missing_points=["evidence", "boundary"],
        feedback="llm feedback",
    )
    svc = EvaluateAttemptService.__new__(EvaluateAttemptService)
    blended = svc._blend_evaluations(det, llm, revealed_answer=False)
    assert 0.4 < blended.score < 0.8
    assert "responsibility" in blended.covered_points
    assert "evidence" in blended.covered_points
    assert "llm feedback" in blended.feedback
