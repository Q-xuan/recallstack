"""Topic / wiki skeleton follows the scanned repo, not the grok-study word list."""

from __future__ import annotations

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
    should_reuse_analyzed_wiki,
    wiki_payload_cites_foreign_tree,
)
from repowiki.core.models import (
    ArchitectureDiagram,
    Citation,
    CodebasePart,
    FileInfo,
    ProjectContext,
    ProjectOverview,
    WikiData,
)
from repowiki.core.modules import group_into_modules
from repowiki.core.outline import build_deterministic_outline, merge_outline
from repowiki.core.scanner import build_file_tree
from repowiki.core.topics import build_deterministic_topics, codebase_structure_for
from repowiki.core.wiki_builder import WikiBuilder, collapse_repeated_mermaid_labels

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
            "packages/boot/src/index.ts",
            "export function boot() { loadBundle() }\n",
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
