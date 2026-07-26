"""prompt templates for repowiki analysis pipeline."""

from __future__ import annotations

import json
import re


def _lang_instruction(language: str) -> str:
    lang_map = {
        "en": "Respond in English.",
        "zh": "请用中文回答。",
        "ja": "日本語で回答してください。",
        "ko": "한국어로 답변해주세요.",
    }
    return lang_map.get(language, "Respond in English.")


def _json_instruction() -> str:
    return (
        "Output ONLY valid JSON. No markdown fences, no explanation text before or after. "
        "Just the JSON object/array."
    )


def build_overview_prompt(file_tree: str, key_files: str, language: str = "en") -> list[dict]:
    return [
        {
            "role": "system",
            "content": (
                "You are a senior software engineer explaining a project to a new team member. "
                "Be direct, specific, and concrete. "
                "Do NOT use filler phrases like 'leveraging', 'utilizing', 'cutting-edge', "
                "'robust', or 'comprehensive'. Just describe what things do. "
                f"{_lang_instruction(language)}"
            ),
        },
        {
            "role": "user",
            "content": (
                f"Here is the file tree and key files of a project:\n\n"
                f"## File Tree\n```\n{file_tree}\n```\n\n"
                f"## Key Files\n{key_files}\n\n"
                f"Generate a project overview as JSON with this structure:\n"
                "{\n"
                '  "name": "project name",\n'
                '  "one_liner": "what this project does in one sentence (max 20 words)",\n'
                '  "description": "2-3 paragraphs explaining the project in plain language",\n'
                '  "tech_stack": [{"name": "Python", "category": "language", "version": "3.10+"}],\n'
                '  "setup_instructions": ["step 1", "step 2"],\n'
                '  "key_features": ["feature 1", "feature 2"]\n'
                "}\n\n"
                f"{_json_instruction()}"
            ),
        },
    ]


def build_module_prompt(
    module_name: str,
    files_context: str,
    project_summary: str,
    language: str = "en",
) -> list[dict]:
    return [
        {
            "role": "system",
            "content": (
                "You are a senior engineer documenting your own code. "
                "Be direct and specific. No filler. "
                "Explain what each file does, how files relate to each other, "
                "and what the key functions/classes are. "
                f"{_lang_instruction(language)}"
            ),
        },
        {
            "role": "user",
            "content": (
                f"Project: {project_summary}\n\n"
                f"Document the '{module_name}' module. Here are its files:\n\n"
                f"{files_context}\n\n"
                "Output JSON:\n"
                "{\n"
                f'  "name": "{module_name}",\n'
                '  "purpose": "one sentence",\n'
                '  "description": "detailed explanation",\n'
                '  "files": [\n'
                '    {"path": "file.py", "purpose": "what it does", '
                '"key_symbols": [{"name": "func_name", "kind": "function", "description": "..."}]}\n'
                '  ],\n'
                '  "relationships": [{"source": "a.py", "target": "b.py", "description": "a imports b for..."}],\n'
                '  "key_concepts": [{"name": "concept", "explanation": "..."}]\n'
                "}\n\n"
                f"{_json_instruction()}"
            ),
        },
    ]


def build_architecture_prompt(
    file_tree: str,
    key_files: str,
    language: str = "en",
) -> list[dict]:
    return [
        {
            "role": "system",
            "content": (
                "You are a software architect analyzing a codebase. "
                "Identify the architecture pattern and generate Mermaid diagrams. "
                "Mermaid syntax must be valid. Use simple node names (no special chars). "
                f"{_lang_instruction(language)}"
            ),
        },
        {
            "role": "user",
            "content": (
                f"## File Tree\n```\n{file_tree}\n```\n\n"
                f"## Key Files\n{key_files}\n\n"
                "Analyze the architecture. Output JSON:\n"
                "{\n"
                '  "architecture_type": "one of: monolith, client-server, microservices, library, cli-tool, framework, plugin-system, pipeline",\n'
                '  "description": "explain the architecture in 2-3 sentences",\n'
                '  "components": [{"name": "...", "purpose": "...", "files": ["..."]}],\n'
                '  "mermaid_component": "graph TD\\n  A[Component] --> B[Component]\\n  ...",\n'
                '  "mermaid_sequence": "sequenceDiagram\\n  participant A\\n  A->>B: request\\n  ...",\n'
                '  "data_flow": "describe the main data flow in 2-3 sentences"\n'
                "}\n\n"
                "IMPORTANT: Mermaid code must be a single string with \\n for newlines. "
                "Use simple alphanumeric node IDs. "
                f"{_json_instruction()}"
            ),
        },
    ]


def build_reading_guide_prompt(
    rankings: str,
    module_summaries: str,
    language: str = "en",
) -> list[dict]:
    return [
        {
            "role": "system",
            "content": (
                "You are a mentor helping a developer understand a new codebase. "
                "Create a reading guide: which files to read, in what order, and why. "
                "Start from entry points and configuration, then core logic, then utilities. "
                "Each step should say WHAT to look for, not just WHICH files. "
                f"{_lang_instruction(language)}"
            ),
        },
        {
            "role": "user",
            "content": (
                f"## File Importance Rankings (by PageRank)\n{rankings}\n\n"
                f"## Module Summaries\n{module_summaries}\n\n"
                "Create a reading guide with 5-10 steps. Output JSON:\n"
                "{\n"
                '  "introduction": "brief intro on how to approach this codebase",\n'
                '  "steps": [\n'
                '    {"order": 1, "title": "step title", "files": ["file1.py", "file2.py"], '
                '"explanation": "what to look for and why", "time_estimate": "5 min"}\n'
                '  ],\n'
                '  "tips": ["general tip 1", "general tip 2"]\n'
                "}\n\n"
                f"{_json_instruction()}"
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
    """extract JSON from LLM output, handling markdown fences and extra text."""
    # strip markdown code fences
    text = re.sub(r"^```(?:json)?\s*\n?", "", text.strip(), flags=re.MULTILINE)
    text = re.sub(r"\n?```\s*$", "", text.strip(), flags=re.MULTILINE)

    # try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # find the first { or [ and match to the last } or ]
    for start_char, end_char in [("{", "}"), ("[", "]")]:
        start = text.find(start_char)
        if start == -1:
            continue
        end = text.rfind(end_char)
        if end == -1 or end <= start:
            continue
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            continue

    return None
