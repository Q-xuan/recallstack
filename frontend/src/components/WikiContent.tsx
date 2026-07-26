import { Suspense, lazy, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
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
  /** Called with an internal wiki page id when a relative link is clicked. */
  onNavigatePage?: (pageId: string) => void;
  /** Called when the reader selects text and asks to look it up. */
  onLookup?: (payload: SelectionExplainPayload) => void;
  onTocChange?: (toc: TocEntry[]) => void;
}

export default function WikiContent({
  content,
  title,
  repositoryId,
  onNavigatePage,
  onLookup,
  onTocChange,
}: Props) {
  const t = useT();
  const ref = useRef<HTMLDivElement>(null);
  // The peek is portalled into a slot injected right after the citation's own
  // block, so the code appears where the claim was made instead of at the end.
  const [peek, setPeek] = useState<{ reference: string; slot: HTMLElement } | null>(null);
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

  const closePeek = useCallback(() => {
    setPeek((prev) => {
      prev?.slot.remove();
      return null;
    });
  }, []);

  useEffect(() => {
    onTocChange?.(toc);
  }, [toc, onTocChange]);

  // A new page means the previously opened citation is no longer relevant.
  useEffect(() => {
    closePeek();
    setToolbar(null);
  }, [content, title, closePeek]);

  useEffect(() => closePeek, [closePeek]);

  const clearToolbar = useCallback(() => setToolbar(null), []);

  // Read inside the click handler without making it depend on `peek`, which
  // would tear down and rebuild the listener on every open/close.
  const peekRef = useRef(peek);
  peekRef.current = peek;

  // Clicks inside rendered HTML: source citations and internal wiki links.
  useEffect(() => {
    const root = ref.current;
    if (!root) return;

    function openPeek(refEl: HTMLElement, value: string) {
      const host = (refEl.closest("li, p, td, blockquote") as HTMLElement | null) ?? refEl;
      const slot = document.createElement("div");
      slot.dataset.peekSlot = "";
      host.after(slot);
      setPeek((prev) => {
        prev?.slot.remove();
        return { reference: value, slot };
      });
    }

    function handleClick(e: MouseEvent) {
      const target = e.target as HTMLElement;

      const refEl = target.closest?.("[data-ref]") as HTMLElement | null;
      if (refEl && repositoryId) {
        e.preventDefault();
        const value = refEl.getAttribute("data-ref") || "";
        if (peekRef.current?.reference === value) closePeek();
        else openPeek(refEl, value);
        return;
      }

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

    root.addEventListener("click", handleClick);
    return () => root.removeEventListener("click", handleClick);
  }, [repositoryId, onNavigatePage, closePeek, blocks]);

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

    function handleMouseDown(e: MouseEvent) {
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
    <div ref={ref} className="relative">
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
            {t("在 Wiki 中查找", "Search wiki for")} 「
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
          return <div key={i} dangerouslySetInnerHTML={{ __html: block.html }} />;
        })}
      </article>

      {peek &&
        repositoryId &&
        createPortal(
          <SourcePeek
            repositoryId={repositoryId}
            reference={peek.reference}
            onClose={closePeek}
          />,
          peek.slot,
        )}
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
