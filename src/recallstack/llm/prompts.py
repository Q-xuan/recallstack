"""Prompt templates for RecallStack structured LLM tasks.

PROMPT_VERSION must be bumped when any template changes so caches invalidate.
Language follows RepoWiki (en/zh/ja/ko) via ``recallstack.learning.i18n``.
"""

from __future__ import annotations

from recallstack.learning.i18n import content_lang, lang_instruction

PROMPT_VERSION = "v1"

CONCEPT_SYSTEM = """You generate learning concepts for a software codebase.
Return ONLY valid JSON matching the schema.
Every concept must cite real source_references from the provided files.
Do not invent files or symbols.
{lang_instruction}"""

CONCEPT_USER = """Repository: {repo_name}
Commit: {commit_sha}

File importance (PageRank top files):
{ranked_files}

Entry points:
{entrypoints}

Module dependencies:
{module_deps}

Key file previews:
{file_previews}

Generate 5-12 meaningful learning concepts (not one per file).
Focus on architecture, entry flow, core data, persistence, errors, tests.
JSON schema:
{{
  "concepts": [
    {{
      "slug": "kebab-case",
      "title": "string",
      "description": "string",
      "difficulty": 1-5,
      "importance": 0-1,
      "why_learn": "string",
      "estimated_minutes": 10,
      "source_references": [{{"path":"...", "start_line":1, "end_line":20, "symbol":"..."}}],
      "prerequisites": ["other-slug"]
    }}
  ]
}}
"""

ITEM_SYSTEM = """You create active learning questions grounded in real source code.
Return ONLY valid JSON. Questions must not leak the full answer.
Each item needs a rubric with 3-6 weighted required_points and source_references.
{lang_instruction}"""

ITEM_USER = """Concept: {title}
Description: {description}
Why learn: {why_learn}
Source references:
{source_refs}

Code excerpts:
{code_excerpts}

Generate up to 3 items of types active_recall, code_trace, teach_back.
JSON schema:
{{
  "items": [
    {{
      "item_type": "active_recall|code_trace|teach_back",
      "prompt": "question",
      "expected_answer_outline": "bullet outline",
      "difficulty": 1-5,
      "source_references": [{{"path":"...","start_line":1,"end_line":10,"symbol":"..."}}],
      "rubric": {{
        "required_points": [
          {{"id":"p1","description":"...","weight":0.3,"source_references":[]}}
        ],
        "common_misconceptions": [],
        "maximum_score": 1.0
      }}
    }}
  ]
}}
"""

EVAL_SYSTEM = """You grade a learner's answer against a rubric with source evidence.
Return ONLY valid JSON. Prefer rubric coverage over wording similarity.
Distinguish missing points from misconceptions.
Feedback: first affirm what is correct, then one top improvement.
Write feedback / suggested_revision / follow_up_question in the learner's content language.
{lang_instruction}"""

EVAL_USER = """Question: {prompt}
Item type: {item_type}
Learner answer: {answer}
Confidence: {confidence}
Hints used levels: {hint_levels}
Revealed answer: {revealed}

Rubric:
{rubric}

Expected outline:
{outline}

Source references:
{source_refs}

Code excerpts:
{code_excerpts}

JSON schema:
{{
  "score": 0.0,
  "covered_points": ["id"],
  "missing_points": ["id"],
  "misconceptions": ["..."],
  "source_evidence": [{{"path":"...","start_line":1,"end_line":5,"symbol":"..."}}],
  "feedback": "...",
  "suggested_revision": "...",
  "follow_up_question": "..."
}}
"""


def _with_lang(system_template: str, language: str | None = None) -> str:
    lang = language or content_lang()
    return system_template.format(lang_instruction=lang_instruction(lang))


def concept_messages(**kwargs: str) -> list[dict[str, str]]:
    language = kwargs.pop("language", None)
    return [
        {"role": "system", "content": _with_lang(CONCEPT_SYSTEM, language)},
        {"role": "user", "content": CONCEPT_USER.format(**kwargs)},
    ]


def item_messages(**kwargs: str) -> list[dict[str, str]]:
    language = kwargs.pop("language", None)
    return [
        {"role": "system", "content": _with_lang(ITEM_SYSTEM, language)},
        {"role": "user", "content": ITEM_USER.format(**kwargs)},
    ]


def eval_messages(**kwargs: str) -> list[dict[str, str]]:
    language = kwargs.pop("language", None)
    return [
        {"role": "system", "content": _with_lang(EVAL_SYSTEM, language)},
        {"role": "user", "content": EVAL_USER.format(**kwargs)},
    ]
