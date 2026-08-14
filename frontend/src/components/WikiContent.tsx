import { Suspense, lazy, useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent, type MouseEvent } from "react";
import CodeBlock from "./CodeBlock";
import SourcePeek from "./SourcePeek";
import { useT } from "../lib/i18n";
import { renderMarkdown, stripLeadingTitle, type TocEntry } from "../lib/markdown";

// Mermaid pulls in cytoscape and katex. Most pages have no diagram, so it is
// loaded only when one actually appears.
const MermaidDiagram = lazy(() => import("./MermaidDiagram"));

export interface SelectionExplainPayload {
  selection: string;
  surroundingText: string;
}

interface Props {
  content: string;
  title: string;
  /** Enables the inline source viewer for `path:line` citations. */
  repositoryId?: string;
  /** Learning-path slug for first-principles peek notes. */
  learnSlug?: string;
  /** Called with an internal wiki page id when a relative link is clicked. */
  onNavigatePage?: (pageId: string) => void;
  /** Called when the reader selects text and asks to look it up. */
  onLookup?: (payload: SelectionExplainPayload) => void;
  onTocChange?: (toc: TocEntry[]) => void;
}

interface PeekState {
  ref: string;
  blockIndex: number;
}

export default function WikiContent({
  content,
  title,
  repositoryId,
  learnSlug,
  onNavigatePage,
  onLookup,
  onTocChange,
}: Props) {
  const t = useT();
  const ref = useRef<HTMLDivElement>(null);
  const [peek, setPeek] = useState<PeekState | null>(null);
  const [toolbar, setToolbar] = useState<{
    selection: string;
    surroundingText: string;
    top: number;
    left: number;
  } | null>(null);

  const { blocks, toc } = useMemo(
    () => renderMarkdown(stripLeadingTitle(content, title)),
    [content, title],
  );

  const closePeek = useCallback(() => setPeek(null), []);

  useEffect(() => {
    onTocChange?.(toc);
  }, [toc, onTocChange]);

  // A new page means the previously opened citation is no longer relevant.
  useEffect(() => {
    closePeek();
    setToolbar(null);
  }, [content, title, closePeek]);

  const clearToolbar = useCallback(() => setToolbar(null), []);

  function chipFromEvent(target: EventTarget | null): HTMLElement | null {
    const el =
      target instanceof Element
        ? target
        : target instanceof Text
          ? target.parentElement
          : null;
    if (!el) return null;
    const refEl = el.closest(".rs-ref[data-ref]") as HTMLElement | null;
    if (!refEl || (ref.current && !ref.current.contains(refEl))) return null;
    return refEl;
  }

  function togglePeek(refEl: HTMLElement) {
    const value = refEl.getAttribute("data-ref") || "";
    const wrap = refEl.closest("[data-md-block-index]") as HTMLElement | null;
    const blockIndex = wrap ? Number(wrap.getAttribute("data-md-block-index")) : -1;
    setPeek((prev) =>
      prev?.ref === value && prev?.blockIndex === blockIndex
        ? null
        : { ref: value, blockIndex },
    );
  }

  function handleClick(e: MouseEvent<HTMLDivElement>) {
    const refEl = chipFromEvent(e.target);
    if (refEl) {
      e.preventDefault();
      e.stopPropagation();
      togglePeek(refEl);
      return;
    }

    const target = e.target as HTMLElement;
    const anchor = target.closest?.("a") as HTMLAnchorElement | null;
    if (!anchor) return;
    const href = anchor.getAttribute("href") || "";
    if (!href || href.startsWith("#")) return;
    // Absolute URLs leave the app; everything else is a wiki page id.
    if (/^(https?:)?\/\//i.test(href) || href.startsWith("mailto:")) {
      anchor.target = "_blank";
      anchor.rel = "noreferrer noopener";
      return;
    }
    if (onNavigatePage) {
      e.preventDefault();
      onNavigatePage(decodeURI(href.replace(/^\.?\//, "")));
    }
  }

  function handleKey(e: KeyboardEvent<HTMLDivElement>) {
    if (e.key !== "Enter" && e.key !== " ") return;
    const refEl = chipFromEvent(e.target);
    if (!refEl) return;
    e.preventDefault();
    togglePeek(refEl);
  }

  // Selection toolbar — "look this up in the wiki".
  useEffect(() => {
    const root = ref.current;
    if (!root || !onLookup) return;

    function handleMouseUp() {
      const sel = window.getSelection();
      if (!sel || sel.isCollapsed || !root) return;
      const text = sel.toString().trim();
      if (!text || text.length > 120) {
        setToolbar(null);
        return;
      }
      const anchor = sel.anchorNode;
      if (!anchor || !root.contains(anchor)) {
        setToolbar(null);
        return;
      }
      const rect = sel.getRangeAt(0).getBoundingClientRect();
      const rootRect = root.getBoundingClientRect();
      setToolbar({
        selection: text,
        surroundingText: surroundingOf(anchor, text),
        top: rect.top - rootRect.top - 8,
        left: Math.min(
          Math.max(rect.left - rootRect.left + rect.width / 2, 60),
          rootRect.width - 60,
        ),
      });
    }

    function handleMouseDown(e: globalThis.MouseEvent) {
      if ((e.target as HTMLElement).closest?.("[data-lookup-toolbar]")) return;
      setToolbar(null);
    }

    root.addEventListener("mouseup", handleMouseUp);
    document.addEventListener("mousedown", handleMouseDown);
    return () => {
      root.removeEventListener("mouseup", handleMouseUp);
      document.removeEventListener("mousedown", handleMouseDown);
    };
  }, [onLookup]);

  return (
    <div ref={ref} className="relative" onClick={handleClick} onKeyDown={handleKey}>
      {toolbar && onLookup && (
        <div
          data-lookup-toolbar
          className="absolute z-20 -translate-x-1/2 -translate-y-full"
          style={{ top: toolbar.top, left: toolbar.left }}
        >
          <button
            type="button"
            className="rs-btn rs-btn-primary h-8 px-3 text-[12px] shadow-lg"
            onMouseDown={(e) => e.preventDefault()}
            onClick={() => {
              onLookup({
                selection: toolbar.selection,
                surroundingText: toolbar.surroundingText,
              });
              clearToolbar();
              window.getSelection()?.removeAllRanges();
            }}
          >
            {t("你来问这段", "You ask about")} 「
            {toolbar.selection.length > 18
              ? `${toolbar.selection.slice(0, 18)}…`
              : toolbar.selection}
            」
          </button>
        </div>
      )}

      <article className="rs-prose">
        {blocks.map((block, i) => {
          if (block.kind === "mermaid") {
            return (
              <Suspense key={i} fallback={<div className="rs-diagram-loading">{t("图表加载中…", "Loading diagram…")}</div>}>
                <MermaidDiagram code={block.code} />
              </Suspense>
            );
          }
          if (block.kind === "code") {
            return <CodeBlock key={i} code={block.code} lang={block.lang} />;
          }
          return (
            <div key={i} data-md-block-index={i}>
              <div dangerouslySetInnerHTML={{ __html: block.html }} />
              {peek?.blockIndex === i && (
                <div data-peek-slot="">
                  <SourcePeek
                    repositoryId={repositoryId}
                    reference={peek.ref}
                    slug={learnSlug}
                    onClose={closePeek}
                  />
                </div>
              )}
            </div>
          );
        })}
      </article>
    </div>
  );
}

function surroundingOf(node: Node | null, fallback: string): string {
  let el: HTMLElement | null =
    node?.nodeType === Node.ELEMENT_NODE ? (node as HTMLElement) : node?.parentElement || null;
  while (el && !/^(P|LI|H1|H2|H3|H4|BLOCKQUOTE|TD|TH)$/i.test(el.tagName)) {
    el = el.parentElement;
  }
  return (el?.textContent || fallback).trim().slice(0, 1200);
}
