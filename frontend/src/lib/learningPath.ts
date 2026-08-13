/**
 * Display-time overlay for the core learning path.
 *
 * Mirrors `recallstack.learning.learning_contract` so persisted scans still
 * hide folder-inventory filler and show a first-principles mission.
 */

export const CORE_PATH_CAP = 8;

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

const FILLER_TITLE = /^(Module:|模块[:：]|Key file:|关键文件[:：]|Focus:|聚焦[:：])/i;
const FILLER_SLUG = /^(module-|file-|focus-)/;
const FILLER_NAME = /(README\.md|Cargo\.toml|__init__\.py|package\.json)/i;

export const PATH_MISSION: [string, string] = [
  "走完这条路径，你要能不靠目录、用自己的话讲清「这个仓库解决什么问题、进程从哪启动、请求怎么走、状态存在哪、失败时怎么办」。",
  "When you finish this path you should be able to explain, in your own words and without leaning on the folder tree: what problem this repo solves, where the process starts, how a request moves, where state lives, and what happens on failure.",
];

const STEP_TASKS: Record<string, [string, string]> = {
  "project-goal": [
    "用两句话写出这个仓库为谁、解决什么、明确不做什么。",
    "Write two sentences: who this repo is for, what problem it solves, and what it explicitly does not do.",
  ],
  "application-entry": [
    "点开入口文件，说出进程启动后最先调用的三步。",
    "Open the entrypoint and name the first three calls after the process starts.",
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
  "call-flow": [
    "顺着一次调用从入口走到副作用，按顺序列出函数。",
    "Follow one call from entry to a side effect; name the functions in order.",
  ],
  "module-boundaries": [
    "指出两个模块，以及绝不能漏过去的那条职责边界。",
    "Name two modules and the one responsibility that must not leak across them.",
  ],
};

export function isFillerConcept(slug: string, title: string): boolean {
  if (CORE_SLUGS.has(slug)) return false;
  if (FILLER_SLUG.test(slug)) return true;
  if (FILLER_TITLE.test(title)) return true;
  if (FILLER_NAME.test(title)) return true;
  return false;
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
    `打开「${shown}」的证据，用自己的话讲清这一层为什么必须存在。`,
    `Open the evidence for \`${shown}\` and explain, in your own words, why this layer must exist.`,
  );
}

export function corePathNodes<
  T extends { concept?: { slug?: string; title?: string } | null },
>(nodes: T[]): T[] {
  const filtered = nodes.filter((n) => {
    const slug = n.concept?.slug || "";
    const title = n.concept?.title || "";
    return !isFillerConcept(slug, title);
  });
  return filtered.slice(0, CORE_PATH_CAP);
}
