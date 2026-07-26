"""Unit tests for the deterministic wiki search ranking."""

from __future__ import annotations

from recallstack.learning.wiki_search import (
    build_documents,
    classify_page,
    search,
    tokenize,
)

PAGES = [
    {
        "id": "index",
        "title": "Overview",
        "content": "# Overview\n\nA scanner turns a repository into a project context.\n",
    },
    {
        "id": "architecture",
        "title": "Architecture",
        "content": "# Architecture\n\n## Dependency graph\n\nThe graph ranks files by PageRank.\n",
    },
    {
        "id": "concepts/dependency-graph",
        "title": "Dependency Graph",
        "content": (
            "# Dependency Graph\n\n"
            "## Source evidence\n\n"
            "- `src/repowiki/core/graph.py:1-80`\n\n"
            "The graph builds edges between modules.\n"
        ),
    },
    {
        "id": "modules/app",
        "title": "app",
        "content": "# app\n\n## Files\n\n- `app/main.py` — Entrypoint\n",
    },
]


def _docs():
    return build_documents(
        PAGES,
        concept_paths={"dependency-graph": ["src/repowiki/core/graph.py"]},
        concept_ids={"dependency-graph": "concept-123"},
    )


def test_tokenize_splits_latin_and_expands_cjk_bigrams():
    assert tokenize("PageRank graph") == ["pagerank", "graph"]
    # A 4-character CJK run contributes its bigrams so partial phrases still hit.
    assert tokenize("依赖图构建") == ["依赖", "赖图", "图构", "构建"]
    # Two-character CJK runs are kept whole rather than split further.
    assert tokenize("依赖") == ["依赖"]


def test_classify_page_maps_ids_to_kinds():
    assert classify_page("index") == "overview"
    assert classify_page("architecture") == "architecture"
    assert classify_page("reading-guide") == "guide"
    assert classify_page("concepts/foo") == "concept"
    assert classify_page("modules/app") == "module"
    assert classify_page("whatever") == "page"


def test_title_match_outranks_body_match():
    results = search(_docs(), "dependency graph")
    assert results, "expected at least one hit"
    assert results[0]["page_id"] == "concepts/dependency-graph"
    # Architecture only mentions it in a heading/body, so it must rank lower.
    ranked_ids = [r["page_id"] for r in results]
    assert ranked_ids.index("concepts/dependency-graph") < ranked_ids.index("architecture")


def test_concept_is_findable_by_cited_source_path():
    results = search(_docs(), "graph.py")
    assert [r["page_id"] for r in results][0] == "concepts/dependency-graph"


def test_results_carry_concept_id_and_snippet():
    top = search(_docs(), "dependency graph")[0]
    assert top["concept_id"] == "concept-123"
    assert top["kind"] == "concept"
    assert top["snippet"]
    # Snippets are plain text — no leftover markdown syntax to render.
    assert "#" not in top["snippet"]


def test_blank_and_unmatched_queries_return_nothing():
    assert search(_docs(), "") == []
    assert search(_docs(), "   ") == []
    assert search(_docs(), "kubernetes") == []


def test_limit_is_respected():
    assert len(search(_docs(), "the", limit=2)) <= 2
