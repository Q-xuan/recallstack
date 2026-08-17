"""Topic / wiki skeleton follows the scanned repo, not the grok-study word list."""

from __future__ import annotations

from recallstack.learning.concept_extractor import ConceptExtractor
from recallstack.learning.learning_contract import suggested_ask_questions
from recallstack.learning.path_builder import PathBuilder
from recallstack.learning.wiki_generator import build_wiki_payload
from repowiki.core.graph import DependencyGraph
from repowiki.core.models import FileInfo, ProjectContext
from repowiki.core.topics import build_deterministic_topics
from repowiki.core.wiki_builder import collapse_repeated_mermaid_labels

GROK_SLUGS = {
    "agent-loop",
    "agent-runtime",
    "terminal-ui",
    "tui-pager",
    "system-prompt",
    "subagent-scheduling",
    "acp-protocol",
    "context-assembly",
    "pty-control",
    "headless-modes",
}
GROK_MARKERS = (
    "xai-grok-pager",
    "xai-grok-agent",
    "start_turn",
    "connect 之后谁接手",
    "一轮里 start_turn",
)


def _file(path: str, content: str, *, entry: bool = False, language: str = "typescript") -> FileInfo:
    return FileInfo(
        path=path,
        size=len(content),
        language=language,
        lines=content.count("\n") + 1,
        preview=content[:400],
        content=content,
        is_entrypoint=entry,
        is_config=path.lower() in {"readme.md", "package.json", "pnpm-workspace.yaml"},
    )


def _dsh_project() -> ProjectContext:
    readme = """# DeepSeek Harness

DeepSeek Harness (`dsh`) is an open-source, plugin-based agent harness.
It adopts an everything-is-a-plugin philosophy, powered by a vendored
Cordis framework.

## Capability Seam

A seam is a swappable capability: Service Definition (`ctx.llm`, `ctx.fs`),
Service Provider (`llm-deepseek`, `fs-local`), and Consumer (`tool-bash`).
"""
    architecture = """# Architecture

Capability Seam: Service Definition / Provider / Consumer.
`packages/core` is the product API spine. `packages/fs` and `packages/llm`
are providers. `vendor/cordis` loads plugins onto ctx.
"""
    return ProjectContext(
        name="deepseek-harness",
        root=".",
        files=[
            _file("README.md", readme, language="markdown"),
            _file("docs/architecture.md", architecture, language="markdown"),
            _file("pnpm-workspace.yaml", "packages:\n  - packages/*\n  - apps/*\n", language="yaml"),
            _file(
                "apps/dsh/src/main.ts",
                "export function main() {\n  harness.boot();\n}\n",
                entry=True,
            ),
            _file(
                "packages/core/src/index.ts",
                "export class Harness {\n  boot() {}\n}\n",
            ),
            _file(
                "packages/core/src/plugin.ts",
                "export function definePlugin() {}\nexport class Plugin {}\n",
            ),
            _file(
                "packages/fs/src/local.ts",
                "export class LocalFS {\n  read() {}\n}\n",
            ),
            _file(
                "packages/llm/src/deepseek.ts",
                "export class DeepSeekLLM {\n  complete() {}\n}\n",
            ),
            _file(
                "vendor/cordis/src/context.ts",
                "export class Context {\n  plugin() {}\n}\n",
            ),
        ],
        file_tree="",
    )


def _all_text(payload: dict) -> str:
    parts = [payload.get("project_name") or ""]
    for page in payload.get("pages") or []:
        parts.append(page.get("title") or "")
        parts.append(page.get("content") or "")
    for item in payload.get("sidebar") or []:
        parts.append(item.get("title") or "")
        for child in item.get("children") or []:
            parts.append(child.get("title") or "")
    return "\n".join(parts)


def test_dsh_like_topics_follow_repo_not_grok_wordlist(monkeypatch):
    monkeypatch.setenv("RECALLSTACK_CONTENT_LANG", "zh")
    project = _dsh_project()
    graph = DependencyGraph.build_from_project(project)
    topics = build_deterministic_topics(project, graph, language="zh")
    ids = {t.id for t in topics}
    blob = " ".join(
        f"{t.id} {t.title} {t.purpose} {' '.join(t.key_files)}" for t in topics
    )

    assert "xai-grok-pager" not in blob
    assert "start_turn" not in blob
    assert not (ids & GROK_SLUGS)
    assert "getting-started" in ids
    assert "entry-and-boot" in ids
    assert any(
        token in ids
        for token in ("capability-seam", "plugin-architecture", "cordis", "core", "fs", "llm")
    )
    assert any(token in blob.lower() for token in ("plugin", "cordis", "seam"))
    boot = next(t for t in topics if t.id == "entry-and-boot")
    assert "grok" not in (boot.purpose or "").lower()
    assert "apps/dsh/src/main.ts" in boot.key_files


def test_dsh_like_wiki_and_path_are_repo_grounded(monkeypatch):
    monkeypatch.setenv("RECALLSTACK_CONTENT_LANG", "zh")
    project = _dsh_project()
    graph = DependencyGraph.build_from_project(project)
    payload = build_wiki_payload(project, graph, [])
    text = _all_text(payload)
    low = text.lower()

    for marker in GROK_MARKERS:
        assert marker.lower() not in low, marker
    assert "xai-grok-pager" not in text
    assert "Pager → start_turn → start_turn" not in text
    assert "start_turn --> start_turn" not in text.replace(" ", "")
    assert "A[\"start_turn\"] --> B[\"start_turn\"]" not in text
    assert any(
        token in low
        for token in ("plugin", "cordis", "capability seam", "packages/core", "ctx.llm")
    )
    assert "## 概述" in text
    assert "这篇文档讲" not in text
    assert "本步要你干什么" not in text

    questions = suggested_ask_questions(payload.get("pages") or [])
    qblob = " ".join(questions)
    assert "connect 之后谁接手" not in qblob
    assert "start_turn 之后谁调模型" not in qblob
    assert questions
    assert any(
        token in qblob.lower()
        for token in ("plugin", "cordis", "seam", "core", "fs", "llm", "dsh", "调用链")
    )

    concepts = ConceptExtractor().extract(project, graph).concepts
    slugs = {c.slug for c in concepts}
    assert not (slugs & GROK_SLUGS)
    path = PathBuilder().build(concepts)
    path_slugs = [n.concept_slug for n in path.nodes]
    assert path_slugs[0] == "project-goal"
    reasons = " ".join(n.reason for n in path.nodes)
    assert "xai-grok-pager" not in reasons
    assert "start_turn 之后谁调模型" not in reasons
    assert "connect 之后谁接手" not in reasons


def test_mermaid_does_not_keep_start_turn_self_loop():
    raw = (
        "flowchart LR\n"
        '  A["Pager"]\n'
        '  B["start_turn"]\n'
        '  C["start_turn"]\n'
        "  A --> B\n"
        "  B --> C\n"
    )
    out = collapse_repeated_mermaid_labels(raw)
    assert "B --> C" not in out
    assert "A --> B" in out
