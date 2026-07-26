import { useEffect, useMemo, useRef, useState } from "react";
import { recallstackApi, type WikiSearchResult } from "../lib/recallstackApi";

interface Props {
  open: boolean;
  repositoryId: string;
  /** Seed query, e.g. text the reader selected in the article. */
  initialQuery?: string;
  onClose: () => void;
  onOpenPage: (pageId: string) => void;
}

const KIND_LABEL: Record<WikiSearchResult["kind"], string> = {
  overview: "总览",
  architecture: "架构",
  guide: "导读",
  module: "模块",
  concept: "词条",
  page: "页面",
};

/**
 * Wiki-wide search.
 *
 * A wiki without search is a folder of files, so this is bound to ⌘K/Ctrl-K and
 * is reachable from anywhere in the reader.
 */
export default function CommandPalette({
  open,
  repositoryId,
  initialQuery,
  onClose,
  onOpenPage,
}: Props) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<WikiSearchResult[]>([]);
  const [active, setActive] = useState(0);
  const [loading, setLoading] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!open) return;
    setQuery(initialQuery ?? "");
    setActive(0);
    // Focus after paint so the caret lands in the field on first open.
    const id = window.setTimeout(() => inputRef.current?.select(), 20);
    return () => window.clearTimeout(id);
  }, [open, initialQuery]);

  useEffect(() => {
    if (!open) return;
    const trimmed = query.trim();
    if (!trimmed) {
      setResults([]);
      setLoading(false);
      return;
    }
    const controller = new AbortController();
    setLoading(true);
    // Debounce: typing a word should not fire a request per keystroke.
    const timer = window.setTimeout(async () => {
      try {
        const res = await recallstackApi.searchWiki(repositoryId, trimmed, 20, controller.signal);
        setResults(res.results);
        setActive(0);
      } catch {
        if (!controller.signal.aborted) setResults([]);
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    }, 140);
    return () => {
      controller.abort();
      window.clearTimeout(timer);
    };
  }, [query, open, repositoryId]);

  const terms = useMemo(
    () => query.trim().split(/\s+/).filter((t) => t.length > 1),
    [query],
  );

  if (!open) return null;

  function choose(index: number) {
    const hit = results[index];
    if (!hit) return;
    onOpenPage(hit.page_id);
    onClose();
  }

  function onKeyDown(e: React.KeyboardEvent) {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive((i) => Math.min(i + 1, results.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((i) => Math.max(i - 1, 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      choose(active);
    } else if (e.key === "Escape") {
      e.preventDefault();
      onClose();
    }
  }

  return (
    <div className="rs-palette-backdrop" onMouseDown={onClose} role="presentation">
      <div
        className="rs-palette"
        onMouseDown={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label="搜索 Wiki"
      >
        <div className="rs-palette-input">
          <span aria-hidden className="rs-palette-icon">
            ⌕
          </span>
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={onKeyDown}
            placeholder="搜索页面、词条、文件名…"
            autoComplete="off"
            spellCheck={false}
          />
          <kbd className="rs-kbd">esc</kbd>
        </div>

        <div className="rs-palette-results">
          {!query.trim() ? (
            <p className="rs-palette-empty">输入关键字搜索整个 Wiki，支持文件名与中文。</p>
          ) : loading && !results.length ? (
            <p className="rs-palette-empty">搜索中…</p>
          ) : !results.length ? (
            <p className="rs-palette-empty">没有匹配「{query.trim()}」的内容。</p>
          ) : (
            <ul>
              {results.map((hit, i) => (
                <li key={hit.page_id}>
                  <button
                    type="button"
                    className={`rs-palette-item ${i === active ? "is-active" : ""}`}
                    onMouseEnter={() => setActive(i)}
                    onClick={() => choose(i)}
                  >
                    <span className="rs-palette-kind">{KIND_LABEL[hit.kind] ?? "页面"}</span>
                    <span className="min-w-0 flex-1">
                      <span className="rs-palette-title">{highlight(hit.title, terms)}</span>
                      {hit.snippet && (
                        <span className="rs-palette-snippet">{highlight(hit.snippet, terms)}</span>
                      )}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="rs-palette-foot">
          <span>
            <kbd className="rs-kbd">↑</kbd>
            <kbd className="rs-kbd">↓</kbd> 选择
          </span>
          <span>
            <kbd className="rs-kbd">↵</kbd> 打开
          </span>
          <span className="ml-auto">{results.length ? `${results.length} 个结果` : ""}</span>
        </div>
      </div>
    </div>
  );
}

/** Wrap query terms in <mark> without going through innerHTML. */
function highlight(text: string, terms: string[]): React.ReactNode {
  if (!terms.length) return text;
  const escaped = terms.map((t) => t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
  const parts = text.split(new RegExp(`(${escaped.join("|")})`, "gi"));
  const lowered = terms.map((t) => t.toLowerCase());
  return parts.map((part, i) =>
    lowered.includes(part.toLowerCase()) ? <mark key={i}>{part}</mark> : part,
  );
}
