"""First-principles learning contract: what each path step is *for*."""

from __future__ import annotations

import re

from recallstack.domain.schemas import ConceptDraft
from recallstack.learning.i18n import t

# The core path is a stack of constraints, not a catalog of folders.
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

_MUTE_REF_RE = re.compile(r"(?m)^- `([^`]+)`\s*$")


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
    return concept.slug in CORE_SLUGS and not is_filler_concept(concept)


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
    """Explicit click instruction wrapping a SOURCE_REF_RE-matching chip."""
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


def _rewrite_mute_chips(text: str) -> str:
    def _sub(match: re.Match[str]) -> str:
        loc = match.group(1).strip()
        if "点击展开" in match.group(0) or "Click to expand" in match.group(0):
            return match.group(0)
        return f"- {format_evidence_line(loc)}"

    return _MUTE_REF_RE.sub(_sub, text)


def upgrade_legacy_concept_markdown(content: str, slug: str = "", title: str = "") -> str:
    """Rewrite persisted concept pages so old scans pick up the new contract."""
    if not content or "## " not in content:
        return content
    text = _rewrite_mute_chips(content)

    evidence_intro = t("Open the evidence first, then keep reading.", "先点开证据再往下。")
    text = re.sub(
        r"(?m)^## (源码证据|Source evidence)\s*$",
        t("## Look at this evidence only", "## 只看这一处证据") + "\n\n" + evidence_intro,
        text,
    )
    text = re.sub(r"(?m)^## (自测|Self-check)\s*$", t("## Pass", "## 过关"), text)
    text = re.sub(
        r"(?m)^## (为什么重要|Why (?:it matters|this matters))\n+(?:>[^\n]*\n)+\n?",
        "",
        text,
        count=1,
    )
    text = re.sub(
        r"(?m)^## (这份仓库做什么|What this repo does|职责与边界|Responsibility and boundaries)\s*$",
        t("## Back to first principles", "## 先回到原理"),
        text,
        count=1,
    )

    task_heading = t("## What this step asks of you", "## 本步要你干什么")
    if task_heading not in text:
        task = step_task_for_slug(slug, title)
        insert = f"{task_heading}\n\n{task}\n\n"
        parts = text.split("\n", 1)
        if parts[0].startswith("# "):
            rest = parts[1] if len(parts) > 1 else ""
            match = re.search(r"(?m)^## ", rest)
            if match:
                rest = rest[: match.start()] + insert + rest[match.start() :]
                text = parts[0] + "\n" + rest
            else:
                text = parts[0] + "\n\n" + insert + rest
        else:
            text = insert + text
    return text.rstrip() + "\n"
