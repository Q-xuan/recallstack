"""Citation verification drops hallucinated paths and keeps real ones."""

from __future__ import annotations

from repowiki.core.cite_check import (
    CiteIndex,
    collect_invalid_paths,
    sanitize_text,
    verify_wiki_data,
)
from repowiki.core.grounding import (
    cite_index_from_texts,
    is_doc_pack_row,
    is_fragment_claim,
    is_hollow_tip,
    repair_grounded_prose,
    scrub_ungrounded_prose,
    scrub_wiki_page_content,
    text_cites_foreign_tree,
)
from repowiki.core.models import (
    ArchitectureDiagram,
    CallChain,
    Citation,
    CodebasePart,
    Component,
    FileDoc,
    FileInfo,
    KeyType,
    ModuleDoc,
    ProjectContext,
    ProjectOverview,
    ReadingGuide,
    ReadingStep,
    Relationship,
    Subsystem,
    TermTip,
    TopicDoc,
    WikiData,
)


def _project() -> ProjectContext:
    main = "from app.core import boot\n\ndef main():\n    return boot()\n"
    core = "def boot():\n    return 'ok'\n"
    return ProjectContext(
        name="demo",
        root=".",
        files=[
            FileInfo(path="app/main.py", size=len(main), language="python", lines=4, content=main),
            FileInfo(path="app/core.py", size=len(core), language="python", lines=2, content=core),
        ],
    )


def test_cite_check_drops_bad_paths_and_keeps_good_ones():
    project = _project()
    data = WikiData(
        overview=ProjectOverview(
            name="demo",
            description="Starts in `app/main.py:3` and never in `ghost/x.py:1`.",
            what_it_is=["boot lives in `app/core.py:1` not `ghost/x.py:1`"],
            citations=[
                Citation(path="app/main.py", start_line=3, note="entry"),
                Citation(path="totally/fake.py", start_line=1, note="nope"),
            ],
        ),
        architecture=ArchitectureDiagram(
            architecture_type="monolith",
            components=[
                Component(name="app", files=["app/main.py", "missing.py"]),
            ],
        ),
        modules=[
            ModuleDoc(
                name="app",
                purpose="core",
                description="See `app/core.py:1` and `no/such.py`.",
                implementation_details="boot lives in `app/core.py:99`.",
                files=[
                    FileDoc(path="app/main.py", purpose="entry"),
                    FileDoc(path="does/not/exist.py", purpose="hallucination"),
                ],
                relationships=[
                    Relationship(source="app/main.py", target="app/core.py", description="imports"),
                    Relationship(source="app/main.py", target="ghost.py", description="bad"),
                ],
                call_chains=[
                    CallChain(
                        name="boot",
                        files=["app/main.py", "app/core.py", "missing.py"],
                        steps=["`app/main.py:3` calls boot"],
                    )
                ],
                citations=[
                    Citation(path="app/core.py", start_line=1),
                    Citation(path="invented.py", start_line=4),
                ],
            )
        ],
        reading_guide=ReadingGuide(
            steps=[
                ReadingStep(order=1, title="start", files=["app/main.py", "ghost.py"]),
            ]
        ),
    )

    index = CiteIndex.from_project(project)
    assert collect_invalid_paths(data.modules[0], index) == [
        "does/not/exist.py",
        "ghost.py",
        "invented.py",
        "missing.py",
    ]

    cleaned = verify_wiki_data(data, project)
    mod = cleaned.modules[0]
    assert [f.path for f in mod.files] == ["app/main.py"]
    assert [(r.source, r.target) for r in mod.relationships] == [("app/main.py", "app/core.py")]
    assert mod.call_chains[0].files == ["app/main.py", "app/core.py"]
    assert [c.path for c in mod.citations] == ["app/core.py"]
    assert "does/not/exist.py" not in mod.description
    assert "`app/core.py:1`" in mod.description
    # out-of-range line dropped, path kept
    assert "`app/core.py`" in mod.implementation_details
    assert ":99" not in mod.implementation_details
    assert [c.path for c in cleaned.overview.citations] == ["app/main.py"]
    assert cleaned.architecture.components[0].files == ["app/main.py"]
    assert cleaned.reading_guide.steps[0].files == ["app/main.py"]
    assert "`app/main.py:3`" in cleaned.overview.description
    assert "ghost/x.py" not in cleaned.overview.description
    assert "`app/core.py:1`" in cleaned.overview.what_it_is[0]
    assert "ghost/x.py" not in cleaned.overview.what_it_is[0]


def test_sanitize_text_resolves_unique_basename():
    index = CiteIndex.from_project(_project())
    out = sanitize_text("look at `main.py:3`", index)
    assert out == "look at `app/main.py:3`"


def test_sanitize_text_keeps_path_line_symbol_and_drops_truncated_chips():
    index = CiteIndex.from_project(_project())
    kept = sanitize_text("boot lives in `app/core.py:1 boot` next to the claim.", index)
    assert "`app/core.py:1 boot`" in kept
    dropped = sanitize_text(
        "schema leftover `src/file.ts:12 TypeName` and `ts:1` and `README.ts:24 Config`.",
        index,
    )
    assert "src/file.ts" not in dropped
    assert "TypeName" not in dropped
    assert "`ts:1`" not in dropped
    assert "README.ts" not in dropped
    nested = sanitize_text(
        "进程从 `apps/dsh/src/main.ts:1` 启动。",
        CiteIndex.from_project(
            ProjectContext(
                name="dsh",
                root=".",
                files=[
                    FileInfo(
                        path="apps/dsh/src/main.ts",
                        size=8,
                        language="typescript",
                        lines=2,
                        content="export function main() {}\n",
                    )
                ],
            )
        ),
    )
    assert "`apps/dsh/src/main.ts:1`" in nested
    assert "`ts:1`" not in nested
    dsh = CiteIndex.from_project(
        ProjectContext(
            name="dsh",
            root=".",
            files=[
                FileInfo(
                    path="README.md",
                    size=20,
                    language="markdown",
                    lines=2,
                    content="# DeepSeek Harness\n",
                ),
                FileInfo(
                    path="apps/dsh/src/main.ts",
                    size=8,
                    language="typescript",
                    lines=2,
                    content="export function main() {}\n",
                )
            ],
        )
    )
    assert not text_cites_foreign_tree(
        "进程从 `apps/dsh/src/main.ts:1` 启动，一次调用从这里进图。",
        dsh,
    )
    scrubbed = scrub_ungrounded_prose(
        "进程从 `apps/dsh/src/main.ts:1` 启动，一次调用从这里进图。"
        "相关源码: `README.md` `apps/dsh/src/main.ts`",
        dsh,
    )
    assert "`apps/dsh/src/main.ts:1`" in scrubbed
    assert "`README.md`" in scrubbed
    assert "README.ts" not in scrubbed
    assert "`ts:1`" not in scrubbed
    assert not scrubbed.startswith("ts:")


def test_repair_grounded_prose_drops_orphan_ext_and_hollow_tips():
    assert is_fragment_claim("ts:1 启动，一次调用从这里进图。")
    assert is_fragment_claim("`ts:1`。")
    assert is_fragment_claim("`client.ts:1`。")
    assert is_fragment_claim("- ts:1 启动，一次调用从这里进图。")
    assert not is_fragment_claim("\n")
    assert not is_fragment_claim("\n\n")
    assert not is_fragment_claim(
        "进程从 `apps/dsh/src/main.ts:1` 启动，一次调用从这里进图。"
    )
    assert is_hollow_tip("列出其顺序")
    assert is_hollow_tip("包含 `package.json`、 与 。")
    assert is_hollow_tip("再叠加 profile 的 、`$DSH_HOME/cordis.patch.yml`")
    assert is_fragment_claim("再叠加 profile 的 、`$DSH_HOME/cordis.patch.yml`。")
    assert is_doc_pack_row("README.md", "README.md")
    assert is_doc_pack_row("README.md", "packages/README.md")
    assert is_doc_pack_row("AGENTS.md", "AGENTS.md")
    assert not is_doc_pack_row("cli", "apps/cli")

    glued = (
        "deepseek-ai-dsh-root is organized as directory modules (1000 files).ts. "
        "Configuration lives in . Hub packages to explain first: `apps`."
    )
    repaired = repair_grounded_prose(glued)
    assert "files).ts" not in repaired
    assert "Configuration lives in ." not in repaired
    assert "`ts:1`" not in repaired

    leftover = scrub_ungrounded_prose(
        "- `ts:1` 启动，一次调用从这里进图。\n"
        "- `client.ts:1`。\n"
        "bundle 列出 `ghost/pack.ts` 与 `nope.ts`。",
        CiteIndex.from_project(_project()),
    )
    assert "`ts:1`" not in leftover
    assert "client.ts:1" not in leftover
    assert "启动，一次调用从这里进图" not in leftover

    hollow_body = (
        "按 `ghost/order.ts` 顺序叠加 bundle patch，"
        "再叠加 profile 的 `ghost/profile.yml`、`$DSH_HOME/cordis.patch.yml`。"
    )
    repaired_body = scrub_ungrounded_prose(hollow_body, CiteIndex.from_project(_project()))
    assert "的 、" not in repaired_body
    assert "的、" not in repaired_body
    assert "按 顺序" not in repaired_body


def test_repair_grounded_prose_keeps_markdown_newlines_and_drops_orphan_chip():
    """GET scrub must not eat ``\\n`` so headings/lists stay on their own lines."""
    raw = (
        "关键类型保持英文 identifier，证据用 path:line Symbol 贴在断言旁边。\n"
        "\n"
        "## 概述\n"
        "- 仓库目标与边界写在 README，而不是目录名。\n"
        "- 进程从 `apps/cli/src/bin.ts:1` 启动，一次调用从这里进图。\n"
        "不按目录。\n"
        "\n"
        "**相关源码:** `apps/cli/src/bin.ts`\n"
        "再进架构和Cordis 与插件容器。\n"
        "\n"
        "## 概述\n"
        "- `ts:1` 启动，一次调用从这里进图。\n"
    )
    repaired = repair_grounded_prose(raw)
    assert "旁边。## 概述" not in repaired
    assert "目录名。- 进程从" not in repaired
    assert "不按目录。**相关源码:**" not in repaired
    assert "插件容器。## 概述" not in repaired
    assert "\n## 概述\n" in repaired
    assert "\n- 仓库目标与边界写在 README" in repaired
    assert "`ts:1`" not in repaired

    index = cite_index_from_texts(
        {
            "apps/cli/src/bin.ts": "export function main() {}\n",
            "README.md": "# dsh\n",
        }
    )
    scrubbed = scrub_wiki_page_content(raw, index)
    assert "旁边。## 概述" not in scrubbed
    assert "\n## 概述\n" in scrubbed
    assert "\n- 仓库目标与边界写在 README" in scrubbed
    assert "`ts:1`" not in scrubbed


def test_cite_check_works_without_llm_on_deterministic_content():
    """Offline path: still strip impossible paths if any slipped in."""
    project = _project()
    data = WikiData(
        modules=[
            ModuleDoc(
                name="app",
                files=[FileDoc(path="app/main.py"), FileDoc(path="not/here.py")],
            )
        ]
    )
    cleaned = verify_wiki_data(data, project)
    assert [f.path for f in cleaned.modules[0].files] == ["app/main.py"]


def test_cite_check_drops_key_types_without_repo_path_and_foreign_term_tips():
    project = _project()
    data = WikiData(
        overview=ProjectOverview(
            name="demo",
            subsystems=[
                Subsystem(
                    name="boot",
                    key_types=[
                        KeyType(name="Cli", role="parse flags", path=""),
                        KeyType(name="boot", role="start", path="app/core.py"),
                        KeyType(name="Ghost", role="nope", path="ghost/x.py"),
                    ],
                )
            ],
            term_tips=[
                TermTip(term="PageRank", tip="虽然未直接使用 / 仅用于文档生成工具"),
                TermTip(term="boot", tip="starts the process in this repo"),
            ],
        ),
        architecture=ArchitectureDiagram(
            architecture_type="monolith",
            components=[
                Component(
                    name="app",
                    key_types=[KeyType(name="Terminal", role="draw", path="")],
                )
            ],
            term_tips=[TermTip(term="PageRank", tip="ranks files")],
        ),
        topics=[
            TopicDoc(
                name="caching",
                title="缓存",
                files=[FileDoc(path="app/main.py")],
                key_types=[KeyType(name="Cache", role="memo", path="")],
            )
        ],
    )
    cleaned = verify_wiki_data(data, project)
    names = [kt.name for kt in cleaned.overview.subsystems[0].key_types]
    assert names == ["boot"]
    assert [t.term for t in cleaned.overview.term_tips] == ["boot"]
    assert cleaned.architecture.components[0].key_types == []
    assert cleaned.architecture.term_tips == []
    assert all(t.name != "caching" for t in cleaned.topics)


def test_cite_check_prefers_symbol_line_over_line_one():
    core = "from app import x\n\ndef boot():\n    return 1\n"
    project = ProjectContext(
        name="demo",
        root=".",
        files=[
            FileInfo(
                path="app/core.py",
                size=len(core),
                language="python",
                lines=4,
                content=core,
            )
        ],
    )
    data = WikiData(
        overview=ProjectOverview(
            citations=[Citation(path="app/core.py", start_line=1, symbol="boot")]
        )
    )
    cleaned = verify_wiki_data(data, project)
    assert cleaned.overview.citations[0].start_line == 3


def test_overview_drops_grok_symbols_missing_from_tree():
    project = _project()
    data = WikiData(
        overview=ProjectOverview(
            name="demo",
            description="`xai-grok-pager` 负责进程启动，`xai-grok-agent` 驱动 agent 循环。",
            runtime_flow="Pager 把一轮交给 start_turn。",
            mermaid_component=(
                "flowchart LR\n"
                '  A["Pager"] --> B["start_turn"] --> C["Agent Loop"]\n'
            ),
            codebase_structure=[
                CodebasePart(
                    name="xai-grok-pager",
                    location="packages/xai-grok-pager",
                    purpose="boot",
                ),
                CodebasePart(name="app", location="app", purpose="entry"),
            ],
        ),
        architecture=ArchitectureDiagram(
            description="xai-grok-pager 负责进程启动。",
            mermaid_component='flowchart LR\n  A["Pager"] --> B["start_turn"]\n',
        ),
    )
    cleaned = verify_wiki_data(data, project)
    blob = " ".join(
        [
            cleaned.overview.description,
            cleaned.overview.runtime_flow,
            cleaned.overview.mermaid_component,
            " ".join(
                f"{p.name} {p.location}" for p in cleaned.overview.codebase_structure
            ),
            cleaned.architecture.description,
            cleaned.architecture.mermaid_component,
        ]
    )
    assert "xai-grok-pager" not in blob
    assert "xai-grok-agent" not in blob
    assert "start_turn" not in blob
    assert "packages/xai-grok-pager" not in blob
    assert any(p.location == "app" for p in cleaned.overview.codebase_structure)


def test_verify_drops_doc_pack_rows_and_hollow_term_tips():
    project = _project()
    project.files.extend(
        [
            FileInfo(path="README.md", size=8, language="markdown", lines=2, content="# demo\n"),
            FileInfo(path="AGENTS.md", size=8, language="markdown", lines=2, content="# agents\n"),
            FileInfo(
                path="packages/README.md",
                size=8,
                language="markdown",
                lines=2,
                content="# pkgs\n",
            ),
        ]
    )
    data = WikiData(
        overview=ProjectOverview(
            name="demo",
            codebase_structure=[
                CodebasePart(name="README.md", location="README.md", purpose="文档"),
                CodebasePart(name="AGENTS.md", location="AGENTS.md", purpose="代理说明"),
                CodebasePart(
                    name="README.md",
                    location="packages/README.md",
                    purpose="`md` 这一包在仓库里的职责边界。",
                ),
                CodebasePart(
                    name="app",
                    location="app",
                    purpose="`app` 这一包在仓库里的职责边界。",
                ),
            ],
            term_tips=[
                TermTip(term="boot", tip="包含 `package.json`、 与 。"),
                TermTip(term="boot", tip="列出其顺序"),
                TermTip(term="boot", tip="进程从入口启动后再装配。"),
            ],
        )
    )
    cleaned = verify_wiki_data(data, project)
    locs = [p.location for p in cleaned.overview.codebase_structure]
    assert "README.md" not in locs
    assert "AGENTS.md" not in locs
    assert "app" in locs
    tips = [t.tip for t in cleaned.overview.term_tips]
    assert all("与 。" not in tip and tip != "列出其顺序" for tip in tips)
    assert any("入口" in tip for tip in tips)
