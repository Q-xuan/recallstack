import { useSyncExternalStore } from "react";

export type Lang = "zh" | "en";

const STORAGE_KEY = "recallstack_lang";
const listeners = new Set<() => void>();

function detect(): Lang {
  const stored = localStorage.getItem(STORAGE_KEY);
  if (stored === "zh" || stored === "en") return stored;
  return navigator.language?.toLowerCase().startsWith("zh") ? "zh" : "en";
}

let current: Lang = detect();

export function setLang(lang: Lang): void {
  current = lang;
  localStorage.setItem(STORAGE_KEY, lang);
  document.documentElement.lang = lang === "zh" ? "zh-CN" : "en";
  listeners.forEach((fn) => fn());
}

function subscribe(fn: () => void): () => void {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

/** Current UI language; re-renders the component when it changes. */
export function useLang(): [Lang, (lang: Lang) => void] {
  const lang = useSyncExternalStore(subscribe, () => current);
  return [lang, setLang];
}

/**
 * Inline translation: `t("中文", "English")`.
 *
 * The pair lives at the call site, mirroring the backend's `t(en, zh)` — no
 * key registry to drift out of sync, and the reader of the code sees both
 * languages where they are used.
 */
export function useT(): (zh: string, en: string) => string {
  const [lang] = useLang();
  return (zh: string, en: string) => (lang === "zh" ? zh : en);
}

/** For non-hook call sites (module-level constants must not use this). */
export function tNow(zh: string, en: string): string {
  return current === "zh" ? zh : en;
}
