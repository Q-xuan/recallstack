"""First-principles learning contract: what each path step is *for*."""

from __future__ import annotations

import logging
import re
from typing import Any

from recallstack.domain.schemas import ConceptDraft, SourceReference
from recallstack.learning.i18n import t
from repowiki.core.topics import is_entry_boot_file, is_toolchain_boot_file

logger = logging.getLogger(__name__)

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

# Generic web-app syllabus. Fine as optional *topics* when the repo actually
# has that system; never a default path node (Jake: not caching / routing fillers).
_WEB_FILLER_SLUGS = frozenset(
    {
        "caching",
        "request-routing",
        "authentication",
        "data-persistence",
        "error-handling",
        "background-tasks",
        "data-model",
        "business-logic",
        "persistence",
        "request-lifecycle",
        "observability",
        "auth-and-identity",
    }
)

# Trunk → big branches → leaves. First steps: process entry, then how a turn runs.
_PATH_TRUNK: tuple[str, ...] = (
    "project-goal",
    "entry-and-boot",
    "application-entry",
    "agent-loop",
    "call-flow",
    "runtime-loop",
    "tool-system",
    "terminal-ui",
    "tui-pager",
    "context-assembly",
    "agent-runtime",
    "session-lifecycle",
    "conversation-store",
)
_PATH_RANK = {slug: i for i, slug in enumerate(_PATH_TRUNK)}

# (path suffixes tried in order, symbol that proves the invariant)
_EVIDENCE_HINTS: dict[str, tuple[tuple[str, ...], str]] = {
    "agent-loop": (
        ("app/agent.rs", "turn.rs", "lifecycle.rs", "app.rs", "loop.rs", "dispatch.rs"),
        "start_turn",
    ),
    "call-flow": (("app/agent.rs", "turn.rs", "app.rs", "loop.rs"), "start_turn"),
    "runtime-loop": (("app/agent.rs", "turn.rs", "app.rs", "loop.rs"), "start_turn"),
    "entry-and-boot": (
        ("bin/grok.rs", "grok.rs", "main.rs", "lib.rs", "boot.rs", "connect.rs", "app.rs"),
        "main",
    ),
    "application-entry": (
        ("bin/grok.rs", "grok.rs", "main.rs", "lib.rs", "boot.rs", "connect.rs", "main.py"),
        "main",
    ),
    "tool-system": (("tool_bridge.rs", "bridge.rs"), "ToolBridge"),
    "terminal-ui": (("pager.rs",), "Pager"),
    "tui-pager": (("pager.rs",), "Pager"),
    "context-assembly": (("conversation_util.rs", "context.rs"), "replace_or_insert_system_head"),
    "agent-runtime": (("runtime.rs", "lifecycle.rs"), "AgentRuntime"),
    "system-prompt": (("agents_md.rs", "prompt.rs", "system.rs"), ""),
    "project-goal": (("README.md", "readme.md"), ""),
}

# Used only when refs are junk (toml/json/sh) and the scan store has no hit.
_FALLBACK_FILES: dict[str, tuple[str, ...]] = {
    "entry-and-boot": (
        "crates/codegen/xai-grok-pager/src/lib.rs",
        "crates/codegen/xai-grok-pager/src/main.rs",
        "crates/tui/src/bin/grok.rs",
    ),
    "agent-loop": (
        "crates/codegen/xai-grok-pager/src/app/agent.rs",
        "crates/codegen/xai-grok-agent/src/turn.rs",
        "crates/codegen/xai-grok-pager/src/app.rs",
        "crates/tui/src/app.rs",
    ),
    "tool-system": (
        "crates/codegen/xai-grok-agent/src/tool_bridge.rs",
        "crates/tools/src/lib.rs",
    ),
    "terminal-ui": (
        "crates/codegen/xai-grok-pager/src/pager.rs",
        "crates/codegen/xai-grok-pager/src/lib.rs",
        "crates/tui/src/pager.rs",
    ),
    "tui-pager": (
        "crates/codegen/xai-grok-pager/src/pager.rs",
        "crates/tui/src/pager.rs",
    ),
    "context-assembly": (
        "crates/codegen/xai-chat-state/src/conversation_util.rs",
        "crates/ai/src/context.rs",
    ),
    "agent-runtime": (
        "crates/codegen/xai-agent-lifecycle/src/runtime.rs",
        "crates/codegen/xai-agent-lifecycle/src/lib.rs",
        "crates/agent/src/runtime.rs",
    ),
    "system-prompt": ("crates/codegen/xai-grok-agent/src/prompt/agents_md.rs",),
}

_JUNK_BASENAMES = frozenset(
    {
        "cargo.toml",
        "package.json",
        "package-lock.json",
        "pnpm-lock.yaml",
        "yarn.lock",
    }
)
_JUNK_EXTS = (".toml", ".json", ".sh", ".bash", ".zsh")
_WEAK_SYMBOLS = frozenset({"main", "new", "run", "init", "start"})
_ENTRY_SYMBOLS = ("main", "connect", "boot")
_PTY_SLUGS = frozenset({"pty-control", "pty"})
_SRC_EXT = (".rs", ".py", ".go")
_DEFN_KW = (
    r"(?:pub(?:\([^)]*\))?\s+)?"
    r"(?:async\s+)?"
    r"(?:fn|struct|enum|trait|type|class|def|impl(?:\s*<[^>]*>)?)\s+"
)

# entry-and-boot is grok/pager boot — never ptyctl-cli or protoc.
_SLUG_DENY_NEEDLES: dict[str, tuple[str, ...]] = {
    "entry-and-boot": ("ptyctl", "protoc", "protobuf", "dotslash", "/proto/"),
    "application-entry": ("ptyctl", "protoc", "protobuf", "dotslash", "/proto/"),
    "agent-loop": ("ptyctl", "protoc"),
    "tool-system": ("ptyctl", "protoc"),
    "terminal-ui": ("ptyctl", "protoc"),
    "tui-pager": ("ptyctl", "protoc"),
    "context-assembly": ("ptyctl", "protoc"),
    "agent-runtime": ("ptyctl", "protoc"),
    "system-prompt": ("ptyctl", "protoc"),
}

# When any matching path exists in the store, drop the rest.
_SLUG_PREFER_NEEDLES: dict[str, tuple[str, ...]] = {
    "entry-and-boot": (
        "xai-grok-pager",
        "xai-grok-agent",
        "/npm/grok/",
        "/bin/grok",
        "crates/tui",
    ),
    "application-entry": (
        "xai-grok-pager",
        "xai-grok-agent",
        "/npm/grok/",
        "/bin/grok",
        "crates/tui",
    ),
    "agent-loop": ("xai-grok-pager", "xai-grok-agent", "crates/tui"),
    "tool-system": ("tool_bridge", "xai-grok-agent", "xai-grok-tools"),
    "terminal-ui": ("xai-grok-pager", "/pager.rs", "crates/tui"),
    "tui-pager": ("xai-grok-pager", "/pager.rs", "crates/tui"),
    "context-assembly": ("xai-chat-state", "conversation_util"),
    "agent-runtime": ("xai-agent-lifecycle",),
    "system-prompt": ("xai-grok-agent", "agents_md", "/prompt/"),
}

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
        "Walk the trunk first: how the process starts, how one turn runs, then tools "
        "and UI. At each step ask only: if this layer vanished, could the system still work?",
        "先看进程怎么进，再看一轮对话怎么转，最后才看工具和界面。"
        "每一步只问：这一层不存在，系统还能不能工作。",
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


def is_web_filler_path_slug(slug: str, wiki_page_id: str | None = None) -> bool:
    """Drop generic-web syllabus nodes unless they are a real `topics/` page."""
    if (slug or "") not in _WEB_FILLER_SLUGS:
        return False
    if (wiki_page_id or "").startswith("topics/"):
        return False
    return True


def path_rank(slug: str) -> int:
    """Lower is earlier: trunk, then branches, then leaves."""
    return _PATH_RANK.get(slug or "", 80)


def drop_duplicate_entry_slug(slug: str, selected_slugs: set[str]) -> bool:
    """``application-entry`` is the same trunk slot as ``entry-and-boot``."""
    return slug == "application-entry" and "entry-and-boot" in selected_slugs


def is_core_path_concept(concept: ConceptDraft) -> bool:
    """Path nodes are real concepts from this repo, not folder inventory."""
    if is_filler_concept(concept):
        return False
    if concept.slug == "getting-started":
        return False
    wiki_id = getattr(concept, "wiki_page_id", None)
    if is_web_filler_path_slug(concept.slug, wiki_id):
        return False
    return True


def is_generic_reason(reason: str) -> bool:
    return not (reason or "").strip() or bool(_GENERIC_REASON_RE.search(reason))


def step_task_for_slug(slug: str, title: str = "") -> str:
    """Concrete action for this step. Stored on the path node as ``reason``."""
    tasks = {
        "project-goal": t(
            "In one sentence: after the user hits Enter in the terminal, which three layers (entry, one turn, model call) must exist for an answer to come back?",
            "用一句话说清：用户在终端里回车之后，系统靠哪三层（入口、一轮循环、模型调用）才能答上来。",
        ),
        "entry-and-boot": t(
            "Open the grok binary entry and name the first runtime constructed after the process starts.",
            "打开 grok 二进制入口，指出进程启动后第一个被构造的运行时是什么。",
        ),
        "application-entry": t(
            "Open the entrypoint and name the first three calls after the process starts — not a crate name.",
            "打开入口文件，指出进程启动后最先调用的三步（不是某个 crate 的名字）。",
        ),
        "agent-loop": t(
            "Open the evidence and point to who calls the model after start_turn (not tools first).",
            "打开证据，指出谁在 start_turn 之后调模型（不是先跑工具）。",
        ),
        "call-flow": t(
            "Follow one turn: name who runs between input entering the turn and the model being called.",
            "顺着一轮对话，指出输入进 turn 之后到模型被调用之间经过谁。",
        ),
        "runtime-loop": t(
            "Open the evidence and point to who calls the model after start_turn (not tools first).",
            "打开证据，指出谁在 start_turn 之后调模型（不是先跑工具）。",
        ),
        "tool-system": t(
            "Open ToolBridge and point to who dispatches a tool call by name after the model returns it.",
            "打开 ToolBridge，指出模型给出 tool call 之后谁按名字执行。",
        ),
        "terminal-ui": t(
            "Open Pager and point to which buffer streaming model output is written into.",
            "打开 Pager，指出模型流式输出时字写进哪一块缓冲区。",
        ),
        "tui-pager": t(
            "Open Pager and point to which buffer streaming model output is written into.",
            "打开 Pager，指出模型流式输出时字写进哪一块缓冲区。",
        ),
        "context-assembly": t(
            "Open replace_or_insert_system_head and say whether the system head is written at the window head or appended after the user message.",
            "打开 replace_or_insert_system_head，指出系统头是写进窗口头还是拼在用户消息后面。",
        ),
        "agent-runtime": t(
            "Open the runtime type and point to what it owns that the turn loop cannot construct by itself.",
            "打开运行时类型，指出一轮循环自己构造不了、必须由它持有的是什么。",
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
        "module-boundaries": t(
            "Name two modules and the one responsibility that must not leak across them.",
            "指出两个模块，以及绝不能漏过去的那条职责边界。",
        ),
    }
    if slug in tasks:
        return tasks[slug]
    shown = title or slug
    return t(
        f"Open the evidence and point to the step `{shown}` must perform on a real call — not a directory name.",
        f"打开证据，指出「{shown}」在一次真实调用里必须发生的那一步（不要用目录名回答）。",
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


def path_principles(concept: Any, project_name: str = "") -> str:
    """2–5 sentences of invariants for the path worksheet. Not a file list."""
    slug = getattr(concept, "slug", "") or ""
    title = getattr(concept, "title", "") or slug
    name = project_name or title
    texts = {
        "project-goal": t(
            f"{name} is a product you run, not a pile of crates. "
            "A binary, one turn, and a model call have to exist or nothing answers. "
            "Invariant: no entry, no turn, no model call — no product.",
            f"{name} 首先是一个能跑起来的产品，不是一组可以随便拆开的 crate。"
            "有入口、有一轮循环、有模型调用，用户才能得到回答。"
            "不变量：没有入口、没有一轮、没有模型调用，产品就不存在。",
        ),
        "entry-and-boot": t(
            "A process starts at one function. TUI, agent, and tool bridge are constructed after that, not before. "
            "If boot first compiles protobuf or warms an unrelated crate, the first keystroke has no receiver. "
            "Invariant: grok binary starts → runtime is assembled → then the turn loop.",
            "进程必须从某一个入口函数开始跑，TUI、Agent、工具桥才能被构造出来。"
            "入口不是某一个 crate，而是二进制真正执行的那一行。"
            "若入口先去编 protobuf 或初始化无关子系统，用户对着终端发的第一句话没有接收者。"
            "不变量：grok 二进制启动 → 装配运行时 → 才进入对话循环。",
        ),
        "application-entry": t(
            "Without an entrypoint there is no process: nothing is wired, nothing runs. "
            "The rest of the graph exists only because something called it. "
            "Invariant: process starts at the entry → it constructs what it owns → then the main loop.",
            "没有入口就没有进程：没有装配，也就没有运行。"
            "其余模块只因为被入口调用才存在。"
            "不变量：进程从入口进来 → 装配自己负责的对象 → 再把控制权交给主循环。",
        ),
        "agent-loop": t(
            "A turn is valid only if user input is taken into the current turn and the model is called first. "
            "Tool calls happen after the model returns; they cannot run first. "
            "If start_turn ran tools before the model, the turn would be a script, not a conversation. "
            "Invariant: input enters the turn → the model is called → tool calls run and write back.",
            "一轮对话能成立，只有一件事必须发生：用户的输入被收进当前 turn 之后，模型先被调用。"
            "工具调用是模型返回之后的事，不能倒过来。"
            "若 start_turn 之后先跑工具再问模型，这一轮就没有「模型决定」，只有「脚本执行」。"
            "不变量：输入进 turn → 模型被调用 → 如有 tool calls 再执行写回。",
        ),
        "call-flow": t(
            "A system is the sequence of calls, not the set of files. "
            "One turn must run from input to model call in order. "
            "Invariant: input enters the turn → the model is called → side effects follow.",
            "系统是调用的顺序，不是文件的集合。"
            "一轮必须从输入走到模型调用，顺序不能反。"
            "不变量：输入进 turn → 模型被调用 → 副作用在后面。",
        ),
        "runtime-loop": t(
            "A turn is valid only if user input is taken into the current turn and the model is called first. "
            "Tool calls happen after the model returns. "
            "Invariant: input enters the turn → the model is called → tool calls run and write back.",
            "一轮对话能成立，只有一件事必须发生：输入进 turn 之后，模型先被调用。"
            "工具调用是模型返回之后的事。"
            "不变量：输入进 turn → 模型被调用 → 如有 tool calls 再执行写回。",
        ),
        "tool-system": t(
            "The model cannot touch disk or a shell. It can only emit a named tool call; execution stays on this side of the bridge. "
            "Without the bridge, a function call the model returned has nobody to run it. "
            "Invariant: model emits a tool call → the bridge dispatches by name → the result is written back for the model.",
            "模型不能自己碰磁盘或 shell。它只能发出带名字的 tool call；执行权必须在桥的这一侧。"
            "若没有桥，模型返回的函数调用没有人跑，对话就会停在「想做」而不是「做完」。"
            "不变量：模型输出 tool call → 桥按名字分发 → 结果写回再交给模型。",
        ),
        "terminal-ui": t(
            "While the model streams tokens, the terminal must have one place that paints the increment. "
            "Otherwise the user sees a blank screen or a full redraw. Pager is that canvas. "
            "Invariant: a model delta arrives → it is written into the pager → the terminal shows it.",
            "模型流式吐字时，终端必须有一个地方把增量画出来，否则用户看见的是空白或整段刷新。"
            "Pager 就是这块画布。"
            "不变量：模型 delta 到达 → 写入 pager → 终端可见。",
        ),
        "tui-pager": t(
            "While the model streams tokens, the terminal must have one place that paints the increment. "
            "Pager is that canvas. "
            "Invariant: a model delta arrives → it is written into the pager → the terminal shows it.",
            "模型流式吐字时，终端必须有一个地方把增量画出来。"
            "Pager 就是这块画布。"
            "不变量：模型 delta 到达 → 写入 pager → 终端可见。",
        ),
        "context-assembly": t(
            "Before each model call the context window must already hold the system head. "
            "The system head is a rule, not chat history. "
            "If a new rule cannot be written at the window head, the model answers under the old rule. "
            "Invariant: assemble context → system head sits at the window head → then send this turn.",
            "每轮问模型之前，上下文窗口里必须先有系统头。"
            "系统头不是聊天记录，是规则。"
            "若新规则不能写进窗口头部，模型按旧规则回答。"
            "不变量：组上下文 → 系统头在窗口头上 → 再发本轮消息。",
        ),
        "agent-runtime": t(
            "The turn loop needs a runtime that already holds tools, context, and session. "
            "The loop cannot construct those from a keystroke. "
            "Invariant: runtime owns the long-lived pieces → the loop only drives one turn.",
            "一轮循环需要一个已经持有工具、上下文和会话的运行时。"
            "循环不能靠一次按键把这些东西现造出来。"
            "不变量：运行时持有长寿命对象 → 循环只负责推一轮。",
        ),
    }
    if slug in texts:
        return texts[slug]
    return t(
        f"If `{title}` vanished, a user-visible behaviour would break. "
        "Name the invariant that must stay true for a real call to complete — not a folder name.",
        f"如果「{title}」这一层消失，用户能察觉的行为会坏。"
        "说出一次真实调用要完成时必须成立的那句话，不要用目录名回答。",
    )


def pass_gate(concept: Any) -> str:
    """One checkable gate. Not a homework dump."""
    slug = getattr(concept, "slug", "") or ""
    title = getattr(concept, "title", "") or slug
    gates = {
        "project-goal": t(
            "One sentence: if this product left the terminal loop, could it still do what it claims?",
            "一句话：这个产品离开终端循环还能不能完成它声称的事？",
        ),
        "entry-and-boot": t(
            "In the entry function, which appears first — TUI or application state? Point to that line.",
            "入口函数里，TUI 和应用状态谁先出现？指出那一行。",
        ),
        "application-entry": t(
            "If the entry file were empty, what would fail to start? Name that object.",
            "如果入口文件是空的，什么将无法启动？说出那个对象。",
        ),
        "agent-loop": t(
            "If you swapped 'call the model' and 'run tools', would this still be a conversation? Answer from the call order after start_turn.",
            "若把「调模型」和「跑工具」对调，这一轮还会是对话吗？用 start_turn 后的调用顺序回答。",
        ),
        "call-flow": t(
            "If you swapped 'call the model' and 'run tools', would this still be a conversation? Answer from the call order after start_turn.",
            "若把「调模型」和「跑工具」对调，这一轮还会是对话吗？用 start_turn 后的调用顺序回答。",
        ),
        "runtime-loop": t(
            "If you swapped 'call the model' and 'run tools', would this still be a conversation? Answer from the call order after start_turn.",
            "若把「调模型」和「跑工具」对调，这一轮还会是对话吗？用 start_turn 后的调用顺序回答。",
        ),
        "tool-system": t(
            "When the model returns an unknown tool name, does the bridge drop it, error, or call the model again? Point to the dispatch.",
            "模型返回一个不存在的工具名时，桥是丢弃、报错，还是继续调模型？指出分发处。",
        ),
        "terminal-ui": t(
            "When a streaming delta arrives, is the whole page redrawn or is it written into the pager? Point to that site.",
            "流式 delta 到达时，是整页重绘还是写入 pager？指出那一处。",
        ),
        "tui-pager": t(
            "When a streaming delta arrives, is the whole page redrawn or is it written into the pager? Point to that site.",
            "流式 delta 到达时，是整页重绘还是写入 pager？指出那一处。",
        ),
        "context-assembly": t(
            "When the system head updates, is the old head replaced or appended? Name the function.",
            "系统头更新时，旧头是被替换还是追加？指出函数名。",
        ),
        "agent-runtime": t(
            "If the runtime were empty, which object would the turn loop fail to find? Name it.",
            "如果运行时是空的，一轮循环会找不到哪个对象？说出名字。",
        ),
    }
    if slug in gates:
        return gates[slug]
    return t(
        f"Point to the one path:line on this step that proves `{title}` must exist, and say what breaks if that line is gone.",
        f"指出本步那一处 path:line，证明「{title}」必须存在，并说出删掉那一行会坏什么。",
    )


def _is_dummy_symbol(name: str) -> bool:
    n = (name or "").strip().strip("`")
    if not n:
        return True
    if "/" in n or "\\" in n:
        return True
    if n.endswith((".rs", ".py", ".ts", ".js", ".go", ".toml", ".md")):
        return True
    return n.lower() in {"lib.rs", "main.rs", "mod.rs", "src", "crates", "packages", "apps", "root"}


def _source_refs_of(concept: Any) -> list[SourceReference]:
    raw = getattr(concept, "source_references", None) or []
    out: list[SourceReference] = []
    for item in raw:
        if isinstance(item, SourceReference):
            out.append(item)
            continue
        path = ""
        start = end = symbol = commit = None
        if isinstance(item, dict):
            path = (item.get("path") or "").strip()
            start = item.get("start_line")
            end = item.get("end_line")
            symbol = item.get("symbol")
            commit = item.get("commit_sha")
        else:
            path = (getattr(item, "path", None) or "").strip()
            start = getattr(item, "start_line", None)
            end = getattr(item, "end_line", None)
            symbol = getattr(item, "symbol", None)
            commit = getattr(item, "commit_sha", None)
        if not path:
            continue
        try:
            out.append(
                SourceReference(
                    path=path,
                    start_line=start,
                    end_line=end,
                    symbol=symbol,
                    commit_sha=commit,
                )
            )
        except ValueError:
            continue
    return out


def _stamp_definition_line(
    path: str,
    line: int,
    symbol: str,
    file_texts: dict[str, str] | None,
) -> tuple[str, int, str]:
    """Once the file is known, read its text and use the struct/impl/fn line."""
    name = (symbol or "").strip()
    text = _file_text_for(file_texts, path)
    if name and text:
        found = _definition_line_in_text(text, name)
        if found:
            return path, found, name
    return path, line, name


def _format_path_chip(path: str, line: int, symbol: str | None) -> str:
    normalized = path.replace("\\", "/")
    loc = f"{normalized}:{int(line) if line else 1}"
    sym = (symbol or "").strip()
    if sym and not _is_dummy_symbol(sym):
        return f"{loc} {sym}"
    return loc


def is_junk_evidence_path(path: str, *, slug: str = "") -> bool:
    """Cargo.toml / package.json / examples / shell — never the one path chip."""
    raw = (path or "").replace("\\", "/")
    low = raw.lower()
    name = low.rsplit("/", 1)[-1]
    if name in {"readme.md", "readme"}:
        return slug != "project-goal"
    if name in _JUNK_BASENAMES or name.endswith(_JUNK_EXTS):
        return True
    wrapped = f"/{low}/"
    if "/examples/" in wrapped or "/example/" in wrapped or "/fixtures/" in wrapped:
        return True
    return False


def _is_js_trampoline(path: str) -> bool:
    low = path.replace("\\", "/").lower()
    name = low.rsplit("/", 1)[-1]
    if "/npm/" in f"/{low}/":
        return True
    if name.endswith((".js", ".mjs", ".cjs")):
        return True
    if "." not in name and "/bin/" in f"/{low}/":
        return True
    return False


def _is_grok_trampoline(path: str) -> bool:
    if not _is_js_trampoline(path):
        return False
    low = path.replace("\\", "/").lower()
    return any(tok in low for tok in ("xai-grok-pager", "/npm/grok/", "/bin/grok"))


def _blocked_for_slug(path: str, slug: str) -> bool:
    """Slug allow/deny: entry-and-boot is grok/pager, never ptyctl-cli/protoc."""
    raw = (path or "").replace("\\", "/")
    if not raw:
        return True
    low = raw.lower()
    if slug not in _PTY_SLUGS:
        if "ptyctl" in low:
            return True
        for needle in _SLUG_DENY_NEEDLES.get(slug, ()):
            if needle in low:
                return True
    if slug in {"entry-and-boot", "application-entry"}:
        if _is_grok_trampoline(raw):
            return False
        if is_toolchain_boot_file(raw):
            return True
        return not is_entry_boot_file(raw)
    return False


def _prefer_score(path: str, slug: str) -> int:
    low = path.replace("\\", "/").lower()
    for i, tok in enumerate(_SLUG_PREFER_NEEDLES.get(slug, ())):
        if tok in low:
            return 80 - min(i, 12) * 3
    return 0


def _path_matches_hint(path: str, suffix: str) -> bool:
    """True when ``path`` is the hinted file, not a longer lookalike.

    ``lifecycle.rs`` must not match ``session_lifecycle.rs``.
    ``app/agent.rs`` still matches ``.../src/app/agent.rs``.
    """
    if not suffix:
        return False
    norm = path.replace("\\", "/")
    suf = suffix.replace("\\", "/").lstrip("./")
    if not suf:
        return False
    if "/" in suf:
        return norm.endswith("/" + suf) or norm.endswith(suf)
    return norm.rsplit("/", 1)[-1] == suf


def _is_type_name(symbol: str) -> bool:
    return bool(symbol) and symbol[0].isupper() and symbol[0].isascii()


def _narrow_preferred_paths(
    paths: list[str],
    slug: str,
    store: dict[str, str] | None = None,
) -> list[str]:
    needles = _SLUG_PREFER_NEEDLES.get(slug, ())
    if not needles or not paths:
        return paths
    if not store:
        return paths
    if not any(any(tok in k.replace("\\", "/").lower() for tok in needles) for k in store):
        return paths
    matching = [p for p in paths if any(tok in p.replace("\\", "/").lower() for tok in needles)]
    return matching if matching else paths


def _crate_dir(path: str) -> str:
    parts = [p for p in path.replace("\\", "/").split("/") if p]
    for root in ("crates", "packages", "apps"):
        if root not in parts:
            continue
        i = parts.index(root)
        rest = parts[i + 1 :]
        if not rest:
            return root
        if rest[0] == "src":
            return root
        skip = {"src", "examples", "tests", "bins", "bin", "npm"}
        if len(rest) >= 2 and rest[1] in skip:
            return "/".join(parts[: i + 2])
        if len(rest) >= 3 and rest[2] in skip:
            return "/".join(parts[: i + 3])
        return "/".join(parts[: i + 2])
    return "/".join(parts[:-1]) if len(parts) > 1 else ""


def _file_text_for(file_texts: dict[str, str] | None, path: str) -> str:
    if not file_texts or not path:
        return ""
    key = path.replace("\\", "/")
    if key in file_texts:
        return file_texts[key]
    matches = [p for p in file_texts if p.endswith("/" + key) or p == key]
    if len(matches) == 1:
        return file_texts[matches[0]]
    base = key.rsplit("/", 1)[-1]
    if not base or "." not in base:
        return ""
    if base.lower() in {"main.rs", "lib.rs", "mod.rs", "index.ts", "index.js", "index.py"}:
        return ""
    named = [p for p in file_texts if p.replace("\\", "/").rsplit("/", 1)[-1] == base]
    if len(named) == 1:
        return file_texts[named[0]]
    src = [p for p in named if "/src/" in p.replace("\\", "/")]
    if len(src) == 1:
        return file_texts[src[0]]
    return ""


def _first_definition_line(text: str) -> tuple[int, str]:
    for i, line in enumerate((text or "").splitlines(), 1):
        match = re.search(
            r"(?:pub(?:\([^)]*\))?\s+)?(?:async\s+)?(?:fn|struct|enum|trait)\s+"
            r"([A-Za-z_][A-Za-z0-9_]*)",
            line,
        )
        if match and not _is_dummy_symbol(match.group(1)):
            return i, match.group(1)
    return 0, ""


def _line_defines_symbol(src_line: str, symbol: str) -> bool:
    """True only when this line *defines* ``symbol``, not a call or comment."""
    if not src_line or not symbol:
        return False
    stripped = src_line.strip()
    if stripped.startswith(("//", "/*", "*", "#", "//!", "///")):
        return False
    if re.match(r"(?:pub\s+)?use\b", stripped):
        return False
    if re.search(_DEFN_KW + re.escape(symbol) + r"\b", src_line):
        return True
    if re.search(r"\b(?:struct|enum|trait|type|class)\s+" + re.escape(symbol) + r"\b", src_line):
        return True
    if re.search(r"\bimpl\b.+\bfor\s+" + re.escape(symbol) + r"\b", src_line):
        return True
    return bool(re.search(r"\bimpl(?:\s*<[^>]*>)?\s+" + re.escape(symbol) + r"\b", src_line))


def _definition_line_in_text(text: str, symbol: str) -> int:
    if not text or not symbol:
        return 0
    for i, line in enumerate(text.splitlines(), 1):
        if _line_defines_symbol(line, symbol):
            return i
    return 0


def _occurrence_line_in_text(text: str, symbol: str) -> int:
    """First non-comment source line that names ``symbol``, else 0."""
    name = (symbol or "").strip()
    if not text or len(name) < 2:
        return 0
    pat = re.compile(r"(?<![A-Za-z0-9_])" + re.escape(name) + r"(?![A-Za-z0-9_])")
    for i, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith(("//", "/*", "*", "#")):
            continue
        if pat.search(line):
            return i
    return 0


def _best_symbol_line(text: str, symbol: str) -> tuple[int, bool]:
    """Return (line, is_definition). Line 0 means not found."""
    defn = _definition_line_in_text(text, symbol)
    if defn:
        return defn, True
    occ = _occurrence_line_in_text(text, symbol)
    return occ, False


def _is_production_src(path: str, *, slug: str = "") -> bool:
    norm = (path or "").replace("\\", "/")
    if not norm or is_junk_evidence_path(norm, slug=slug) or _is_js_trampoline(norm):
        return False
    if not norm.lower().endswith(_SRC_EXT):
        return False
    wrapped = f"/{norm.lower()}/"
    if "/examples/" in wrapped or "/example/" in wrapped or "/fixtures/" in wrapped:
        return False
    if "/tests/" in wrapped or "/test/" in wrapped:
        return False
    return True


def _pick_definition_in_store(
    file_texts: dict[str, str],
    symbol: str,
    slug: str,
    suffixes: tuple[str, ...],
) -> tuple[str, int] | None:
    """First production ``*.rs`` (or py/go) that defines ``symbol``.

    Searches the whole scan store. The concept ref's crate is not a filter —
    ``start_turn`` lives in ``xai-grok-pager/src/app/agent.rs``, not in the
    ``xai-grok-agent/src/agent.rs`` topic ref.
    """
    name = (symbol or "").strip()
    if not file_texts or len(name) < 2:
        return None
    hits: list[tuple[int, str, int]] = []
    for path, text in file_texts.items():
        norm = path.replace("\\", "/")
        if not _is_production_src(norm, slug=slug) or _blocked_for_slug(norm, slug):
            continue
        defn, is_defn = _best_symbol_line(text, name)
        if not defn or not is_defn:
            continue
        score = 50 if norm.lower().endswith(".rs") else 20
        score += 120
        if "/src/" in f"/{norm.lower()}/":
            score += 10
        score += _prefer_score(norm, slug)
        for i, suffix in enumerate(suffixes):
            if _path_matches_hint(norm, suffix):
                score += 40 - min(i, 12)
                break
        hits.append((score, norm, defn))
    if not hits:
        return None
    preferred = [
        item
        for item in hits
        if any(tok in item[1].lower() for tok in _SLUG_PREFER_NEEDLES.get(slug, ()))
    ]
    ranked = preferred or hits
    ranked.sort(key=lambda item: (-item[0], item[1]))
    _score, path, line = ranked[0]
    return path, line


def _candidate_paths(
    refs: list[SourceReference],
    slug: str,
    file_texts: dict[str, str] | None,
) -> list[str]:
    seen: list[str] = []

    def add(raw: str) -> None:
        path = (raw or "").replace("\\", "/")
        if not path or path in seen:
            return
        if is_junk_evidence_path(path, slug=slug):
            return
        if _blocked_for_slug(path, slug):
            return
        seen.append(path)

    for ref in refs:
        add(ref.path)
    suffixes = _EVIDENCE_HINTS.get(slug, ((), ""))[0]
    crates = {_crate_dir(ref.path) for ref in refs if ref.path}
    if file_texts:
        for path in file_texts:
            norm = path.replace("\\", "/")
            if is_junk_evidence_path(norm, slug=slug):
                continue
            if any(_path_matches_hint(norm, suffix) for suffix in suffixes):
                add(norm)
                continue
            crate = _crate_dir(norm)
            if crate and crate in crates and norm.endswith(_SRC_EXT):
                add(norm)
    for fallback in _FALLBACK_FILES.get(slug, ()):
        add(fallback)
    return seen


def _score_path(
    path: str,
    *,
    slug: str,
    symbol: str,
    suffixes: tuple[str, ...],
    refs: list[SourceReference],
    file_texts: dict[str, str] | None,
) -> tuple[int, int, str]:
    """Return (score, line, symbol_to_emit)."""
    score = 0
    line = 1
    use_sym = symbol
    in_refs = False
    for ref in refs:
        if ref.path.replace("\\", "/") != path:
            continue
        in_refs = True
        if ref.start_line and ref.start_line > 1:
            line = ref.start_line
            score += 8
    if path.endswith(".rs"):
        score += 50
    elif path.endswith((".py", ".go")):
        score += 25
    if _is_js_trampoline(path) and not _is_grok_trampoline(path):
        score -= 50
    elif _is_grok_trampoline(path):
        score -= 10
    low = f"/{path.lower()}/"
    if "/tests/" in low or "/test/" in low:
        score -= 25
    score += _prefer_score(path, slug)
    for i, suffix in enumerate(suffixes):
        if _path_matches_hint(path, suffix):
            score += 40 - min(i, 12)
            break
    text = _file_text_for(file_texts, path)
    if not text and not in_refs:
        score -= 80
    if text and symbol:
        line_no, is_defn = _best_symbol_line(text, symbol)
        if line_no and is_defn:
            line = line_no
            score += 120
        elif line_no and not _is_type_name(symbol):
            line = line_no
            score += 40
        else:
            # Use/call site of a type, or the file never names the hint.
            use_sym = ""
            score -= 50
    elif text and not symbol:
        found_line, found_sym = _first_definition_line(text)
        if found_line > 1:
            line = found_line
            use_sym = found_sym
            score += 15
    return score, line, use_sym


def _pick_entry_or_weak(
    store: dict[str, str],
    refs: list[SourceReference],
    slug: str,
    suffixes: tuple[str, ...],
    symbol: str,
) -> tuple[str, int, str] | None:
    """Grok/pager boot for entry-and-boot; never the first random ``fn main``."""
    candidates = _candidate_paths(refs, slug, store)
    if slug in {"entry-and-boot", "application-entry"}:
        for path in store:
            norm = path.replace("\\", "/")
            if _blocked_for_slug(norm, slug) or is_junk_evidence_path(norm, slug=slug):
                continue
            if norm in candidates:
                continue
            if is_entry_boot_file(norm) or _is_grok_trampoline(norm):
                candidates.append(norm)
        names = _ENTRY_SYMBOLS
    else:
        names = (symbol,) if symbol else ()

    scored: list[tuple[int, str, int, str]] = []
    for path in candidates:
        if _blocked_for_slug(path, slug) or is_junk_evidence_path(path, slug=slug):
            continue
        if _is_js_trampoline(path) and not _is_grok_trampoline(path):
            continue
        text = _file_text_for(store, path)
        if _is_grok_trampoline(path):
            scored.append((15 + _prefer_score(path, slug), path, 1, ""))
            continue
        if not text:
            continue
        use_sym = ""
        line = 0
        for fn in names:
            found = _definition_line_in_text(text, fn)
            if found:
                line = found
                use_sym = fn
                break
        if not line:
            continue
        score = 50 if path.endswith(".rs") else 10
        score += _prefer_score(path, slug)
        if use_sym == "main":
            score += 20
        if path.endswith("main.rs") or path.endswith("bin/grok.rs"):
            score += 15
        for i, suffix in enumerate(suffixes):
            if _path_matches_hint(path, suffix):
                score += 12 - min(i, 8)
                break
        scored.append((score, path, line, use_sym))

    if not scored:
        return None
    rust = [item for item in scored if item[1].endswith(_SRC_EXT)]
    pool = rust if rust else scored
    preferred_paths = _narrow_preferred_paths([item[1] for item in pool], slug, store)
    preferred = [item for item in pool if item[1] in set(preferred_paths)]
    pool = preferred or pool
    pool.sort(key=lambda item: (-item[0], item[1]))
    _score, path, line, use_sym = pool[0]
    return path, line, use_sym


def path_evidence_chip(
    concept: Any,
    file_texts: dict[str, str] | None = None,
) -> str | None:
    """Exactly one ``path:line Symbol`` chip that proves the principle."""
    slug = getattr(concept, "slug", "") or ""
    refs = _source_refs_of(concept)
    suffixes, hint_sym = _EVIDENCE_HINTS.get(slug, ((), ""))
    symbol = hint_sym.strip() if hint_sym else ""

    if slug == "project-goal":
        for ref in refs:
            path = ref.path.replace("\\", "/")
            name = path.rsplit("/", 1)[-1].lower()
            if name in {"readme.md", "readme"}:
                return _format_path_chip(path, ref.start_line or 1, "")
        return _format_path_chip("README.md", 1, "")

    store = file_texts or {}
    if not store:
        logger.debug("learning-path evidence: empty scan store for slug=%s", slug)

    # Definition-first: if the hint is not in the topic ref, search every
    # production *.rs in version_files. Weak names like ``main`` stay on
    # slug-allowed files (grok/pager boot, never ptyctl-cli).
    if symbol and store and symbol.lower() not in _WEAK_SYMBOLS:
        hit = _pick_definition_in_store(store, symbol, slug, suffixes)
        if hit:
            path, line, use_sym = _stamp_definition_line(hit[0], hit[1], symbol, store)
            return _format_path_chip(path, line, use_sym)
        logger.info(
            "learning-path evidence: no production definition of %s for slug=%s (%d files)",
            symbol,
            slug,
            len(store),
        )
    elif symbol and store and symbol.lower() in _WEAK_SYMBOLS:
        hit = _pick_entry_or_weak(store, refs, slug, suffixes, symbol)
        if hit:
            path, line, use_sym = _stamp_definition_line(hit[0], hit[1], hit[2], store)
            return _format_path_chip(path, line, use_sym)

    candidates = _candidate_paths(refs, slug, file_texts)
    scored: list[tuple[int, str, int, str]] = []
    for path in candidates:
        if is_junk_evidence_path(path, slug=slug) or _blocked_for_slug(path, slug):
            continue
        score, line, use_sym = _score_path(
            path,
            slug=slug,
            symbol=symbol,
            suffixes=suffixes,
            refs=refs,
            file_texts=file_texts,
        )
        scored.append((score, path, line, use_sym))

    if not scored:
        return None
    preferred_paths = _narrow_preferred_paths([item[1] for item in scored], slug, file_texts)
    preferred = [item for item in scored if item[1] in set(preferred_paths)]
    pool = preferred or scored
    rust = [item for item in pool if item[1].endswith(_SRC_EXT)]
    if rust:
        pool = rust
    pool.sort(key=lambda item: (-item[0], item[1]))
    _score, path, line, use_sym = pool[0]
    if _is_js_trampoline(path) and not _is_grok_trampoline(path):
        rust_hit = next((item for item in pool if item[1].endswith(_SRC_EXT)), None)
        if rust_hit is None:
            return None
        _score, path, line, use_sym = rust_hit
    elif _is_grok_trampoline(path):
        rust_hit = next(
            (
                item
                for item in pool
                if item[1].endswith(_SRC_EXT) and not _blocked_for_slug(item[1], slug)
            ),
            None,
        )
        if rust_hit is not None:
            _score, path, line, use_sym = rust_hit
    path, line, use_sym = _stamp_definition_line(path, line, use_sym, store)
    return _format_path_chip(path, line, use_sym)


_WIKI_PILL_RE = re.compile(
    r"^([A-Za-z0-9_./\-]+?\.[A-Za-z0-9]+)(?::(\d+)(?:-\d+)?)?(?:[ \t]+(.+))?$"
)
_WIKI_KEY_TYPE_HEADING_RE = re.compile(r"(?im)^#{2,3}[ \t]+(关键类型|Key types)\b")


def resolve_symbol_definition(
    file_texts: dict[str, str],
    symbol: str,
    *,
    prefer_path: str = "",
) -> tuple[str, int] | None:
    """Store-wide struct/impl/fn of ``symbol``. Skip toml/json/sh. No use-sites."""
    name = (symbol or "").strip()
    if not file_texts or len(name) < 2:
        return None
    prefer = (prefer_path or "").replace("\\", "/")
    hits: list[tuple[int, str, int]] = []
    for path, text in file_texts.items():
        norm = path.replace("\\", "/")
        if is_junk_evidence_path(norm) or not _is_production_src(norm):
            continue
        line = _definition_line_in_text(text, name)
        if not line:
            continue
        score = 50 if norm.lower().endswith(".rs") else 20
        if prefer and (norm == prefer or norm.endswith("/" + prefer)):
            score += 80
        if "/src/" in f"/{norm.lower()}/":
            score += 10
        hits.append((score, norm, line))
    if not hits:
        return None
    hits.sort(key=lambda item: (-item[0], item[1]))
    _score, path, line = hits[0]
    return path, line


def fill_wiki_key_type_lines(content: str, file_texts: dict[str, str] | None) -> str:
    """GET: `` `path Symbol` `` → `` `path:line Symbol` `` from the scan store.

    Only ``## 关键类型``. Overview 核心子系统 path-only pills stay as-is.
    """
    if not content or not file_texts or "`" not in content:
        return content

    def rewrite_section(section: str) -> str:
        def pill_repl(match: re.Match[str]) -> str:
            inner = (match.group(1) or "").strip()
            parsed = _WIKI_PILL_RE.match(inner)
            if not parsed:
                return match.group(0)
            path = (parsed.group(1) or "").strip()
            line = (parsed.group(2) or "").strip()
            symbol = (parsed.group(3) or "").strip()
            if not path or not symbol or _is_dummy_symbol(symbol):
                return match.group(0)
            if line and line != "1":
                return match.group(0)
            if is_junk_evidence_path(path):
                return match.group(0)
            hit = resolve_symbol_definition(file_texts, symbol, prefer_path=path)
            if not hit:
                return match.group(0)
            new_path, new_line = hit
            if line == "1" and new_line <= 1:
                return match.group(0)
            return f"`{new_path}:{new_line} {symbol}`"

        return re.sub(r"`([^`]+)`", pill_repl, section)

    parts = re.split(r"(?m)(?=^## )", content)
    out: list[str] = []
    for part in parts:
        first, _, _rest = part.partition("\n")
        if _WIKI_KEY_TYPE_HEADING_RE.match(first):
            out.append(rewrite_section(part))
        else:
            out.append(part)
    return "".join(out)


_ASK_QUESTION_RULES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("entry-and-boot", "application-entry", "入口", "boot", "connect"), "这个项目的入口在哪，connect 之后谁接手？"),
    (("agent-loop", "start_turn", "agent loop", "一轮"), "一轮对话里 start_turn 之后谁调模型？"),
    (("acp", "protocol", "协议"), "ACP 会话是在哪建立的，connect 做了什么？"),
    (("pager", "terminal-ui", "tui-pager", "终端"), "Pager 把模型流式输出写进哪块缓冲区？"),
    (("tool-system", "tool_bridge", "toolbridge", "工具"), "模型返回 tool call 之后谁按名字执行？"),
)
_ASK_HOST_LEFTOVERS = ("复习调度", "复训调度", "FSRS", "依赖图是怎么构建")


def suggested_ask_questions(pages: list[Any] | None) -> list[str]:
    """Three Chinese questions grounded in THIS wiki. Never host-product leftovers."""
    items = list(pages or [])
    if not items:
        return []
    blobs: list[str] = []
    titles: list[str] = []
    for page in items:
        if isinstance(page, dict):
            pid = str(page.get("id") or "")
            title = str(page.get("title") or "")
            body = str(page.get("content") or "")[:800]
        else:
            pid = str(getattr(page, "id", "") or "")
            title = str(getattr(page, "title", "") or "")
            body = str(getattr(page, "content", "") or "")[:800]
        titles.append(title)
        blobs.append(f"{pid} {title} {body}".lower())
    hay = "\n".join(blobs)
    out: list[str] = []
    for needles, question in _ASK_QUESTION_RULES:
        if any(tok.lower() in hay for tok in needles):
            if question not in out:
                out.append(question)
        if len(out) >= 3:
            break
    if len(out) < 3:
        for title in titles:
            title = (title or "").strip()
            if not title or title in {"概述", "Overview", "架构概览", "Architecture"}:
                continue
            q = f"「{title}」在链路里承担什么？"
            if q not in out:
                out.append(q)
            if len(out) >= 3:
                break
    return [q for q in out[:3] if not any(bad in q for bad in _ASK_HOST_LEFTOVERS)]


def path_worksheet(
    concept: Any,
    project_name: str = "",
    file_texts: dict[str, str] | None = None,
) -> str:
    """Learning-path page only. Never mixed into the reading wiki."""
    title = getattr(concept, "title", None) or getattr(concept, "slug", "") or ""
    slug = getattr(concept, "slug", "") or ""
    task = step_task_for_slug(slug, title)
    principles = path_principles(concept, project_name)
    chip = path_evidence_chip(concept, file_texts=file_texts)
    gate = pass_gate(concept)
    evidence_body = (
        f"`{chip}`"
        if chip
        else t(
            "This step has no source line. Pass by stating the invariant in one sentence.",
            "这一步不靠源码行，过关看你能不能一句话讲清不变量。",
        )
    )
    parts = [
        f"# {title}",
        "",
        f"## {t('What this step asks of you', '本步要你干什么')}",
        "",
        task,
        "",
        f"## {t('Back to first principles', '先回到原理')}",
        "",
        principles,
        "",
        f"## {t('Look at this evidence only', '只看这一处证据')}",
        "",
        evidence_body,
        "",
        f"## {t('Pass', '过关')}",
        "",
        gate,
        "",
    ]
    return "\n".join(parts)


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
