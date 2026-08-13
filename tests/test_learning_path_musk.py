"""First-principles learning-path worksheet (Musk rubric), not the reading wiki."""

from __future__ import annotations

import re
from types import SimpleNamespace

from recallstack.api.serializers import path_out
from recallstack.domain.schemas import ConceptDraft, SourceReference
from recallstack.learning.learning_contract import (
    is_core_path_concept,
    path_evidence_chip,
    path_rank,
    path_worksheet,
    step_task_for_slug,
    upgrade_legacy_concept_markdown,
)
from recallstack.learning.path_builder import PathBuilder
from recallstack.learning.wiki_generator import append_concept_pages
from repowiki.core.wiki_builder import Wiki

_PATH_CHIP_RE = re.compile(
    r"`((?:[A-Za-z0-9_.@-]+/)*[A-Za-z0-9_.@-]+\.[A-Za-z0-9]+)(?::\d+(?:-\d+)?)?(?:\s+[^`]+)?`"
)


def _loop_draft() -> ConceptDraft:
    return ConceptDraft(
        slug="agent-loop",
        title="Agent Loop",
        description="一轮对话。",
        wiki_page_id="topics/agent-loop",
        source_references=[
            SourceReference(
                path="crates/tui/src/app.rs",
                start_line=142,
                symbol="start_turn",
            ),
            SourceReference(path="crates/agent/src/loop.rs", start_line=1, symbol="agent_loop"),
        ],
    )


def test_path_worksheet_has_four_headings_and_one_chip(monkeypatch):
    monkeypatch.setenv("RECALLSTACK_CONTENT_LANG", "zh")
    text = path_worksheet(_loop_draft())
    for heading in ("## 本步要你干什么", "## 先回到原理", "## 只看这一处证据", "## 过关"):
        assert heading in text
    assert "## 架构图" not in text
    assert "## 核心子系统" not in text
    assert "```mermaid" not in text
    assert "您" not in text
    assert "点击展开" not in text
    assert "了解模块" not in text
    assert "start_turn 之后调模型" in text
    assert "不变量" in text
    chips = _PATH_CHIP_RE.findall(text)
    assert len(chips) == 1
    chip = path_evidence_chip(_loop_draft())
    assert chip == "crates/tui/src/app.rs:142 start_turn"
    assert f"`{chip}`" in text
    assert "调模型" in text.split("## 过关", 1)[1]


def test_path_rank_trunk_before_leaves():
    assert path_rank("project-goal") < path_rank("entry-and-boot")
    assert path_rank("entry-and-boot") < path_rank("agent-loop")
    assert path_rank("agent-loop") < path_rank("tool-system")
    assert path_rank("tool-system") < path_rank("acp-protocol")
    assert path_rank("agent-loop") < path_rank("codebase-graph")


def test_filler_slugs_excluded_from_path():
    concepts = [
        ConceptDraft(slug="project-goal", title="项目目标", importance=1.0),
        ConceptDraft(
            slug="entry-and-boot",
            title="入口",
            importance=0.95,
            wiki_page_id="topics/entry-and-boot",
        ),
        ConceptDraft(
            slug="application-entry",
            title="应用入口",
            importance=0.94,
            wiki_page_id="topics/application-entry",
        ),
        ConceptDraft(
            slug="agent-loop",
            title="Agent Loop",
            importance=0.9,
            wiki_page_id="topics/agent-loop",
        ),
        ConceptDraft(slug="caching", title="缓存", importance=0.99),
        ConceptDraft(slug="request-routing", title="请求路由", importance=0.99),
        ConceptDraft(slug="module-foo", title="模块：foo", importance=0.8),
        ConceptDraft(
            slug="acp-protocol",
            title="ACP",
            importance=0.4,
            wiki_page_id="topics/acp-protocol",
        ),
        ConceptDraft(
            slug="codebase-graph",
            title="图谱",
            importance=0.4,
            wiki_page_id="topics/codebase-graph",
        ),
        ConceptDraft(
            slug="pty-control",
            title="PTY",
            importance=0.4,
            wiki_page_id="topics/pty-control",
        ),
        ConceptDraft(
            slug="headless-modes",
            title="Headless",
            importance=0.4,
            wiki_page_id="topics/headless-modes",
        ),
        ConceptDraft(
            slug="tool-system",
            title="工具",
            importance=0.85,
            wiki_page_id="topics/tool-system",
        ),
        ConceptDraft(
            slug="terminal-ui",
            title="TUI",
            importance=0.8,
            wiki_page_id="topics/terminal-ui",
        ),
        ConceptDraft(
            slug="context-assembly",
            title="上下文",
            importance=0.75,
            wiki_page_id="topics/context-assembly",
        ),
    ]
    assert not is_core_path_concept(next(c for c in concepts if c.slug == "caching"))
    assert not is_core_path_concept(next(c for c in concepts if c.slug == "request-routing"))
    path = PathBuilder().build(concepts)
    slugs = [n.concept_slug for n in path.nodes]
    assert slugs[:3] == ["project-goal", "entry-and-boot", "agent-loop"]
    assert "application-entry" not in slugs
    assert slugs.index("agent-loop") < slugs.index("tool-system")
    assert "caching" not in slugs
    assert "request-routing" not in slugs
    assert "module-foo" not in slugs
    assert len(slugs) <= 8
    assert "agent-loop" in slugs
    assert slugs.index("agent-loop") < 4


def test_concept_wiki_pages_stay_handbook(monkeypatch):
    monkeypatch.setenv("RECALLSTACK_CONTENT_LANG", "zh")
    wiki = Wiki(project_name="grok-study", pages=[], sidebar=[])
    draft = _loop_draft()
    page = append_concept_pages(wiki, [draft]).get_page("concepts/agent-loop")
    assert page is not None
    assert "## 它是什么" in page.content
    assert "## 它在系统里的位置" in page.content
    assert "## 本步要你干什么" not in page.content
    assert "## 先回到原理" not in page.content
    assert "## 只看这一处证据" not in page.content
    assert "## 过关" not in page.content
    assert "start_turn 之后调模型" not in page.content


def test_upgrade_legacy_concept_markdown_still_strips_path_homework(monkeypatch):
    monkeypatch.setenv("RECALLSTACK_CONTENT_LANG", "zh")
    mixed = path_worksheet(_loop_draft())
    upgraded = upgrade_legacy_concept_markdown(mixed, slug="agent-loop", title="Agent Loop")
    assert "## 本步要你干什么" not in upgraded
    assert "## 过关" not in upgraded
    assert "## 只看这一处证据" not in upgraded
    assert "## 先回到原理" not in upgraded
    assert "## 它是什么" in upgraded or "## 它在系统里的位置" in upgraded


def test_path_out_rebuilds_worksheet_on_get(monkeypatch):
    monkeypatch.setenv("RECALLSTACK_CONTENT_LANG", "zh")

    def concept(**kw):
        base = dict(
            id="c1",
            repository_id="r",
            repository_version_id="v",
            slug="agent-loop",
            title="Agent Loop",
            description="old handbook",
            difficulty=2,
            importance=0.9,
            source_references=[
                {
                    "path": "crates/tui/src/app.rs",
                    "start_line": 142,
                    "symbol": "start_turn",
                }
            ],
            content_hash="",
            stale=False,
            why_learn="",
            estimated_minutes=15,
            wiki_page_id="topics/agent-loop",
        )
        base.update(kw)
        return SimpleNamespace(**base)

    loop = concept()
    cache = concept(
        id="c2",
        slug="caching",
        title="缓存",
        source_references=[],
        wiki_page_id=None,
        importance=0.99,
    )
    routing = concept(
        id="c3",
        slug="request-routing",
        title="请求路由",
        source_references=[],
        wiki_page_id=None,
    )
    crate = concept(
        id="c4",
        slug="codebase-graph",
        title="图谱",
        wiki_page_id="topics/codebase-graph",
        source_references=[{"path": "crates/code-graph/src/main.rs", "start_line": 1}],
        importance=0.2,
    )
    boot = concept(
        id="c5",
        slug="entry-and-boot",
        title="入口与启动",
        wiki_page_id="topics/entry-and-boot",
        source_references=[{"path": "bin/grok.rs", "start_line": 1, "symbol": "main"}],
        importance=0.95,
    )
    goal = concept(
        id="c0",
        slug="project-goal",
        title="项目目标",
        wiki_page_id="index",
        source_references=[{"path": "README.md", "start_line": 1}],
        importance=1.0,
    )

    def node(cid, conc, pos):
        return SimpleNamespace(
            id=f"n-{cid}",
            concept_id=cid,
            position=pos,
            reason="Ordered by prerequisites and importance",
            concept=conc,
        )

    path = SimpleNamespace(
        id="p1",
        repository_version_id="v",
        title="旧路径",
        description="状态存在哪",
        estimated_minutes=40,
        nodes=[
            node("c2", cache, 1),
            node("c4", crate, 2),
            node("c1", loop, 3),
            node("c3", routing, 4),
            node("c5", boot, 5),
            node("c0", goal, 6),
        ],
    )
    out = path_out(path)
    slugs = [n.concept.slug for n in out.nodes if n.concept]
    assert slugs[:3] == ["project-goal", "entry-and-boot", "agent-loop"]
    assert "caching" not in slugs
    assert "request-routing" not in slugs
    loop_node = next(n for n in out.nodes if n.concept and n.concept.slug == "agent-loop")
    assert loop_node.reason.startswith("打开证据")
    assert "不变量" in loop_node.principles
    assert loop_node.evidence_chip == "crates/tui/src/app.rs:142 start_turn"
    assert "调模型" in loop_node.pass_gate
    ws = loop_node.worksheet
    assert "## 本步要你干什么" in ws
    assert "## 先回到原理" in ws
    assert "## 只看这一处证据" in ws
    assert "## 过关" in ws
    assert ws.count("`crates/tui/src/app.rs:142 start_turn`") == 1
    assert "架构图" not in ws
    assert "核心子系统" not in ws
    assert "先看进程怎么进" in out.description


def test_step_task_is_action_not_了解模块(monkeypatch):
    monkeypatch.setenv("RECALLSTACK_CONTENT_LANG", "zh")
    task = step_task_for_slug("agent-loop", "Agent Loop")
    assert "了解" not in task
    assert "打开" in task
    assert "start_turn" in task


_APP_RS_STUCK_AT_LINE_1 = """\
mod pager;
pub struct App {
    pager: Pager,
}

impl App {
    pub fn new() -> Self {
        Self { pager: Pager::new() }
    }

    pub fn start_turn(&mut self) {
        self.call_model();
    }
}
"""


def test_evidence_chip_resolves_symbol_line_from_stored_file(monkeypatch):
    monkeypatch.setenv("RECALLSTACK_CONTENT_LANG", "zh")
    draft = ConceptDraft(
        slug="agent-loop",
        title="Agent Loop",
        wiki_page_id="topics/agent-loop",
        source_references=[
            SourceReference(path="crates/tui/src/app.rs", start_line=1),
        ],
    )
    stuck = path_evidence_chip(draft)
    assert stuck is not None
    assert stuck.endswith("start_turn")
    assert ":1 " in stuck

    texts = {"crates/tui/src/app.rs": _APP_RS_STUCK_AT_LINE_1}
    chip = path_evidence_chip(draft, file_texts=texts)
    assert chip == "crates/tui/src/app.rs:11 start_turn"
    assert ":1 " not in chip
    worksheet = path_worksheet(draft, file_texts=texts)
    assert "`crates/tui/src/app.rs:11 start_turn`" in worksheet
    assert worksheet.count("## 只看这一处证据") == 1


def test_junk_refs_lose_to_sibling_rs_with_symbol(monkeypatch):
    monkeypatch.setenv("RECALLSTACK_CONTENT_LANG", "zh")
    util = """\
pub struct PromptContext;

pub fn replace_or_insert_system_head(window: &mut Window, head: &str) {
    window.replace_head(head);
}
"""
    draft = ConceptDraft(
        slug="context-assembly",
        title="上下文装配",
        wiki_page_id="topics/context-assembly",
        source_references=[
            SourceReference(
                path="crates/codegen/xai-chat-state/Cargo.toml",
                start_line=1,
            ),
        ],
    )
    texts = {
        "crates/codegen/xai-chat-state/Cargo.toml": "[package]\nname = \"xai-chat-state\"\n",
        "crates/codegen/xai-chat-state/src/conversation_util.rs": util,
    }
    chip = path_evidence_chip(draft, file_texts=texts)
    assert chip is not None
    assert chip.startswith("crates/codegen/xai-chat-state/src/conversation_util.rs:")
    assert "replace_or_insert_system_head" in chip
    assert ":1 " not in chip
    assert "Cargo.toml" not in chip


def test_sh_json_toml_never_win_even_without_store():
    draft = ConceptDraft(
        slug="tool-system",
        title="工具层",
        wiki_page_id="topics/tool-system",
        source_references=[
            SourceReference(
                path="crates/codegen/xai-grok-hooks/examples/hooks/bin/tool-logger.sh",
                start_line=1,
            ),
            SourceReference(
                path="crates/codegen/xai-grok-pager/npm/grok/package.json",
                start_line=1,
            ),
            SourceReference(
                path="crates/codegen/xai-chat-state/Cargo.toml",
                start_line=1,
            ),
            SourceReference(
                path="crates/codegen/xai-grok-agent/src/tool_bridge.rs",
                start_line=1,
            ),
        ],
    )
    chip = path_evidence_chip(draft)
    assert chip is not None
    assert "tool_bridge.rs" in chip
    assert "ToolBridge" in chip
    assert ".sh" not in chip
    assert "package.json" not in chip
    assert "Cargo.toml" not in chip


def test_live_grok_payload_picks_rs_not_toml_json_sh():
    """Exact shapes from Jake's grok-study GET after 4eb66b0."""
    store = {
        "README.md": "# grok\n",
        "crates/codegen/xai-grok-pager/npm/grok/bin/grok": "#!/usr/bin/env node\n",
        "crates/codegen/xai-grok-pager/src/lib.rs": "pub struct Pager;\n\npub fn boot() {}\n",
        "crates/codegen/xai-grok-pager/src/main.rs": (
            "fn main() {\n    xai_grok_pager::boot();\n}\n"
        ),
        "crates/codegen/xai-grok-agent/src/agent.rs": "pub struct Agent;\n",
        "crates/codegen/xai-grok-agent/src/turn.rs": (
            "impl Agent {\n    pub fn start_turn(&mut self) {\n        self.call_model();\n    }\n}\n"
        ),
        "crates/codegen/xai-grok-hooks/examples/hooks/bin/tool-logger.sh": "#!/bin/sh\n",
        "crates/codegen/xai-grok-agent/src/tool_bridge.rs": (
            "// Tool dispatch.\n\npub struct ToolBridge;\n\nimpl ToolBridge {\n    pub fn dispatch(&self) {}\n}\n"
        ),
        "crates/codegen/xai-grok-pager/npm/grok/package.json": '{"name":"grok"}\n',
        "crates/codegen/xai-grok-pager/src/pager.rs": "// pager\npub struct Pager {\n    buf: String,\n}\n",
        "crates/codegen/xai-chat-state/Cargo.toml": "[package]\nname=\"xai-chat-state\"\n",
        "crates/codegen/xai-chat-state/src/conversation_util.rs": (
            "// system head\npub fn replace_or_insert_system_head() {}\n"
        ),
        "crates/codegen/xai-agent-lifecycle/Cargo.toml": "[package]\nname=\"lifecycle\"\n",
        "crates/codegen/xai-agent-lifecycle/src/runtime.rs": "// runtime\npub struct AgentRuntime;\n",
        "crates/codegen/xai-grok-agent/src/prompt/agents_md.rs": (
            "pub fn load_agents_md() {}\n"
        ),
    }

    def chip(slug: str, path: str) -> str | None:
        return path_evidence_chip(
            ConceptDraft(
                slug=slug,
                title=slug,
                wiki_page_id=f"topics/{slug}",
                source_references=[SourceReference(path=path, start_line=1)],
            ),
            file_texts=store,
        )

    goal = chip("project-goal", "README.md")
    assert goal is not None and goal.startswith("README.md:")

    boot = chip("entry-and-boot", "crates/codegen/xai-grok-pager/npm/grok/bin/grok")
    assert boot is not None
    assert boot.endswith(".rs:1 main") or ".rs:" in boot
    assert "npm/" not in boot
    assert boot.endswith(" main") or "fn main" in store.get(boot.split(":")[0], "")

    loop = chip("agent-loop", "crates/codegen/xai-grok-agent/src/agent.rs")
    assert loop == "crates/codegen/xai-grok-agent/src/turn.rs:2 start_turn"

    tools = chip(
        "tool-system",
        "crates/codegen/xai-grok-hooks/examples/hooks/bin/tool-logger.sh",
    )
    assert tools == "crates/codegen/xai-grok-agent/src/tool_bridge.rs:3 ToolBridge"

    tui = chip("terminal-ui", "crates/codegen/xai-grok-pager/npm/grok/package.json")
    assert tui == "crates/codegen/xai-grok-pager/src/pager.rs:2 Pager"

    ctx = chip("context-assembly", "crates/codegen/xai-chat-state/Cargo.toml")
    assert ctx == (
        "crates/codegen/xai-chat-state/src/conversation_util.rs:2 "
        "replace_or_insert_system_head"
    )

    runtime = chip("agent-runtime", "crates/codegen/xai-agent-lifecycle/Cargo.toml")
    assert runtime is not None
    assert "AgentRuntime" in runtime
    assert "Cargo.toml" not in runtime
    assert ":1 " not in runtime

    prompt = chip("system-prompt", "crates/codegen/xai-grok-agent/src/prompt/agents_md.rs")
    assert prompt is not None
    assert "agents_md.rs" in prompt
    assert "Cargo.toml" not in prompt
    assert ".json" not in prompt
    assert ".sh" not in prompt


def test_path_out_get_upgrade_resolves_line_from_scan_store(monkeypatch):
    monkeypatch.setenv("RECALLSTACK_CONTENT_LANG", "zh")
    loop = SimpleNamespace(
        id="c-loop",
        repository_id="r",
        repository_version_id="v",
        slug="agent-loop",
        title="Agent Loop",
        description="",
        difficulty=2,
        importance=0.9,
        source_references=[{"path": "crates/tui/src/app.rs", "start_line": 1}],
        content_hash="",
        stale=False,
        why_learn="",
        estimated_minutes=15,
        wiki_page_id="topics/agent-loop",
    )
    path = SimpleNamespace(
        id="p1",
        repository_version_id="v",
        title="路径",
        description="",
        estimated_minutes=10,
        nodes=[
            SimpleNamespace(
                id="n1",
                concept_id="c-loop",
                position=1,
                reason="old",
                concept=loop,
            )
        ],
    )
    out = path_out(path, file_texts={"crates/tui/src/app.rs": _APP_RS_STUCK_AT_LINE_1})
    node = out.nodes[0]
    assert node.evidence_chip == "crates/tui/src/app.rs:11 start_turn"
    assert "`crates/tui/src/app.rs:11 start_turn`" in node.worksheet
    assert ":1 start_turn" not in node.worksheet
    assert "## 本步要你干什么" not in upgrade_legacy_concept_markdown(
        node.worksheet, slug="agent-loop", title="Agent Loop"
    )


def _rs_with_def_at(line: int, statement: str) -> str:
    rows = [f"// pad {i}" for i in range(1, line)]
    rows.append(statement)
    return "\n".join(rows) + "\n"


def _jake_grok_store() -> dict[str, str]:
    """Concept refs at :1; real defs in other crates — Jake's grok-study shape."""
    return {
        "README.md": "# grok\n",
        "crates/codegen/xai-grok-pager/npm/grok/bin/grok": "#!/usr/bin/env node\nrequire('../src');\n",
        "crates/codegen/xai-grok-pager/src/main.rs": (
            "fn main() {\n    xai_grok_pager::boot();\n}\n"
        ),
        "crates/codegen/ptyctl-cli/src/main.rs": _rs_with_def_at(12, "fn main() {"),
        "crates/codegen/protoc-gen-xai/src/main.rs": "fn main() {}\n",
        "crates/codegen/xai-grok-agent/src/agent.rs": (
            "//! Agent types for the grok crate.\n\n"
            "pub struct Agent;\n\n"
            "impl Agent {\n    fn go(&mut self) {}\n}\n"
        ),
        "crates/codegen/xai-grok-pager/src/app/agent.rs": _rs_with_def_at(
            791, "    pub fn start_turn(&mut self) {"
        ),
        "crates/codegen/xai-grok-hooks/examples/hooks/bin/tool-logger.sh": "#!/bin/sh\necho tool\n",
        "crates/codegen/xai-grok-agent/src/tool_bridge.rs": _rs_with_def_at(
            40, "pub struct ToolBridge {"
        ),
        "crates/codegen/xai-grok-pager/npm/grok/package.json": '{"name":"grok"}\n',
        "crates/codegen/xai-grok-pager/src/pager.rs": _rs_with_def_at(
            88, "pub struct Pager {"
        ),
        "crates/codegen/xai-chat-state/Cargo.toml": "[package]\nname=\"xai-chat-state\"\n",
        "crates/codegen/xai-chat-state/src/conversation_util.rs": _rs_with_def_at(
            55, "pub fn replace_or_insert_system_head(window: &mut Window, head: &str) {"
        ),
        "crates/codegen/xai-agent-lifecycle/Cargo.toml": "[package]\nname=\"lifecycle\"\n",
        "crates/codegen/xai-agent-lifecycle/src/runtime.rs": _rs_with_def_at(
            22, "pub struct AgentRuntime {"
        ),
        "crates/agent/src/runtime.rs": "pub struct AgentRuntime;\n",
        "crates/codegen/xai-grok-agent/src/prompt/agents_md.rs": (
            "//! prompt\n\npub fn load_agents_md() {}\n"
        ),
    }


def test_start_turn_definition_is_in_pager_not_grok_agent_ref():
    """4eb66b0/f76f179: first agent.rs ref + overlay start_turn, never left that file."""
    store = _jake_grok_store()
    agent_ref = "crates/codegen/xai-grok-agent/src/agent.rs"
    assert "start_turn" not in store[agent_ref]
    assert store[agent_ref].splitlines()[0].startswith("//!")
    pager = store["crates/codegen/xai-grok-pager/src/app/agent.rs"].splitlines()
    assert pager[790] == "    pub fn start_turn(&mut self) {"

    draft = ConceptDraft(
        slug="agent-loop",
        title="Agent Loop",
        wiki_page_id="topics/agent-loop",
        source_references=[SourceReference(path=agent_ref, start_line=1)],
    )
    chip = path_evidence_chip(draft, file_texts=store)
    assert chip == "crates/codegen/xai-grok-pager/src/app/agent.rs:791 start_turn"
    worksheet = path_worksheet(draft, file_texts=store)
    assert worksheet.count("`crates/codegen/xai-grok-pager/src/app/agent.rs:791 start_turn`") == 1
    assert "xai-grok-agent/src/agent.rs" not in worksheet


def test_hinted_symbols_search_whole_store_not_concept_ref():
    store = _jake_grok_store()
    cases = (
        (
            "tool-system",
            "crates/codegen/xai-grok-hooks/examples/hooks/bin/tool-logger.sh",
            "crates/codegen/xai-grok-agent/src/tool_bridge.rs:40 ToolBridge",
        ),
        (
            "terminal-ui",
            "crates/codegen/xai-grok-pager/npm/grok/package.json",
            "crates/codegen/xai-grok-pager/src/pager.rs:88 Pager",
        ),
        (
            "context-assembly",
            "crates/codegen/xai-chat-state/Cargo.toml",
            "crates/codegen/xai-chat-state/src/conversation_util.rs:55 "
            "replace_or_insert_system_head",
        ),
        (
            "agent-runtime",
            "crates/codegen/xai-agent-lifecycle/Cargo.toml",
            "crates/codegen/xai-agent-lifecycle/src/runtime.rs:22 AgentRuntime",
        ),
    )
    for slug, ref_path, expected in cases:
        chip = path_evidence_chip(
            ConceptDraft(
                slug=slug,
                title=slug,
                wiki_page_id=f"topics/{slug}",
                source_references=[SourceReference(path=ref_path, start_line=1)],
            ),
            file_texts=store,
        )
        assert chip == expected, (slug, chip)


def test_call_site_in_ref_file_does_not_beat_real_definition():
    store = _jake_grok_store()
    store["crates/codegen/xai-grok-agent/src/agent.rs"] = (
        "//! Agent types.\n\n"
        "impl Agent {\n    fn go(&mut self) { self.pager.start_turn(); }\n}\n"
    )
    chip = path_evidence_chip(
        ConceptDraft(
            slug="agent-loop",
            title="Agent Loop",
            wiki_page_id="topics/agent-loop",
            source_references=[
                SourceReference(
                    path="crates/codegen/xai-grok-agent/src/agent.rs",
                    start_line=1,
                )
            ],
        ),
        file_texts=store,
    )
    assert chip == "crates/codegen/xai-grok-pager/src/app/agent.rs:791 start_turn"


def test_junk_and_trampoline_never_used_when_store_has_rust_def():
    store = _jake_grok_store()
    boot = path_evidence_chip(
        ConceptDraft(
            slug="entry-and-boot",
            title="入口与启动",
            wiki_page_id="topics/entry-and-boot",
            source_references=[
                SourceReference(
                    path="crates/codegen/xai-grok-pager/npm/grok/bin/grok",
                    start_line=1,
                )
            ],
        ),
        file_texts=store,
    )
    assert boot is not None
    assert "npm/" not in boot
    assert ".sh" not in boot
    assert "package.json" not in boot
    assert "Cargo.toml" not in boot
    assert boot.endswith(" main")
    assert boot.startswith("crates/codegen/xai-grok-pager/src/main.rs:")
    assert "ptyctl" not in boot
    assert "protoc" not in boot


def test_path_out_get_upgrade_uses_pager_start_turn_from_store(monkeypatch):
    monkeypatch.setenv("RECALLSTACK_CONTENT_LANG", "zh")
    store = _jake_grok_store()
    loop = SimpleNamespace(
        id="c-loop",
        repository_id="r",
        repository_version_id="9e01e58d-075d-46c0-ba9b-a8661d7ff98d",
        slug="agent-loop",
        title="Agent Loop",
        description="",
        difficulty=2,
        importance=0.9,
        source_references=[
            {
                "path": "crates/codegen/xai-grok-agent/src/agent.rs",
                "start_line": 1,
            }
        ],
        content_hash="",
        stale=False,
        why_learn="",
        estimated_minutes=15,
        wiki_page_id="topics/agent-loop",
    )
    path = SimpleNamespace(
        id="p1",
        repository_version_id="9e01e58d-075d-46c0-ba9b-a8661d7ff98d",
        title="路径",
        description="",
        estimated_minutes=10,
        nodes=[
            SimpleNamespace(
                id="n1",
                concept_id="c-loop",
                position=1,
                reason="old",
                concept=loop,
            )
        ],
    )
    out = path_out(path, file_texts=store)
    node = out.nodes[0]
    assert node.evidence_chip == (
        "crates/codegen/xai-grok-pager/src/app/agent.rs:791 start_turn"
    )
    assert "`crates/codegen/xai-grok-pager/src/app/agent.rs:791 start_turn`" in node.worksheet
    assert "xai-grok-agent/src/agent.rs:1" not in node.worksheet


def test_load_version_file_texts_from_data_dir_when_cwd_has_none(tmp_path, monkeypatch):
    import json

    from recallstack.learning.code_loader import load_version_file_texts

    vid = "9e01e58d-075d-46c0-ba9b-a8661d7ff98d"
    data = tmp_path / "data"
    vf = data / "version_files"
    vf.mkdir(parents=True)
    payload = {
        "crates/codegen/xai-grok-pager/src/app/agent.rs": _rs_with_def_at(
            791, "    pub fn start_turn(&mut self) {"
        )
    }
    (vf / f"{vid}.json").write_text(json.dumps(payload), encoding="utf-8")
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    monkeypatch.setenv("RECALLSTACK_DATA_DIR", str(data))
    texts = load_version_file_texts(vid)
    assert "crates/codegen/xai-grok-pager/src/app/agent.rs" in texts
    assert "pub fn start_turn" in texts["crates/codegen/xai-grok-pager/src/app/agent.rs"]
    chip = path_evidence_chip(
        ConceptDraft(
            slug="agent-loop",
            title="Agent Loop",
            wiki_page_id="topics/agent-loop",
            source_references=[
                SourceReference(
                    path="crates/codegen/xai-grok-agent/src/agent.rs",
                    start_line=1,
                )
            ],
        ),
        file_texts=texts,
    )
    assert chip == "crates/codegen/xai-grok-pager/src/app/agent.rs:791 start_turn"


def test_entry_and_boot_skips_ptyctl_when_grok_pager_exists():
    store = _jake_grok_store()
    chip = path_evidence_chip(
        ConceptDraft(
            slug="entry-and-boot",
            title="入口与启动",
            wiki_page_id="topics/entry-and-boot",
            source_references=[
                SourceReference(
                    path="crates/codegen/ptyctl-cli/src/main.rs",
                    start_line=12,
                    symbol="main",
                )
            ],
        ),
        file_texts=store,
    )
    assert chip == "crates/codegen/xai-grok-pager/src/main.rs:1 main"
    assert "ptyctl" not in chip
    assert "protoc" not in chip


def test_entry_and_boot_uses_grok_trampoline_not_ptyctl_without_pager_rs():
    store = {
        "crates/codegen/xai-grok-pager/npm/grok/bin/grok": (
            "#!/usr/bin/env node\nrequire('../src');\n"
        ),
        "crates/codegen/ptyctl-cli/src/main.rs": _rs_with_def_at(12, "fn main() {"),
        "crates/codegen/protoc-gen-xai/src/main.rs": "fn main() {}\n",
    }
    chip = path_evidence_chip(
        ConceptDraft(
            slug="entry-and-boot",
            title="入口与启动",
            wiki_page_id="topics/entry-and-boot",
            source_references=[
                SourceReference(
                    path="crates/codegen/xai-grok-pager/npm/grok/bin/grok",
                    start_line=1,
                )
            ],
        ),
        file_texts=store,
    )
    assert chip is not None
    assert "ptyctl" not in chip
    assert "protoc" not in chip
    assert "npm/grok/bin/grok" in chip


def test_agent_runtime_prefers_lifecycle_crate_over_crates_agent():
    store = _jake_grok_store()
    chip = path_evidence_chip(
        ConceptDraft(
            slug="agent-runtime",
            title="Agent Runtime",
            wiki_page_id="topics/agent-runtime",
            source_references=[
                SourceReference(path="crates/agent/src/runtime.rs", start_line=1)
            ],
        ),
        file_texts=store,
    )
    assert chip == "crates/codegen/xai-agent-lifecycle/src/runtime.rs:22 AgentRuntime"
    assert "crates/agent/" not in chip


def test_toolbridge_impl_line_not_one():
    store = {
        "crates/codegen/xai-grok-agent/src/tool_bridge.rs": _rs_with_def_at(
            55, "impl ToolBridge {"
        )
    }
    chip = path_evidence_chip(
        ConceptDraft(
            slug="tool-system",
            title="工具层",
            wiki_page_id="topics/tool-system",
            source_references=[
                SourceReference(
                    path="crates/codegen/xai-grok-agent/src/tool_bridge.rs",
                    start_line=1,
                )
            ],
        ),
        file_texts=store,
    )
    assert chip == "crates/codegen/xai-grok-agent/src/tool_bridge.rs:55 ToolBridge"


def test_pager_struct_line_not_one():
    store = {
        "crates/codegen/xai-grok-pager/src/pager.rs": _rs_with_def_at(
            88, "pub struct Pager {"
        )
    }
    chip = path_evidence_chip(
        ConceptDraft(
            slug="terminal-ui",
            title="Terminal UI",
            wiki_page_id="topics/terminal-ui",
            source_references=[
                SourceReference(
                    path="crates/codegen/xai-grok-pager/src/pager.rs",
                    start_line=1,
                )
            ],
        ),
        file_texts=store,
    )
    assert chip == "crates/codegen/xai-grok-pager/src/pager.rs:88 Pager"
