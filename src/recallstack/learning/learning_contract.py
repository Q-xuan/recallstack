"""First-principles learning contract: what each path step is *for*."""

from __future__ import annotations

import re

from recallstack.domain.schemas import ConceptDraft
from recallstack.learning.i18n import t

# Kept as step-task templates only. Do NOT use this as the default learning
# path for every repo — that was a generic web-app syllabus.
CORE_SLUGS: tuple[str, ...] = (
    "project-goal",
    "application-entry",
    "configuration",
    "request-routing",
    "authentication",
    "data-persistence",
    "caching",
    "error-handling",
    "background-tasks",
    "testing-structure",
    "call-flow",
    "module-boundaries",
)

_FILLER_TITLE_RE = re.compile(
    r"^(Module:|模块[:：]|Key file:|关键文件[:：]|Focus:|聚焦[:：])",
    re.I,
)
_FILLER_SLUG_RE = re.compile(r"^(module-|file-|focus-)")
_FILLER_NAME_RE = re.compile(
    r"(README\.md|Cargo\.toml|__init__\.py|package\.json)",
    re.I,
)
_GENERIC_REASON_RE = re.compile(
    r"按先修关系与重要度安排|Ordered by prerequisites and importance",
    re.I,
)

CORE_PATH_CAP = 8

_SOURCE_CHIP_RE = re.compile(
    r"(?i)^[\w./\-]+(?:\.[A-Za-z0-9]+)+(?::\d+(?:-\d+)?)?$"
)
_CHROME_LINE_RE = re.compile(
    r"(?i)(\*\*(难度|Difficulty)\*\*.*(阅读时长|Reading time)|"
    r"\*\*(阅读时长|Reading time)\*\*.*(重要度|Importance))"
)
_CLICK_CHIP_RE = re.compile(
    r"(?:点击展开|Click to expand)\s*`([^`]+)`(?:（[^）]*）|\s*\([^)]*\))?"
)
_PRACTICE_LINE_RE = re.compile(
    r"(?i)(#practice|打开练习|practice panel|先看证据，再到底部|"
    r"先点开证据再往下|Open the evidence first)"
)
_HOMEWORK_HEADINGS = {
    "本步要你干什么",
    "What this step asks of you",
    "过关",
    "Pass",
    "自测",
    "Self-check",
    "只看这一处证据",
    "Look at this evidence only",
    "源码证据",
    "Source evidence",
    "Source Evidence",
    "为什么重要",
    "Why it matters",
    "Why this matters",
}
_WHAT_HEADINGS = {
    "它是什么",
    "What it is",
    "What is this",
    "先回到原理",
    "Back to first principles",
    "这份仓库做什么",
    "What this repo does",
    "职责与边界",
    "Responsibility and boundaries",
}
_POSITION_HEADINGS = {
    "它在系统里的位置",
    "Where it sits",
}
_FLOW_HEADINGS = {
    "一次调用怎么走",
    "How a call runs",
}
_TYPE_ROLE_HEADINGS = {
    "关键类型在链路上的职责",
    "Key types and their roles",
}
_NOT_THIS_HEADINGS = {
    "不是什么",
    "What this is not",
}
_TIPS_HEADINGS = {
    "术语小贴士",
    "Term tips",
}
_PREREQ_HEADINGS = {
    "先读",
    "Read first",
}
_NEXT_HEADINGS = {
    "接下来",
    "Next",
    "继续读",
    "Leads to",
}
_RELATED_HEADINGS = {
    "相关源码",
    "Related source",
    "Relevant source files",
}
_FLOW_SLUGS = {
    "application-entry",
    "request-routing",
    "call-flow",
    "authentication",
    "data-persistence",
    "error-handling",
    "background-tasks",
    "caching",
    "configuration",
}


def path_mission() -> str:
    return t(
        "When you finish this path you should be able to explain, in your own words "
        "and without leaning on the folder tree: what problem this repo solves, where "
        "the process starts, how a request moves, where state lives, and what happens "
        "on failure.",
        "走完这条路径，你要能不靠目录、用自己的话讲清「这个仓库解决什么问题、"
        "进程从哪启动、请求怎么走、状态存在哪、失败时怎么办」。",
    )


def is_filler_slug_title(slug: str, title: str) -> bool:
    """Folder/file inventory items — fine in 词条, not on the core path."""
    slug = slug or ""
    title = title or ""
    if slug in CORE_SLUGS:
        return False
    if _FILLER_SLUG_RE.match(slug):
        return True
    if _FILLER_TITLE_RE.match(title):
        return True
    if _FILLER_NAME_RE.search(title):
        return True
    return False


def is_filler_concept(concept: ConceptDraft) -> bool:
    return is_filler_slug_title(concept.slug, concept.title)


def is_core_path_concept(concept: ConceptDraft) -> bool:
    """Path nodes are real concepts from this repo, not folder inventory."""
    if is_filler_concept(concept):
        return False
    if concept.slug == "getting-started":
        return False
    return True


def is_generic_reason(reason: str) -> bool:
    return not (reason or "").strip() or bool(_GENERIC_REASON_RE.search(reason))


def step_task_for_slug(slug: str, title: str = "") -> str:
    """Concrete action for this step. Stored on the path node as ``reason``."""
    tasks = {
        "project-goal": t(
            "Write two sentences: who this repo is for, what problem it solves, and what it explicitly does not do.",
            "用两句话写出这个仓库为谁、解决什么、明确不做什么。",
        ),
        "application-entry": t(
            "Open the entrypoint and name the first three calls after the process starts.",
            "点开入口文件，说出进程启动后最先调用的三步。",
        ),
        "configuration": t(
            "Find where config enters runtime and name one behaviour it changes.",
            "找出配置从哪进入运行时，并指出它改变的一个行为。",
        ),
        "request-routing": t(
            "Trace one request from the outside in: which file receives it, which function handles it.",
            "顺着一个外部请求往里追：哪个文件接住它，哪个函数处理它。",
        ),
        "authentication": t(
            "Point to where identity is checked, and what happens if it fails.",
            "指出身份在哪被检查，以及失败时会发生什么。",
        ),
        "data-persistence": t(
            "Name the object that is written or read, and the function that does it.",
            "说出被写入或读出的对象，以及做这件事的函数。",
        ),
        "caching": t(
            "Say what is cached and what becomes wrong if the cache is stale.",
            "说出缓存了什么，以及缓存过期时会错在哪。",
        ),
        "error-handling": t(
            "Name one failure path and where it is caught or returned.",
            "指出一条失败路径，以及它在哪里被接住或返回。",
        ),
        "background-tasks": t(
            "Find one async/job path and say what side effect it performs.",
            "找出一条异步/任务路径，说出它产生的副作用。",
        ),
        "testing-structure": t(
            "Open one test and say which behaviour it is locking down.",
            "打开一个测试，说出它锁住的是哪段行为。",
        ),
        "call-flow": t(
            "Follow one call from entry to a side effect; name the functions in order.",
            "顺着一次调用从入口走到副作用，按顺序列出函数。",
        ),
        "module-boundaries": t(
            "Name two modules and the one responsibility that must not leak across them.",
            "指出两个模块，以及绝不能漏过去的那条职责边界。",
        ),
    }
    if slug in tasks:
        return tasks[slug]
    shown = title or slug
    return t(
        f"Open the evidence for `{shown}` and explain, in your own words, why this layer must exist.",
        f"打开「{shown}」的证据，用自己的话讲清这一层为什么必须存在。",
    )


def step_task(concept: ConceptDraft) -> str:
    if (getattr(concept, "task", None) or "").strip():
        return concept.task.strip()
    return step_task_for_slug(concept.slug, concept.title)


def first_principles(concept: ConceptDraft, project_name: str) -> str:
    name = project_name or concept.title
    slug = concept.slug
    if slug == "project-goal":
        return t(
            f"If {name} had no stated purpose, every file would look equally important. "
            "The constraint is the user problem: directories are consequences, not the reason the repo exists.",
            f"如果 {name} 没有目标，每个文件都会显得同样重要。"
            "约束是用户要解决的问题：目录是结果，不是仓库存在的原因。",
        )
    if slug == "application-entry":
        return t(
            "Without an entrypoint there is no process: nothing is wired, nothing runs. "
            "Read the boot path first; the rest of the graph only exists because something called it.",
            "没有入口就没有进程：没有装配，也就没有运行。"
            "先读启动路径；其余模块只因为被它调用才存在。",
        )
    if slug == "configuration":
        return t(
            "If config never entered runtime, behaviour would be frozen in code. "
            "The question is which knobs exist and who reads them — not how many YAML files sit in the tree.",
            "如果配置进不了运行时，行为就被写死在代码里。"
            "要问的是有哪些旋钮、谁在读它们——不是树里有多少 YAML。",
        )
    if slug == "request-routing":
        return t(
            "If nothing maps an external event to a function, the system cannot be used. "
            "Follow one request; folder names are not the path.",
            "如果外部事件没有映射到函数，系统就无法被使用。"
            "顺着一个请求走；目录名不是路径。",
        )
    if slug == "authentication":
        return t(
            "If identity is never checked, every caller is trusted. The constraint is who may act, not where the auth folder sits.",
            "如果从不核对身份，每个调用者都被信任。约束是谁可以行动，不是 auth 目录在哪。",
        )
    if slug == "data-persistence":
        return t(
            "If state is never written, the program forgets. Find the write/read, not the ORM folder.",
            "如果状态从不落盘，程序就会失忆。找写入/读出，而不是 ORM 目录。",
        )
    if slug == "caching":
        return t(
            "A cache is a lie that is usually true. Know what becomes false when it is stale.",
            "缓存是一种通常成立的谎言。要知道它过期时哪句话会变成假的。",
        )
    if slug == "error-handling":
        return t(
            "The happy path lies. Robustness is what happens when an assumption is false.",
            "只看成功路径会被骗。鲁棒性是假设为假时系统怎么走。",
        )
    if slug == "background-tasks":
        return t(
            "If work happens after the request returns, the user-visible path is incomplete. Find the side effect.",
            "如果工作发生在请求返回之后，用户看到的路径就是不完整的。去找副作用。",
        )
    if slug == "testing-structure":
        return t(
            "Tests are claims about behaviour. If you cannot name the claim, the test is just another file.",
            "测试是对行为的断言。说不出断言，测试就只是又一个文件。",
        )
    if slug == "call-flow":
        return t(
            "A system is the sequence of calls, not the set of files. Trace one path end to end.",
            "系统是调用的顺序，不是文件的集合。把一条路径从头跟到尾。",
        )
    if slug == "module-boundaries":
        return t(
            "A boundary exists to stop a responsibility leaking. Name what must not cross it.",
            "边界存在是为了拦住职责泄漏。说出什么绝不能穿过去。",
        )
    return t(
        f"If `{concept.title}` disappeared, which user-visible behaviour would break? "
        "Answer from the evidence, not from the directory name.",
        f"如果「{concept.title}」这一层消失，用户能察觉的哪段行为会坏？"
        "从证据回答，不要从目录名回答。",
    )


def pass_questions(concept: ConceptDraft) -> str:
    title = concept.title
    if concept.slug == "project-goal":
        return t(
            f"1. After opening the evidence: who is `{title}` for, in one sentence?\n"
            "2. What problem does it solve that a pile of files would not?\n"
            "3. Name one thing this repo is NOT responsible for, citing the evidence\n",
            f"1. 点开证据之后：用一句话说清「{title}」给谁用\n"
            "2. 它解决了什么问题——是一堆文件解决不了的？\n"
            "3. 举一件这个仓库明确不负责的事，并指出证据里的依据\n",
        )
    if concept.slug == "application-entry":
        return t(
            f"1. Which file is the entrypoint for `{title}`, and what does it call first?\n"
            "2. What does the entrypoint own vs. only wire in?\n"
            "3. If that file were empty, what would fail to start?\n",
            f"1. 「{title}」的入口是哪个文件，它首先调用了什么？\n"
            "2. 入口自己负责什么，只是装配进来的又是什么？\n"
            "3. 如果这个文件是空的，什么将无法启动？\n",
        )
    return t(
        f"1. After opening the evidence, what does `{title}` own — and where does that stop?\n"
        "2. Point to one path:line on this page that proves it\n"
        "3. If this boundary moved, which earlier or later step would change?\n",
        f"1. 点开证据之后：用自己的话说明「{title}」负责什么、边界停在哪里\n"
        "2. 指出本页一处 path:line 作为证据\n"
        "3. 如果这条边界移动，前面或后面哪一步会变？\n",
    )


def format_evidence_line(loc: str) -> str:
    """Path UI helper: wrap a SOURCE_REF_RE chip in a click instruction.

    Wiki handbook pages must use the bare ``path:line`` chip instead.
    """
    loc = loc.strip()
    if not loc:
        return ""
    start, end = _parse_line_span(loc)
    if start and end and start != end:
        return t(
            f"Click to expand `{loc}` (lines {start}–{end})",
            f"点击展开 `{loc}`（第 {start}–{end} 行）",
        )
    if start:
        return t(
            f"Click to expand `{loc}` (line {start})",
            f"点击展开 `{loc}`（第 {start} 行）",
        )
    path = loc.split(":", 1)[0]
    return t(
        f"Click to expand `{loc}` ({path})",
        f"点击展开 `{loc}`（{path}）",
    )


def handbook_lede(slug: str, title: str = "") -> str:
    """Opening line for a concept *wiki* page — not the learning-path task."""
    shown = title or slug
    if slug == "project-goal":
        return t(
            "This page explains what problem the repo solves and who it is for. "
            "After reading you should be able to state the goal and what it "
            "explicitly does not do, without leaning on the folder tree.",
            "这篇说明这个仓库解决什么问题、给谁用。读完应能不靠目录讲清目标与明确不做什么。",
        )
    if slug == "application-entry":
        return t(
            "This page explains where the process starts and what it wires first. "
            "After reading you should be able to name the entrypoint and the first calls.",
            "这篇说明进程从哪启动、启动后先装配什么。读完应能指出入口文件和最先的几步调用。",
        )
    if slug in _FLOW_SLUGS:
        return t(
            f"This page explains how `{shown}` sits on a real call path. "
            "After reading you should be able to say who calls it, what it calls, "
            "and what breaks if it disappears.",
            f"这篇说明「{shown}」在一次真实调用里的位置。读完应能讲清谁调用它、它调用谁、消失会坏哪。",
        )
    return t(
        f"This page explains `{shown}`. After reading you should be able to say "
        "what it owns and where that responsibility stops.",
        f"这篇说明「{shown}」。读完应能讲清它负责什么、边界停在哪里。",
    )


def handbook_position(slug: str, title: str = "") -> str:
    """Who calls it / what it calls / what breaks — wiki voice, not a worksheet."""
    shown = title or slug
    if slug == "project-goal":
        return t(
            "The goal constrains how the rest of the wiki is read: start at the "
            "entrypoints, then the hub modules. Directories are a consequence, "
            "not the reason the repository exists.",
            "目标约束整份 Wiki 的阅读顺序：先看入口，再看枢纽模块。目录是结果，不是仓库存在的原因。",
        )
    if slug == "application-entry":
        return t(
            "The OS or runtime calls the entrypoint; the entrypoint then wires "
            "the rest. If it disappeared, nothing else in the graph would run.",
            "进程由运行时调进入口；入口再去装配其余模块。如果它消失，图上别的节点都不会跑。",
        )
    return t(
        f"If `{shown}` disappeared, a user-visible behaviour would break. "
        "Name the callers and callees from the evidence, not from the folder name.",
        f"如果「{shown}」这一层消失，用户能察觉的行为会坏。"
        "从证据说出调用它的和它调用的，不要从目录名说。",
    )


def flow_narrative(slug: str, title: str = "") -> str:
    """Short how-a-call-runs blurb. Empty when the concept has no runtime flow."""
    if slug not in _FLOW_SLUGS:
        return ""
    shown = title or slug
    texts = {
        "application-entry": t(
            "The process enters at the entrypoint file, constructs what it owns, "
            "and hands control to the main loop or server.",
            "进程从入口文件进来，装配自己负责的对象，再把控制权交给主循环或服务器。",
        ),
        "request-routing": t(
            "An external event hits the receiving layer, is mapped to a handler, "
            "then enters business logic.",
            "外部事件打到接收层，映射到处理函数，再进入业务逻辑。",
        ),
        "call-flow": t(
            "One call runs from the entrypoint through collaborators to a side effect.",
            "一次调用从入口穿过协作对象，走到副作用。",
        ),
        "authentication": t(
            "A request reaches the identity check; on success it continues, on failure it stops.",
            "请求先经过身份检查：通过则继续，失败则停下。",
        ),
        "data-persistence": t(
            "A write or read is issued by a caller; the persistence layer talks to storage and returns.",
            "调用方发出写入或读出，持久化层与存储对话后再返回。",
        ),
        "error-handling": t(
            "An assumption fails, the error is caught or returned, and the user-visible path changes.",
            "某个假设为假，错误被接住或返回，用户看到的路径随之改变。",
        ),
        "background-tasks": t(
            "Work continues after the request returns; the side effect runs on a job or async path.",
            "请求返回之后工作仍在继续；副作用走任务或异步路径。",
        ),
        "caching": t(
            "A read hits the cache first; on miss it loads the source of truth and stores the result.",
            "读取先打到缓存；未命中再加载真相源并写回。",
        ),
        "configuration": t(
            "Config is loaded at boot, then read by the code paths whose behaviour it changes.",
            "配置在启动时载入，再被它会改变行为的代码路径读走。",
        ),
    }
    return texts.get(slug) or t(
        f"Follow one call that touches `{shown}` from the outside in.",
        f"顺着一次碰到「{shown}」的调用从外往里走。",
    )


def wiki_prose_excerpt(content: str, max_chars: int = 360) -> str:
    """First sentences of a wiki page, skipping diagrams, tables, and lists."""
    if not content:
        return ""
    text = re.sub(r"```[\s\S]*?```", "\n", content)
    kept: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("|") or stripped.startswith("- ") or stripped.startswith("* "):
            continue
        if stripped.startswith(">"):
            stripped = stripped[1:].strip()
        if not stripped or _CHROME_LINE_RE.search(stripped):
            continue
        if _PRACTICE_LINE_RE.search(stripped):
            continue
        kept.append(stripped)
    blob = " ".join(kept)
    blob = re.sub(r"\s+", " ", blob).strip()
    if not blob:
        return ""
    parts = re.split(r"(?<=[。.!？?])\s+", blob)
    excerpt = " ".join(parts[:2]).strip()
    if len(excerpt) > max_chars:
        excerpt = excerpt[: max_chars - 1].rstrip() + "…"
    return excerpt


def related_source_chip_line(
    locs: list[str],
    *,
    label: str | None = None,
    symbols: list[str] | None = None,
) -> str:
    chips: list[str] = []
    seen: set[str] = set()
    extras = list(symbols or [])
    for i, loc in enumerate(locs):
        chip = (loc or "").strip()
        if not chip or chip in seen or not _SOURCE_CHIP_RE.match(chip):
            continue
        seen.add(chip)
        symbol = extras[i].strip() if i < len(extras) and extras[i] else ""
        pill = f"{chip} {symbol}".strip() if symbol else chip
        chips.append(f"`{pill}`")
        if len(chips) >= 8:
            break
    if not chips:
        return ""
    heading = label or t("Related source", "相关源码")
    return f"**{heading}:** " + " ".join(chips)


def _parse_line_span(loc: str) -> tuple[int | None, int | None]:
    if ":" not in loc:
        return None, None
    span = loc.rsplit(":", 1)[-1]
    if "-" in span:
        a, b = span.split("-", 1)
        if a.isdigit() and b.isdigit():
            return int(a), int(b)
        return None, None
    if span.isdigit():
        n = int(span)
        return n, n
    return None, None


def _collect_source_chips(text: str) -> tuple[list[str], list[str]]:
    found: list[str] = []
    symbols: list[str] = []
    seen: set[str] = set()
    for match in re.finditer(
        r"(?:点击展开|Click to expand)\s*`([^`]+)`(?:（[^）]*）|\s*\([^)]*\))?(?:\s*—\s*`([^`]+)`)?",
        text or "",
    ):
        loc = match.group(1).strip()
        if loc and loc not in seen and _SOURCE_CHIP_RE.match(loc):
            seen.add(loc)
            found.append(loc)
            symbols.append((match.group(2) or "").strip())
    for match in re.finditer(r"`([^`]+)`(?:\s*—\s*`([^`]+)`)?", text or ""):
        loc = match.group(1).strip()
        if loc and loc not in seen and _SOURCE_CHIP_RE.match(loc):
            seen.add(loc)
            found.append(loc)
            symbols.append((match.group(2) or "").strip())
    return found, symbols


def _split_markdown_sections(content: str) -> tuple[str, list[tuple[str, str]]]:
    parts = re.split(r"(?m)^## ", content)
    lead = parts[0]
    sections: list[tuple[str, str]] = []
    for part in parts[1:]:
        title, _, rest = part.partition("\n")
        sections.append((title.strip(), rest))
    return lead, sections


def _heading_bucket(title: str) -> str | None:
    stripped = title.strip()
    if stripped in _HOMEWORK_HEADINGS or stripped in _RELATED_HEADINGS:
        return "drop"
    if stripped in _WHAT_HEADINGS:
        return "what"
    if stripped in _POSITION_HEADINGS:
        return "position"
    if stripped in _FLOW_HEADINGS:
        return "flow"
    if stripped in _TYPE_ROLE_HEADINGS:
        return "types"
    if stripped in _NOT_THIS_HEADINGS:
        return "not"
    if stripped in _TIPS_HEADINGS:
        return "tips"
    if stripped in _PREREQ_HEADINGS:
        return "prereq"
    if stripped in _NEXT_HEADINGS:
        return "next"
    return None


def _clean_lead(lead: str) -> tuple[str, str, list[str], list[str]]:
    """Return (title_line, leftover_prose, chips, symbols) from the pre-heading block."""
    title_line = ""
    quotes: list[str] = []
    prose: list[str] = []
    chips, symbols = _collect_source_chips(lead)
    for raw in lead.splitlines():
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("# ") and not title_line:
            title_line = stripped
            continue
        if _CHROME_LINE_RE.search(stripped):
            continue
        if _PRACTICE_LINE_RE.search(stripped):
            continue
        if stripped.startswith("**相关源码") or stripped.startswith("**Related source"):
            continue
        if stripped.startswith(">"):
            quote = stripped.lstrip("> ").strip()
            if quote and quote not in quotes:
                quotes.append(quote)
            continue
        prose.append(stripped)
    leftover = "\n\n".join(item for item in [*quotes, *prose] if item)
    return title_line, leftover, chips, symbols


def _join_bodies(chunks: list[str]) -> str:
    seen: list[str] = []
    for chunk in chunks:
        text = (chunk or "").strip()
        if not text:
            continue
        text = _CLICK_CHIP_RE.sub(lambda m: f"`{m.group(1).strip()}`", text)
        text = re.sub(r"(?m)^[ \t]*\*\*(难度|Difficulty)\*\*.*$", "", text)
        text = re.sub(
            r"(?m)^[ \t]*\*\*(相关源码|Related source).*$",
            "",
            text,
        )
        lines = [ln for ln in text.splitlines() if not _PRACTICE_LINE_RE.search(ln)]
        text = "\n".join(lines).strip()
        if not text:
            continue
        if any(text == other for other in seen):
            continue
        if any(text in other and text != other for other in seen):
            continue
        seen = [other for other in seen if not (other in text and other != text)]
        seen.append(text)
    return "\n\n".join(seen)


def _strip_leading_lede(text: str, lede: str) -> str:
    text = (text or "").strip()
    lede = (lede or "").strip()
    if not text or not lede:
        return text
    if text == lede:
        return ""
    if text.startswith(lede):
        return text[len(lede) :].strip()
    return text


def _append_section(out: list[str], heading: str, body: str) -> None:
    body = (body or "").strip()
    if not body:
        return
    out.append(f"## {heading}\n")
    out.append(f"{body}\n")


def upgrade_legacy_concept_markdown(
    content: str,
    slug: str = "",
    title: str = "",
    *,
    has_overview: bool = False,
    has_architecture: bool = False,
    overview_excerpt: str = "",
) -> str:
    """Strip homework chrome from persisted concept wiki pages.

    Learning-path ``step_task`` stays on the path API; it must not be written
    back into wiki markdown on GET.
    """
    if not content or "## " not in content:
        return content

    lead, sections = _split_markdown_sections(content)
    title_line, leftover, chips, chip_symbols = _clean_lead(lead)
    grouped: dict[str, list[str]] = {
        key: []
        for key in (
            "what",
            "position",
            "flow",
            "types",
            "not",
            "tips",
            "prereq",
            "next",
            "other",
        )
    }
    for heading, body in sections:
        extra_locs, extra_symbols = _collect_source_chips(body)
        chips.extend(extra_locs)
        chip_symbols.extend(extra_symbols)
        bucket = _heading_bucket(heading)
        if bucket == "drop":
            continue
        if bucket is None:
            grouped["other"].append(f"## {heading}\n\n{body.strip()}".strip())
            continue
        grouped[bucket].append(body)

    shown_title = title or (
        title_line[2:].strip() if title_line.startswith("# ") else slug
    )
    lede = handbook_lede(slug, shown_title)
    what_chunks = [
        _strip_leading_lede(leftover, lede),
        *(_strip_leading_lede(body, lede) for body in grouped["what"]),
    ]
    what = _join_bodies(what_chunks)
    position = _join_bodies(grouped["position"])
    if not position:
        position = handbook_position(slug, title)
        extra_links: list[str] = []
        if has_overview:
            extra_links.append(t("[Overview](index)", "[概述](index)"))
        if has_architecture:
            extra_links.append(t("[Architecture](architecture)", "[架构概览](architecture)"))
        if extra_links:
            position = (
                position
                + "\n\n"
                + t("See also: ", "相关页面：")
                + " · ".join(extra_links)
            )
        excerpt = (overview_excerpt or "").strip()
        if excerpt and excerpt not in what and excerpt not in position:
            position = f"{position}\n\n{excerpt}"

    out: list[str] = []
    out.append(title_line if title_line else f"# {shown_title}")
    out.append("")
    out.append(f"> {lede}\n")
    chip_line = related_source_chip_line(chips, symbols=chip_symbols)
    if chip_line:
        out.append(chip_line)
        out.append("")

    _append_section(out, t("What it is", "它是什么"), what)
    _append_section(out, t("Where it sits", "它在系统里的位置"), position)
    _append_section(out, t("How a call runs", "一次调用怎么走"), _join_bodies(grouped["flow"]))
    _append_section(
        out,
        t("Key types and their roles", "关键类型在链路上的职责"),
        _join_bodies(grouped["types"]),
    )
    _append_section(out, t("What this is not", "不是什么"), _join_bodies(grouped["not"]))
    _append_section(out, t("Term tips", "术语小贴士"), _join_bodies(grouped["tips"]))
    _append_section(out, t("Read first", "先读"), _join_bodies(grouped["prereq"]))
    _append_section(out, t("Next", "接下来"), _join_bodies(grouped["next"]))
    for block in grouped["other"]:
        cleaned = _join_bodies([block])
        if cleaned:
            out.append(cleaned)
            out.append("")

    text = "\n".join(out)
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Never re-insert the learning-path task into wiki markdown.
    if "本步要你干什么" in text or "What this step asks of you" in text:
        text = re.sub(
            r"(?ms)^## (本步要你干什么|What this step asks of you)\n.*?(?=^## |\Z)",
            "",
            text,
        )
    if "过关" in text or re.search(r"(?m)^## Pass\s*$", text):
        text = re.sub(r"(?ms)^## (过关|Pass)\n.*?(?=^## |\Z)", "", text)
    return text.rstrip() + "\n"
