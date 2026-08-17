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
  "capability-seam": 3,
  "plugin-architecture": 4,
  "core-architecture": 5,
  "cordis": 6,
  "core": 7,
  "agent-loop": 8,
  "call-flow": 9,
  "runtime-loop": 10,
  "tool-system": 11,
  "session-lifecycle": 12,
  "agent-runtime": 13,
  "acp-protocol": 14,
  "context-assembly": 15,
  "terminal-ui": 16,
  "tui-pager": 17,
  "conversation-store": 18,
  "system-prompt": 19,
};

const FILLER_TITLE = /^(Module:|模块[:：]|Key file:|关键文件[:：]|Focus:|聚焦[:：])/i;
const FILLER_SLUG = /^(module-|file-|focus-)/;
const FILLER_NAME = /(README\.md|Cargo\.toml|__init__\.py|package\.json)/i;

export const PATH_MISSION: [string, string] = [
  "主干是进程怎么进、本仓库的核心系统怎么接，以及 seam / 硬弯落在哪。每一层对照本仓库证据看调用，不套另一仓库的词表。",
  "The trunk is how the process starts, how this repo's core systems join, and where the seam or hard turn sits. Follow evidence from this tree, not a vocabulary copied from another repository.",
];

const STEP_TASKS: Record<string, [string, string]> = {
  "project-goal": [
    "对着证据那一行，说明这个仓库给谁用、一次真实运行必须成立的约束。不要用目录清单回答。",
    "On the evidence line, say who this repo is for and what must stay true for a real run. Name the constraint — not a folder list.",
  ],
  "entry-and-boot": [
    "打开进程入口，指出第一记调用之后谁接手（不要用包名回答）。",
    "Open the process entry and name who receives control after the first call — not a package name.",
  ],
  "application-entry": [
    "打开入口文件，指出进程启动后最先调用的三步（不是某个 crate 的名字）。",
    "Open the entrypoint and name the first three calls after the process starts — not a crate name.",
  ],
  "agent-loop": [
    "打开证据：start_turn 之后谁调模型（不是先跑工具）。写出那个函数名。",
    "Open the evidence: who calls the model after start_turn (not tools first). Write that function name.",
  ],
  "call-flow": [
    "顺着一轮对话，指出输入进 turn 之后到模型被调用之间经过谁。",
    "Follow one turn and name who runs between input entering the turn and the model being called.",
  ],
  "runtime-loop": [
    "打开证据：start_turn 之后谁调模型（不是先跑工具）。写出那个函数名。",
    "Open the evidence: who calls the model after start_turn (not tools first). Write that function name.",
  ],
  "tool-system": [
    "指出 start_turn 之后谁把 tool 结果写回再调模型。写出函数名，不要说「工具层」。",
    "Point to who writes the tool result back and calls the model again after start_turn. Name the function — not “the tool layer”.",
  ],
  "terminal-ui": [
    "打开 Pager，指出模型流式输出时字写进哪一块缓冲区。写出字段或函数名。",
    "Open Pager and point to which buffer streaming output is written into. Name the field or function.",
  ],
  "tui-pager": [
    "打开 Pager，指出模型流式输出时字写进哪一块缓冲区。写出字段或函数名。",
    "Open Pager and point to which buffer streaming output is written into. Name the field or function.",
  ],
  "context-assembly": [
    "打开 replace_or_insert_system_head，证明系统头是写进窗口头还是拼在用户消息后面。",
    "Open replace_or_insert_system_head and prove whether the system head is written at the window head or appended after the user.",
  ],
  "agent-runtime": [
    "指出用户取消一轮时谁把还在飞的模型调用停掉。若停不掉，说出终端上会留下什么。",
    "Point to who stops an in-flight model call when the user cancels. If that stop never fires, name what the terminal still shows.",
  ],
  "session-lifecycle": [
    "指出用户取消一轮时谁把还在飞的模型调用停掉。若停不掉，说出终端上会留下什么。",
    "Point to who stops an in-flight model call when the user cancels. If that stop never fires, name what the terminal still shows.",
  ],
  "acp-protocol": [
    "证明 ACP 的 connect 和 TUI 入口是两扇门还是同一条路。connect 之后谁持有会话。",
    "Prove whether ACP connect and the TUI entry are two doors or one road. After connect, who holds the session?",
  ],
  "configuration": [
    "找出配置从哪进入运行时，指出它改变的一个行为。",
    "Find where config enters runtime and name one behaviour it changes.",
  ],
  "request-routing": [
    "顺着一个外部请求往里追，指出哪个文件接住它、哪个函数处理它。",
    "Trace one request and name the file that receives it and the function that handles it.",
  ],
  "authentication": [
    "指出身份在哪被检查，以及失败时会发生什么。",
    "Point to where identity is checked and what happens if it fails.",
  ],
  "data-persistence": [
    "说出被写入或读出的对象，以及做这件事的函数。",
    "Name the object that is written or read, and the function that does it.",
  ],
  "caching": [
    "说出缓存了什么，以及缓存过期时会错在哪。",
    "Say what is cached and what becomes wrong if the cache is stale.",
  ],
  "error-handling": [
    "指出一条失败路径，以及它在哪里被接住或返回。",
    "Name one failure path and where it is caught or returned.",
  ],
  "background-tasks": [
    "找出一条异步/任务路径，说出它产生的副作用。",
    "Find one async/job path and say what side effect it performs.",
  ],
  "testing-structure": [
    "打开一个测试，说出它锁住的是哪段行为。",
    "Open one test and say which behaviour it is locking down.",
  ],
  "module-boundaries": [
    "指出两个模块，以及绝不能漏过去的那条职责边界。",
    "Name two modules and the one responsibility that must not leak across them.",
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
    `打开证据，指出「${shown}」在调用链上必须发生的那一步（不要用目录名回答）。`,
    `Open the evidence and point to the step \`${shown}\` must perform on the call path — not a directory name.`,
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
