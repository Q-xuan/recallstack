"""First-principles learning contract: what each path step is *for*."""

from __future__ import annotations

import logging
import re
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Iterator

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

CORE_PATH_CAP = 10

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

# Trunk → hard turns → UI. Crate-inventory leaves stay off the path.
_PATH_TRUNK: tuple[str, ...] = (
    "project-goal",
    "entry-and-boot",
    "application-entry",
    "agent-loop",
    "call-flow",
    "runtime-loop",
    "tool-system",
    "session-lifecycle",
    "agent-runtime",
    "acp-protocol",
    "context-assembly",
    "terminal-ui",
    "tui-pager",
    "conversation-store",
    "system-prompt",
)
_SHALLOW_PATH_LEAVES = frozenset(
    {
        "codebase-graph",
        "pty-control",
        "codegen",
        "headless-modes",
        "subagent-scheduling",
    }
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
    "session-lifecycle": (("session_lifecycle.rs", "lifecycle.rs"), "cancel"),
    "acp-protocol": (("channel.rs", "acp/mod.rs"), "AcpChannel"),
    "system-prompt": (("agents_md.rs", "prompt.rs", "system.rs"), ""),
    "project-goal": (("agent.rs", "app.rs", "turn.rs"), "start_turn"),
}

# Hint paths tried only when that exact key exists in version_files.
# Never emit these if the store is loaded and the key is absent.
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
    "session-lifecycle": (
        "crates/codegen/xai-agent-lifecycle/src/lib.rs",
        "crates/codegen/xai-agent-lifecycle/src/session_lifecycle.rs",
    ),
    "acp-protocol": (
        "crates/codegen/xai-grok-agent/src/acp/mod.rs",
    ),
    "system-prompt": ("crates/codegen/xai-grok-agent/src/prompt/agents_md.rs",),
    "project-goal": (
        "crates/codegen/xai-grok-pager/src/app/agent.rs",
        "crates/codegen/xai-grok-agent/src/turn.rs",
    ),
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
_CHIP_DENY_SYMBOLS = frozenset({"xor_encrypt", "xor_decrypt"})
_LIFECYCLE_BASENAMES = (
    "runtime.rs",
    "lifecycle.rs",
    "local.rs",
    "send.rs",
    "contributors.rs",
    "lib.rs",
)
_ENTRY_SYMBOLS = ("main", "connect", "boot")
_PTY_SLUGS = frozenset({"pty-control", "pty"})
_SRC_EXT = (".rs", ".py", ".go", ".ts", ".tsx")
_DEFN_KW = (
    r"(?:pub(?:\([^)]*\))?\s+)?"
    r"(?:export\s+)?"
    r"(?:default\s+)?"
    r"(?:async\s+)?"
    r"(?:abstract\s+)?"
    r"(?:fn|struct|enum|trait|type|class|def|function|interface|impl(?:\s*<[^>]*>)?)\s+"
)
_CRATE_ROOT_NAMES = frozenset(
    {
        "lib.rs",
        "mod.rs",
        "lib.py",
        "mod.py",
        "__init__.py",
        "index.ts",
        "index.tsx",
        "index.js",
        "cargo.toml",
        "package.json",
        "readme.md",
        "readme",
    }
)
_FIRST_DEFN_RE = re.compile(
    r"(?:pub(?:\([^)]*\))?\s+)?"
    r"(?:export\s+)?"
    r"(?:default\s+)?"
    r"(?:async\s+)?"
    r"(?:abstract\s+)?"
    r"(?:fn|struct|enum|trait|type|class|def|function|interface)\s+"
    r"([A-Za-z_][A-Za-z0-9_]*)"
)
_REEXPORT_RE = re.compile(
    r"pub\s+use\s+(?:[\w:]+::)+([A-Za-z_][A-Za-z0-9_]*)"
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
    "agent-runtime": ("ptyctl", "protoc", "/scripts/", "encrypt", "xor_encrypt"),
    "session-lifecycle": ("ptyctl", "protoc", "/scripts/", "encrypt", "xor_encrypt"),
    "acp-protocol": ("ptyctl", "protoc", "/scripts/", "encrypt", "xor_encrypt"),
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
    "session-lifecycle": ("xai-agent-lifecycle", "session_lifecycle"),
    "acp-protocol": ("acp", "channel", "xai-grok-agent"),
    "system-prompt": ("xai-grok-agent", "agents_md", "/prompt/"),
    "project-goal": ("xai-grok-pager", "xai-grok-agent", "crates/tui"),
}

_SOURCE_CHIP_RE = re.compile(
    r"(?i)^[\w./\-]+(?:\.[A-Za-z0-9]+)+(?::\d+(?:-\d+)?)?(?:[ \t]+[A-Za-z_][A-Za-z0-9_]*)?$"
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
    "概述",
    "Overview",
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
    "架构",
    "Architecture",
    "它在系统里的位置",
    "Where it sits",
}
_FLOW_HEADINGS = {
    "调用链",
    "Call path",
    "一次调用怎么走",
    "How a call runs",
}
_TYPE_ROLE_HEADINGS = {
    "关键类型",
    "Key types",
    "关键类型在链路上的职责",
    "Key types and their roles",
}
_IMPL_HEADINGS = {
    "实现",
    "Implementation",
    "实现要点",
    "Implementation details",
}
_BOUNDARY_HEADINGS = {
    "边界",
    "Boundaries",
    "边界条件",
    "Boundary conditions",
}
_NOT_THIS_HEADINGS = {
    "不是什么",
    "What this is not",
}
_WATERY_HANDBOOK_RE = re.compile(
    r"缺了它哪条能力会断|"
    r"what breaks if it disappears|"
    r"用户能察觉的行为会坏|"
    r"a user-visible behaviour would break|"
    r"出现在上文链路中的角色|"
    r"a role on the path described above|"
    r"从证据说出调用它的和它调用的|"
    r"Name the callers and callees from the evidence",
    re.I,
)
_TIPS_HEADINGS = {
    "术语",
    "Terms",
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
        "You own the trunk: how the process starts, how one turn runs, then the hard "
        "turns — tool write-back, cancel, ACP vs TUI. You sign off each layer: if it "
        "vanished, which user-visible thing dies?",
        "你要能指出进程怎么进、一轮怎么转，以及硬弯：工具写回、取消、ACP 和 TUI 两扇门。"
        "每一层你签字：这一层不存在，用户能看见的哪件事会死。",
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


def is_shallow_path_leaf(slug: str) -> bool:
    """Crate-inventory / aux topics — wiki is fine, not a path step."""
    return (slug or "") in _SHALLOW_PATH_LEAVES


def is_core_path_concept(concept: ConceptDraft) -> bool:
    """Path nodes are real concepts from this repo, not folder inventory."""
    if is_filler_concept(concept):
        return False
    if concept.slug == "getting-started":
        return False
    wiki_id = getattr(concept, "wiki_page_id", None)
    if is_web_filler_path_slug(concept.slug, wiki_id):
        return False
    if is_shallow_path_leaf(concept.slug):
        return False
    return True


def is_generic_reason(reason: str) -> bool:
    return not (reason or "").strip() or bool(_GENERIC_REASON_RE.search(reason))


def step_task_for_slug(slug: str, title: str = "") -> str:
    """Concrete action for this step. Stored on the path node as ``reason``."""
    tasks = {
        "project-goal": t(
            "You own this: on the evidence line, prove whether the user lives in a terminal turn or a crate list. Name which of entry / one turn / start_turn would make Enter produce no answer — then sign off.",
            "你负责：对着证据那一行，证明用户被放在终端对话里还是 crate 清单里。说出入口、一轮循环、start_turn 里少了哪一层回车没回答，并签字。",
        ),
        "entry-and-boot": t(
            "You own this: rule out “both are entry”. Point to who receives control after connect, and who receives it after the TUI door — then sign off.",
            "你负责：排除「都是入口」。指出 connect 之后谁接手、TUI 那扇门交给谁，并签字。",
        ),
        "application-entry": t(
            "You own this: open the entrypoint and name the first three calls after the process starts — not a crate name — then sign off.",
            "你负责：打开入口文件，指出进程启动后最先调用的三步（不是某个 crate 的名字），并签字。",
        ),
        "agent-loop": t(
            "You own this: open the evidence and point to who calls the model after start_turn (not tools first). Write that function name and sign off.",
            "你负责：打开证据，指出谁在 start_turn 之后调模型（不是先跑工具）。写出那个函数名，并签字。",
        ),
        "call-flow": t(
            "You own this: follow one turn and name who runs between input entering the turn and the model being called — then sign off.",
            "你负责：顺着一轮对话，指出输入进 turn 之后到模型被调用之间经过谁，并签字。",
        ),
        "runtime-loop": t(
            "You own this: open the evidence and point to who calls the model after start_turn (not tools first). Write that function name and sign off.",
            "你负责：打开证据，指出谁在 start_turn 之后调模型（不是先跑工具）。写出那个函数名，并签字。",
        ),
        "tool-system": t(
            "You own this: point to who writes the tool result back and calls the model again after start_turn. Name the function — not “the tool layer” — and sign off.",
            "你负责：指出 start_turn 之后谁把 tool 结果写回再调模型。写出函数名，不要说「工具层」，并签字。",
        ),
        "terminal-ui": t(
            "You own this: open Pager and point to which buffer streaming output is written into. Name the field or function and sign off.",
            "你负责：打开 Pager，指出模型流式输出时字写进哪一块缓冲区。写出字段或函数名，并签字。",
        ),
        "tui-pager": t(
            "You own this: open Pager and point to which buffer streaming output is written into. Name the field or function and sign off.",
            "你负责：打开 Pager，指出模型流式输出时字写进哪一块缓冲区。写出字段或函数名，并签字。",
        ),
        "context-assembly": t(
            "You own this: open replace_or_insert_system_head and prove whether the system head is written at the window head or appended after the user — then sign off.",
            "你负责：打开 replace_or_insert_system_head，证明系统头是写进窗口头还是拼在用户消息后面，并签字。",
        ),
        "agent-runtime": t(
            "You own this: point to who stops an in-flight model call when the user cancels. If that stop never fires, name what the terminal still shows — then sign off.",
            "你负责：指出用户取消一轮时谁把还在飞的模型调用停掉。若停不掉，说出终端上会留下什么，并签字。",
        ),
        "session-lifecycle": t(
            "You own this: point to who stops an in-flight model call when the user cancels. If that stop never fires, name what the terminal still shows — then sign off.",
            "你负责：指出用户取消一轮时谁把还在飞的模型调用停掉。若停不掉，说出终端上会留下什么，并签字。",
        ),
        "acp-protocol": t(
            "You own this: prove whether ACP connect and the TUI entry are two doors or one road. After connect, who holds the session? Sign off.",
            "你负责：证明 ACP 的 connect 和 TUI 入口是两扇门还是同一条路。connect 之后谁持有会话，并签字。",
        ),
        "configuration": t(
            "You own this: find where config enters runtime and name one behaviour it changes — then sign off.",
            "你负责：找出配置从哪进入运行时，指出它改变的一个行为，并签字。",
        ),
        "request-routing": t(
            "You own this: trace one request and name the file that receives it and the function that handles it — then sign off.",
            "你负责：顺着一个外部请求往里追，指出哪个文件接住它、哪个函数处理它，并签字。",
        ),
        "authentication": t(
            "You own this: point to where identity is checked and what happens if it fails — then sign off.",
            "你负责：指出身份在哪被检查，以及失败时会发生什么，并签字。",
        ),
        "data-persistence": t(
            "You own this: name the object that is written or read, and the function that does it — then sign off.",
            "你负责：说出被写入或读出的对象，以及做这件事的函数，并签字。",
        ),
        "caching": t(
            "You own this: say what is cached and what becomes wrong if the cache is stale — then sign off.",
            "你负责：说出缓存了什么，以及缓存过期时会错在哪，并签字。",
        ),
        "error-handling": t(
            "You own this: name one failure path and where it is caught or returned — then sign off.",
            "你负责：指出一条失败路径，以及它在哪里被接住或返回，并签字。",
        ),
        "background-tasks": t(
            "You own this: find one async/job path and say what side effect it performs — then sign off.",
            "你负责：找出一条异步/任务路径，说出它产生的副作用，并签字。",
        ),
        "testing-structure": t(
            "You own this: open one test and say which behaviour it is locking down — then sign off.",
            "你负责：打开一个测试，说出它锁住的是哪段行为，并签字。",
        ),
        "module-boundaries": t(
            "You own this: name two modules and the one responsibility that must not leak across them — then sign off.",
            "你负责：指出两个模块，以及绝不能漏过去的那条职责边界，并签字。",
        ),
    }
    if slug in tasks:
        return tasks[slug]
    shown = title or slug
    return t(
        f"You own this: open the evidence and point to the step `{shown}` must perform on a real call — not a directory name — then sign off.",
        f"你负责：打开证据，指出「{shown}」在一次真实调用里必须发生的那一步（不要用目录名回答），并签字。",
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
        f"`{concept.title}` is a role on the call path. State what it owns from the "
        "evidence, not from the directory name.",
        f"「{concept.title}」是调用链上的角色。职责以源码证据为准，不以目录名为准。",
    )


def path_principles(concept: Any, project_name: str = "") -> str:
    """4–7 sentences: invariant, counterfactual, rejected analogy. Not a file list."""
    slug = getattr(concept, "slug", "") or ""
    title = getattr(concept, "title", "") or slug
    name = project_name or title
    texts = {
        "project-goal": t(
            f"{name} is a product that must finish one terminal turn, not a crate inventory. "
            "Invariant: entry, one turn, and a model call all exist, or Enter produces no answer. "
            "If this were false, the user hits Enter and the screen never shows a model reply — only files that compile. "
            "Do not treat this as “read the README and you understand the product”, and do not treat the repo as a crate list you can shuffle. "
            "The first README line pins the product shape. Directories are a consequence of someone wiring entry to a turn to a model.",
            f"{name} 首先是一个能在终端里跑完一轮对话的产品，不是 crate 目录。"
            "不变量：入口、一轮循环、模型调用三层都在，用户回车才有回答。"
            "若这不成立，用户对着终端按下回车，屏幕上不会出现模型回复，只剩一堆可以编译的文件。"
            "不要把这当成「读完 README 就等于懂了产品」，也不要把仓库当成可以随便拆开的 crate 清单。"
            "README 第一行钉住的是产品形态。目录是结果：有人从入口把一轮接上模型，产品才存在。",
        ),
        "entry-and-boot": t(
            "A process enters through one door: the TUI loop or ACP connect. Those doors must not each build a private runtime. "
            "Invariant: grok binary starts → one door is chosen → runtime is assembled → then the turn loop. "
            "If this were false, the first sentence from the IDE or the terminal has no receiver, or two states step on each other. "
            "This is not “find a file named main”. Entry is a hand-off of control, not a crate name. "
            "If boot compiles protobuf or warms an unrelated CLI first, the first keystroke still has no receiver. "
            "TUI and ACP are two doors, not two names for the same road.",
            "进程必须从一扇门进来：TUI 主循环或 ACP 的 connect。两扇门不能各造一套运行时。"
            "不变量：grok 二进制启动 → 选定一扇门 → 装配运行时 → 才进入对话。"
            "若这不成立，用户在 IDE 里走 ACP、在终端里走 TUI，第一句话没有接收者，或两套状态互相踩。"
            "不要把这当成「找一个叫 main 的文件就完了」。入口是控制权交接，不是 crate 名。"
            "若入口先去编 protobuf 或拉起无关 CLI，用户的第一句仍然没人接。"
            "TUI 和 ACP 是两扇门，不是同一条路的两个别名。",
        ),
        "application-entry": t(
            "Without an entrypoint there is no process: nothing is wired, nothing runs. "
            "Invariant: the process starts at the entry → it constructs what it owns → then the main loop. "
            "If this were false, every later module exists on disk and still never runs. "
            "This is not “the src/ folder is the entry”. The rest of the graph exists only because something called it.",
            "没有入口就没有进程：没有装配，也就没有运行。"
            "不变量：进程从入口进来 → 装配自己负责的对象 → 再把控制权交给主循环。"
            "若这不成立，后面每个模块都在磁盘上，却没有人调用它们。"
            "不要把这当成「src 目录就是入口」。其余模块只因为被入口调用才存在。",
        ),
        "agent-loop": t(
            "A turn is valid only after user input enters the current turn and the model is called first. "
            "Invariant: input enters the turn → the model is called → tool calls run, write back, then the model is called again. "
            "If this were false, the user does not see a model decide — they see a script finish tools, and the turn becomes a batch job. "
            "This is not “a while True around the model”. The loop is a turn state machine: cancel, write-back, and the next model call hang on this turn. "
            "Tools cannot run before the model, or there is no model decision. "
            "start_turn is the gate of this turn, not another name for painting the UI.",
            "一轮对话能成立，只有输入进当前 turn 之后模型先被调用。"
            "不变量：输入进 turn → 模型被调用 → 如有 tool calls 再执行、写回、再问模型。"
            "若这不成立，用户看见的不是「模型在决定」，而是脚本自己跑完工具，对话变成批处理。"
            "不要把这当成「一个 while True 围着模型转」。循环不是空转，是 turn 的状态机，取消、写回、再问都挂在这一轮上。"
            "工具不能抢在模型前面跑，否则没有「模型决定」。"
            "start_turn 是这一轮的闸门，不是画 UI 的别名。",
        ),
        "call-flow": t(
            "A system is the sequence of calls, not the set of files. "
            "Invariant: input enters the turn → the model is called → side effects follow. "
            "If this were false, a folder named loop still would not produce an answer. "
            "This is not “list the crates in order”. One turn must run from input to model call, and the order cannot flip.",
            "系统是调用的顺序，不是文件的集合。"
            "不变量：输入进 turn → 模型被调用 → 副作用在后面。"
            "若这不成立，就算有一个叫 loop 的目录，用户也等不到回答。"
            "不要把这当成「按 crate 名单走一遍」。一轮必须从输入走到模型调用，顺序不能反。",
        ),
        "runtime-loop": t(
            "A turn is valid only after input enters the current turn and the model is called first. "
            "Invariant: input enters the turn → the model is called → tool calls run, write back, then the model is called again. "
            "If this were false, the turn is a script, not a conversation. "
            "This is not “a while True around the model”.",
            "一轮对话能成立，只有输入进 turn 之后模型先被调用。"
            "不变量：输入进 turn → 模型被调用 → 如有 tool calls 再执行、写回、再问模型。"
            "若这不成立，这一轮就没有「模型决定」，只有脚本。"
            "不要把这当成「一个 while True 围着模型转」。",
        ),
        "tool-system": t(
            "The model cannot touch disk or a shell. It can only emit a named tool call; execution stays on this side of the bridge. "
            "Invariant: the model emits a tool call → the bridge runs it by name → the result is written back on the same turn → the model is called again. "
            "If this were false, the tool finished and the next model call never sees the result — the user watches the model pretend or hang. "
            "This is not “there is a tools crate”. The missing piece is write-back, not a directory. "
            "An unknown tool name needs a failure path; silent drop then fake success is not a conversation. "
            "The bridge sits outside the model. Execution must not leak back into the model process.",
            "模型不能自己碰磁盘或 shell。它只能发出带名字的 tool call；执行权必须在桥的这一侧。"
            "不变量：模型输出 tool call → 桥按名字执行 → 结果写回同一轮 → 再调模型。"
            "若这不成立，工具跑完了，下一轮模型看不到结果，用户会看见模型假装做完或卡住。"
            "不要把这当成「有一个 tools crate 就行」。缺的是写回，不是目录。"
            "未知工具名必须有失败路径，不能静默丢弃后再假装成功。"
            "桥在模型的外侧，执行权不能漏回模型进程。",
        ),
        "terminal-ui": t(
            "While the model streams tokens, the terminal must have one place that paints the increment. "
            "Invariant: a model delta arrives → it is written into the pager → the terminal shows it. "
            "If this were false, the user sees a blank screen or a full redraw after every token. "
            "This is not “Pager is just scrollback”. It is the only canvas the stream can land on. "
            "TUI is one door onto the same turn; it does not own a second model call.",
            "模型流式吐字时，终端必须有一个地方把增量画出来。"
            "不变量：模型 delta 到达 → 写入 pager → 终端可见。"
            "若这不成立，用户看见的是空白，或每个 token 都整页刷新。"
            "不要把这当成「Pager 只是一段回滚缓冲」。它是流式输出唯一能落下的画布。"
            "TUI 是同一轮对话的一扇门，它不另养一次模型调用。",
        ),
        "tui-pager": t(
            "While the model streams tokens, the terminal must have one place that paints the increment. "
            "Invariant: a model delta arrives → it is written into the pager → the terminal shows it. "
            "If this were false, the stream has nowhere to land. "
            "This is not “Pager is just scrollback”.",
            "模型流式吐字时，终端必须有一个地方把增量画出来。"
            "不变量：模型 delta 到达 → 写入 pager → 终端可见。"
            "若这不成立，流式输出没有落点。"
            "不要把这当成「Pager 只是一段回滚缓冲」。",
        ),
        "context-assembly": t(
            "Before each model call the context window must already hold the system head. "
            "The system head is a rule, not chat history. "
            "Invariant: assemble context → system head sits at the window head → then send this turn. "
            "If this were false, a new rule never reaches the window head and the model answers under the old rule. "
            "This is not “concatenate the last N messages”. Order at the head is the rule; append-after-user is a different product.",
            "每轮问模型之前，上下文窗口里必须先有系统头。"
            "系统头不是聊天记录，是规则。"
            "不变量：组上下文 → 系统头在窗口头上 → 再发本轮消息。"
            "若这不成立，新规则到不了窗口头部，模型按旧规则回答。"
            "不要把这当成「把最近 N 条消息拼起来」。头上的顺序才是规则；拼在用户消息后面是另一个产品。",
        ),
        "agent-runtime": t(
            "The runtime holds this turn’s cancel right and the long-lived objects. The loop cannot build those from one keystroke. "
            "Invariant: the runtime owns session and the cancel signal → the loop only drives one turn → cancel must abort an in-flight model call. "
            "If this were false, the user hits cancel and the model keeps streaming; Pager keeps writing; the terminal will not stop. "
            "This is not “there is a runtime struct in some crate”. Ask where the cancel signal goes. "
            "An empty runtime should fail before a turn starts, not halfway through a write. "
            "Lifecycle is whether this turn can be killed, not a list of background jobs.",
            "运行时持有这一轮的取消权和长寿命对象。循环不能靠一次按键把它们现造出来。"
            "不变量：运行时持有 session 和取消信号 → 循环只推一轮 → 取消必须能打断 in-flight 的模型调用。"
            "若这不成立，用户按了取消，模型仍在吐字，Pager 继续写，终端停不下来。"
            "不要把这当成「某个 crate 里有个 runtime 结构体」。要问的是取消信号传到哪。"
            "空运行时应该在开始一轮之前失败，而不是写到一半。"
            "生命周期不是后台任务列表，是这一轮能不能被杀掉。",
        ),
        "session-lifecycle": t(
            "A turn that cannot be cancelled is a turn the user does not own. "
            "Invariant: cancel reaches the in-flight model call and tears down this turn’s session work. "
            "If this were false, cancel is a UI label and tokens keep arriving. "
            "This is not “session_lifecycle.rs exists”. Name the stop, not the file. "
            "The next turn must not inherit a half-killed stream.",
            "一轮不能被取消，等于这一轮不属于用户。"
            "不变量：取消必须传到还在飞的模型调用，并拆掉这一轮的会话工作。"
            "若这不成立，取消只是界面上的一个词，token 还在往下走。"
            "不要把这当成「有一个 session_lifecycle.rs」。要说的是停在哪，不是文件名。"
            "下一轮不能继承一条杀到一半的流。",
        ),
        "acp-protocol": t(
            "ACP is the door IDE and external clients use. It is not a nickname for the TUI. "
            "Invariant: connect opens a session → later messages share that channel → a turn is still driven by start_turn. "
            "If this were false, the IDE is connected but has no session object, or TUI and ACP fight over one block of state and one side drops keystrokes. "
            "This is not “one more protocol crate”. The protocol must hand over a session; it must not grow a second loop. "
            "Both doors share the later turn, tools, and write-back. They must not each keep a private model call. "
            "If channel messages do not line up, connect succeeding still is not a conversation.",
            "ACP 是 IDE 和外部客户端进产品的那扇门，不是 TUI 的别名。"
            "不变量：connect 建立会话 → 后续消息走同一条通道 → 一轮仍由 start_turn 推。"
            "若这不成立，IDE 连上了但没有会话对象，或 TUI 和 ACP 抢同一块状态，一边打字另一边丢消息。"
            "不要把这当成「多一个协议 crate」。协议层必须交出会话，而不是自己再写一套循环。"
            "两扇门共用后面的 turn、工具和写回，不能各养一个模型调用。"
            "通道上的消息对不上，connect 成功也没有对话。",
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
    """Checkable gate: name a function, state, or failure path. Not a slogan."""
    slug = getattr(concept, "slug", "") or ""
    title = getattr(concept, "title", "") or slug
    gates = {
        "project-goal": t(
            "You sign off: if start_turn is missing, can the dialogue the README claims still happen? Name the missing function. Do not summarize the product.",
            "你签字：若没有 start_turn 这一层，README 声称的对话还能发生吗？说出缺的函数名，不要概括产品。",
        ),
        "entry-and-boot": t(
            "You sign off: after connect returns, which type holds session state? If connect fails, does the TUI door open by itself? Name the type or function.",
            "你签字：connect 返回之后，会话状态落在哪个类型上？若 connect 失败，TUI 那扇门还会不会自己开？说出类型或函数名。",
        ),
        "application-entry": t(
            "You sign off: if the entry file were empty, what would fail to start? Name that object.",
            "你签字：如果入口文件是空的，什么将无法启动？说出那个对象。",
        ),
        "agent-loop": t(
            "You sign off: if you swap “call the model” and “run tools”, what is the first function after start_turn? Name the real function and the failure path the user would see.",
            "你签字：把「调模型」和「跑工具」对调之后，start_turn 后面第一个函数名是什么？指出真实顺序里那个函数，并写出对调后用户看到的失败路径。",
        ),
        "call-flow": t(
            "You sign off: if you swap “call the model” and “run tools”, what is the first function after start_turn? Name the real function and the failure path.",
            "你签字：把「调模型」和「跑工具」对调之后，start_turn 后面第一个函数名是什么？指出真实顺序里那个函数，并写出对调后的失败路径。",
        ),
        "runtime-loop": t(
            "You sign off: if you swap “call the model” and “run tools”, what is the first function after start_turn? Name the real function and the failure path.",
            "你签字：把「调模型」和「跑工具」对调之后，start_turn 后面第一个函数名是什么？指出真实顺序里那个函数，并写出对调后的失败路径。",
        ),
        "tool-system": t(
            "You sign off: after a tool returns, which function writes the result into context and calls the model again? If write-back fails, which state does this turn stop in?",
            "你签字：工具返回之后，哪个函数把结果写进上下文并再次调用模型？若写回失败，这一轮停在什么状态？",
        ),
        "terminal-ui": t(
            "You sign off: when a streaming delta arrives, is the whole page redrawn or is it written into the pager? Name the function or field.",
            "你签字：流式 delta 到达时，是整页重绘还是写入 pager？说出函数名或字段名。",
        ),
        "tui-pager": t(
            "You sign off: when a streaming delta arrives, is the whole page redrawn or is it written into the pager? Name the function or field.",
            "你签字：流式 delta 到达时，是整页重绘还是写入 pager？说出函数名或字段名。",
        ),
        "context-assembly": t(
            "You sign off: when the system head updates, is the old head replaced or appended? Name the function.",
            "你签字：系统头更新时，旧头是被替换还是追加？指出函数名。",
        ),
        "agent-runtime": t(
            "You sign off: on cancel, which function or state aborts the in-flight call? If that signal is lost, which failure does the user see?",
            "你签字：取消时哪个函数或状态把 in-flight 调用打断？若那个信号丢失，用户会看到哪条失败路径？",
        ),
        "session-lifecycle": t(
            "You sign off: on cancel, which function or state aborts the in-flight call? If that signal is lost, which failure does the user see?",
            "你签字：取消时哪个函数或状态把 in-flight 调用打断？若那个信号丢失，用户会看到哪条失败路径？",
        ),
        "acp-protocol": t(
            "You sign off: after connect, which type holds the channel? If that object is empty, which failure path does the next message take?",
            "你签字：connect 之后哪个类型持有通道？若这个对象是空的，下一帧消息走哪条失败路径？",
        ),
    }
    if slug in gates:
        return gates[slug]
    return t(
        f"You sign off: point to the one path:line that proves `{title}` must exist, and name what breaks if that line is gone.",
        f"你签字：指出本步那一处 path:line，证明「{title}」必须存在，并说出删掉那一行会坏什么。",
    )


def _is_dummy_symbol(name: str) -> bool:
    n = (name or "").strip().strip("`")
    if not n:
        return True
    if "/" in n or "\\" in n:
        return True
    if n.endswith((".rs", ".py", ".ts", ".js", ".go", ".toml", ".md")):
        return True
    return n.lower() in {
        "lib.rs",
        "main.rs",
        "mod.rs",
        "src",
        "crates",
        "packages",
        "apps",
        "root",
        *_CHIP_DENY_SYMBOLS,
    }


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
    key = _resolve_store_key(file_texts, path) if file_texts else None
    if key:
        path = key
    text = _file_text_for(file_texts, path)
    if name and text:
        found = _definition_line_in_text(text, name)
        if found:
            return path, found, name
        return path, 0, name
    return path, line, name


def _format_path_chip(path: str, line: int, symbol: str | None) -> str:
    normalized = path.replace("\\", "/")
    loc = f"{normalized}:{int(line)}" if line and int(line) > 0 else normalized
    sym = (symbol or "").strip()
    if sym and not _is_dummy_symbol(sym):
        return f"{loc} {sym}"
    return loc


def _emit_store_chip(
    path: str,
    line: int,
    symbol: str,
    store: dict[str, str] | None,
) -> str | None:
    """Never emit a path that is not a version_files key when the store is loaded.

    Gate chips need a definition ``:line``. Occurrence-only / ``:1`` fallbacks
    are not enough unless line 1 is the actual definition.
    """
    if store:
        key = _resolve_store_key(store, path)
        if not key:
            return None
        path, line, symbol = _stamp_definition_line(key, line, symbol, store)
        if symbol and not line:
            hit = resolve_symbol_definition(store, symbol, prefer_path=path)
            if hit:
                path, line = hit
        if not line:
            first, emit = _first_definition_line(store.get(path) or "")
            if first and emit and not _is_dummy_symbol(emit):
                line, symbol = first, symbol or emit
        if not line:
            return None
        return _format_path_chip(path, line, symbol)
    path, line, symbol = _stamp_definition_line(path, line, symbol, store)
    return _format_path_chip(path, line, symbol)


_PATH_CHIP_RE = re.compile(
    r"^`?([A-Za-z0-9_./\-]+?\.[A-Za-z0-9]+)(?::(\d+)(?:-\d+)?)?(?:[ \t]+([A-Za-z_][A-Za-z0-9_]*))?`?$"
)
_GATE_IDENT_RE = re.compile(
    r"\b([A-Z][A-Za-z0-9_]{2,}|[a-z][a-z0-9]*(?:_[a-z0-9]+)+)\b"
)
_FAILURE_DEFAULTS: tuple[str, ...] = (
    "失败",
    "停在",
    "写回",
    "写不回",
    "无法",
    "打不开",
    "中断",
    "丢失",
    "abort",
    "fail",
    "cancel",
    "坏掉",
    "看不见",
    "空的",
    "对调",
)


def parse_path_chip(chip: str) -> tuple[str, int, str]:
    """``path:line Symbol`` → (path, line, symbol). Line 0 / empty symbol if absent."""
    raw = (chip or "").strip().strip("`")
    match = _PATH_CHIP_RE.match(raw)
    if not match:
        return "", 0, ""
    return (
        (match.group(1) or "").strip(),
        int(match.group(2) or 0),
        (match.group(3) or "").strip(),
    )


def is_crate_root_path(path: str) -> bool:
    name = (path or "").replace("\\", "/").rsplit("/", 1)[-1].lower()
    return name in _CRATE_ROOT_NAMES


def is_readme_path(path: str) -> bool:
    name = (path or "").replace("\\", "/").rsplit("/", 1)[-1].lower()
    return name in {"readme.md", "readme"} or "readme.md" in (path or "").lower()


def chip_is_definition_line(chip: str) -> bool:
    """True when ``chip`` is already a real ``path:line Symbol`` definition."""
    path, line, symbol = parse_path_chip(chip or "")
    if not path or line < 1:
        return False
    if not symbol or _is_dummy_symbol(symbol):
        return False
    if is_junk_evidence_path(path) or is_readme_path(path):
        return False
    return True


def chip_needs_restamp(slug: str, chip: str) -> bool:
    """True when a persisted chip is not a real definition ``path:line Symbol``.

    Driven by the chip itself (junk path, file-start, missing symbol) — not a
    slug allowlist. ``slug`` only changes junk-path rules such as README.
    """
    path, line, symbol = parse_path_chip(chip or "")
    if not path:
        return True
    if is_readme_path(path):
        return True
    if is_junk_evidence_path(path, slug=slug):
        return True
    if line < 1:
        return True
    if not symbol or _is_dummy_symbol(symbol):
        return True
    return False


def source_refs_from_chip(
    chip: str, commit_sha: str | None = None
) -> list[SourceReference]:
    path, line, symbol = parse_path_chip(chip or "")
    if not path:
        return []
    return [
        SourceReference(
            path=path,
            start_line=line or None,
            end_line=line or None,
            symbol=symbol or None,
            commit_sha=commit_sha or None,
        )
    ]


def concept_refs_need_rebind(
    refs: list[Any] | None,
    slug: str = "",
    chip: str = "",
) -> bool:
    """True when persisted concept refs are file-start / junk vs a real chip."""
    items = _source_refs_of(type("C", (), {"source_references": refs or []})())
    if chip and chip_is_definition_line(chip):
        cpath, cline, csym = parse_path_chip(chip)
        for ref in items:
            if (
                (ref.path or "").replace("\\", "/") == cpath
                and int(ref.start_line or 0) == cline
                and (ref.symbol or "").strip() == csym
            ):
                return False
        return True
    if not items:
        return True
    for ref in items:
        path = (ref.path or "").replace("\\", "/")
        start = int(ref.start_line or 0)
        end = int(ref.end_line or 0)
        symbol = (ref.symbol or "").strip()
        if is_readme_path(path) or is_junk_evidence_path(path, slug=slug):
            return True
        if start <= 1 and end > start:
            return True
        if start < 1:
            return True
        if start <= 1 and (not symbol or _is_dummy_symbol(symbol)):
            return True
    return False


def gate_failure_tokens(gate: str) -> list[str]:
    """Tokens a 过关 answer must hit: failure-path words from the gate text."""
    text = gate or ""
    out: list[str] = []
    seen: set[str] = set()
    for tok in _FAILURE_DEFAULTS:
        if tok in text and tok not in seen:
            seen.add(tok)
            out.append(tok)
    if not out:
        out.extend(["失败", "停在"])
    return out


def gate_required_symbol(gate: str, chip_symbol: str = "") -> str:
    """Concrete fn/type the gate asks for. Chip symbol wins when present."""
    if chip_symbol and not _is_dummy_symbol(chip_symbol):
        return chip_symbol.strip()
    for match in _GATE_IDENT_RE.finditer(gate or ""):
        name = match.group(1)
        if not _is_dummy_symbol(name) and name.lower() not in {"readme", "path", "line"}:
            return name
    return (chip_symbol or "").strip()


def path_step_contract(
    concept: Any,
    *,
    chip: str | None = None,
    file_texts: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Analyze/GET snapshot: chip + gate tokens used to generate and score items."""
    slug = getattr(concept, "slug", "") or ""
    title = getattr(concept, "title", "") or slug
    evidence = chip if chip is not None else path_evidence_chip(concept, file_texts=file_texts)
    path, line, symbol = parse_path_chip(evidence or "")
    gate = pass_gate(concept)
    required = gate_required_symbol(gate, symbol)
    return {
        "chip": evidence or "",
        "path": path,
        "line": line,
        "symbol": required,
        "task": step_task_for_slug(slug, title),
        "gate": gate,
        "failure_tokens": gate_failure_tokens(gate),
        "slug": slug,
    }


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
    if "/scripts/" in wrapped:
        return True
    if "encrypt" in name or name.startswith("xor_"):
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


def _resolve_store_key(file_texts: dict[str, str] | None, path: str) -> str | None:
    """Return the version_files key for ``path``, or None if it is not in the store."""
    if not file_texts or not path:
        return None
    key = path.replace("\\", "/")
    if key in file_texts:
        return key
    matches = [
        p.replace("\\", "/")
        for p in file_texts
        if p.replace("\\", "/") == key or p.replace("\\", "/").endswith("/" + key)
    ]
    if len(matches) == 1:
        return matches[0]
    return None


def line_of_symbol_in_text(text: str, symbol: str) -> int:
    """Definition line, else first real occurrence. 0 if the name is absent."""
    name = (symbol or "").strip()
    if not text or len(name) < 2:
        return 0
    found = _definition_line_in_text(text, name)
    if found:
        return found
    return _occurrence_line_in_text(text, name)


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
        stripped = line.strip()
        if stripped.startswith(("//", "/*", "*", "#", "//!", "///")):
            continue
        match = _FIRST_DEFN_RE.search(line)
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
    cached = _DEFINITION_INDEX.get()
    indexed = cached.definitions(name) if cached is not None else None
    if indexed:
        candidates: list[tuple[str, int]] = indexed
    else:
        candidates = []
        for path, text in file_texts.items():
            norm = path.replace("\\", "/")
            if not _is_production_src(norm, slug=slug) or _blocked_for_slug(norm, slug):
                continue
            defn, is_defn = _best_symbol_line(text, name)
            if not defn or not is_defn:
                continue
            candidates.append((norm, defn))
    for path, defn in candidates:
        norm = path.replace("\\", "/")
        if not _is_production_src(norm, slug=slug) or _blocked_for_slug(norm, slug):
            continue
        score = 50 if norm.lower().endswith(".rs") else 20
        score += 120
        if "/src/" in f"/{norm.lower()}/":
            score += 10
        if _is_bin_path(norm):
            score -= 40
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


def _pick_symbol_in_store(
    file_texts: dict[str, str],
    symbol: str,
    slug: str,
    suffixes: tuple[str, ...],
) -> tuple[str, int] | None:
    """Symbol in a production store key. Prefer a definition; never invent a path."""
    hit = _pick_definition_in_store(file_texts, symbol, slug, suffixes)
    if hit:
        return hit
    name = (symbol or "").strip()
    if not file_texts or len(name) < 2:
        return None
    hits: list[tuple[int, str, int]] = []
    for path, text in file_texts.items():
        norm = path.replace("\\", "/")
        if not _is_production_src(norm, slug=slug) or _blocked_for_slug(norm, slug):
            continue
        occ = _occurrence_line_in_text(text, name)
        if not occ:
            continue
        score = 50 if norm.lower().endswith(".rs") else 20
        score += 30
        if "/src/" in f"/{norm.lower()}/":
            score += 10
        score += _prefer_score(norm, slug)
        for i, suffix in enumerate(suffixes):
            if _path_matches_hint(norm, suffix):
                score += 40 - min(i, 12)
                break
        hits.append((score, norm, occ))
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


def _is_lifecycle_rs(path: str) -> bool:
    low = (path or "").replace("\\", "/").lower()
    return "xai-agent-lifecycle" in low and low.endswith(".rs")


def _pick_lifecycle_crate(
    store: dict[str, str],
    slug: str,
) -> tuple[str, int, str] | None:
    """Best existing ``xai-agent-lifecycle/**/*.rs``. Never invent ``runtime.rs``."""
    hits: list[tuple[int, str, int, str]] = []
    for path, text in store.items():
        norm = path.replace("\\", "/")
        if not _is_lifecycle_rs(norm):
            continue
        if is_junk_evidence_path(norm, slug=slug) or _blocked_for_slug(norm, slug):
            continue
        if not _is_production_src(norm, slug=slug):
            continue
        name = norm.rsplit("/", 1)[-1].lower()
        score = 50
        if "/src/" in f"/{norm.lower()}/":
            score += 10
        for i, pref in enumerate(_LIFECYCLE_BASENAMES):
            if name == pref or (pref == "contributors.rs" and "contributors" in norm.lower()):
                score += 40 - min(i, 10) * 3
                break
        defn = _definition_line_in_text(text, "AgentRuntime")
        if defn:
            line, emit = defn, "AgentRuntime"
            score += 80
        else:
            line, emit = _first_definition_line(text)
            if _is_dummy_symbol(emit):
                line, emit = 0, ""
        if not line or not emit:
            continue
        hits.append((score, norm, line, emit))
    if not hits:
        return None
    hits.sort(key=lambda item: (-item[0], item[1]))
    _score, path, line, emit = hits[0]
    return path, line, emit


def _best_store_ref(
    refs: list[SourceReference],
    slug: str,
    store: dict[str, str],
    symbol: str,
) -> tuple[str, int, str] | None:
    """Best concept ref whose path is a store key. ``:line`` only if the symbol is in the text."""
    scored: list[tuple[int, str, int, str]] = []
    for ref in refs:
        key = _resolve_store_key(store, ref.path)
        if not key or is_junk_evidence_path(key, slug=slug) or _blocked_for_slug(key, slug):
            continue
        text = store.get(key) or ""
        ref_sym = (getattr(ref, "symbol", None) or "").strip()
        line = line_of_symbol_in_text(text, symbol) if symbol else 0
        emit_sym = symbol if line else ""
        if not line and ref_sym and not _is_dummy_symbol(ref_sym):
            line = line_of_symbol_in_text(text, ref_sym)
            emit_sym = ref_sym if line else ""
        if _is_dummy_symbol(emit_sym):
            line, emit_sym = 0, ""
        score = 50 if key.endswith(_SRC_EXT) else 10
        score += _prefer_score(key, slug)
        if line:
            score += 40
        if ref.start_line and line == ref.start_line:
            score += 8
        scored.append((score, key, line, emit_sym))
    if not scored:
        return None
    rust = [item for item in scored if item[1].endswith(_SRC_EXT)]
    pool = rust if rust else scored
    pool.sort(key=lambda item: (-item[0], item[1]))
    return pool[0][1], pool[0][2], pool[0][3]


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
        if file_texts:
            key = _resolve_store_key(file_texts, path)
            if not key:
                return
            path = key
        if path in seen:
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
            if slug in {"agent-runtime", "session-lifecycle"} and _is_lifecycle_rs(norm):
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
    line = 0
    use_sym = symbol
    in_refs = False
    for ref in refs:
        if ref.path.replace("\\", "/") != path:
            continue
        in_refs = True
        if ref.start_line and ref.start_line > 0:
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
        if line_no:
            line = line_no
            score += 120 if is_defn else 40
        else:
            use_sym = ""
            line = 0
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

    store = file_texts or {}
    if slug == "project-goal":
        if store:
            hit = _pick_symbol_in_store(
                store, "start_turn", slug, suffixes or ("agent.rs", "app.rs", "turn.rs")
            )
            if hit:
                chip = _emit_store_chip(hit[0], hit[1], "start_turn", store)
                if chip:
                    return chip
        for ref in refs:
            path = ref.path.replace("\\", "/")
            name = path.rsplit("/", 1)[-1].lower()
            if name in {"readme.md", "readme"}:
                return _format_path_chip(path, ref.start_line or 1, "")
        if store:
            for key in store:
                name = key.replace("\\", "/").rsplit("/", 1)[-1].lower()
                if name in {"readme.md", "readme"}:
                    return _format_path_chip(key.replace("\\", "/"), 1, "")
        return _format_path_chip("README.md", 1, "")

    if not store:
        logger.debug("learning-path evidence: empty scan store for slug=%s", slug)

    # Definition-first: if the hint is not in the topic ref, search every
    # production *.rs in version_files. Weak names like ``main`` stay on
    # slug-allowed files (grok/pager boot, never ptyctl-cli).
    if symbol and store and symbol.lower() not in _WEAK_SYMBOLS:
        hit = _pick_symbol_in_store(store, symbol, slug, suffixes)
        if hit:
            chip = _emit_store_chip(hit[0], hit[1], symbol, store)
            if chip:
                return chip
        logger.info(
            "learning-path evidence: no store occurrence of %s for slug=%s (%d files)",
            symbol,
            slug,
            len(store),
        )
        if slug in {"agent-runtime", "session-lifecycle"}:
            life = _pick_lifecycle_crate(store, slug)
            if life:
                chip = _emit_store_chip(life[0], life[1], life[2], store)
                if chip:
                    return chip
        ref_hit = _best_store_ref(refs, slug, store, symbol)
        if ref_hit:
            chip = _emit_store_chip(ref_hit[0], ref_hit[1], ref_hit[2], store)
            if chip:
                return chip
    elif symbol and store and symbol.lower() in _WEAK_SYMBOLS:
        hit = _pick_entry_or_weak(store, refs, slug, suffixes, symbol)
        if hit:
            chip = _emit_store_chip(hit[0], hit[1], hit[2], store)
            if chip:
                return chip
        ref_hit = _best_store_ref(refs, slug, store, symbol)
        if ref_hit:
            chip = _emit_store_chip(ref_hit[0], ref_hit[1], ref_hit[2], store)
            if chip:
                return chip

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
    chip = _emit_store_chip(path, line, use_sym, store)
    if chip:
        return chip
    if store:
        ref_hit = _best_store_ref(refs, slug, store, symbol)
        if ref_hit:
            chip = _emit_store_chip(ref_hit[0], ref_hit[1], ref_hit[2], store)
            if chip:
                return chip
        return None
    return _format_path_chip(path, line, use_sym)


def _bind_crate_root_definition(
    path: str,
    file_texts: dict[str, str],
    *,
    slug: str = "",
) -> tuple[str, int, str] | None:
    """Follow ``pub use`` / sibling files so crate-root ``lib.rs:1`` is not the claim."""
    store = file_texts or {}
    key = _resolve_store_key(store, path)
    if not key:
        return None
    text = store.get(key) or ""
    for match in _REEXPORT_RE.finditer(text):
        name = match.group(1)
        if not name or _is_dummy_symbol(name):
            continue
        hit = resolve_symbol_definition(store, name, prefer_path=key)
        if hit and _resolve_store_key(store, hit[0]):
            return hit[0], hit[1], name
    parent = key.rsplit("/", 1)[0]
    scored: list[tuple[int, str, int, str]] = []
    for other, other_text in store.items():
        norm = other.replace("\\", "/")
        if norm == key or not parent or not norm.startswith(parent + "/"):
            continue
        if is_junk_evidence_path(norm, slug=slug) or not _is_production_src(norm, slug=slug):
            continue
        line, symbol = _first_definition_line(other_text or "")
        if not line or not symbol or _is_dummy_symbol(symbol):
            continue
        score = 50 if norm.lower().endswith(".rs") else 20
        if not is_crate_root_path(norm):
            score += 15
        scored.append((score, norm, line, symbol))
    if not scored:
        return None
    scored.sort(key=lambda item: (-item[0], item[1]))
    _score, norm, line, symbol = scored[0]
    return norm, line, symbol


def _bind_one_source_path(
    path: str,
    file_texts: dict[str, str] | None,
    *,
    slug: str = "",
    commit_sha: str = "",
) -> SourceReference | None:
    raw = (path or "").replace("\\", "/")
    if not raw:
        return None
    store = file_texts or {}
    key = _resolve_store_key(store, raw) if store else raw
    if store and not key:
        return None
    path = key or raw
    if is_junk_evidence_path(path, slug=slug) and not (
        slug == "project-goal" and is_readme_path(path)
    ):
        return None
    text = (store.get(path) or "") if store else ""
    line, symbol = _first_definition_line(text)
    if line and symbol and not _is_dummy_symbol(symbol):
        return SourceReference(
            path=path,
            start_line=line,
            end_line=line,
            symbol=symbol,
            commit_sha=commit_sha or None,
        )
    if store and is_crate_root_path(path):
        hit = _bind_crate_root_definition(path, store, slug=slug)
        if hit:
            return SourceReference(
                path=hit[0],
                start_line=hit[1],
                end_line=hit[1],
                symbol=hit[2],
                commit_sha=commit_sha or None,
            )
    return None


def bind_concept_source_references(
    paths: list[str],
    file_texts: dict[str, str] | None,
    *,
    slug: str = "",
    commit_sha: str = "",
) -> list[SourceReference]:
    """Bind key-file paths to real definition lines. Never invent missing keys.

    File-start ``:1-40`` / README / Cargo.toml / package.json are dropped when a
    Rust / TS / Python definition can be resolved in ``file_texts``.
    """
    store = file_texts or {}
    bound: list[SourceReference] = []
    seen: set[str] = set()

    def add(ref: SourceReference) -> None:
        key = f"{ref.path}:{int(ref.start_line or 0)}:{ref.symbol or ''}"
        if key in seen:
            return
        if store and not _resolve_store_key(store, ref.path):
            return
        seen.add(key)
        bound.append(ref)

    for path in paths:
        ref = _bind_one_source_path(path, store, slug=slug, commit_sha=commit_sha)
        if ref:
            add(ref)

    chip_refs: list[SourceReference] = []
    if store and slug:
        draft = ConceptDraft(
            slug=slug,
            title=slug,
            source_references=list(bound),
        )
        chip = path_evidence_chip(draft, file_texts=store)
        if chip and chip_is_definition_line(chip):
            chip_refs = source_refs_from_chip(chip, commit_sha)

    if chip_refs:
        chip_path = chip_refs[0].path
        extras = [
            ref
            for ref in bound
            if ref.path != chip_path and not is_junk_evidence_path(ref.path, slug=slug)
        ]
        return chip_refs + extras[:3]

    if bound:
        return bound

    if slug == "project-goal":
        for key in store:
            if is_readme_path(key):
                return [
                    SourceReference(
                        path=key.replace("\\", "/"),
                        start_line=1,
                        end_line=1,
                        commit_sha=commit_sha or None,
                    )
                ]
        for path in paths:
            if is_readme_path(path):
                if store and not _resolve_store_key(store, path):
                    continue
                return [
                    SourceReference(
                        path=path.replace("\\", "/"),
                        start_line=1,
                        end_line=1,
                        commit_sha=commit_sha or None,
                    )
                ]
    return []


_WIKI_PILL_RE = re.compile(
    r"^([A-Za-z0-9_./\-]+?\.[A-Za-z0-9]+)(?::(\d+)(?:-(\d+))?)?(?:[ \t]+(.+))?$"
)
_INDEX_DEFN_RE = re.compile(
    r"(?:pub(?:\([^)]*\))?\s+)?"
    r"(?:export\s+)?(?:default\s+)?"
    r"(?:async\s+)?"
    r"(?:abstract\s+)?"
    r"(?:fn|struct|enum|trait|type|class|def|function|interface)\s+"
    r"([A-Za-z_][A-Za-z0-9_]*)"
    r"|impl(?:\s*<[^>]*>)?\s+([A-Za-z_][A-Za-z0-9_]*)"
    r"|impl\b.+\bfor\s+([A-Za-z_][A-Za-z0-9_]*)"
)

_DEFINITION_INDEX: ContextVar["DefinitionIndex | None"] = ContextVar(
    "recallstack_definition_index", default=None
)


def _is_bin_path(path: str) -> bool:
    low = (path or "").replace("\\", "/").lower()
    wrapped = f"/{low}/"
    return low.startswith("bin/") or "/bin/" in wrapped or "/src/bin/" in wrapped


def _path_resolve_score(norm: str, *, prefer_key: str = "") -> int:
    score = 50 if norm.lower().endswith(".rs") else 20
    if "/src/" in f"/{norm.lower()}/":
        score += 10
    if _is_bin_path(norm):
        score -= 40
    if prefer_key and norm == prefer_key:
        score += 80
    return score


class DefinitionIndex:
    """One pass over the scan store: symbol → definition (path, line)."""

    def __init__(self, file_texts: dict[str, str] | None):
        self.file_texts = file_texts or {}
        self._defs: dict[str, list[tuple[str, int]]] = {}
        self._build()

    def _build(self) -> None:
        for path, text in self.file_texts.items():
            norm = path.replace("\\", "/")
            if is_junk_evidence_path(norm) or not _is_production_src(norm):
                continue
            seen: set[str] = set()
            for i, line in enumerate((text or "").splitlines(), 1):
                stripped = line.strip()
                if stripped.startswith(("//", "/*", "*", "#", "//!", "///")):
                    continue
                if re.match(r"(?:pub\s+)?use\b", stripped):
                    continue
                for match in _INDEX_DEFN_RE.finditer(line):
                    name = next((g for g in match.groups() if g), "")
                    if not name or name in seen or _is_dummy_symbol(name):
                        continue
                    if not _line_defines_symbol(line, name):
                        continue
                    seen.add(name)
                    self._defs.setdefault(name, []).append((norm, i))

    def definitions(self, symbol: str) -> list[tuple[str, int]]:
        return list(self._defs.get((symbol or "").strip(), ()))

    def resolve(self, symbol: str, *, prefer_path: str = "") -> tuple[str, int] | None:
        name = (symbol or "").strip()
        if len(name) < 2:
            return None
        prefer_key = _resolve_store_key(self.file_texts, prefer_path)
        hits = [
            (_path_resolve_score(path, prefer_key=prefer_key or "") + 80, path, line)
            for path, line in self.definitions(name)
        ]
        if not hits:
            return None
        hits.sort(key=lambda item: (-item[0], item[1]))
        _score, path, line = hits[0]
        return path, line


@contextmanager
def definition_index_scope(file_texts: dict[str, str] | None) -> Iterator[DefinitionIndex | None]:
    """Build a store index once so pill/chip resolution is not O(files × symbols)."""
    if not file_texts:
        token = _DEFINITION_INDEX.set(None)
        try:
            yield None
        finally:
            _DEFINITION_INDEX.reset(token)
        return
    index = DefinitionIndex(file_texts)
    token = _DEFINITION_INDEX.set(index)
    try:
        yield index
    finally:
        _DEFINITION_INDEX.reset(token)


def resolve_symbol_definition(
    file_texts: dict[str, str],
    symbol: str,
    *,
    prefer_path: str = "",
) -> tuple[str, int] | None:
    """Store-wide struct/impl/fn of ``symbol``. Path must be a version_files key.

    Definitions beat use-sites. ``prefer_path`` only boosts a key that exists;
    a missing ``tool_bridge.rs`` never wins.
    """
    name = (symbol or "").strip()
    if not file_texts or len(name) < 2:
        return None
    cached = _DEFINITION_INDEX.get()
    if cached is not None:
        hit = cached.resolve(name, prefer_path=prefer_path)
        if hit:
            return hit
    prefer_key = _resolve_store_key(file_texts, prefer_path)
    defs: list[tuple[int, str, int]] = []
    occs: list[tuple[int, str, int]] = []
    for path, text in file_texts.items():
        norm = path.replace("\\", "/")
        if is_junk_evidence_path(norm) or not _is_production_src(norm):
            continue
        defn = _definition_line_in_text(text, name)
        occ = _occurrence_line_in_text(text, name) if not defn else 0
        if not defn and not occ:
            continue
        score = _path_resolve_score(norm, prefer_key=prefer_key or "")
        if defn:
            defs.append((score + 80, norm, defn))
        else:
            occs.append((score, norm, occ))
    hits = defs or occs
    if not hits:
        return None
    hits.sort(key=lambda item: (-item[0], item[1]))
    _score, path, line = hits[0]
    return path, line


def fill_wiki_key_type_lines(content: str, file_texts: dict[str, str] | None) -> str:
    """Stamp wiki pills from the scan store.

    `` `path Symbol` `` / `` `path:1 Symbol` `` become the definition line.
    Path-only ``:1`` / crate-root pills resolve to a definition or are dropped
    so architecture/index do not keep crate-root ``:1`` when it is not the claim.
    Non-root path-only pills without a line stay as-is.
    """
    if not content or not file_texts or "`" not in content:
        return content

    def drop_crate_root_chip(path: str) -> str:
        return path.replace("\\", "/").rsplit("/", 1)[-1]

    def stamp_or_drop_path_only(path: str, line: str, end: str) -> str:
        is_line_one = line == "1"
        is_span = bool(end and end != line)
        is_root = is_crate_root_path(path)
        if not is_line_one and not is_root:
            return ""
        if is_span and is_readme_path(path):
            return ""
        store_path = _resolve_store_key(file_texts, path)
        if store_path:
            first, emit = _first_definition_line(file_texts.get(store_path) or "")
            if first and emit and not _is_dummy_symbol(emit):
                return f"`{store_path}:{first} {emit}`"
            hit = _bind_crate_root_definition(store_path, file_texts)
            if hit:
                return f"`{hit[0]}:{hit[1]} {hit[2]}`"
        if is_line_one and (is_root or is_junk_evidence_path(path) or is_readme_path(path)):
            return drop_crate_root_chip(path)
        return ""

    def pill_repl(match: re.Match[str]) -> str:
        inner = (match.group(1) or "").strip()
        parsed = _WIKI_PILL_RE.match(inner)
        if not parsed:
            return match.group(0)
        path = (parsed.group(1) or "").strip()
        line = (parsed.group(2) or "").strip()
        end = (parsed.group(3) or "").strip()
        symbol = (parsed.group(4) or "").strip()
        if not path:
            return match.group(0)
        if not symbol or _is_dummy_symbol(symbol):
            rewritten = stamp_or_drop_path_only(path, line, end)
            return rewritten if rewritten else match.group(0)
        if line and line != "1":
            store_existing = _resolve_store_key(file_texts, path)
            if store_existing or not file_texts:
                return match.group(0)
        if is_junk_evidence_path(path):
            return match.group(0)
        hit = resolve_symbol_definition(file_texts, symbol, prefer_path=path)
        if hit:
            new_path, new_line = hit
            if _resolve_store_key(file_texts, new_path):
                return f"`{new_path}:{new_line} {symbol}`"
        store_path = _resolve_store_key(file_texts, path)
        if store_path:
            found = line_of_symbol_in_text(file_texts.get(store_path) or "", symbol)
            if found:
                return f"`{store_path}:{found} {symbol}`"
            if line == "1":
                sibling = _bind_crate_root_definition(store_path, file_texts)
                if sibling:
                    return f"`{sibling[0]}:{sibling[1]} {symbol}`"
                return f"`{store_path} {symbol}`"
        return match.group(0)

    return re.sub(r"`([^`]+)`", pill_repl, content)


_ASK_QUESTION_RULES: tuple[tuple[tuple[str, ...], str], ...] = (
    (("entry-and-boot", "application-entry", "入口", "boot", "connect"), "你要能指出这个项目的入口在哪，connect 之后谁接手？"),
    (("agent-loop", "start_turn", "agent loop", "一轮"), "你要能指出一轮里 start_turn 之后谁调模型？"),
    (("acp", "protocol", "协议"), "你要能指出 ACP 会话是在哪建立的，connect 做了什么？"),
    (("pager", "terminal-ui", "tui-pager", "终端"), "你要能指出 Pager 把模型流式输出写进哪块缓冲区？"),
    (("tool-system", "tool_bridge", "toolbridge", "工具"), "你要能指出模型返回 tool call 之后谁按名字执行？"),
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
            q = f"你要能指出「{title}」在链路里承担什么，并签字？"
            if q not in out:
                out.append(q)
            if len(out) >= 3:
                break
    return [q for q in out[:3] if not any(bad in q for bad in _ASK_HOST_LEFTOVERS)]


def evidence_reading(concept: Any, chip: str | None = None) -> str:
    """2–3 sentences: why this one line proves the invariant. Not syntax."""
    slug = getattr(concept, "slug", "") or ""
    texts = {
        "project-goal": t(
            "This line is not a crate inventory. It pins the product to a runnable dialogue. "
            "If it only listed packages, entry and start_turn would have no constraint. "
            "Read it as the claim that Enter must produce an answer.",
            "这一行不是 crate 清单，它把产品钉在「能跑的对话」上。"
            "若它只是介绍包名，后面的入口和 start_turn 就没有约束。"
            "把它读成：回车必须换来回答。",
        ),
        "entry-and-boot": t(
            "connect is one door, not a comment on main. "
            "This line is where ACP hands control to a session; the TUI door is the other hand-off. "
            "If this line never ran, an IDE client would have no receiver.",
            "connect 是一扇门，不是写在 main 旁边的注释。"
            "这一行是 ACP 把控制权交给会话的地方；TUI 是另一扇门。"
            "若这一行从不执行，IDE 客户端没有接收者。",
        ),
        "application-entry": t(
            "This line is the first call the process actually makes. "
            "A crate name next to it does not start anything. "
            "If it disappeared, later modules would sit on disk and never run.",
            "这一行是进程真正发出的第一记调用。"
            "旁边的 crate 名不会让任何东西跑起来。"
            "若它消失，后面的模块只在磁盘上。",
        ),
        "agent-loop": t(
            "start_turn is the gate of this turn, not a UI redraw. "
            "The next call after this line must be the model, or the turn is a script. "
            "If this line ran tools first, the user would not see a model decision.",
            "start_turn 是这一轮的闸门，不是重绘界面。"
            "这一行之后第一个调用必须是模型，否则这一轮是脚本。"
            "若这一行先跑工具，用户看不见「模型在决定」。",
        ),
        "call-flow": t(
            "This line is a call in order, not a file in a list. "
            "Read who runs between input and the model. "
            "If the order flipped, the user-visible turn would change.",
            "这一行是顺序里的一次调用，不是名单上的一个文件。"
            "看输入到模型之间经过谁。"
            "若顺序反了，用户看见的这一轮会变。",
        ),
        "runtime-loop": t(
            "start_turn is the gate of this turn. "
            "The next call after this line must be the model. "
            "If tools ran first, the turn would be a batch job.",
            "start_turn 是这一轮的闸门。"
            "这一行之后第一个调用必须是模型。"
            "若先跑工具，这一轮就变成批处理。",
        ),
        "tool-system": t(
            "This line is the write-back, not a tools folder. "
            "After a tool returns, the same turn must put the result where the next model call can see it. "
            "If this line only dispatched and never wrote back, the model would guess or hang.",
            "这一行是写回，不是 tools 目录。"
            "工具返回之后，同一轮必须把结果放到下一次模型调用能看见的地方。"
            "若这一行只分发、不写回，模型只能猜或卡住。",
        ),
        "terminal-ui": t(
            "This line is where a stream delta becomes pixels. "
            "It is not a scrollback type alias. "
            "If it did not write into the pager, the user would see a blank or a full redraw.",
            "这一行是流式 delta 变成像素的地方。"
            "它不是回滚缓冲的别名。"
            "若它不写入 pager，用户看见空白或整页刷新。",
        ),
        "tui-pager": t(
            "This line is where a stream delta becomes pixels. "
            "If it did not write into the pager, the stream would have nowhere to land.",
            "这一行是流式 delta 变成像素的地方。"
            "若它不写入 pager，流没有落点。",
        ),
        "context-assembly": t(
            "This line decides whether the system head is a rule at the window head or leftover text after the user. "
            "If it appended, the model would answer under the old rule. "
            "The function name is the proof, not the file name.",
            "这一行决定系统头是窗口头上的规则，还是用户消息后面的残留。"
            "若它是追加，模型按旧规则回答。"
            "证明在函数名，不在文件名。",
        ),
        "agent-runtime": t(
            "This line is where cancel or session ownership lives, not a struct tourist stop. "
            "If it does not reach an in-flight model call, cancel is a label and tokens keep arriving. "
            "Name the stop, not the crate.",
            "这一行是取消或会话所有权所在，不是路过某个结构体。"
            "若它到不了还在飞的模型调用，取消只是一个词，token 还在走。"
            "要说停在哪，不要说 crate。",
        ),
        "session-lifecycle": t(
            "This line must be able to kill this turn. "
            "If it only logs a cancel, the stream continues. "
            "The next turn must not inherit a half-killed call.",
            "这一行必须能杀掉这一轮。"
            "若它只是记下取消，流还在走。"
            "下一轮不能继承一条杀到一半的调用。",
        ),
        "acp-protocol": t(
            "This line is the ACP door handing over a channel or session. "
            "It is not a second turn loop. "
            "If the object it builds is empty, the next message has no path.",
            "这一行是 ACP 这扇门交出通道或会话的地方。"
            "它不是第二套循环。"
            "若它造出的对象是空的，下一帧消息没有路。",
        ),
    }
    if slug in texts:
        return texts[slug]
    shown = getattr(concept, "title", "") or slug
    return t(
        f"This line is the proof that `{shown}` must exist on a real call. "
        "Read the invariant, not the syntax. "
        "If the line vanished, name the user-visible break.",
        f"这一行证明「{shown}」在一次真实调用里必须存在。"
        "读不变量，不要读语法。"
        "若这一行消失，说出用户能看见的那处损坏。",
    )


def path_worksheet(
    concept: Any,
    project_name: str = "",
    file_texts: dict[str, str] | None = None,
    evidence_chip: str | None = None,
) -> str:
    """Learning-path page only. Never mixed into the reading wiki."""
    title = getattr(concept, "title", None) or getattr(concept, "slug", "") or ""
    slug = getattr(concept, "slug", "") or ""
    task = step_task_for_slug(slug, title)
    principles = path_principles(concept, project_name)
    chip = (
        evidence_chip
        if evidence_chip is not None
        else path_evidence_chip(concept, file_texts=file_texts)
    )
    gate = pass_gate(concept)
    reading = evidence_reading(concept, chip)
    judge = t(
        "You decide whether this line is enough. Open it; annotations help you decide, they do not sign off for you.",
        "你来判断这一行是否够。点开它，标注只帮你决定，不替你签字。",
    )
    if chip:
        evidence_body = f"`{chip}`\n\n{judge}\n\n{reading}"
    else:
        evidence_body = t(
            "This step has no source line. You still sign off by naming the function or failure path the invariant requires.",
            "这一步不靠源码行。你仍然要签字：说出不变量要求的那个函数或失败路径。",
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


def handbook_section_title(key: str) -> str:
    """Handbook section heading. Old workbook names stay in the upgrade maps."""
    titles = {
        "what": ("Overview", "概述"),
        "position": ("Architecture", "架构"),
        "flow": ("Call path", "调用链"),
        "impl": ("Implementation", "实现"),
        "types": ("Key types", "关键类型"),
        "boundary": ("Boundaries", "边界"),
        "not": ("What this is not", "不是什么"),
        "tips": ("Terms", "术语"),
        "prereq": ("Read first", "先读"),
        "next": ("Next", "接下来"),
    }
    en, zh = titles[key]
    return t(en, zh)


def handbook_lede(slug: str, title: str = "") -> str:
    """Opening line for a concept *wiki* page — not the learning-path task."""
    shown = title or slug
    if slug == "project-goal":
        return t(
            "What problem this repo solves, who it is for, and what it explicitly "
            "does not do. The goal lives in the README, not the folder names.",
            "这个仓库解决什么问题、给谁用，以及明确不做什么。目标写在 README，不在目录名里。",
        )
    if slug == "application-entry":
        return t(
            "Where the process starts and what it wires first. The entrypoint is "
            "the first hop on the call path.",
            "进程从哪启动、启动后先装配什么。入口文件是调用链的第一跳。",
        )
    if slug in _FLOW_SLUGS:
        return t(
            f"Where `{shown}` sits on a real call path: who calls it, and what it calls.",
            f"「{shown}」在一次真实调用里的位置：谁调用它、它调用谁。",
        )
    return t(
        f"What `{shown}` owns, and where that responsibility stops.",
        f"「{shown}」负责什么，以及边界停在哪里。",
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
        f"`{shown}` sits on the call path: who calls it, and what it calls. "
        "Read that from the evidence, not from the folder name.",
        f"「{shown}」接在调用链上：谁调用它、它调用谁，以源码证据为准，不以目录名为准。",
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


_PATH_PRINCIPLE_MARKERS = (
    "若这不成立",
    "If this were false",
    "不要把这当成",
    "This is not “",
    "This is not \"",
)


def _is_path_principle_body(body: str) -> bool:
    text = body or ""
    return any(marker in text for marker in _PATH_PRINCIPLE_MARKERS)


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
    if stripped in _IMPL_HEADINGS:
        return "impl"
    if stripped in _TYPE_ROLE_HEADINGS:
        return "types"
    if stripped in _BOUNDARY_HEADINGS:
        return "boundary"
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
            "impl",
            "types",
            "boundary",
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
        if heading.strip() in {"先回到原理", "Back to first principles"} and _is_path_principle_body(
            body
        ):
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

    _append_section(out, handbook_section_title("what"), what)
    _append_section(out, handbook_section_title("position"), position)
    _append_section(out, handbook_section_title("flow"), _join_bodies(grouped["flow"]))
    _append_section(out, handbook_section_title("impl"), _join_bodies(grouped["impl"]))
    _append_section(out, handbook_section_title("types"), _join_bodies(grouped["types"]))
    _append_section(
        out, handbook_section_title("boundary"), _join_bodies(grouped["boundary"])
    )
    _append_section(out, handbook_section_title("not"), _join_bodies(grouped["not"]))
    _append_section(out, handbook_section_title("tips"), _join_bodies(grouped["tips"]))
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


def is_watery_handbook_text(text: str) -> bool:
    """True when a concept-page body is only the generic topic stub."""
    blob = (text or "").strip()
    if not blob:
        return True
    if re.search(r"`[^`]+\:\d+", blob):
        return False
    return bool(_WATERY_HANDBOOK_RE.search(blob))


def should_deepen_concept_page(concept: Any) -> bool:
    """High-importance / trunk concepts get the three handbook sections."""
    slug = getattr(concept, "slug", "") or ""
    title = getattr(concept, "title", "") or ""
    if not slug or slug == "getting-started":
        return False
    if is_shallow_path_leaf(slug) or is_filler_slug_title(slug, title):
        return False
    if slug in _PATH_RANK:
        return True
    try:
        importance = float(getattr(concept, "importance", 0) or 0)
    except (TypeError, ValueError):
        importance = 0.0
    return importance >= 0.85


def _signature_at(text: str, line: int) -> str:
    lines = (text or "").splitlines()
    if line < 1 or line > len(lines):
        return ""
    return (lines[line - 1] or "").strip()[:160]


def _defs_in_store_file(
    file_texts: dict[str, str], path: str, *, limit: int = 4
) -> list[tuple[int, str]]:
    text = file_texts.get(path) or ""
    out: list[tuple[int, str]] = []
    seen: set[str] = set()
    for i, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith(("//", "/*", "*", "#", "//!", "///")):
            continue
        if re.match(r"(?:pub\s+)?use\b", stripped):
            continue
        for match in _INDEX_DEFN_RE.finditer(line):
            name = next((g for g in match.groups() if g), "")
            if not name or name in seen or _is_dummy_symbol(name):
                continue
            if not _line_defines_symbol(line, name):
                continue
            seen.add(name)
            out.append((i, name))
            if len(out) >= limit:
                return out
    return out


def concept_definition_hits(
    concept: Any,
    file_texts: dict[str, str] | None,
) -> list[tuple[str, int, str]]:
    """Real ``path:line Symbol`` hits from chips / refs / hints. Never invents keys."""
    store = file_texts or {}
    if not store:
        return []
    hits: list[tuple[str, int, str]] = []
    seen: set[str] = set()

    def add(path: str, line: int, symbol: str) -> None:
        path = (path or "").replace("\\", "/")
        symbol = (symbol or "").strip()
        if not path or int(line or 0) < 1 or not symbol or _is_dummy_symbol(symbol):
            return
        key = _resolve_store_key(store, path)
        if not key:
            return
        token = f"{key}:{int(line)}:{symbol}"
        if token in seen:
            return
        seen.add(token)
        hits.append((key, int(line), symbol))

    chip = path_evidence_chip(concept, file_texts=store)
    if chip and chip_is_definition_line(chip):
        path, line, symbol = parse_path_chip(chip)
        add(path, line, symbol)

    for ref in _source_refs_of(concept):
        path = (ref.path or "").replace("\\", "/")
        symbol = (ref.symbol or "").strip()
        line = int(ref.start_line or 0)
        if symbol:
            resolved = resolve_symbol_definition(store, symbol, prefer_path=path)
            if resolved:
                path, line = resolved
        add(path, line, symbol)

    slug = getattr(concept, "slug", "") or ""
    suffixes, hint_sym = _EVIDENCE_HINTS.get(slug, ((), ""))
    if hint_sym and hint_sym.lower() not in _WEAK_SYMBOLS:
        picked = _pick_symbol_in_store(store, hint_sym, slug, suffixes)
        if picked:
            add(picked[0], picked[1], hint_sym)

    if len(hits) < 3 and hits:
        for line, symbol in _defs_in_store_file(store, hits[0][0], limit=4):
            add(hits[0][0], line, symbol)
            if len(hits) >= 4:
                break
    return hits[:6]


def _sanitize_handbook_cites(text: str, file_texts: dict[str, str]) -> str:
    """Keep only pills whose path is a version_files key; stamp definition lines."""
    if not text or not file_texts:
        return (text or "").strip()
    stamped = fill_wiki_key_type_lines(text, file_texts)

    def keep_pill(match: re.Match[str]) -> str:
        inner = (match.group(1) or "").strip()
        parsed = _WIKI_PILL_RE.match(inner)
        if not parsed:
            return match.group(0)
        path = (parsed.group(1) or "").strip()
        if not path:
            return match.group(0)
        if not _resolve_store_key(file_texts, path):
            return path.rsplit("/", 1)[-1]
        return match.group(0)

    return re.sub(r"`([^`]+)`", keep_pill, stamped).strip()


def _llm_or_deterministic(llm_text: str, det_text: str, store: dict[str, str]) -> str:
    cleaned = _sanitize_handbook_cites(llm_text, store)
    if cleaned and not is_watery_handbook_text(cleaned):
        return cleaned
    return det_text


def _impl_section_body(
    concept: Any, hits: list[tuple[str, int, str]], store: dict[str, str]
) -> str:
    notes = str(getattr(concept, "implementation_notes", "") or "").strip()
    path, line, symbol = hits[0]
    chip = f"{path}:{line} {symbol}"
    shown = getattr(concept, "title", "") or getattr(concept, "slug", "") or symbol
    parts = [
        t(
            f"`{shown}` is implemented at `{chip}`.",
            f"「{shown}」的实现钉在 `{chip}`。",
        )
    ]
    sig = _signature_at(store.get(path) or "", line)
    if sig:
        parts.append(
            t(
                f"The definition line is `{sig}`.",
                f"定义行是 `{sig}`。",
            )
        )
    reading = evidence_reading(concept, chip)
    if reading:
        parts.append(reading)
    for extra_path, extra_line, extra_sym in hits[1:3]:
        parts.append(
            t(
                f"Related definition: `{extra_path}:{extra_line} {extra_sym}`.",
                f"相关定义：`{extra_path}:{extra_line} {extra_sym}`。",
            )
        )
    return _llm_or_deterministic(notes, "\n\n".join(parts), store)


def _type_role_for(symbol: str, slug: str) -> str:
    roles = {
        "start_turn": t("starts one turn and must call the model next", "开一轮，下一记必须调模型"),
        "ToolBridge": t("runs a tool call by name after the model returns", "模型返回后按名执行 tool call"),
        "Pager": t("writes streaming output into the terminal buffer", "把流式输出写入终端缓冲"),
        "AgentRuntime": t("owns cancel / in-flight abort for the session", "持有取消与 in-flight 中断"),
        "main": t("process entry — the first call that actually runs", "进程入口，真正跑起来的第一记调用"),
        "connect": t("ACP door: hands the channel to a session", "ACP 那扇门：把通道交给会话"),
    }
    return roles.get(symbol) or t("a role on this call path", "这条调用链上的角色")


def _types_section_body(
    concept: Any, hits: list[tuple[str, int, str]], store: dict[str, str]
) -> str:
    slug = getattr(concept, "slug", "") or ""
    lead: list[str] = []
    flow = flow_narrative(slug, getattr(concept, "title", "") or "")
    if flow:
        path, line, symbol = hits[0]
        lead.append(f"{flow} `{path}:{line} {symbol}`")
    bullets: list[str] = []
    extra_roles = getattr(concept, "key_type_roles", None) or []
    if isinstance(extra_roles, list):
        for item in extra_roles:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or item.get("symbol") or "").strip()
            path = str(item.get("path") or "").strip()
            try:
                line = int(item.get("line") or 0)
            except (TypeError, ValueError):
                line = 0
            role = str(item.get("role") or "").strip()
            if name and path:
                resolved = resolve_symbol_definition(store, name, prefer_path=path)
                if resolved:
                    path, line = resolved
            if name and path and line and _resolve_store_key(store, path):
                bullets.append(
                    f"- {name} — {role or _type_role_for(name, slug)} — `{path}:{line} {name}`"
                )
    if not bullets:
        for path, line, symbol in hits:
            bullets.append(
                f"- {symbol} — {_type_role_for(symbol, slug)} — `{path}:{line} {symbol}`"
            )
    return "\n\n".join([*lead, *bullets]).strip()


def _boundary_section_body(
    concept: Any, hits: list[tuple[str, int, str]], store: dict[str, str]
) -> str:
    path, line, symbol = hits[0]
    chip = f"{path}:{line} {symbol}"
    items: list[str] = []
    for note in list(getattr(concept, "boundary_notes", None) or []) + list(
        getattr(concept, "not_this", None) or []
    ):
        text = str(note or "").strip()
        if not text:
            continue
        cleaned = _sanitize_handbook_cites(text, store)
        if cleaned:
            items.append(f"- {cleaned.lstrip('- ').strip()}")
    items.append(
        t(
            f"- The claim is pinned at `{chip}`; `{symbol}` is the type, not a folder name.",
            f"- 主张钉在 `{chip}`：`{symbol}` 是类型，不是目录名。",
        )
    )
    items.append(
        t(
            f"- This is not a directory or crate name. The claim is `{symbol}` at `{path}:{line}`.",
            f"- 这不是目录名或 crate 名。主张是 `{path}:{line}` 上的 `{symbol}`。",
        )
    )
    # unique, keep order
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        out.append(item)
    return "\n".join(out[:6])


_HANDBOOK_SECTION_ALIASES = {
    "实现": ("实现要点", "Implementation details", "这条链路怎么转", "How it actually runs"),
    "Implementation": ("Implementation details", "How it actually runs", "实现要点"),
    "关键类型": ("关键类型在链路上的职责", "Key types and their roles"),
    "Key types": ("Key types and their roles", "关键类型在链路上的职责"),
    "边界": ("边界条件", "Boundary conditions", "失败与边界"),
    "Boundaries": ("Boundary conditions", "Failures and edges"),
}


def _upsert_handbook_section(content: str, heading: str, body: str) -> str:
    body = (body or "").strip()
    if not body:
        return content
    block = f"## {heading}\n\n{body}\n\n"
    names = (heading, *(_HANDBOOK_SECTION_ALIASES.get(heading) or ()))
    pattern = re.compile(
        rf"(?ms)^## (?:{'|'.join(re.escape(n) for n in names)})\n.*?(?=^## |\Z)"
    )
    match = pattern.search(content or "")
    if match:
        existing = match.group(0)
        if not is_watery_handbook_text(existing):
            return content
        return pattern.sub(block, content, count=1)
    insert_at = re.search(
        r"(?m)^## (不是什么|What this is not|术语|Terms|术语小贴士|Term tips|先读|Read first|接下来|Next)\s*$",
        content or "",
    )
    if insert_at:
        return content[: insert_at.start()] + block + content[insert_at.start() :]
    return (content or "").rstrip() + "\n\n" + block


def deepen_concept_markdown(
    content: str,
    concept: Any,
    file_texts: dict[str, str] | None,
) -> str:
    """Fill implementation / key types / boundaries from the definition index.

    No-op without a store or when the concept is a low-rank stub. Existing
    non-watery sections are kept. Never invents paths missing from version_files.
    """
    store = file_texts or {}
    if not content or not store or not should_deepen_concept_page(concept):
        return content
    hits = concept_definition_hits(concept, store)
    if not hits:
        return content
    content = _upsert_handbook_section(
        content,
        handbook_section_title("impl"),
        _impl_section_body(concept, hits, store),
    )
    content = _upsert_handbook_section(
        content,
        handbook_section_title("types"),
        _types_section_body(concept, hits, store),
    )
    content = _upsert_handbook_section(
        content,
        handbook_section_title("boundary"),
        _boundary_section_body(concept, hits, store),
    )
    return re.sub(r"\n{3,}", "\n\n", content).rstrip() + "\n"
