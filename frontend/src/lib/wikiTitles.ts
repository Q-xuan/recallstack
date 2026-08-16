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
  index: ["概述", "Overview"],
  architecture: ["架构概览", "Architecture"],
  "getting-started": ["快速开始", "Quick start"],
  "reading-guide": ["导读", "Reading Guide"],
  dependencies: ["依赖", "Dependencies"],
  "modules/root": ["根目录", "Root"],
};

const GROUP_LABELS: Record<string, [string, string]> = {
  modules: ["按目录", "By directory"],
  模块: ["按目录", "By directory"],
  "by directory": ["按目录", "By directory"],
  按目录: ["按目录", "By directory"],
  concepts: ["词条", "Concepts"],
  词条: ["词条", "Concepts"],
  "getting started": ["入门指南", "Getting Started"],
  入门指南: ["入门指南", "Getting Started"],
  "deep dive": ["深入探索", "Deep Dive"],
  深入探索: ["深入探索", "Deep Dive"],
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
