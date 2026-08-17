"""prompt templates for repowiki analysis pipeline."""

from __future__ import annotations

import json
import re

_LANG_NAMES = {
    "en": "English",
    "zh": "Simplified Chinese (简体中文)",
    "ja": "Japanese (日本語)",
    "ko": "Korean (한국어)",
}


def _lang_instruction(language: str) -> str:
    lang_map = {
        "en": (
            "Write a professional handbook page, not an API catalog or file tree. "
            "State what the system is and how one real flow is wired. "
            "Do not write 'After reading you should be able to…' or homework ledes. "
            "Never list every method on a type. Never say 'the entry point is lib.rs' "
            "or 'submodules are …'. Never write 'Heaviest modules by PageRank'."
        ),
        "zh": (
            "请用手册体简体中文撰写手册正文（对齐 DeepSeek Harness README.zh / DeepWiki）："
            "直接陈述概念、seam 和角色，再讲目录。不要讲义腔，不要机翻。"
            "禁止「读完应能」「读完你应该能」「这篇文档讲…读完应能…」"
            "「它是什么」「一次调用怎么走」「缺了它哪条能力会断」「用户能察觉的行为会坏」。"
            "专有名词保持英文（Agent、plugin、harness、chip、wiki、concept、Capability Seam）；"
            "必要时括号补中文，例如 harness（智能体框架）、agent（智能体）。"
            "禁止翻译 identifier、类型名、crate/包名、协议名（如 ACP、`PtyHandle`）。"
            "plugin 可写作「插件」（约定译名），不要用「插件系统」来翻译 plugin；"
            "Agent 不要译成「代理人」。"
            "用「你」不用「您」，禁止翻译腔。"
            "路径、crate/包名、符号、协议名保持英文原文（如 ACP、`PtyHandle`），不要音译。"
            "禁止目录腔，禁止 “Heaviest modules”，禁止接口清单"
            "（入口是 lib.rs、子模块是 keys/pty/server、给 struct 列 spawn/resize/is_alive）。"
        ),
        "ja": "日本語で回答してください。",
        "ko": "한국어로 답변해주세요.",
    }
    return lang_map.get(language, lang_map["en"])


def _term_tips_field() -> str:
    return '  "term_tips": [{"term": "ACP", "tip": "how this repo uses it"}],\n'


def _term_tips_rules(*, required: bool) -> str:
    count = (
        "term_tips is REQUIRED: 3-8 items. "
        if required
        else "term_tips: 3-8 items when this page has jargon a mid-level engineer might not know here; otherwise []. "
    )
    return (
        count
        + "Each tip is how THIS repository uses the term, not a generic encyclopedia entry. "
        "Only terms that appear as identifiers or crate/dir names in THIS repo's source. "
        "Never tip PageRank / wiki-pipeline jargon or say the term is unused here. "
        "Keep `term` as the code identifier in English (ACP, crate); write `tip` in the output language."
    )


def _json_instruction(language: str = "en") -> str:
    """Closing contract for a prompt: JSON shape, then output language.

    The language directive is repeated here rather than left to the system
    message alone. Every schema in this module is written with English keys and
    English placeholder values, and smaller models copy the language of that
    example over a single instruction several hundred tokens earlier.
    """
    base = (
        "Output ONLY valid JSON. No markdown fences, no explanation text before or after. "
        "Just the JSON object/array."
    )
    name = _LANG_NAMES.get(language)
    if not name or language == "en":
        return base
    return (
        f"{base}\n\n"
        f"LANGUAGE: keep the JSON keys exactly as shown above in English, but write "
        f"every human-readable value in {name}. The placeholder values in the schema "
        f"are English only to show the shape — do not copy their language. "
        f"{_lang_instruction(language)}"
    )


def build_outline_prompt(
    file_tree: str,
    module_summaries: str,
    rankings: str,
    entrypoints: str,
    language: str = "en",
) -> list[dict]:
    return [
        {
            "role": "system",
            "content": (
                "You are a staff engineer planning a codebase wiki. "
                "Produce a COMPACT writing plan (topics only), not the wiki itself. "
                "Keep the JSON small enough to finish: 8-14 topics, short strings. "
                "Prioritize entrypoints and high-PageRank files. "
                f"{_lang_instruction(language)}"
            ),
        },
        {
            "role": "user",
            "content": (
                f"## File Tree\n```\n{file_tree}\n```\n\n"
                f"## Modules (evidence only — do NOT outline each one)\n{module_summaries}\n\n"
                f"## File importance (PageRank)\n{rankings}\n\n"
                f"## Entrypoints and config\n{entrypoints}\n\n"
                "Output a wiki outline as JSON:\n"
                "{\n"
                '  "overview_focus": "what the overview page must explain",\n'
                '  "architecture_focus": "what the architecture page must explain",\n'
                '  "topics": [\n'
                "    {\n"
                '      "id": "agent-runtime",\n'
                '      "title": "Agent Runtime",\n'
                '      "section": "deep-dive",\n'
                '      "purpose": "what the reader can explain after this page",\n'
                '      "key_files": ["real/path.rs"],\n'
                '      "depth": "deep"\n'
                "    }\n"
                "  ]\n"
                "}\n\n"
                "topics are the PRIMARY wiki IA (zread 深入探索): 8-14 conceptual systems "
                "this repo actually has (Agent Runtime, Agent Loop, Tool System, ACP, TUI, entry/boot). "
                "section is getting-started or deep-dive. Titles are human system names, "
                "NEVER directory paths and NEVER 'Module: crates/foo'. "
                "Do NOT invent a generic web-app syllabus (authentication, caching, "
                "request-routing, data-persistence) unless a first-class crate/directory "
                "is named that way (e.g. `xai-grok-auth`). A helper file named auth.rs "
                "inside another crate does not count. "
                "topics[].key_files MUST be real paths from the tree (2-6 per topic). "
                "agent-loop key_files MUST be the runtime loop "
                "(xai-grok-agent `agent.rs` / run / turn / tool dispatch, or crates/agent loop.rs) "
                "— NEVER conversation_util.rs, PromptContext, or replace_or_insert_system_head, "
                "and prefer production files over tests/. "
                "Context assembly (System head, PromptContext, xai-chat-state) is a SEPARATE "
                "topic id context-assembly, not a subtitle of agent-loop. "
                "entry-and-boot key_files MUST be the grok binary / pager boot "
                "(bin/grok.rs, xai-grok-pager, pager app/boot, CLI main.rs the user runs). "
                "NEVER bin/protoc, protobuf codegen, dotslash toolchain scripts, "
                "code-graph, or fast-worktree CLIs. "
                "tool-system key_files MUST include ToolBridge when that type exists. "
                "depth is one of deep, standard, brief. Mark at most a third as deep. "
                "Do NOT emit modules[], reading_order, or emphasized_pages — those are planned locally. "
                "Do NOT dump a crate inventory. Keep purpose to one sentence. "
                "overview_focus and architecture_focus must be narrative (responsibilities and wiring), "
                "never a PageRank file dump.\n\n"
                f"{_json_instruction(language)}"
            ),
        },
    ]


def build_overview_prompt(
    file_tree: str,
    key_files: str,
    language: str = "en",
    *,
    outline_focus: str = "",
    emphasized: str = "",
    topic_titles: list[str] | None = None,
) -> list[dict]:
    outline_block = ""
    if outline_focus or emphasized:
        outline_block = (
            f"## Wiki outline focus\n{outline_focus or '(none)'}\n\n"
            f"## Pages/modules to emphasize\n{emphasized or '(none)'}\n\n"
        )
    titles = [t for t in (topic_titles or []) if t]
    if titles:
        listed = "\n".join(f"- {t}" for t in titles[:12])
        outline_block += (
            "## Planned deep-dive wiki pages (cross-link these by title in see_also / subsystems)\n"
            f"{listed}\n\n"
        )
    return [
        {
            "role": "system",
            "content": (
                "You are a senior software engineer writing a DeepWiki overview page. "
                "Be direct, specific, and concrete. "
                "Do NOT use filler phrases like 'leveraging', 'utilizing', 'cutting-edge', "
                "'robust', or 'comprehensive'. Just describe what things do. "
                "Cite real file paths from the tree using backticks like `src/app.py:12`. "
                "The builder renders lists and tables — fill structured fields, "
                "do not dump one long description blob. "
                "FORBIDDEN: README dump, crate inventory, file inventory, JavaDoc/method dumps, "
                "'Heaviest modules by PageRank', key_features as marketing bullets, "
                "homework headings (what this step asks of you / 本步要你干什么 / pass check). "
                f"{_lang_instruction(language)}"
            ),
        },
        {
            "role": "user",
            "content": (
                f"Here is the file tree and key files of a project:\n\n"
                f"## File Tree\n```\n{file_tree}\n```\n\n"
                f"## Key Files\n{key_files}\n\n"
                f"{outline_block}"
                "Generate a project overview as JSON with this structure:\n"
                "{\n"
                '  "name": "project name",\n'
                '  "one_liner": "what this project does in one sentence (max 20 words)",\n'
                '  "document_scope": "what this is and where it sits on the call path — no After-reading-you-should",\n'
                '  "what_it_is": [\n'
                '    "concrete characteristic with a `path:line` cite",\n'
                '    "another characteristic with a `path:line` cite"\n'
                "  ],\n"
                '  "runtime_flow": "2-4 short paragraphs: name types as roles on ONE real flow.",\n'
                '  "mermaid_component": "flowchart TD\\n  A[Entry] --> B[Core]",\n'
                '  "codebase_structure": [\n'
                '    {"name": "crate-or-package", "location": "crates/foo", "purpose": "role in the flow"}\n'
                "  ],\n"
                "  \"subsystems\": [\n"
                "    {\n"
                '      "name": "subsystem matching a planned topic if possible",\n'
                '      "role": "what it does on the call flow",\n'
                '      "key_types": [{"name": "start_turn", "role": "pager dispatch / start_turn", "path": "src/file.rs:12"}],\n'
                '      "files": ["src/file.rs"],\n'
                '      "mermaid": "flowchart LR\\n  A[Pager] --> B[Agent] --> C[Model]"\n'
                "    }\n"
                "  ],\n"
                '  "see_also": ["architecture", "topics/agent-loop"],\n'
                '  "description": "backup sentence only; do not dump the README here",\n'
                '  "tech_stack": [{"name": "Python", "category": "language", "version": "3.10+"}],\n'
                '  "setup_instructions": [],\n'
                '  "key_features": [],\n'
                '  "citations": [{"path": "real/file.py", "start_line": 1, "symbol": "Type", "note": "why this file matters"}],\n'
                f"{_term_tips_field()}"
                "}\n\n"
                "REQUIRED (DeepWiki handbook, not a README): "
                "document_scope is a handbook lede (what this is / where it sits; "
                "in 简体中文: 直接陈述，禁止「这篇文档讲…读完应能…」, 用你不用您). "
                "what_it_is: 3-6 characteristic sentences, each with a real `path:line` cite "
                "(not a crate folder and not a path without a line). "
                "runtime_flow: types as roles on one real call. "
                "mermaid_component: a mermaid flowchart of that runtime (not a crate tree); "
                "first line MUST be flowchart LR / flowchart TD / sequenceDiagram "
                "(never a bare `A --> B` with no diagram type). "
                "codebase_structure: 2-8 rows from REAL paths (crates/, src/, packages/), "
                "columns name / location / purpose — not a file dump. "
                "subsystems: 3-8. Each row MUST be a real Type, one-line duty, and one "
                "`path:line Symbol` key_type — not an empty heading. "
                "Each subsystem mermaid MUST start with `flowchart LR` or `sequenceDiagram`; "
                "prefer 3-6 labeled nodes that are the key_types (Type as role); "
                "labels ≤ ~12 CJK characters; "
                "FORBIDDEN: 2-node one-edge toys, crate-folder nodes, unlabeled A/B. "
                "Example: flowchart LR\\n  A[Pager] --> B[start_turn] --> C[ToolBridge]. "
                "Name Agent Loop (pager dispatch / start_turn), never 'Agent Loop 与上下文装配'. "
                "Terminal UI / TUI MUST cite pager types (Pager / TuiPager), not an empty section. "
                "Omit a key_type if `path` is missing; never invent Type names that are not in the source. "
                "Never use lib.rs or a crate folder name as a Type. "
                "see_also: architecture plus planned topic ids only "
                "(e.g. topics/agent-loop, topics/context-assembly when that topic is planned). "
                "Never invent topics/pty-control or topics/code-graph — use the planned ids "
                "(topics/agent-loop, topics/context-assembly, topics/tui-pager, topics/codebase-graph). "
                "If a crate is code-graph / codebase-graph, name that subsystem "
                "代码图谱 / codebase graph, never 代码生成. "
                "Leave key_features empty. Do not dump a file inventory, method list, or JavaDoc. "
                "Never write homework headings (what this step asks, 本步要你干什么, pass check). "
                "Never list Python/JavaScript with version 未指定 unless those languages "
                "actually appear in the tree. Leave tech_stack empty when unsure. "
                f"{_term_tips_rules(required=True)} "
                "citations.path MUST be a real path from the tree. Omit citations rather than invent paths.\n\n"
                f"{_json_instruction(language)}"
            ),
        },
    ]


def build_module_prompt(
    module_name: str,
    files_context: str,
    project_summary: str,
    language: str = "en",
    *,
    depth: str = "standard",
    outline_notes: str = "",
    key_files: list[str] | None = None,
    key_symbols: list[str] | None = None,
    sections: list[str] | None = None,
    topic_id: str = "",
) -> list[dict]:
    depth = depth if depth in {"deep", "standard", "brief"} else "standard"
    focus = ""
    if outline_notes or key_files or key_symbols or sections:
        keys = ", ".join(f"`{p}`" for p in (key_files or [])[:8]) or "(none)"
        symbols = ", ".join(key_symbols or []) or "(none)"
        planned = ", ".join(sections or []) or depth
        focus = (
            f"Writing plan: depth={depth}; sections={planned}.\n"
            f"Notes: {outline_notes or '(none)'}\n"
            f"Load-bearing files (roles in the flow, not a tree): {keys}\n"
            f"Candidate types/functions for the walkthrough (NOT a method list): {symbols}\n\n"
        )

    forbidden = (
        "FORBIDDEN (these are the JavaDoc / rustdoc smell — never produce them):\n"
        "- 'The entry point is lib.rs. Submodules are keys, pty, server, session…'\n"
        "- Listing every method on a struct (spawn, resize, is_alive, …)\n"
        "- Turning the page into a file tree or crate inventory\n"
        "- Repeating the same sentence in purpose, description, and implementation_details\n"
        "- 'Heaviest modules by PageRank'\n"
    )

    if depth == "brief":
        term_tips_required = False
        extra_rules = (
            "This is a low-priority module. Keep purpose to one sentence and description short. "
            "Leave implementation_details, call_chains, and edge_cases empty unless one real "
            "flow is obvious from the source. "
        )
        length_hint = "Keep the JSON compact."
    else:
        term_tips_required = depth == "deep"
        extra_rules = (
            "Write a DeepWiki handbook page for one subsystem, not an interface catalog. "
            "document_scope: what this is and where it sits on the call path. "
            "No 'After reading you should' / 「读完应能」. "
            "what_it_is: 2-4 characteristic sentences, each with a `path:line` cite. "
            "purpose: role in the system — who calls this, what it calls, what "
            "breaks if it disappeared. Do not repeat document_scope. "
            "description: same as purpose if you only fill one; do not dump README. "
            "key_types: 2-4 types as roles (`Type` — job on the flow — `path`). "
            "Omit a key_type if you do not have a real path; never invent Type names. "
            "mermaid: one small flowchart of THIS subsystem on the call path. "
            "First line MUST be flowchart LR or sequenceDiagram; never a bare "
            "`A --> B` with no diagram type. Prefer 3-6 labeled nodes. "
            "Node labels ≤ ~12 CJK characters (or ~24 ASCII), complete phrases, "
            "no trailing incomplete verbs (合并为 / 调用 cut mid-word). "
            "implementation_details: ONE happy-path walkthrough in prose paragraphs, with "
            "`path:line` cites and types in backticks. Control flow and state, not a file list. "
            "call_chains: REQUIRED, 1-3 named flows. Each step is "
            "'who calls whom, with what, then what happens', citing real functions from the "
            "provided source. Not 'see pty.rs'. "
            "edge_cases: concrete failures from THIS code (child dies, resize, lock, missing PTY). "
            "files: at most 4-6 load-bearing files, each with a one-clause purpose. "
            "Do not nest method lists under files. "
            "key_symbols (if any) only for 1-3 types/functions that already appear in the "
            "walkthrough — never a method dump. "
            "No homework headings (本步要你干什么 / what this step asks). "
        )
        if depth == "deep":
            extra_rules += (
                "This is a HIGH-IMPORTANCE module: longform walkthrough, at least one call_chain "
                "with 3+ steps, concrete edge_cases. "
            )
            length_hint = "description: 2-4 paragraphs. implementation_details: 2-5 paragraphs."
        else:
            extra_rules += "Walkthrough + at least one call_chain are required at this depth. "
            length_hint = "description: 1-3 paragraphs. implementation_details: 2-4 paragraphs."

    tid = f"{topic_id} {module_name}".lower()
    if "agent-loop" in tid or "agent loop" in tid:
        extra_rules += (
            "THIS PAGE IS THE RUNTIME AGENT LOOP, not context assembly. "
            "Title must stay Agent Loop — never 'Agent Loop 与上下文装配'. "
            "调用链 MUST be this spine, in this order: "
            "收用户输入 → 组会话/prompt → 调模型 → 解析 tool calls → 执行工具 → "
            "把结果写回 → 再调模型 / 结束 "
            "(English: user input → assemble session/prompt → model call → parse tool calls → "
            "run tools → write results back → call model again / stop). "
            "call_chains and implementation_details must walk that loop (下一轮 / observe / 工具调用). "
            "mermaid is REQUIRED: a flowchart of THAT loop starting with flowchart LR, "
            "not System[0] alignment. "
            "FORBIDDEN as the spine/lede of this page: replace_or_insert_system_head, "
            "PromptContext-as-the-loop, traceparent injection, ChatStateActor System head. "
            "Those belong on topics/context-assembly, at most a short aside here. "
            "Cite production model-call / ToolBridge sites, not tests/. "
            "Do NOT invent types named AgentLoop or HooksSystem. "
            "Mermaid node labels must be complete words (no truncated 'Cont' / 'Sess' / 'ToolB'), "
            "≤ ~12 CJK characters, no trailing incomplete verbs. "
        )
    if "tool-system" in tid or "工具层" in tid:
        extra_rules += (
            "THIS PAGE IS THE TOOL SYSTEM. Include ToolBridge "
            "(model tool calls → execute → write-back), not only hooks. "
        )
    if "entry-and-boot" in tid or "入口与启动" in tid or "entry and boot" in tid:
        extra_rules += (
            "THIS PAGE IS HOW THE USER STARTS GROK: the product binary, pager boot, "
            "or ACP server start — not the build toolchain. "
            "Do NOT lead with bin/protoc, a dotslash script, protobuf codegen, "
            "code-graph, or fast-worktree CLIs. Those are at most a one-line aside. "
        )
    if "context-assembly" in tid or "上下文装配" in tid:
        extra_rules += (
            "THIS PAGE IS CONTEXT ASSEMBLY (System head / PromptContext / "
            "replace_or_insert_system_head), not the agent runtime loop. "
            "Do not make session → model → tool → observe the spine here. "
        )

    return [
        {
            "role": "system",
            "content": (
                "You are a senior engineer writing a DeepWiki handbook page for one module. "
                "Be direct and specific. No filler. "
                "Only cite file paths that appear in the provided source. "
                "Never invent paths, line numbers, or symbols. "
                "FORBIDDEN: homework headings (本步要你干什么). "
                f"{_lang_instruction(language)}"
            ),
        },
        {
            "role": "user",
            "content": (
                f"Project: {project_summary}\n\n"
                f"Document the '{module_name}' module. Here are its files:\n\n"
                f"{files_context}\n\n"
                f"{focus}"
                f"{forbidden}"
                f"{extra_rules}{length_hint}\n\n"
                "Output JSON:\n"
                "{\n"
                f'  "name": "{module_name}",\n'
                '  "document_scope": "what this is and where it sits on the call path",\n'
                '  "what_it_is": ["characteristic with `path:line`", "characteristic with `path:line`"],\n'
                '  "purpose": "what this page is for, and what the reader can explain afterwards",\n'
                '  "description": "who calls this, what it calls, what breaks if it disappears",\n'
                '  "key_types": [{"name": "Type", "role": "job on the flow", "path": "src/file.rs"}],\n'
                '  "mermaid": "flowchart TD\\n  A[Caller] --> B[This subsystem]",\n'
                '  "implementation_details": "ONE happy-path walkthrough with `path:line` cites",\n'
                '  "call_chains": [\n'
                '    {"name": "one session", "description": "request to PTY bytes", '
                '"steps": ["handler in `server.rs:40` receives the session", '
                '"`PtyHandle` in `pty.rs:12` opens the child", '
                '"read loop copies bytes back to the socket"], '
                '"files": ["server.rs", "pty.rs"]}\n'
                "  ],\n"
                '  "edge_cases": ["child dies: read returns EIO and the session ends"],\n'
                '  "files": [\n'
                '    {"path": "pty.rs", "purpose": "owns PtyHandle on the happy path"}\n'
                "  ],\n"
                '  "relationships": [{"source": "a.py", "target": "b.py", "description": "a new fact not already in the walkthrough"}],\n'
                '  "key_concepts": [{"name": "concept", "explanation": "only if it adds a fact the walkthrough does not say"}],\n'
                '  "citations": [{"path": "file.py", "start_line": 12, "symbol": "func_name", "note": "why"}],\n'
                f"{_term_tips_field()}"
                "}\n\n"
                "files[].path, relationships, call_chains.files, and citations.path MUST be "
                "paths shown above. Use 0 for unknown line numbers rather than guessing. "
                "Omit files[].key_symbols; names belong in the walkthrough as `path:line` cites. "
                "Never write 本步要你干什么 or a homework worksheet. "
                f"{_term_tips_rules(required=term_tips_required)}\n\n"
                f"{_json_instruction(language)}"
            ),
        },
    ]


def build_architecture_prompt(
    file_tree: str,
    key_files: str,
    language: str = "en",
    *,
    outline_focus: str = "",
    core_modules: str = "",
) -> list[dict]:
    outline_block = ""
    if outline_focus or core_modules:
        outline_block = (
            f"## Architecture focus\n{outline_focus or '(none)'}\n\n"
            f"## Core modules\n{core_modules or '(none)'}\n\n"
        )
    return [
        {
            "role": "system",
            "content": (
                "You are a software architect writing a DeepWiki architecture page. "
                "Lead with a valid Mermaid diagram of the runtime flow, then describe "
                "components as roles on that flow — not as a file tree. "
                "Mermaid syntax must be valid. Use simple node names (no special chars). "
                "Cite real file paths from the tree; never invent them. "
                "FORBIDDEN: README dump, crate inventory, file inventory, JavaDoc/method dumps, "
                "'Heaviest modules by PageRank', homework headings (本步要你干什么). "
                f"{_lang_instruction(language)}"
            ),
        },
        {
            "role": "user",
            "content": (
                f"## File Tree\n```\n{file_tree}\n```\n\n"
                f"## Key Files\n{key_files}\n\n"
                f"{outline_block}"
                "Analyze the architecture. Output JSON:\n"
                "{\n"
                '  "architecture_type": "one of: monolith, client-server, microservices, library, framework, plugin-system, pipeline — never cli-tool",\n'
                '  "description": "2-4 professional paragraphs: types as roles on ONE real flow, with `path:line` cites. NEVER a PageRank file dump. NEVER invent AgentLoop.",\n'
                '  "components": [\n'
                "    {\n"
                '      "name": "Subsystem",\n'
                '      "role": "job on the flow",\n'
                '      "purpose": "same as role if you only fill one",\n'
                '      "key_types": [{"name": "start_turn", "role": "pager dispatch", "path": "src/file.rs:12"}],\n'
                '      "files": ["real/path.py"]\n'
                "    }\n"
                "  ],\n"
                '  "mermaid_component": "graph TD\\n  A[Component] --> B[Component]\\n  ...",\n'
                '  "mermaid_sequence": "sequenceDiagram\\n  participant Pager\\n  participant Turn as start_turn\\n  participant Model\\n  participant Bridge as ToolBridge\\n  Pager->>Turn: dispatch\\n  Turn->>Model: complete\\n  Model-->>Turn: tool calls\\n  Turn->>Bridge: execute\\n  Bridge-->>Turn: write-back\\n  Turn->>Turn: on_turn_done",\n'
                '  "data_flow": "walk one request through the mermaid boxes in 2-4 sentences",\n'
                '  "citations": [{"path": "real/path.py", "start_line": 1, "symbol": "start_turn", "note": "why this file is architectural"}],\n'
                f"{_term_tips_field()}"
                "}\n\n"
                "IMPORTANT: Mermaid code must be a single string with \\n for newlines. "
                "Use simple alphanumeric node IDs. mermaid_component is REQUIRED when the "
                "graph is knowable — it is rendered at the top of 系统架构 / System architecture. "
                "components: each is a ROLE in the flow (who calls whom), not a folder listing. "
                "Each component MUST include 2-4 key_types (Type — job — `path:line Symbol`), not just "
                "name — purpose — files. Omit a key_type if `path` is missing; never invent Type names "
                "(no AgentLoop, no lib.rs as a type). "
                "Live agent loop is pager dispatch → start_turn → TurnRunning → model → ToolBridge → "
                "write-back → on_turn_done. mermaid_sequence MUST call the model BEFORE tools "
                "(never tools then model). "
                "Do not set architecture_type to cli-tool; omit it or use pipeline. "
                "citations MUST include symbol when the cited type/function is known. "
                "Keep files to 1-3 load-bearing paths per component. "
                "components.files and citations.path MUST be real paths from the tree. "
                "description must explain the system as a call path, not list heaviest files. "
                "Never write a method dump or homework worksheet. "
                f"{_term_tips_rules(required=True)}\n\n"
                f"{_json_instruction(language)}"
            ),
        },
    ]


def build_reading_guide_prompt(
    rankings: str,
    module_summaries: str,
    language: str = "en",
    *,
    reading_order: str = "",
) -> list[dict]:
    order_block = ""
    if reading_order:
        order_block = f"## Suggested reading order (from wiki outline)\n{reading_order}\n\n"
    return [
        {
            "role": "system",
            "content": (
                "You are a mentor helping a developer understand a new codebase. "
                "Create a reading guide: which files to read, in what order, and why. "
                "Start from entry points and configuration, then core logic, then utilities. "
                "Each step should say WHAT to look for, not just WHICH files. "
                "Only list files that appear in the rankings or module summaries. "
                f"{_lang_instruction(language)}"
            ),
        },
        {
            "role": "user",
            "content": (
                f"## File Importance Rankings (by PageRank)\n{rankings}\n\n"
                f"## Module Summaries\n{module_summaries}\n\n"
                f"{order_block}"
                "Create a reading guide with 5-10 steps. Output JSON:\n"
                "{\n"
                '  "introduction": "brief intro on how to approach this codebase",\n'
                '  "steps": [\n'
                '    {"order": 1, "title": "step title", "files": ["file1.py", "file2.py"], '
                '"explanation": "what to look for and why", "time_estimate": "5 min"}\n'
                "  ],\n"
                '  "tips": ["general tip 1", "general tip 2"]\n'
                "}\n\n"
                "steps[].files MUST be real paths from the rankings.\n\n"
                f"{_json_instruction(language)}"
            ),
        },
    ]


def build_citation_repair_prompt(
    module_name: str,
    module_json: str,
    invalid_paths: list[str],
    valid_paths: list[str],
    language: str = "en",
) -> list[dict]:
    invalid = "\n".join(f"- {p}" for p in invalid_paths[:20]) or "(none)"
    valid = "\n".join(f"- {p}" for p in valid_paths[:40]) or "(none)"
    return [
        {
            "role": "system",
            "content": (
                "You repair documentation JSON so every file citation is real. "
                "Do not invent new claims. Replace or drop bad paths only. "
                f"{_lang_instruction(language)}"
            ),
        },
        {
            "role": "user",
            "content": (
                f"The '{module_name}' module doc cites files that are not in the repository.\n\n"
                f"## Invalid paths\n{invalid}\n\n"
                f"## Valid paths in this project\n{valid}\n\n"
                f"## Current JSON\n{module_json}\n\n"
                "Return the same JSON object, with invalid paths rewritten to a valid path "
                "when the intent is obvious, otherwise removed. Keep implementation_details, "
                "call_chains, and citations consistent with the valid path list. "
                "Do not add new files that were not listed as valid.\n\n"
                f"{_json_instruction(language)}"
            ),
        },
    ]


def build_chat_prompt(
    question: str,
    context_chunks: str,
    language: str = "en",
) -> list[dict]:
    return [
        {
            "role": "system",
            "content": (
                "You are a knowledgeable developer answering questions about a codebase. "
                "Answer based on the actual code shown below, not general knowledge. "
                "Reference specific files and line numbers when relevant. "
                "Be direct -- answer the question, don't give a lecture. "
                f"{_lang_instruction(language)}"
            ),
        },
        {
            "role": "user",
            "content": (
                f"## Relevant Code\n{context_chunks}\n\n"
                f"## Question\n{question}"
            ),
        },
    ]


def build_inline_explain_prompt(
    *,
    selection: str,
    question: str,
    context_chunks: str,
    wiki_page_title: str = "",
    surrounding_text: str = "",
    language: str = "en",
) -> list[dict]:
    """Prompt for in-wiki term/symbol explanation (reading assistant)."""
    page_line = f"Wiki page: {wiki_page_title}\n" if wiki_page_title else ""
    surround = ""
    if surrounding_text.strip():
        # keep prompt bounded
        clipped = surrounding_text.strip()
        if len(clipped) > 1200:
            clipped = clipped[:1200] + "…"
        surround = f"\n## Surrounding wiki text\n{clipped}\n"

    user_q = question.strip() or (
        f"在本仓库中，「{selection}」是什么意思？它负责什么？"
        if language.startswith("zh")
        else f"In this codebase, what does “{selection}” mean and what is it responsible for?"
    )

    structure = (
        "用下面结构简短回答（结合本仓库，不要空讲百科）：\n"
        "1. 一句话定义（贴合本项目）\n"
        "2. 在本项目中的职责/位置\n"
        "3. 1-3 个源码证据（文件路径，如有符号一并写出）\n"
        "4. 它不是什么（若容易混淆）\n"
        "5. 一个可选的加深思考问题\n"
        if language.startswith("zh")
        else (
            "Answer briefly using this structure (grounded in THIS repo, not generic encyclopedia):\n"
            "1. One-sentence definition (project-specific)\n"
            "2. Role / where it lives in this project\n"
            "3. 1-3 code evidence items (file paths; symbols if known)\n"
            "4. What it is NOT (if easy to confuse)\n"
            "5. One optional deeper question for the reader\n"
        )
    )

    return [
        {
            "role": "system",
            "content": (
                "You are a reading assistant embedded in a codebase wiki. "
                "The user highlighted a term or symbol while reading documentation. "
                "Explain it in the context of THIS repository using the code evidence provided. "
                "Be concise and concrete. Prefer project meaning over general definitions. "
                f"{_lang_instruction(language)}"
            ),
        },
        {
            "role": "user",
            "content": (
                f"{page_line}"
                f"## Selected term\n{selection}\n"
                f"{surround}"
                f"## Relevant Code\n{context_chunks}\n\n"
                f"## Question\n{user_q}\n\n"
                f"{structure}"
            ),
        },
    ]


def extract_json(text: str) -> dict | list | None:
    """Extract JSON from LLM output: fences, trailing commas, truncated objects."""
    if text is None:
        return None
    raw = str(text).strip()
    if not raw:
        return None
    for candidate in _json_candidates(raw):
        parsed = _loads_relaxed(candidate)
        if parsed is not None:
            return parsed
    return None


def _strip_fences(text: str) -> str:
    text = text.strip()
    fenced = re.search(r"```(?:json)?\s*\r?\n?(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if fenced:
        return fenced.group(1).strip()
    text = re.sub(r"^```(?:json)?\s*\r?\n?", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\r?\n?```\s*$", "", text)
    return text.strip()


def _json_candidates(text: str) -> list[str]:
    stripped = _strip_fences(text)
    out: list[str] = [stripped]
    if stripped != text.strip():
        out.append(text.strip())
    for start_char in ("{", "["):
        start = stripped.find(start_char)
        if start == -1:
            continue
        end_char = "}" if start_char == "{" else "]"
        end = stripped.rfind(end_char)
        if end > start:
            out.append(stripped[start : end + 1])
        out.append(stripped[start:])
    seen: set[str] = set()
    uniq: list[str] = []
    for item in out:
        if item and item not in seen:
            seen.add(item)
            uniq.append(item)
    return uniq


def _strip_trailing_commas(text: str) -> str:
    prev = None
    while prev != text:
        prev = text
        text = re.sub(r",(\s*[}\]])", r"\1", text)
    return text


def _unclosed_string(text: str) -> bool:
    in_string = False
    escape = False
    for ch in text:
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
        elif ch == '"':
            in_string = True
    return in_string


def _closers_for(text: str) -> str:
    in_string = False
    escape = False
    stack: list[str] = []
    for ch in text:
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch in "{[":
            stack.append("}" if ch == "{" else "]")
        elif ch in "}]":
            if stack and stack[-1] == ch:
                stack.pop()
    return "".join(reversed(stack))


def _repair_truncated_json(text: str) -> str | None:
    s = _strip_trailing_commas(text.strip())
    if _unclosed_string(s):
        s += '"'
    s = re.sub(r":\s*$", "", s)
    s = _strip_trailing_commas(s)
    for _ in range(12):
        candidate = s + _closers_for(s)
        try:
            json.loads(candidate)
            return candidate
        except json.JSONDecodeError:
            last_comma = s.rfind(",")
            if last_comma <= 0:
                break
            s = _strip_trailing_commas(s[:last_comma])
    candidate = s + _closers_for(s)
    try:
        json.loads(candidate)
        return candidate
    except json.JSONDecodeError:
        return None


def _loads_relaxed(text: str) -> dict | list | None:
    for variant in (text, _strip_trailing_commas(text)):
        try:
            return json.loads(variant)
        except json.JSONDecodeError:
            continue
    repaired = _repair_truncated_json(text)
    if not repaired:
        return None
    try:
        return json.loads(repaired)
    except json.JSONDecodeError:
        return None
