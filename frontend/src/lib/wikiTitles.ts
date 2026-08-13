/**
 * Display-time labels for structural wiki sidebar/chrome.
 *
 * Persisted payloads may still say "Overview" / "Modules" from an older
 * analyze. Mapping by page_id (then known English/Chinese titles) lets the UI
 * language switch without re-scanning. Real path segments are left alone.
 */

export type WikiTitleT = (zh: string, en: string) => string;

export interface WikiTitleSource {
  title: string;
  page_id?: string;
}

const PAGE_ID_LABELS: Record<string, [string, string]> = {
  index: ["总览", "Overview"],
  architecture: ["架构", "Architecture"],
  "reading-guide": ["导读", "Reading Guide"],
  dependencies: ["依赖", "Dependencies"],
  "modules/root": ["根目录", "Root"],
};

const GROUP_LABELS: Record<string, [string, string]> = {
  modules: ["模块", "Modules"],
  模块: ["模块", "Modules"],
  concepts: ["词条", "Concepts"],
  词条: ["词条", "Concepts"],
};

export function localizeSidebarTitle(item: WikiTitleSource, t: WikiTitleT): string {
  const id = (item.page_id || "").trim();
  const byId = PAGE_ID_LABELS[id];
  if (byId) return t(...byId);

  const raw = item.title.trim();
  const key = raw.toLowerCase();

  // Parent nodes (Modules / Concepts) have an empty page_id.
  if (!id) {
    const group = GROUP_LABELS[key] || GROUP_LABELS[raw];
    if (group) return t(...group);
  }

  return item.title;
}

export function localizeBreadcrumbSegment(segment: string, t: WikiTitleT): string {
  const key = segment.trim().toLowerCase();
  const group = GROUP_LABELS[key] || GROUP_LABELS[segment.trim()];
  if (group) return t(...group);
  return segment;
}
