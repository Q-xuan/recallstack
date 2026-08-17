"""First-principles learning-path worksheet (Musk rubric), not the reading wiki."""

from __future__ import annotations

import re
from types import SimpleNamespace

from recallstack.api.serializers import path_out, wiki_out
from recallstack.domain.schemas import ConceptDraft, SourceReference
from recallstack.learning.learning_contract import (
    chip_needs_restamp,
    fill_wiki_key_type_lines,
    is_core_path_concept,
    parse_path_chip,
    path_evidence_chip,
    path_rank,
    path_step_contract,
    path_worksheet,
    step_task_for_slug,
    suggested_ask_questions,
    upgrade_legacy_concept_markdown,
)
from recallstack.learning.question_generator import QuestionGenerator
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
    for heading in ("## 这一步", "## 原理", "## 这一处证据", "## 核对"):
        assert heading in text
    assert "## 架构图" not in text
    assert "## 核心子系统" not in text
    assert "```mermaid" not in text
    assert "您" not in text
    assert "点击展开" not in text
    assert "了解模块" not in text
    assert "start_turn 之后谁调模型" in text
    assert "不变量" in text
    chips = _PATH_CHIP_RE.findall(text)
    assert len(chips) == 1
    chip = path_evidence_chip(_loop_draft())
    assert chip == "crates/tui/src/app.rs:142 start_turn"
    assert f"`{chip}`" in text
    assert "调模型" in text.split("## 核对", 1)[1]
    assert "若这不成立" in text.split("## 原理", 1)[1]
    assert "while True" in text.split("## 原理", 1)[1]
    evidence = text.split("## 这一处证据", 1)[1].split("## 核对", 1)[0]
    assert "闸门" in evidence or "模型" in evidence
    assert "判断是否够" in evidence
    gate = text.split("## 核对", 1)[1]
    assert "函数" in gate
    assert "核对" in gate
    assert "你签字" not in gate
    assert "一句话概括" not in gate
    assert "离开终端循环还能不能完成它声称的事" not in gate
    task = text.split("## 这一步", 1)[1].split("## 原理", 1)[0]
    assert "你负责" not in task
    assert "签字" not in task
    assert "start_turn" in task


def test_path_worksheet_is_deep_not_shallow(monkeypatch):
    monkeypatch.setenv("RECALLSTACK_CONTENT_LANG", "zh")
    text = path_worksheet(_loop_draft())
    principle = text.split("## 原理", 1)[1].split("## 这一处证据", 1)[0]
    sentences = [s for s in re.split(r"[。！？.!?]", principle) if s.strip()]
    assert 4 <= len(sentences) <= 8
    assert "若这不成立" in principle
    assert "不要把这当成" in principle
    assert path_worksheet(_loop_draft()).count("`") == 2
    wiki = upgrade_legacy_concept_markdown(text, slug="agent-loop", title="Agent Loop")
    assert "## 本步要你干什么" not in wiki
    assert "## 先回到原理" not in wiki
    assert "## 过关" not in wiki
    assert "若这不成立" not in wiki
    assert "while True" not in wiki
    assert "您" not in text


def test_path_owner_voice_task_and_gate_name_a_function(monkeypatch):
    monkeypatch.setenv("RECALLSTACK_CONTENT_LANG", "zh")
    text = path_worksheet(_loop_draft())
    task = text.split("## 这一步", 1)[1].split("## 原理", 1)[0]
    gate = text.split("## 核对", 1)[1]
    assert "打开" in task or "指出" in task
    assert "核对" in gate
    assert "你负责" not in task
    assert "你签字" not in gate
    assert "start_turn" in task
    assert "start_turn" in gate
    assert "了解模块" not in task
    assert "请了解" not in text
    assert "参观" not in task
    assert "您" not in text
    wiki = upgrade_legacy_concept_markdown(text, slug="agent-loop", title="Agent Loop")
    assert "## 本步要你干什么" not in wiki
    assert "## 过关" not in wiki
    assert "## 这一步" not in wiki
    assert "## 核对" not in wiki
    assert "你签字" not in wiki


def test_path_rank_trunk_before_leaves():
    assert path_rank("project-goal") < path_rank("entry-and-boot")
    assert path_rank("entry-and-boot") < path_rank("agent-loop")
    assert path_rank("agent-loop") < path_rank("tool-system")
    assert path_rank("tool-system") < path_rank("session-lifecycle")
    assert path_rank("session-lifecycle") < path_rank("acp-protocol")
    assert path_rank("tool-system") < path_rank("acp-protocol")
    assert path_rank("acp-protocol") < path_rank("codebase-graph")
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
    assert slugs.index("tool-system") < slugs.index("acp-protocol")
    assert "caching" not in slugs
    assert "request-routing" not in slugs
    assert "module-foo" not in slugs
    assert "codebase-graph" not in slugs
    assert "pty-control" not in slugs
    assert "headless-modes" not in slugs
    assert "encrypt_templates" not in slugs
    assert len(slugs) <= 10
    assert "agent-loop" in slugs
    assert slugs.index("agent-loop") < 4
    assert "acp-protocol" in slugs


def test_concept_wiki_pages_stay_handbook(monkeypatch):
    monkeypatch.setenv("RECALLSTACK_CONTENT_LANG", "zh")
    wiki = Wiki(project_name="grok-study", pages=[], sidebar=[])
    draft = _loop_draft()
    page = append_concept_pages(wiki, [draft]).get_page("concepts/agent-loop")
    assert page is not None
    assert "## 概述" in page.content
    assert "## 架构" in page.content
    assert "## 本步要你干什么" not in page.content
    assert "## 先回到原理" not in page.content
    assert "## 只看这一处证据" not in page.content
    assert "## 过关" not in page.content
    assert "start_turn 之后调模型" not in page.content
    assert "若这不成立" not in page.content
    assert "不要把这当成" not in page.content


def test_upgrade_legacy_concept_markdown_still_strips_path_homework(monkeypatch):
    monkeypatch.setenv("RECALLSTACK_CONTENT_LANG", "zh")
    mixed = path_worksheet(_loop_draft())
    upgraded = upgrade_legacy_concept_markdown(mixed, slug="agent-loop", title="Agent Loop")
    assert "## 本步要你干什么" not in upgraded
    assert "## 过关" not in upgraded
    assert "## 只看这一处证据" not in upgraded
    assert "## 先回到原理" not in upgraded
    assert "## 概述" in upgraded or "## 架构" in upgraded


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
    assert "你负责" not in loop_node.reason
    assert "start_turn" in loop_node.reason
    assert "不变量" in loop_node.principles
    assert "若这不成立" in loop_node.principles
    assert "while True" in loop_node.principles
    assert loop_node.evidence_chip == "crates/tui/src/app.rs:142 start_turn"
    assert "函数" in loop_node.pass_gate
    assert "核对" in loop_node.pass_gate
    assert "你签字" not in loop_node.pass_gate
    assert "离开终端循环还能不能完成它声称的事" not in loop_node.pass_gate
    ws = loop_node.worksheet
    assert "## 这一步" in ws
    assert "## 原理" in ws
    assert "## 这一处证据" in ws
    assert "## 核对" in ws
    assert "## 本步要你干什么" not in ws
    assert "## 过关" not in ws
    assert ws.count("`crates/tui/src/app.rs:142 start_turn`") == 1
    assert "架构图" not in ws
    assert "核心子系统" not in ws
    assert "进程怎么进" in out.description


def test_step_task_is_action_not_了解模块(monkeypatch):
    monkeypatch.setenv("RECALLSTACK_CONTENT_LANG", "zh")
    task = step_task_for_slug("agent-loop", "Agent Loop")
    assert "了解" not in task
    assert "你负责" not in task
    assert "签字" not in task
    assert "打开" in task
    assert "start_turn" in task
    assert "您" not in task


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
    assert worksheet.count("## 这一处证据") == 1


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
    assert goal == "crates/codegen/xai-grok-agent/src/turn.rs:2 start_turn"
    assert not goal.startswith("README.md")

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


def _live_use_site_store() -> dict[str, str]:
    """Jake's grok-study GET after 8ac69a9: refs are import/call sites."""
    agent = ["//! Agent types."] + [f"// pad {i}" for i in range(2, 6)]
    agent.append("use crate::tool_bridge::ToolBridge;")
    modes = [f"// pad {i}" for i in range(1, 341)]
    modes.append("    let pager = Pager::new();")
    return {
        "crates/codegen/xai-grok-agent/src/agent.rs": "\n".join(agent) + "\n",
        "crates/codegen/xai-grok-agent/src/tool_bridge.rs": (
            "/// Dispatches tool calls by name.\n\n"
            "pub struct ToolBridge {\n    tools: Vec<String>,\n}\n\n"
            "impl ToolBridge {\n    pub fn dispatch(&self, name: &str) {}\n}\n"
        ),
        "crates/codegen/xai-grok-pager/src/app/dispatch/modes.rs": "\n".join(modes) + "\n",
        "crates/codegen/xai-grok-pager/src/pager.rs": (
            "/// Terminal canvas.\n\n"
            "pub struct Pager {\n    buf: String,\n}\n"
        ),
        "crates/codegen/xai-agent-lifecycle/src/session_lifecycle.rs": (
            "//! Session lifecycle hooks.\n\n"
            "use crate::runtime::AgentRuntime;\n"
        ),
        "crates/codegen/xai-agent-lifecycle/src/runtime.rs": (
            "pub struct AgentRuntime {\n    session: u64,\n}\n"
        ),
        "crates/codegen/xai-grok-agent/src/acp/mod.rs": _rs_with_def_at(
            152, "    pub async fn connect("
        ),
        "crates/codegen/ptyctl-cli/src/main.rs": _rs_with_def_at(12, "fn main() {"),
        "crates/codegen/xai-chat-state/src/conversation_util.rs": _rs_with_def_at(
            27, "pub fn replace_or_insert_system_head(window: &mut Window, head: &str) {"
        ),
        "crates/codegen/xai-grok-pager/src/app/agent.rs": _rs_with_def_at(
            791, "    pub fn start_turn(&mut self) {"
        ),
    }


def test_toolbridge_import_loses_to_tool_bridge_struct():
    store = _live_use_site_store()
    assert "use crate::tool_bridge::ToolBridge;" in store[
        "crates/codegen/xai-grok-agent/src/agent.rs"
    ].splitlines()[5]
    chip = path_evidence_chip(
        ConceptDraft(
            slug="tool-system",
            title="工具层",
            wiki_page_id="topics/tool-system",
            source_references=[
                SourceReference(
                    path="crates/codegen/xai-grok-agent/src/agent.rs",
                    start_line=6,
                    symbol="ToolBridge",
                )
            ],
        ),
        file_texts=store,
    )
    assert chip == "crates/codegen/xai-grok-agent/src/tool_bridge.rs:3 ToolBridge"
    assert "agent.rs" not in chip


def test_pager_call_site_loses_to_pager_rs_struct():
    store = _live_use_site_store()
    assert "Pager::new()" in store[
        "crates/codegen/xai-grok-pager/src/app/dispatch/modes.rs"
    ].splitlines()[340]
    chip = path_evidence_chip(
        ConceptDraft(
            slug="terminal-ui",
            title="Terminal UI",
            wiki_page_id="topics/terminal-ui",
            source_references=[
                SourceReference(
                    path="crates/codegen/xai-grok-pager/src/app/dispatch/modes.rs",
                    start_line=341,
                    symbol="Pager",
                )
            ],
        ),
        file_texts=store,
    )
    assert chip == "crates/codegen/xai-grok-pager/src/pager.rs:3 Pager"
    assert "modes.rs" not in chip


def test_session_lifecycle_line_one_loses_to_agent_runtime_struct():
    store = _live_use_site_store()
    chip = path_evidence_chip(
        ConceptDraft(
            slug="agent-runtime",
            title="Agent Runtime",
            wiki_page_id="topics/agent-runtime",
            source_references=[
                SourceReference(
                    path="crates/codegen/xai-agent-lifecycle/src/session_lifecycle.rs",
                    start_line=1,
                )
            ],
        ),
        file_texts=store,
    )
    assert chip == "crates/codegen/xai-agent-lifecycle/src/runtime.rs:1 AgentRuntime"
    assert "session_lifecycle" not in chip


def test_kept_live_chips_entry_loop_context():
    store = _live_use_site_store()
    entry = path_evidence_chip(
        ConceptDraft(
            slug="entry-and-boot",
            title="入口与启动",
            wiki_page_id="topics/entry-and-boot",
            source_references=[
                SourceReference(
                    path="crates/codegen/xai-grok-agent/src/acp/mod.rs",
                    start_line=152,
                    symbol="connect",
                )
            ],
        ),
        file_texts=store,
    )
    assert entry == "crates/codegen/xai-grok-agent/src/acp/mod.rs:152 connect"
    assert "ptyctl" not in entry

    loop = path_evidence_chip(
        ConceptDraft(
            slug="agent-loop",
            title="Agent Loop",
            wiki_page_id="topics/agent-loop",
            source_references=[
                SourceReference(
                    path="crates/codegen/xai-grok-pager/src/app/agent.rs",
                    start_line=791,
                    symbol="start_turn",
                )
            ],
        ),
        file_texts=store,
    )
    assert loop == "crates/codegen/xai-grok-pager/src/app/agent.rs:791 start_turn"

    ctx = path_evidence_chip(
        ConceptDraft(
            slug="context-assembly",
            title="上下文装配",
            wiki_page_id="topics/context-assembly",
            source_references=[
                SourceReference(
                    path="crates/codegen/xai-chat-state/src/conversation_util.rs",
                    start_line=27,
                    symbol="replace_or_insert_system_head",
                )
            ],
        ),
        file_texts=store,
    )
    assert ctx == (
        "crates/codegen/xai-chat-state/src/conversation_util.rs:27 "
        "replace_or_insert_system_head"
    )


def test_wiki_key_types_get_line_from_store_not_use_site():
    md = (
        "## 关键类型\n\n"
        "- ToolBridge — 按名分发 — "
        "`crates/codegen/xai-grok-agent/src/agent.rs ToolBridge`\n"
        "- Pager — 画布 — "
        "`crates/codegen/xai-grok-pager/src/pager.rs Pager`\n"
    )
    store = _live_use_site_store()
    filled = fill_wiki_key_type_lines(md, store)
    assert "`crates/codegen/xai-grok-agent/src/tool_bridge.rs:3 ToolBridge`" in filled
    assert "`crates/codegen/xai-grok-pager/src/pager.rs:3 Pager`" in filled
    assert "`crates/codegen/xai-grok-agent/src/agent.rs ToolBridge`" not in filled


def test_wiki_core_subsystems_path_only_unchanged():
    md = (
        "## 核心子系统\n\n"
        "- 工具层 — `crates/codegen/xai-grok-agent/src/tool_bridge.rs`\n"
    )
    filled = fill_wiki_key_type_lines(md, _live_use_site_store())
    assert "`crates/codegen/xai-grok-agent/src/tool_bridge.rs`" in filled
    assert ":3" not in filled


def test_toolbridge_line_comes_from_file_text_not_one():
    """Store finds the file; chip must use the struct line (Jake: :1 on the right file)."""
    store = {
        "crates/codegen/xai-grok-agent/src/tool_bridge.rs": _rs_with_def_at(
            40, "pub struct ToolBridge {"
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
                    symbol="ToolBridge",
                )
            ],
        ),
        file_texts=store,
    )
    assert chip == "crates/codegen/xai-grok-agent/src/tool_bridge.rs:40 ToolBridge"


def test_toolbridge_reads_store_text_when_path_prefix_differs():
    store = {
        "crates/xai-grok-agent/src/tool_bridge.rs": _rs_with_def_at(
            40, "pub struct ToolBridge {"
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
                    symbol="ToolBridge",
                )
            ],
        ),
        file_texts=store,
    )
    assert chip.endswith(":40 ToolBridge")
    assert chip.rsplit("/", 1)[-1] == "tool_bridge.rs:40 ToolBridge"


def test_pager_and_runtime_stamp_def_line_not_one():
    store = {
        "crates/codegen/xai-grok-pager/src/pager.rs": _rs_with_def_at(
            88, "pub struct Pager {"
        ),
        "crates/codegen/xai-agent-lifecycle/src/runtime.rs": _rs_with_def_at(
            22, "pub struct AgentRuntime {"
        ),
    }
    pager = path_evidence_chip(
        ConceptDraft(
            slug="terminal-ui",
            title="Terminal UI",
            wiki_page_id="topics/terminal-ui",
            source_references=[
                SourceReference(
                    path="crates/codegen/xai-grok-pager/src/pager.rs",
                    start_line=1,
                    symbol="Pager",
                )
            ],
        ),
        file_texts=store,
    )
    runtime = path_evidence_chip(
        ConceptDraft(
            slug="agent-runtime",
            title="Agent Runtime",
            wiki_page_id="topics/agent-runtime",
            source_references=[
                SourceReference(
                    path="crates/codegen/xai-agent-lifecycle/src/runtime.rs",
                    start_line=1,
                    symbol="AgentRuntime",
                )
            ],
        ),
        file_texts=store,
    )
    assert pager == "crates/codegen/xai-grok-pager/src/pager.rs:88 Pager"
    assert runtime == "crates/codegen/xai-agent-lifecycle/src/runtime.rs:22 AgentRuntime"


def test_suggested_ask_questions_are_wiki_grounded_not_fsrs():
    grok_pages = [
        {"id": "topics/entry-and-boot", "title": "入口与启动", "content": "acp connect"},
        {"id": "topics/agent-loop", "title": "Agent Loop", "content": "start_turn"},
        {"id": "topics/acp-protocol", "title": "ACP", "content": "protocol"},
        {"id": "topics/terminal-ui", "title": "Terminal UI", "content": "Pager"},
    ]
    qs = suggested_ask_questions(grok_pages)
    assert len(qs) == 3
    blob = " ".join(qs)
    assert "start_turn" in blob or "connect" in blob or "Pager" in blob or "ACP" in blob
    assert all("你要能指出" not in q for q in qs)
    assert all("你负责" not in q for q in qs)
    assert any("connect" in q or "start_turn" in q or "Pager" in q or "ACP" in q for q in qs)
    assert "复习调度" not in blob
    assert "复训调度" not in blob
    assert "FSRS" not in blob
    assert "依赖图是怎么构建" not in blob

    empty = suggested_ask_questions([])
    assert empty == []


def test_wiki_out_applies_key_type_line_from_store(monkeypatch):
    monkeypatch.setenv("RECALLSTACK_CONTENT_LANG", "zh")
    md = (
        "# 工具层\n\n"
        "## 关键类型\n\n"
        "- ToolBridge — 按名分发 — "
        "`crates/codegen/xai-grok-agent/src/tool_bridge.rs ToolBridge`\n"
        "- Ghost — 无定义 — `crates/ghost/src/lib.rs Ghost`\n"
    )
    store = {
        "crates/codegen/xai-grok-agent/src/tool_bridge.rs": _rs_with_def_at(
            40, "pub struct ToolBridge {"
        )
    }

    class _Version:
        id = "ver-key-types"
        wiki_pages = {
            "project_name": "grok-study",
            "pages": [
                {"id": "topics/tool-system", "title": "工具层", "content": md},
                {"id": "topics/agent-loop", "title": "Agent Loop", "content": "start_turn\n"},
            ],
            "sidebar": [],
        }

    result = wiki_out("repo-1", _Version(), file_texts=store)
    page = next(p for p in result.pages if p.id == "topics/tool-system")
    assert "`crates/codegen/xai-grok-agent/src/tool_bridge.rs:40 ToolBridge`" in page.content
    assert "`crates/ghost/src/lib.rs Ghost`" in page.content
    assert ":1 Ghost`" not in page.content
    assert result.suggested_questions
    assert "复习调度" not in " ".join(result.suggested_questions)
    assert any("start_turn" in q or "tool call" in q for q in result.suggested_questions)


def test_missing_preferred_file_uses_store_symbol_not_invented_pager():
    """pager.rs absent; Pager only lives in an existing store key."""
    store = {
        "src/app/foo.rs": "// dispatch\n\npub struct Pager {\n    buf: String,\n}\n",
        "crates/codegen/xai-grok-pager/src/app/dispatch/modes.rs": (
            "fn draw() {\n    let _ = 1;\n}\n"
        ),
    }
    chip = path_evidence_chip(
        ConceptDraft(
            slug="terminal-ui",
            title="Terminal UI",
            wiki_page_id="topics/terminal-ui",
            source_references=[
                SourceReference(
                    path="crates/codegen/xai-grok-pager/src/app/dispatch/modes.rs",
                    start_line=1,
                    symbol="Pager",
                )
            ],
        ),
        file_texts=store,
    )
    assert chip == "src/app/foo.rs:3 Pager"
    assert "pager.rs" not in chip


def test_symbol_absent_from_store_keeps_existing_ref_not_invented_file():
    store = {
        "crates/codegen/xai-grok-agent/src/agent.rs": (
            "//! Agent types.\n\npub struct Agent;\n"
        ),
        "crates/codegen/xai-grok-pager/src/app/agent.rs": _rs_with_def_at(
            791, "    pub fn start_turn(&mut self) {"
        ),
        "crates/codegen/xai-chat-state/src/conversation_util.rs": _rs_with_def_at(
            27, "pub fn replace_or_insert_system_head(window: &mut Window, head: &str) {"
        ),
        "crates/codegen/xai-grok-agent/src/acp/mod.rs": _rs_with_def_at(
            152, "    pub async fn connect("
        ),
    }
    tools = path_evidence_chip(
        ConceptDraft(
            slug="tool-system",
            title="工具层",
            wiki_page_id="topics/tool-system",
            source_references=[
                SourceReference(
                    path="crates/codegen/xai-grok-agent/src/agent.rs",
                    start_line=6,
                    symbol="ToolBridge",
                )
            ],
        ),
        file_texts=store,
    )
    assert tools is not None
    assert "tool_bridge.rs" not in tools
    assert tools.startswith("crates/codegen/xai-grok-agent/src/agent.rs")
    assert ":1 " not in tools

    tui = path_evidence_chip(
        ConceptDraft(
            slug="terminal-ui",
            title="Terminal UI",
            wiki_page_id="topics/terminal-ui",
            source_references=[
                SourceReference(
                    path="crates/codegen/xai-grok-pager/src/app/agent.rs",
                    start_line=791,
                )
            ],
        ),
        file_texts=store,
    )
    assert tui is not None
    assert "pager.rs" not in tui
    assert tui.startswith("crates/codegen/xai-grok-pager/src/app/agent.rs")

    runtime = path_evidence_chip(
        ConceptDraft(
            slug="agent-runtime",
            title="Agent Runtime",
            wiki_page_id="topics/agent-runtime",
            source_references=[
                SourceReference(
                    path="crates/codegen/xai-grok-agent/src/agent.rs",
                    start_line=1,
                )
            ],
        ),
        file_texts=store,
    )
    assert runtime is not None
    assert "runtime.rs" not in runtime
    assert "agent.rs" in runtime


def test_agent_runtime_uses_lifecycle_rs_not_encrypt_script():
    """No runtime.rs; lifecycle lib.rs + encrypt_templates.py → lifecycle, not the script."""
    store = {
        "crates/codegen/xai-agent-lifecycle/src/lib.rs": (
            "pub mod local;\npub mod send;\n\npub struct SessionHooks;\n"
        ),
        "crates/codegen/xai-grok-agent/scripts/encrypt_templates.py": (
            "def xor_encrypt(data: bytes, key: bytes) -> bytes:\n    return data\n"
        ),
        "crates/codegen/xai-grok-agent/src/agent.rs": "pub struct Agent;\n",
    }
    chip = path_evidence_chip(
        ConceptDraft(
            slug="agent-runtime",
            title="Agent Runtime",
            wiki_page_id="topics/agent-runtime",
            source_references=[
                SourceReference(
                    path="crates/codegen/xai-grok-agent/scripts/encrypt_templates.py",
                    start_line=27,
                    symbol="xor_encrypt",
                ),
                SourceReference(
                    path="crates/codegen/xai-grok-agent/src/agent.rs",
                    start_line=1,
                ),
            ],
        ),
        file_texts=store,
    )
    assert chip is not None
    assert "xai-agent-lifecycle" in chip
    assert ".rs" in chip
    assert "runtime.rs" not in chip
    assert "encrypt" not in chip
    assert "scripts/" not in chip
    assert "xor_encrypt" not in chip
    assert chip.startswith("crates/codegen/xai-agent-lifecycle/src/lib.rs")
    path, line, symbol = parse_path_chip(chip)
    assert path.endswith("lib.rs")
    assert line >= 1
    assert symbol
    assert symbol != "Agent Runtime"


def test_wiki_key_types_do_not_invent_missing_store_path():
    md = (
        "## 关键类型\n\n"
        "- ToolBridge — 分发 — "
        "`crates/codegen/xai-grok-agent/src/tool_bridge.rs ToolBridge`\n"
    )
    store = {"crates/codegen/xai-grok-agent/src/agent.rs": "pub struct Agent;\n"}
    filled = fill_wiki_key_type_lines(md, store)
    assert "tool_bridge.rs:1" not in filled
    assert "`crates/codegen/xai-grok-agent/src/tool_bridge.rs ToolBridge`" in filled


def test_wiki_key_types_use_existing_store_symbol_not_invented_pager():
    md = (
        "## 关键类型\n\n"
        "- Pager — 画布 — "
        "`crates/codegen/xai-grok-pager/src/pager.rs Pager`\n"
    )
    store = {"src/app/foo.rs": "// dispatch\n\npub struct Pager {\n    buf: String,\n}\n"}
    filled = fill_wiki_key_type_lines(md, store)
    assert "pager.rs" not in filled
    assert "`src/app/foo.rs:3 Pager`" in filled


def test_project_goal_binds_start_turn_not_readme_when_store_has_def():
    store = _jake_grok_store()
    chip = path_evidence_chip(
        ConceptDraft(
            slug="project-goal",
            title="项目目标",
            wiki_page_id="topics/project-goal",
            source_references=[SourceReference(path="README.md", start_line=1)],
        ),
        file_texts=store,
    )
    assert chip == "crates/codegen/xai-grok-pager/src/app/agent.rs:791 start_turn"
    assert chip != "README.md:1"
    assert not chip.startswith("README.md")
    path, line, symbol = parse_path_chip(chip)
    assert path.endswith("app/agent.rs")
    assert line == 791
    assert symbol == "start_turn"
    contract = path_step_contract(
        ConceptDraft(slug="project-goal", title="项目目标"),
        chip=chip,
        file_texts=store,
    )
    assert contract["path"] == path
    assert contract["line"] == 791
    assert contract["symbol"] == "start_turn"
    assert "start_turn" in contract["gate"]


def test_project_goal_falls_back_to_readme_when_start_turn_absent():
    store = {
        "README.md": "# grok\n",
        "crates/codegen/xai-grok-pager/src/main.rs": "fn main() {}\n",
    }
    chip = path_evidence_chip(
        ConceptDraft(
            slug="project-goal",
            title="项目目标",
            source_references=[SourceReference(path="README.md", start_line=1)],
        ),
        file_texts=store,
    )
    assert chip == "README.md:1"
    assert chip_needs_restamp("project-goal", chip)


def test_agent_runtime_stamps_runtime_rs_not_file_only_lib():
    store = {
        "crates/codegen/xai-agent-lifecycle/src/lib.rs": (
            "pub mod runtime;\npub use runtime::AgentRuntime;\n"
        ),
        "crates/codegen/xai-agent-lifecycle/src/runtime.rs": _rs_with_def_at(
            22, "pub struct AgentRuntime {"
        ),
    }
    chip = path_evidence_chip(
        ConceptDraft(
            slug="agent-runtime",
            title="Agent Runtime",
            wiki_page_id="topics/agent-runtime",
            source_references=[
                SourceReference(
                    path="crates/codegen/xai-agent-lifecycle/src/lib.rs",
                    start_line=1,
                    symbol=None,
                )
            ],
        ),
        file_texts=store,
    )
    assert chip == "crates/codegen/xai-agent-lifecycle/src/runtime.rs:22 AgentRuntime"
    path, line, symbol = parse_path_chip(chip)
    assert line == 22
    assert symbol == "AgentRuntime"
    assert not chip_needs_restamp("agent-runtime", chip)
    assert chip_needs_restamp(
        "agent-runtime", "crates/codegen/xai-agent-lifecycle/src/lib.rs"
    )

    contract = path_step_contract(
        ConceptDraft(slug="agent-runtime", title="Agent Runtime"),
        chip=chip,
        file_texts=store,
    )
    items = QuestionGenerator().generate_from_contract(
        title="Agent Runtime",
        contract=contract,
    ).items
    assert items
    for item in items:
        assert item.source_references
        assert item.source_references[0].start_line == 22
        assert item.source_references[0].symbol == "AgentRuntime"
        assert item.rubric.contract["line"] == 22
        assert item.rubric.contract["symbol"] == "AgentRuntime"
