/**
 * Display-time overlay for the core learning path.
 *
 * Mirrors `recallstack.learning.learning_contract` so persisted scans still
 * hide folder-inventory filler and show a first-principles mission.
 */

export const CORE_PATH_CAP = 8;

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
  "terminal-ui": 7,
  "tui-pager": 8,
  "context-assembly": 9,
  "agent-runtime": 10,
  "session-lifecycle": 11,
  "conversation-store": 12,
};

const FILLER_TITLE = /^(Module:|模块[:：]|Key file:|关键文件[:：]|Focus:|聚焦[:：])/i;
const FILLER_SLUG = /^(module-|file-|focus-)/;
const FILLER_NAME = /(README\.md|Cargo\.toml|__init__\.py|package\.json)/i;

export const PATH_MISSION: [string, string] = [
  "先看进程怎么进，再看一轮对话怎么转，最后才看工具和界面。每一步只问：这一层不存在，系统还能不能工作。",
  "Walk the trunk first: how the process starts, how one turn runs, then tools and UI. At each step ask only: if this layer vanished, could the system still work?",
];

const STEP_TASKS: Record<string, [string, string]> = {
  "project-goal": [
    "用一句话说清：用户在终端里回车之后，系统靠哪三层（入口、一轮循环、模型调用）才能答上来。",
    "In one sentence: after the user hits Enter in the terminal, which three layers (entry, one turn, model call) must exist for an answer to come back?",
  ],
  "entry-and-boot": [
    "打开 grok 二进制入口，指出进程启动后第一个被构造的运行时是什么。",
    "Open the grok binary entry and name the first runtime constructed after the process starts.",
  ],
  "application-entry": [
    "打开入口文件，指出进程启动后最先调用的三步（不是某个 crate 的名字）。",
    "Open the entrypoint and name the first three calls after the process starts — not a crate name.",
  ],
  "agent-loop": [
    "打开证据，指出谁在 start_turn 之后调模型（不是先跑工具）。",
    "Open the evidence and point to who calls the model after start_turn (not tools first).",
  ],
  "call-flow": [
    "顺着一轮对话，指出输入进 turn 之后到模型被调用之间经过谁。",
    "Follow one turn: name who runs between input entering the turn and the model being called.",
  ],
  "runtime-loop": [
    "打开证据，指出谁在 start_turn 之后调模型（不是先跑工具）。",
    "Open the evidence and point to who calls the model after start_turn (not tools first).",
  ],
  "tool-system": [
    "打开 ToolBridge，指出模型给出 tool call 之后谁按名字执行。",
    "Open ToolBridge and point to who dispatches a tool call by name after the model returns it.",
  ],
  "terminal-ui": [
    "打开 Pager，指出模型流式输出时字写进哪一块缓冲区。",
    "Open Pager and point to which buffer streaming model output is written into.",
  ],
  "tui-pager": [
    "打开 Pager，指出模型流式输出时字写进哪一块缓冲区。",
    "Open Pager and point to which buffer streaming model output is written into.",
  ],
  "context-assembly": [
    "打开 replace_or_insert_system_head，指出系统头是写进窗口头还是拼在用户消息后面。",
    "Open replace_or_insert_system_head and say whether the system head is written at the window head or appended after the user message.",
  ],
  "agent-runtime": [
    "打开运行时类型，指出一轮循环自己构造不了、必须由它持有的是什么。",
    "Open the runtime type and point to what it owns that the turn loop cannot construct by itself.",
  ],
  "configuration": [
    "找出配置从哪进入运行时，并指出它改变的一个行为。",
    "Find where config enters runtime and name one behaviour it changes.",
  ],
  "request-routing": [
    "顺着一个外部请求往里追：哪个文件接住它，哪个函数处理它。",
    "Trace one request from the outside in: which file receives it, which function handles it.",
  ],
  "authentication": [
    "指出身份在哪被检查，以及失败时会发生什么。",
    "Point to where identity is checked, and what happens if it fails.",
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
    `打开证据，指出「${shown}」在一次真实调用里必须发生的那一步（不要用目录名回答）。`,
    `Open the evidence and point to the step \`${shown}\` must perform on a real call — not a directory name.`,
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
