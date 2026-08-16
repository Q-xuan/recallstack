/**
 * Display-time overlay for the core learning path.
 *
 * Mirrors `recallstack.learning.learning_contract` so persisted scans still
 * hide folder-inventory filler and show a first-principles mission.
 */

export const CORE_PATH_CAP = 10;

/** Step-task copy for well-known slugs. Not the default path for every repo. */
export const CORE_SLUGS = new Set([
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
]);

const WEB_FILLER_SLUGS = new Set([
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
]);

const PATH_RANK: Record<string, number> = {
  "project-goal": 0,
  "entry-and-boot": 1,
  "application-entry": 2,
  "agent-loop": 3,
  "call-flow": 4,
  "runtime-loop": 5,
  "tool-system": 6,
  "session-lifecycle": 7,
  "agent-runtime": 8,
  "acp-protocol": 9,
  "context-assembly": 10,
  "terminal-ui": 11,
  "tui-pager": 12,
  "conversation-store": 13,
  "system-prompt": 14,
};

const FILLER_TITLE = /^(Module:|模块[:：]|Key file:|关键文件[:：]|Focus:|聚焦[:：])/i;
const FILLER_SLUG = /^(module-|file-|focus-)/;
const FILLER_NAME = /(README\.md|Cargo\.toml|__init__\.py|package\.json)/i;

export const PATH_MISSION: [string, string] = [
  "你要能指出进程怎么进、一轮怎么转，以及硬弯：工具写回、取消、ACP 和 TUI 两扇门。每一层你签字：这一层不存在，用户能看见的哪件事会死。",
  "You own the trunk: how the process starts, how one turn runs, then the hard turns — tool write-back, cancel, ACP vs TUI. You sign off each layer: if it vanished, which user-visible thing dies?",
];

const STEP_TASKS: Record<string, [string, string]> = {
  "project-goal": [
    "你负责：对着证据那一行，证明用户被放在终端对话里还是 crate 清单里。说出入口、一轮循环、start_turn 里少了哪一层回车没回答，并签字。",
    "You own this: on the evidence line, prove whether the user lives in a terminal turn or a crate list. Name which of entry / one turn / start_turn would make Enter produce no answer — then sign off.",
  ],
  "entry-and-boot": [
    "你负责：排除「都是入口」。指出 connect 之后谁接手、TUI 那扇门交给谁，并签字。",
    "You own this: rule out “both are entry”. Point to who receives control after connect, and who receives it after the TUI door — then sign off.",
  ],
  "application-entry": [
    "你负责：打开入口文件，指出进程启动后最先调用的三步（不是某个 crate 的名字），并签字。",
    "You own this: open the entrypoint and name the first three calls after the process starts — not a crate name — then sign off.",
  ],
  "agent-loop": [
    "你负责：打开证据，指出谁在 start_turn 之后调模型（不是先跑工具）。写出那个函数名，并签字。",
    "You own this: open the evidence and point to who calls the model after start_turn (not tools first). Write that function name and sign off.",
  ],
  "call-flow": [
    "你负责：顺着一轮对话，指出输入进 turn 之后到模型被调用之间经过谁，并签字。",
    "You own this: follow one turn and name who runs between input entering the turn and the model being called — then sign off.",
  ],
  "runtime-loop": [
    "你负责：打开证据，指出谁在 start_turn 之后调模型（不是先跑工具）。写出那个函数名，并签字。",
    "You own this: open the evidence and point to who calls the model after start_turn (not tools first). Write that function name and sign off.",
  ],
  "tool-system": [
    "你负责：指出 start_turn 之后谁把 tool 结果写回再调模型。写出函数名，不要说「工具层」，并签字。",
    "You own this: point to who writes the tool result back and calls the model again after start_turn. Name the function — not “the tool layer” — and sign off.",
  ],
  "terminal-ui": [
    "你负责：打开 Pager，指出模型流式输出时字写进哪一块缓冲区。写出字段或函数名，并签字。",
    "You own this: open Pager and point to which buffer streaming output is written into. Name the field or function and sign off.",
  ],
  "tui-pager": [
    "你负责：打开 Pager，指出模型流式输出时字写进哪一块缓冲区。写出字段或函数名，并签字。",
    "You own this: open Pager and point to which buffer streaming output is written into. Name the field or function and sign off.",
  ],
  "context-assembly": [
    "你负责：打开 replace_or_insert_system_head，证明系统头是写进窗口头还是拼在用户消息后面，并签字。",
    "You own this: open replace_or_insert_system_head and prove whether the system head is written at the window head or appended after the user — then sign off.",
  ],
  "agent-runtime": [
    "你负责：指出用户取消一轮时谁把还在飞的模型调用停掉。若停不掉，说出终端上会留下什么，并签字。",
    "You own this: point to who stops an in-flight model call when the user cancels. If that stop never fires, name what the terminal still shows — then sign off.",
  ],
  "session-lifecycle": [
    "你负责：指出用户取消一轮时谁把还在飞的模型调用停掉。若停不掉，说出终端上会留下什么，并签字。",
    "You own this: point to who stops an in-flight model call when the user cancels. If that stop never fires, name what the terminal still shows — then sign off.",
  ],
  "acp-protocol": [
    "你负责：证明 ACP 的 connect 和 TUI 入口是两扇门还是同一条路。connect 之后谁持有会话，并签字。",
    "You own this: prove whether ACP connect and the TUI entry are two doors or one road. After connect, who holds the session? Sign off.",
  ],
  "configuration": [
    "你负责：找出配置从哪进入运行时，指出它改变的一个行为，并签字。",
    "You own this: find where config enters runtime and name one behaviour it changes — then sign off.",
  ],
  "request-routing": [
    "你负责：顺着一个外部请求往里追，指出哪个文件接住它、哪个函数处理它，并签字。",
    "You own this: trace one request and name the file that receives it and the function that handles it — then sign off.",
  ],
  "authentication": [
    "你负责：指出身份在哪被检查，以及失败时会发生什么，并签字。",
    "You own this: point to where identity is checked and what happens if it fails — then sign off.",
  ],
  "data-persistence": [
    "你负责：说出被写入或读出的对象，以及做这件事的函数，并签字。",
    "You own this: name the object that is written or read, and the function that does it — then sign off.",
  ],
  "caching": [
    "你负责：说出缓存了什么，以及缓存过期时会错在哪，并签字。",
    "You own this: say what is cached and what becomes wrong if the cache is stale — then sign off.",
  ],
  "error-handling": [
    "你负责：指出一条失败路径，以及它在哪里被接住或返回，并签字。",
    "You own this: name one failure path and where it is caught or returned — then sign off.",
  ],
  "background-tasks": [
    "你负责：找出一条异步/任务路径，说出它产生的副作用，并签字。",
    "You own this: find one async/job path and say what side effect it performs — then sign off.",
  ],
  "testing-structure": [
    "你负责：打开一个测试，说出它锁住的是哪段行为，并签字。",
    "You own this: open one test and say which behaviour it is locking down — then sign off.",
  ],
  "module-boundaries": [
    "你负责：指出两个模块，以及绝不能漏过去的那条职责边界，并签字。",
    "You own this: name two modules and the one responsibility that must not leak across them — then sign off.",
  ],
};

export function isFillerConcept(slug: string, title: string): boolean {
  if (FILLER_SLUG.test(slug)) return true;
  if (FILLER_TITLE.test(title)) return true;
  if (FILLER_NAME.test(title)) return true;
  return false;
}

const SHALLOW_PATH_LEAVES = new Set([
  "codebase-graph",
  "pty-control",
  "codegen",
  "headless-modes",
  "subagent-scheduling",
]);

function isWebFiller(slug: string, wikiPageId?: string | null): boolean {
  if (!WEB_FILLER_SLUGS.has(slug)) return false;
  if ((wikiPageId || "").startsWith("topics/")) return false;
  return true;
}

function pathRank(slug: string): number {
  return PATH_RANK[slug] ?? 80;
}

export function stepTask(
  t: (zh: string, en: string) => string,
  slug: string,
  title: string,
): string {
  const mapped = STEP_TASKS[slug];
  if (mapped) return t(mapped[0], mapped[1]);
  const shown = title || slug;
  return t(
    `你负责：打开证据，指出「${shown}」在一次真实调用里必须发生的那一步（不要用目录名回答），并签字。`,
    `You own this: open the evidence and point to the step \`${shown}\` must perform on a real call — not a directory name — then sign off.`,
  );
}

export function corePathNodes<
  T extends {
    concept?: { slug?: string; title?: string; wiki_page_id?: string | null } | null;
  },
>(nodes: T[]): T[] {
  const filtered = nodes.filter((n) => {
    const slug = n.concept?.slug || "";
    const title = n.concept?.title || "";
    const wikiId = n.concept?.wiki_page_id;
    if (isFillerConcept(slug, title)) return false;
    if (isWebFiller(slug, wikiId)) return false;
    if (SHALLOW_PATH_LEAVES.has(slug)) return false;
    return true;
  });
  const slugs = new Set(filtered.map((n) => n.concept?.slug || ""));
  const deduped = slugs.has("entry-and-boot")
    ? filtered.filter((n) => n.concept?.slug !== "application-entry")
    : filtered;
  const ranked = [...deduped].sort((a, b) => {
    const sa = a.concept?.slug || "";
    const sb = b.concept?.slug || "";
    const d = pathRank(sa) - pathRank(sb);
    return d !== 0 ? d : sa.localeCompare(sb);
  });
  return ranked.slice(0, CORE_PATH_CAP);
}
