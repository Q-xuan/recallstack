"""Topic / wiki skeleton follows the scanned repo, not the grok-study word list."""

from __future__ import annotations

import re

from recallstack.domain.schemas import ConceptDraft, SourceReference
from recallstack.learning.concept_extractor import ConceptExtractor
from recallstack.learning.learning_contract import suggested_ask_questions
from recallstack.learning.path_builder import PathBuilder
from recallstack.learning.wiki_generator import (
    WIKI_GROUND_REVISION,
    append_concept_pages,
    build_deterministic_wiki_data,
    build_wiki_payload,
)
from recallstack.learning.wiki_serve import materialize_wiki_payload
from repowiki.core.cite_check import verify_wiki_data
from repowiki.core.graph import DependencyGraph
from repowiki.core.grounding import (
    is_hollow_tip,
    rewrite_lecture_claim,
    rewrite_lecture_prose,
    should_reuse_analyzed_wiki,
    wiki_payload_cites_foreign_tree,
)
from repowiki.core.models import (
    ArchitectureDiagram,
    Citation,
    CodebasePart,
    FileInfo,
    KeyType,
    ProjectContext,
    ProjectOverview,
    Subsystem,
    TermTip,
    WikiData,
)
from repowiki.core.modules import group_into_modules
from repowiki.core.outline import build_deterministic_outline, merge_outline
from repowiki.core.scanner import build_file_tree
from repowiki.core.topics import (
    build_deterministic_topics,
    callpath_mermaid_for,
    codebase_structure_for,
    fill_codebase_purposes,
    is_boilerplate_pack_purpose,
    is_config_file_concept,
    is_english_pack_purpose,
    mermaid_is_local_package_subgraph,
    pin_topic_evidence_cite,
    prefer_overview_mermaid,
)
from repowiki.core.wiki_builder import (
    WikiBuilder,
    clip_mermaid_label,
    collapse_repeated_mermaid_labels,
    localize_split_table_markdown,
    rewrite_start_claim_helper_symbols,
)

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

```ts
export type Config = { name: string };
```
"""
    architecture = """# Architecture

This note is the title page, not the seam contract.

## Capability Seam

A seam is a swappable capability defined by three roles:
Service Definition (`ctx.llm`, `ctx.fs`), Service Provider, and Consumer.
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


def _dsh_project_with_decoys() -> ProjectContext:
    """Real harness plus the files that stole seam / loop / plugin evidence."""
    project = _dsh_project()
    decoys = [
        _file("AGENTS.md", "# Agent notes\nnot a package.\n", language="markdown"),
        _file("CLAUDE.md", "# Claude\nnot a package.\n", language="markdown"),
        _file("packages/README.md", "# packages\nnot a crate.\n", language="markdown"),
        _file(
            "packages/client/tsdown.client.ts",
            "export const browserSourcePath = 1\n"
            "export const clientBundle = 1\n"
            "export const clientLibrary = 1\n"
            "export const clientOnly = 1\n"
            "export function defineStore() {}\n",
        ),
        _file(
            "packages/client/src/store.ts",
            "export function defineStore() { return null }\n",
        ),
        _file(
            "docs/postmortem/0003-web-agent-gui-feedback-loop.md",
            "seedPackageInventory whenTurnsSettled\n",
            language="markdown",
        ),
        _file(
            "apps/cli/README.md",
            "# CLI\nprofile and bundle.\n",
            language="markdown",
        ),
        _file(
            "apps/cli/config/agent-presets/code/agent.cordis.yml",
            "Clock: {}\n",
            language="yaml",
        ),
        _file(
            "apps/cli/e2e/WebScaffold.ts",
            "export class WebScaffold {}\n",
        ),
        _file("apps/cli/e2e/session.jsonl", '{"d":1}\n', language="jsonl"),
        _file(
            "apps/web/tests/goal-multi-turn-actions.e2e.ts",
            "export class WebScaffold {\n  drive() {}\n}\n",
        ),
        _file(
            "apps/web/src/node-module-stub.ts",
            "export type LoadHookContext = { href: string }\n"
            "export function load(ctx: LoadHookContext) { return ctx }\n",
        ),
        _file(
            "apps/cli/src/bin.ts",
            "export function readVersion() { return '1' }\n"
            "export function main() { boot() }\n",
            entry=True,
        ),
        _file(
            "packages/acp/package.json",
            '{"name":"@dsh/acp","description":"The ACP group exposes harness agents over JSON-RPC"}\n',
            language="json",
        ),
        _file(
            "packages/acp/src/index.ts",
            "export function serveAcp() {}\n",
        ),
        _file(
            "packages/api/src/index.ts",
            "export function createApi() {}\n",
        ),
        _file(
            "packages/client/src/session.ts",
            "export function openSession() {}\n",
        ),
        _file(
            "packages/client/src/ui.ts",
            "export function renderUi() {}\n",
        ),
        _file(
            "apps/web/src/main.ts",
            "export function main() { mount() }\n",
            entry=True,
        ),
        _file(
            "packages/boot/src/index.ts",
            "export function boot() { loadBundle() }\n",
        ),
        _file(
            "packages/boot/src/app-boot.ts",
            "/** Stack bundle patches into the Cordis root and expose ctx. */\n"
            "export function appBoot(ctx) { ctx.plugin(loadBundle()) }\n",
        ),
        _file(
            "packages/boot/package.json",
            '{"name":"@dsh/boot","description":"Stack bundle patches into the Cordis root"}\n',
            language="json",
        ),
        _file(
            "apps/cli/package.json",
            '{"name":"@dsh/cli","description":"Parse argv and start the runner by profile"}\n',
            language="json",
        ),
        _file(
            "apps/cli/src/args.ts",
            "export function parseArgs(argv: string[]) { return argv }\n",
        ),
        _file(
            "apps/web/package.json",
            '{"name":"@dsh/web","description":"Desktop/Web client UI"}\n',
            language="json",
        ),
        _file(
            "packages/bundle/src/index.ts",
            "export function loadBundle() {}\n",
        ),
        _file(
            "packages/core/src/session.ts",
            "export async function runTurn() { await model() }\n",
        ),
    ]
    project.files.extend(decoys)
    return project


def _dsh_project_with_notes() -> ProjectContext:
    """Harness product plus a bulky `.agents/notes` tree (DeepWiki gap)."""
    project = _dsh_project()
    readme = next(f for f in project.files if f.path == "README.md")
    readme.content = (
        (readme.content or "")
        + "\n\n## Install\n\n```bash\npnpm install\npnpm --filter dsh start\n"
        "pnpm --filter @dsh/web dev\n```\n"
    )
    readme.preview = readme.content[:400]
    extras = [
        _file(
            ".i18n.yaml",
            "nav:\n  overview: 概述\n  notes: 决策日志\n",
            language="yaml",
        ),
        _file(
            ".agents/notes/archived/old-decision.md",
            "# archived\n旧决策，不是产品主线。\n",
            language="markdown",
        ),
        _file(
            ".agents/notes/tools-schema.md",
            "# 工具系统与 schema\n笔记，不是 ToolBridge。\n",
            language="markdown",
        ),
    ]
    for i in range(36):
        extras.append(
            _file(
                f".agents/notes/decision-{i:02d}.md",
                f"# Decision {i}\n这是决策日志，不是 dsh 源码。\n",
                language="markdown",
            )
        )
    project.files.extend(extras)
    project.file_tree = build_file_tree(project.files)
    return project


_NOTES_AS_PRODUCT = (
    "不是源码实现",
    "只是决策日志",
    "决策日志仓库",
    "架构记忆库",
    "notes 目录层级",
    "i18n 元数据与导航翻译",
    "archived 决策日志",
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


def test_dsh_like_polluted_llm_overview_is_rewritten_to_tree(monkeypatch):
    monkeypatch.setenv("RECALLSTACK_CONTENT_LANG", "zh")
    project = _dsh_project()
    graph = DependencyGraph.build_from_project(project)
    polluted = WikiData(
        overview=ProjectOverview(
            name="deepseek-harness",
            description="`xai-grok-pager` 负责进程启动，`xai-grok-agent` 驱动 agent 循环。",
            runtime_flow="一轮从 Pager 进 start_turn。",
            mermaid_component=(
                "flowchart LR\n"
                '  A["Pager"] --> B["start_turn"] --> C["Agent Loop"]\n'
            ),
            codebase_structure=[
                CodebasePart(
                    name="xai-grok-pager",
                    location="packages/xai-grok-pager",
                    purpose="进程启动",
                )
            ],
        ),
        architecture=ArchitectureDiagram(
            architecture_type="plugin-system",
            description="Pager → start_turn → Agent Loop",
            mermaid_component='flowchart LR\n  A["Pager"] --> B["start_turn"]\n',
        ),
    )
    cleaned = verify_wiki_data(polluted, project)
    payload = build_wiki_payload(project, graph, [], wiki_data=cleaned)
    text = _all_text(payload)
    for marker in GROK_MARKERS:
        assert marker.lower() not in text.lower(), marker
    assert "packages/xai-grok-pager" not in text
    assert "Pager → start_turn" not in text
    assert payload.get("ground_revision") == WIKI_GROUND_REVISION
    assert any(
        token in text
        for token in ("packages/core", "Cordis", "plugin", "Capability Seam")
    )
    questions = suggested_ask_questions(payload.get("pages") or [])
    qblob = " ".join(questions)
    assert "一轮里 start_turn 之后谁调模型" not in qblob
    assert "Pager 把模型流式输出写进哪块缓冲区" not in qblob
    assert questions
    assert any(
        token in qblob.lower()
        for token in ("plugin", "cordis", "seam", "core", "fs", "llm", "dsh", "调用链")
    )
    texts = {f.path: f.content or "" for f in project.files}
    assert not wiki_payload_cites_foreign_tree(payload, texts)
    stale = {
        "ground_revision": 0,
        "pages": [
            {
                "id": "index",
                "title": "概述",
                "content": "`xai-grok-pager` 负责进程启动。Pager → start_turn。",
            }
        ],
    }
    assert wiki_payload_cites_foreign_tree(stale, texts)
    assert not should_reuse_analyzed_wiki(stale, texts)
    assert should_reuse_analyzed_wiki(payload, texts)


def test_dsh_like_notes_volume_does_not_steal_overview(monkeypatch):
    monkeypatch.setenv("RECALLSTACK_CONTENT_LANG", "zh")
    project = _dsh_project_with_notes()
    graph = DependencyGraph.build_from_project(project)
    topics = build_deterministic_topics(project, graph, language="zh")
    ids = {t.id for t in topics}
    titles = " ".join(t.title for t in topics)
    blob = " ".join(
        f"{t.id} {t.title} {t.purpose} {' '.join(t.key_files)}" for t in topics
    )

    assert "getting-started" in ids
    gs = next(t for t in topics if t.id == "getting-started")
    assert gs.title == "快速开始"
    assert gs.key_files == ["README.md"]
    assert "notes 目录" not in gs.title
    assert any(
        token in ids
        for token in ("capability-seam", "plugin-architecture", "cordis", "core")
    )
    assert any(token in blob.lower() for token in ("plugin", "cordis", "seam"))
    assert "i18n" not in ids
    assert "archived" not in ids
    assert "agents" not in ids
    assert "决策日志" not in titles
    assert "i18n 元数据" not in titles
    assert not any(p.startswith(".agents/") for t in topics for p in t.key_files)
    assert not any(p == ".i18n.yaml" for t in topics for p in t.key_files)

    payload = build_wiki_payload(project, graph, [])
    text = _all_text(payload)
    index = next(p for p in payload["pages"] if p["id"] == "index")
    gs_page = next(p for p in payload["pages"] if p["id"] == "getting-started")
    assert index["title"] == "概述"
    assert "# DeepSeek Harness" in index["content"]
    assert "# TypeName" not in index["content"]
    assert "决策日志仓库" not in index["content"]
    for phrase in _NOTES_AS_PRODUCT:
        assert phrase not in index["content"], phrase
        assert phrase not in gs_page["title"], phrase
        assert phrase not in gs_page["content"].split("\n")[0], phrase
    assert gs_page["title"] == "快速开始"
    assert "notes 目录层级" not in gs_page["title"]
    assert "跑起来" in gs_page["content"]
    assert any(tok in gs_page["content"] for tok in ("pnpm", "npm", "源码", "Web UI"))
    assert any(
        token in text
        for token in ("Cordis", "plugin", "Capability Seam", "packages/core")
    )
    sidebar_titles = []
    for item in payload.get("sidebar") or []:
        sidebar_titles.append(item.get("title") or "")
        for child in item.get("children") or []:
            sidebar_titles.append(child.get("title") or "")
    side = " ".join(sidebar_titles)
    assert "Cordis" in side or "Plugin" in side or "Capability Seam" in side
    assert "i18n 元数据" not in side
    assert "archived 决策日志" not in side
    assert "notes 目录层级" not in side

    modules = group_into_modules(project.files)
    outline = build_deterministic_outline(project, modules, graph, language="zh")
    assert ".agents" not in outline.overview_focus
    assert "packages" in outline.overview_focus or "apps" in outline.overview_focus
    tree = project.file_tree
    assert "packages/" in tree or "core" in tree
    assert "decision-00.md" not in tree
    assert "agent-notes files" in tree

    concepts = ConceptExtractor().extract(project, graph).concepts
    path = PathBuilder().build(concepts)
    path_slugs = [n.concept_slug for n in path.nodes]
    assert path_slugs[0] == "project-goal"
    assert "agents" not in path_slugs
    assert "notes" not in path_slugs
    assert "i18n" not in path_slugs
    assert "archived" not in path_slugs


def test_dsh_like_notes_as_product_llm_overview_is_rewritten(monkeypatch):
    monkeypatch.setenv("RECALLSTACK_CONTENT_LANG", "zh")
    project = _dsh_project_with_notes()
    graph = DependencyGraph.build_from_project(project)
    polluted = WikiData(
        overview=ProjectOverview(
            name="DeepSeek Harness 决策日志仓库（.agents/notes）",
            one_liner="这个仓库不是 dsh 的源码实现，而是决策日志与架构记忆库。",
            document_scope="这个仓库不是 dsh 的源码实现，而是决策日志与架构记忆库。",
            description="notes 目录层级与生命周期。",
            runtime_flow="从 `.agents/notes` 读决策日志。",
        )
    )
    cleaned = verify_wiki_data(polluted, project)
    payload = build_wiki_payload(project, graph, [], wiki_data=cleaned)
    index = next(p for p in payload["pages"] if p["id"] == "index")
    assert "决策日志仓库" not in index["content"]
    assert "不是" not in index["content"].split("\n")[0]
    assert "# DeepSeek Harness" in index["content"]
    assert "# TypeName" not in index["content"]
    assert any(
        token in _all_text(payload)
        for token in ("Cordis", "plugin", "Capability Seam", "packages/core")
    )
    gs = next(p for p in payload["pages"] if p["id"] == "getting-started")
    assert gs["title"] == "快速开始"
    assert "notes 目录层级" not in gs["title"]


def test_merge_outline_drops_notes_as_product_focus():
    project = _dsh_project_with_notes()
    modules = group_into_modules(project.files)
    graph = DependencyGraph.build_from_project(project)
    base = build_deterministic_outline(project, modules, graph, language="zh")
    from repowiki.core.models import WikiOutline

    llm = WikiOutline(
        overview_focus="这个仓库不是源码实现，只是决策日志。",
        architecture_focus="Hub packages to explain first: `.agents/notes`.",
        topics=[],
    )
    merged = merge_outline(
        base, llm, known_modules=set(modules), known_paths={f.path for f in project.files}
    )
    assert "不是源码" not in merged.overview_focus
    assert "只是决策日志" not in merged.overview_focus


def _assert_overview_chips_intact(content: str) -> None:
    first = next((ln for ln in content.splitlines() if ln.startswith("# ")), "")
    assert first == "# DeepSeek Harness"
    assert "# TypeName" not in content
    assert "README.ts" not in content
    assert "`ts:1`" not in content
    assert "src/file.ts" not in content
    assert "`README.md`" in content or "`README.md:" in content
    assert "README.md`" in content
    assert "apps/dsh/src/main.ts" in content
    assert content.count("启动，一次调用从这里进图") <= 1


def test_dsh_like_overview_survives_materialize_without_broken_chips(monkeypatch):
    """GET materialize must not smash H1 / path:line chips (DeepWiki regression)."""
    monkeypatch.setenv("RECALLSTACK_CONTENT_LANG", "zh")
    project = _dsh_project_with_notes()
    graph = DependencyGraph.build_from_project(project)
    payload = build_wiki_payload(project, graph, [])
    texts = {f.path: f.content or "" for f in project.files}
    out = materialize_wiki_payload(payload, [], texts)
    index = next(p for p in out["pages"] if p["id"] == "index")
    _assert_overview_chips_intact(index["content"])
    assert any(
        token in index["content"]
        for token in ("Cordis", "plugin", "Capability Seam", "packages")
    )
    for phrase in _NOTES_AS_PRODUCT:
        assert phrase not in index["content"], phrase
    gs = next(p for p in out["pages"] if p["id"] == "getting-started")
    assert gs["title"] == "快速开始"
    assert "open-source, plugin-based agent harness" not in gs["content"]
    assert "export type Config" not in gs["content"]
    assert "跑起来" in gs["content"]
    assert any(tok in gs["content"] for tok in ("pnpm", "npm", "源码", "Web UI"))
    assert "`README.md`" in gs["content"]


def test_dsh_like_typename_llm_overview_is_repaired(monkeypatch):
    """Schema leftovers (TypeName / src/file.ts / ts:1) must not become the H1 or chips."""
    monkeypatch.setenv("RECALLSTACK_CONTENT_LANG", "zh")
    project = _dsh_project()
    graph = DependencyGraph.build_from_project(project)
    polluted = WikiData(
        overview=ProjectOverview(
            name="TypeName",
            description=(
                "# TypeName\n\n"
                "DeepSeek Harness (`dsh`) is an open-source, plugin-based agent harness.\n"
            ),
            what_it_is=[
                "仓库目标与边界写在 README，而不是目录名。 `README.ts:24 Config`",
                "进程从 `src/file.ts:12 TypeName` 启动，一次调用从这里进图。",
                "进程从 `ts:1` 启动，一次调用从这里进图。",
                "进程从 `apps/dsh/src/main.ts:1` 启动，一次调用从这里进图。",
                "进程从 `apps/dsh/src/main.ts:1 main` 启动，一次调用从这里进图。",
            ],
            citations=[
                Citation(path="README.ts", start_line=24, symbol="Config"),
                Citation(path="src/file.ts", start_line=12, symbol="TypeName"),
                Citation(path="README.md", start_line=1, note="README"),
                Citation(path="apps/dsh/src/main.ts", start_line=1, symbol="main"),
            ],
        )
    )
    cleaned = verify_wiki_data(polluted, project)
    payload = build_wiki_payload(project, graph, [], wiki_data=cleaned)
    texts = {f.path: f.content or "" for f in project.files}
    out = materialize_wiki_payload(payload, [], texts)
    index = next(p for p in out["pages"] if p["id"] == "index")
    _assert_overview_chips_intact(index["content"])
    assert any(
        token in _all_text(out)
        for token in ("Cordis", "plugin", "Capability Seam", "packages")
    )
    gs = next(p for p in out["pages"] if p["id"] == "getting-started")
    assert "open-source, plugin-based agent harness" not in gs["content"]
    assert "# TypeName" not in gs["content"]


def test_dsh_decoys_do_not_steal_overview_or_topics(monkeypatch):
    monkeypatch.setenv("RECALLSTACK_CONTENT_LANG", "zh")
    project = _dsh_project_with_decoys()
    graph = DependencyGraph.build_from_project(project)
    topics = build_deterministic_topics(project, graph, language="zh")
    by_id = {t.id: t for t in topics}

    structure = codebase_structure_for(project, language="zh")
    locs = {row.location for row in structure}
    names = {row.name for row in structure}
    assert "README.md" not in locs
    assert "AGENTS.md" not in names
    assert "CLAUDE.md" not in names
    assert "packages/README.md" not in locs
    assert any(loc.startswith("apps/") or loc.startswith("packages/") for loc in locs)

    seam = by_id["capability-seam"]
    assert any("docs/architecture.md" in p or "packages/core" in p for p in seam.key_files)
    assert not any("tsdown" in p or "defineStore" in p for p in seam.key_files)
    assert "Capability Seam" in (seam.purpose or "")
    assert "Definition" in (seam.purpose or "") or "Provider" in (seam.purpose or "")

    plugin = by_id["plugin-architecture"]
    assert any(
        tok in p
        for p in plugin.key_files
        for tok in ("packages/boot", "packages/bundle", "packages/core", "plugin")
    )
    assert not any(p.endswith("README.md") for p in plugin.key_files)

    cordis = by_id["cordis"]
    assert any("vendor/cordis" in p or "packages/core" in p for p in cordis.key_files)
    assert not any(p.endswith(".yml") or p.endswith(".yaml") for p in cordis.key_files)

    if "agent-loop" in by_id:
        loop_files = by_id["agent-loop"].key_files
        assert not any("postmortem" in p or "e2e" in p or p.endswith(".md") for p in loop_files)
        assert not any("WebScaffold" in p or "/tests/" in p for p in loop_files)

    payload = build_wiki_payload(project, graph, [])
    texts = {f.path: f.content or "" for f in project.files}
    out = materialize_wiki_payload(payload, [], texts)
    index = next(p for p in out["pages"] if p["id"] == "index")
    gs = next(p for p in out["pages"] if p["id"] == "getting-started")
    blob = index["content"] + "\n" + gs["content"]
    assert "`ts:1`" not in blob
    assert "- ts:1" not in blob
    assert "`client.ts:1`" not in blob
    assert "- client.ts:1" not in blob
    assert "files).ts" not in blob
    assert "organized as directory modules" not in blob
    assert "Configuration lives in ." not in blob
    split_sec = ""
    if "代码如何拆分" in index["content"]:
        split_sec = index["content"].split("代码如何拆分", 1)[1]
        split_sec = split_sec.split("## ", 1)[0]
    assert "| README.md |" not in split_sec
    assert "| AGENTS.md |" not in split_sec
    assert "| CLAUDE.md |" not in split_sec
    assert "packages/README.md" not in split_sec
    assert "tsdown.client.ts" not in index["content"]
    assert "seedPackageInventory" not in index["content"]
    assert "whenTurnsSettled" not in index["content"]
    assert "agent.cordis.yml" not in index["content"]
    assert "WebScaffold" not in index["content"]
    start_lines = [
        ln
        for ln in index["content"].splitlines()
        if "启动，一次调用从这里进图" in ln or "process starts at" in ln.lower()
    ]
    assert start_lines
    assert all(
        "node-module-stub" not in ln
        and "LoadHookContext" not in ln
        and "e2e" not in ln
        and "fixture" not in ln
        and "tsdown" not in ln
        for ln in start_lines
    )
    assert any(
        "apps/cli/src/bin.ts" in ln
        or "apps/web/src/main.ts" in ln
        or "apps/dsh/src/main.ts" in ln
        for ln in start_lines
    )
    link_lines = [
        ln
        for ln in index["content"].splitlines()
        if "接住链路上的一段工作" in ln or "owns one stretch" in ln.lower()
    ]
    assert link_lines
    assert all(
        "node-module-stub" not in ln
        and "LoadHookContext" not in ln
        and "e2e" not in ln
        and "fixture" not in ln
        and "tsdown" not in ln
        for ln in link_lines
    )
    cordis_lines = [ln for ln in link_lines if "Cordis" in ln or "插件容器" in ln]
    assert cordis_lines
    assert all(
        "vendor/cordis" in ln or "packages/boot" in ln or "app-boot" in ln
        for ln in cordis_lines
    )
    assert "这一包在仓库里的职责边界" not in split_sec
    assert "Responsibility boundary of" not in split_sec
    if "| cli |" in split_sec or "| boot |" in split_sec:
        assert "职责边界" not in split_sec
    if "| cli |" in split_sec:
        assert "argv" in split_sec or "profile" in split_sec or "runner" in split_sec
    if "| boot |" in split_sec:
        assert "bundle" in split_sec or "Cordis" in split_sec or "patch" in split_sec
    assert "概述页需要说明" not in gs["content"]
    assert "产品形态包括" not in gs["content"]
    gs_flow = ""
    if "## 调用链" in gs["content"]:
        gs_flow = gs["content"].split("## 调用链", 1)[1].split("## ", 1)[0]
    assert gs_flow
    assert "概述页需要说明" not in gs_flow
    assert any(tok in gs_flow for tok in ("pnpm", "dsh web", "bin.ts", "args.ts", "启动"))
    assert "的 、" not in blob
    assert "的、" not in blob
    assert "start_turn" not in blob.lower() or "start_turn" in texts.get(
        "packages/core/src/session.ts", ""
    )

    seam_page = next(
        (p for p in out["pages"] if p["id"] == "topics/capability-seam"), None
    )
    assert seam_page is not None
    assert "defineStore" not in seam_page["content"]
    assert "Definition" in seam_page["content"] or "Provider" in seam_page["content"]

    wiki = WikiBuilder().build(
        project,
        build_deterministic_wiki_data(project, graph, []),
        graph,
        language="zh",
    )
    draft = ConceptDraft(
        slug="agent-loop",
        title="Agent Loop",
        description="一轮对话怎么走。",
        importance=0.9,
        source_references=[
            SourceReference(path="packages/core/src/session.ts", start_line=1, symbol="runTurn"),
        ],
    )
    page = append_concept_pages(wiki, [draft], file_texts=texts).get_page("concepts/agent-loop")
    assert page is not None
    assert "start_turn 是这一轮的闸门" not in page.content
    assert "不是重绘界面" not in page.content
    assert "WebScaffold" not in page.content
    assert ".e2e.ts" not in page.content
    assert "goal-multi-turn-actions" not in page.content

    stolen = ConceptDraft(
        slug="agent-loop",
        title="Agent Loop",
        description="一轮由 e2e 测试通过 WebScaffold 驱动。",
        importance=0.9,
        source_references=[
            SourceReference(
                path="apps/web/tests/goal-multi-turn-actions.e2e.ts",
                start_line=15,
                symbol="WebScaffold",
            ),
        ],
    )
    stolen_page = append_concept_pages(
        WikiBuilder().build(
            project,
            build_deterministic_wiki_data(project, graph, []),
            graph,
            language="zh",
        ),
        [stolen],
        file_texts=texts,
    ).get_page("concepts/agent-loop")
    assert stolen_page is not None
    assert "WebScaffold" not in stolen_page.content
    assert ".e2e.ts" not in stolen_page.content
    materialized = materialize_wiki_payload(
        {
            "pages": [
                {
                    "id": "concepts/agent-loop",
                    "title": "Agent Loop",
                    "content": stolen_page.content,
                    "parent_id": "",
                    "order": 1,
                }
            ],
            "sidebar": [],
        },
        [stolen],
        texts,
    )
    concept_md = next(
        p["content"] for p in materialized["pages"] if p["id"] == "concepts/agent-loop"
    )
    assert "WebScaffold" not in concept_md
    assert ".e2e.ts" not in concept_md


def test_callpath_stub_boilerplate_and_overview_instruction_are_rewritten(monkeypatch):
    """Deterministic fallback must not keep stub evidence, 职责边界, or 概述页提纲."""
    monkeypatch.setenv("RECALLSTACK_CONTENT_LANG", "zh")
    project = _dsh_project_with_decoys()
    graph = DependencyGraph.build_from_project(project)
    polluted = WikiData(
        overview=ProjectOverview(
            name="deepseek-harness",
            runtime_flow=(
                "概述页需要说明这个仓库是 DeepSeek 官方桌面/Web 客户端与 CLI 的 monorepo："
                "产品形态包括 apps/web。"
            ),
            what_it_is=[
                "「Cordis 与插件容器」接住链路上的一段工作，"
                "证据在 `apps/web/src/node-module-stub.ts:12 LoadHookContext`。",
                "进程从 `apps/cli/src/bin.ts:1` 启动，一次调用从这里进图。",
            ],
            codebase_structure=[
                CodebasePart(
                    name="cli",
                    location="apps/cli",
                    purpose="`apps/cli` 这一包在仓库里的职责边界。",
                ),
                CodebasePart(
                    name="boot",
                    location="packages/boot",
                    purpose="`packages/boot` 这一包在仓库里的职责边界。",
                ),
            ],
            subsystems=[
                Subsystem(
                    name="Cordis 与插件容器",
                    role="装 plugin",
                    key_types=[
                        KeyType(
                            name="LoadHookContext",
                            path="apps/web/src/node-module-stub.ts",
                            line=12,
                        )
                    ],
                    files=["apps/web/src/node-module-stub.ts"],
                )
            ],
        ),
        architecture=ArchitectureDiagram(
            architecture_type="plugin-system",
            description=(
                "按 `ghost/order.ts` 顺序叠加 bundle patch，"
                "再叠加 profile 的 `ghost/profile.yml`、`$DSH_HOME/cordis.patch.yml`。"
            ),
        ),
    )
    cleaned = verify_wiki_data(polluted, project)
    assert not any(
        "node-module-stub" in (item or "") for item in cleaned.overview.what_it_is
    )
    assert all(
        not is_boilerplate_pack_purpose(row.purpose)
        for row in cleaned.overview.codebase_structure
    )
    payload = build_wiki_payload(project, graph, [], wiki_data=cleaned)
    texts = {f.path: f.content or "" for f in project.files}
    out = materialize_wiki_payload(payload, [], texts)
    index = next(p for p in out["pages"] if p["id"] == "index")
    gs = next(p for p in out["pages"] if p["id"] == "getting-started")
    arch = next(p for p in out["pages"] if p["id"] == "architecture")
    assert "node-module-stub" not in index["content"]
    assert "LoadHookContext" not in index["content"]
    assert "这一包在仓库里的职责边界" not in index["content"]
    assert "argv" in index["content"] or "profile" in index["content"]
    assert "bundle" in index["content"] or "Cordis" in index["content"]
    assert "概述页需要说明" not in gs["content"]
    assert "产品形态包括" not in gs["content"]
    assert any(tok in gs["content"] for tok in ("pnpm", "bin.ts", "args.ts", "dsh"))
    assert "的 、" not in arch["content"]
    assert "的、" not in arch["content"]
    assert "按 顺序" not in arch["content"]


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


def _polluted_90_wiki(project: ProjectContext) -> WikiData:
    """LLM leftover that must still reach 90 after fallback/verify."""
    return WikiData(
        overview=ProjectOverview(
            name="deepseek-harness",
            what_it_is=[
                "解释 Capability Seam 如何界定插件与宿主之间的能力边界。"
                "证据在 `docs/architecture.md:1`。",
                "说明 client runtime 中的 conversation 如何保存会话。",
                "Capability Seam 是 Service Definition / Provider / Consumer，把 / 接上。",
                "进程从 `apps/cli/src/bin.ts:20 readVersion` 启动，一次调用从这里进图。",
            ],
            mermaid_component=(
                "flowchart TD\n"
                '  a["packages/client/src/session.ts"] --> b["packages/client/src/ui.ts"]\n'
                '  b --> c["packages/client/src/store.ts"]\n'
            ),
            codebase_structure=[
                CodebasePart(
                    name="acp",
                    location="packages/acp",
                    purpose="English | The ACP group exposes harness agents over JSON-RPC",
                ),
                CodebasePart(
                    name="cli",
                    location="apps/cli",
                    purpose="Parse argv and start the runner by profile",
                ),
                CodebasePart(
                    name="boot",
                    location="packages/boot",
                    purpose="Stack bundle patches into the Cordis root",
                ),
                CodebasePart(
                    name="client",
                    location="packages/client",
                    purpose="The client package implements the browser SDK talking to the host",
                ),
            ],
            subsystems=[
                Subsystem(
                    name="Capability Seam",
                    role=(
                        "解释 Capability Seam 如何界定插件与宿主之间的能力边界，"
                        "以及 permission policy 与 skill invocation policy 如何落在这条 seam 上。"
                    ),
                    key_types=[
                        KeyType(
                            name="Service Definition",
                            role="swappable capability contract",
                            path="docs/architecture.md",
                            line=1,
                        ),
                        KeyType(
                            name="Provider",
                            role="implements a definition",
                            path="docs/architecture.md",
                            line=1,
                        ),
                        KeyType(
                            name="Consumer",
                            role="uses ctx.llm / ctx.fs",
                            path="docs/architecture.md",
                            line=1,
                        ),
                    ],
                ),
                Subsystem(
                    name="客户端运行时与会话",
                    role="说明 client runtime 中的 conversation、pending、notifier、remotes 等会话原语如何保存会话。",
                    key_types=[
                        KeyType(
                            name="Harness",
                            role="session runtime",
                            path="packages/core/src/index.ts",
                            line=1,
                        )
                    ],
                ),
                Subsystem(
                    name="客户端连接层",
                    role="说明 connection 包如何建立客户端与后端/本地 loopback 的连接。",
                    key_types=[
                        KeyType(
                            name="Context",
                            role="plugin ctx",
                            path="vendor/cordis/src/context.ts",
                            line=1,
                        )
                    ],
                ),
                Subsystem(
                    name="Agent 预设与设置存储",
                    role="说明 ui-agent-preset 如何管理 agent 预设的 settings-store。",
                    key_types=[
                        KeyType(
                            name="defineStore",
                            role="settings store",
                            path="packages/client/src/store.ts",
                            line=1,
                        )
                    ],
                ),
            ],
        ),
        architecture=ArchitectureDiagram(
            architecture_type="plugin-system",
            mermaid_component=(
                "flowchart TD\n"
                '  a["packages/client/src/session.ts"] --> b["packages/client"]\n'
            ),
            term_tips=[
                TermTip(term="Capability Seam", tip="插件通过 seam 暴露的上下文（如 、）"),
                TermTip(term="profile", tip="包含 `package.json`、 与"),
                TermTip(term="cmdline", tip="把 交给 app"),
            ],
        ),
    )


def test_fixture_1_split_table_is_handbook_zh(monkeypatch):
    monkeypatch.setenv("RECALLSTACK_CONTENT_LANG", "zh")
    project = _dsh_project_with_decoys()
    rows = fill_codebase_purposes(
        [
            CodebasePart(
                name="acp",
                location="packages/acp",
                purpose="English | The ACP group exposes harness agents over JSON-RPC",
            ),
            CodebasePart(name="cli", location="apps/cli", purpose=""),
            CodebasePart(name="boot", location="packages/boot", purpose=""),
            CodebasePart(name="client", location="packages/client", purpose=""),
        ],
        project,
        language="zh",
    )
    by_name = {r.name: r.purpose for r in rows}
    assert not any(is_english_pack_purpose(p) for p in by_name.values())
    assert "English |" not in by_name["acp"]
    assert "The ACP group" not in by_name["acp"]
    assert "解析 argv" in by_name["cli"] and "profile" in by_name["cli"]
    assert "bundle" in by_name["boot"] and "Cordis" in by_name["boot"]
    assert "浏览器" in by_name["client"] or "桌面" in by_name["client"]

    table = localize_split_table_markdown(
        "## 代码如何拆分\n\n"
        "| 名称 | 位置 | 职责 |\n"
        "| --- | --- | --- |\n"
        "| acp | packages/acp | English | The ACP group exposes harness agents |\n",
        language="zh",
    )
    assert "English |" not in table
    assert "The ACP group" not in table

    payload = build_wiki_payload(project, DependencyGraph.build_from_project(project), [])
    index = next(p for p in payload["pages"] if p["id"] == "index")
    split = index["content"].split("代码如何拆分", 1)[1].split("## ", 1)[0]
    assert "English |" not in split
    assert "The ACP group" not in split
    assert "解析 argv" in split or "profile" in split


def test_fixture_2_overview_mermaid_is_one_call_not_client_subgraph(monkeypatch):
    monkeypatch.setenv("RECALLSTACK_CONTENT_LANG", "zh")
    project = _dsh_project_with_decoys()
    graph = DependencyGraph.build_from_project(project)
    client_only = (
        "flowchart TD\n"
        '  a["packages/client/src/session.ts"] --> b["packages/client/src/ui.ts"]\n'
        '  b --> c["packages/client/src/store.ts"]\n'
    )
    assert mermaid_is_local_package_subgraph(client_only)
    diagram = prefer_overview_mermaid(project, graph, current=client_only, language="zh")
    assert mermaid_is_local_package_subgraph(diagram) is False
    for token in (
        "CLI 启动器",
        "Bundle 装配",
        "Boot/Cordis",
        "ACP 协议层",
        "API 网关",
        "Client 运行时",
        "Web 应用壳",
    ):
        assert token in diagram
    assert '["CLI"]' not in diagram
    assert '["Bundle"]' not in diagram
    assert "packages/client/src/session.ts" not in diagram
    raw = callpath_mermaid_for(project, language="zh")
    assert raw.startswith("flowchart LR")
    assert "CLI 启动器" in raw and "Web 应用壳" in raw
    en = callpath_mermaid_for(project, language="en")
    assert "CLI launcher" in en and "Web app shell" in en
    assert '["CLI"]' not in en

    cleaned = verify_wiki_data(_polluted_90_wiki(project), project)
    payload = build_wiki_payload(project, graph, [], wiki_data=cleaned)
    index = next(p for p in payload["pages"] if p["id"] == "index")
    arch = next(p for p in payload["pages"] if p["id"] == "architecture")
    for page in (index, arch):
        assert "packages/client/src/session.ts" not in page["content"]
        assert "CLI 启动器" in page["content"]
        assert "Boot/Cordis" in page["content"] or "Cordis" in page["content"]


def test_fixture_3_overview_drops_lecture_how_voice(monkeypatch):
    monkeypatch.setenv("RECALLSTACK_CONTENT_LANG", "zh")
    spaced = "解释 Capability Seam 如何界定插件与宿主之间的能力边界。"
    assert "解释" not in rewrite_lecture_claim(spaced)
    assert "如何" not in rewrite_lecture_claim(spaced)
    assert "说明" not in rewrite_lecture_claim(
        "说明 client runtime 中的 conversation 如何保存会话。"
    )
    assert "Service Definition" in rewrite_lecture_claim(spaced)
    assert "conversation / pending" in rewrite_lecture_claim(
        "说明 client runtime 中的 conversation、pending、notifier、remotes 等会话原语如何保存会话。"
    )
    assert "loopback" in rewrite_lecture_claim(
        "说明 connection 包如何建立客户端与后端/本地 loopback 的连接。"
    )
    paragraph = (
        "### Capability Seam\n"
        "解释 Capability Seam 如何界定插件与宿主之间的能力边界，"
        "以及 permission policy 与 skill invocation policy 如何落在这条 seam 上。\n"
    )
    rewritten = rewrite_lecture_prose(paragraph)
    assert "解释" not in rewritten
    assert "说明" not in rewritten
    assert re.search(r"解释\s+\S.{0,80}如何", rewritten) is None
    project = _dsh_project_with_decoys()
    graph = DependencyGraph.build_from_project(project)
    payload = build_wiki_payload(
        project, graph, [], wiki_data=_polluted_90_wiki(project)
    )
    index = next(p for p in payload["pages"] if p["id"] == "index")
    arch = next(p for p in payload["pages"] if p["id"] == "architecture")
    for page in (index, arch):
        body = page["content"]
        assert "解释 Capability Seam 如何" not in body
        assert "说明 client runtime 中的 conversation" not in body
        assert "说明 connection 包如何" not in body
        assert "说明 ui-agent-preset 如何" not in body
        assert re.search(r"(?:解释|说明)\s+\S.{0,80}如何", body) is None
    assert "Capability Seam 是 Service Definition" in index["content"]
    assert "conversation / pending" in index["content"]
    assert "loopback" in index["content"]


def test_fixture_4_capability_seam_pins_definition_line(monkeypatch):
    monkeypatch.setenv("RECALLSTACK_CONTENT_LANG", "zh")
    project = _dsh_project_with_decoys()
    cite = pin_topic_evidence_cite(
        "docs/architecture.md:1", project, "capability-seam"
    )
    assert cite != "docs/architecture.md:1"
    assert cite.startswith("docs/architecture.md:")
    line = int(cite.rsplit(":", 1)[1])
    assert line > 1
    text = next(f.content for f in project.files if f.path == "docs/architecture.md")
    hit = text.splitlines()[line - 1]
    assert any(
        tok in hit
        for tok in ("Service Definition", "Provider", "Consumer", "ctx.llm", "ctx.fs")
    )
    payload = build_wiki_payload(
        project,
        DependencyGraph.build_from_project(project),
        [],
        wiki_data=_polluted_90_wiki(project),
    )
    index = next(p for p in payload["pages"] if p["id"] == "index")
    assert "docs/architecture.md:1" not in index["content"]
    assert "docs/architecture.md:" in index["content"]
    assert f"docs/architecture.md:{line}" in index["content"]
    assert "Service Definition" in index["content"]
    assert "Provider" in index["content"]
    assert "Consumer" in index["content"]
    for name in ("Service Definition", "Provider", "Consumer"):
        assert f"docs/architecture.md:1 {name}" not in index["content"]
        assert f"docs/architecture.md:{line} {name}" in index["content"]


def test_fixture_5_hollow_terms_are_filled_or_dropped(monkeypatch):
    monkeypatch.setenv("RECALLSTACK_CONTENT_LANG", "zh")
    assert is_hollow_tip("插件通过 seam 暴露的上下文（如 、）")
    assert is_hollow_tip("包含 `package.json`、 与")
    assert is_hollow_tip("把 交给 app")
    assert is_hollow_tip("把 / 接上")
    assert is_hollow_tip("Capability Seam 是 Service Definition / Provider / Consumer，把 / 接上。")
    project = _dsh_project_with_decoys()
    payload = build_wiki_payload(
        project,
        DependencyGraph.build_from_project(project),
        [],
        wiki_data=_polluted_90_wiki(project),
    )
    index = next(p for p in payload["pages"] if p["id"] == "index")
    arch = next(p for p in payload["pages"] if p["id"] == "architecture")
    for page in (index, arch):
        assert "把 / 接上" not in page["content"]
        assert "把/接上" not in page["content"]
        assert "package.json、 与" not in page["content"]
        assert "`package.json`、 与" not in page["content"]
    assert "（如 、）" not in arch["content"]
    assert "如 、" not in arch["content"]
    assert "把 交给" not in arch["content"]
    if "cmdline" in arch["content"]:
        assert "argv" in arch["content"]
    if "profile" in arch["content"]:
        assert "bundle" in arch["content"] or "cordis" in arch["content"].lower()
    if "Capability Seam" in arch["content"]:
        assert "ctx.llm" in arch["content"] or "ctx.fs" in arch["content"]


def test_overview_start_chip_is_bin_main_not_readversion(monkeypatch):
    monkeypatch.setenv("RECALLSTACK_CONTENT_LANG", "zh")
    project = _dsh_project_with_decoys()
    payload = build_wiki_payload(
        project,
        DependencyGraph.build_from_project(project),
        [],
        wiki_data=_polluted_90_wiki(project),
    )
    index = next(p for p in payload["pages"] if p["id"] == "index")
    start_lines = [
        ln for ln in index["content"].splitlines() if "启动，一次调用从这里进图" in ln
    ]
    assert start_lines
    assert all("readVersion" not in ln for ln in start_lines)
    assert any("apps/cli/src/bin.ts" in ln for ln in start_lines)
    rewritten = rewrite_start_claim_helper_symbols(
        "进程从 `apps/cli/src/bin.ts:20 readVersion` 启动，一次调用从这里进图。"
    )
    assert "readVersion" not in rewritten
    assert "apps/cli/src/bin.ts" in rewritten


def test_config_filename_is_not_a_concept_page(monkeypatch):
    monkeypatch.setenv("RECALLSTACK_CONTENT_LANG", "zh")
    assert is_config_file_concept("vitest.shared.ts", "vitest.shared.ts")
    assert is_config_file_concept("vitest-shared-ts", "vitest.shared.ts")
    project = _dsh_project_with_decoys()
    wiki = WikiBuilder().build(
        project,
        build_deterministic_wiki_data(
            project, DependencyGraph.build_from_project(project), []
        ),
        DependencyGraph.build_from_project(project),
        language="zh",
    )
    draft = ConceptDraft(
        slug="vitest.shared.ts",
        title="vitest.shared.ts",
        description="shared vitest config",
        importance=0.4,
        source_references=[SourceReference(path="vitest.shared.ts", start_line=1)],
    )
    out = append_concept_pages(wiki, [draft])
    assert out.get_page("concepts/vitest.shared.ts") is None


def test_clip_mermaid_label_keeps_backticks_and_full_words():
    assert "`" not in clip_mermaid_label("`writeDefaultPreset` 构造 `") or (
        clip_mermaid_label("`writeDefaultPreset` 构造 `").count("`") % 2 == 0
    )
    clipped = clip_mermaid_label("`writeDefaultPreset` 构造 `defaultPreset`")
    assert not clipped.endswith("`") or clipped.count("`") % 2 == 0
    assert "构造 `" not in clipped
    assert clip_mermaid_label("返回 undefined") == "返回 undefined"
    long_en = clip_mermaid_label("返回 undefined 并继续写下去直到被截断")
    assert not long_en.endswith("undefine")
