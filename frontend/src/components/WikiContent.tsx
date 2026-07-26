import { useCallback, useEffect, useRef, useState } from "react";
import MermaidDiagram from "./MermaidDiagram";

export interface SelectionExplainPayload {
  selection: string;
  surroundingText: string;
  rect: { top: number; left: number; bottom: number };
}

interface Props {
  content: string;
  title: string;
  onExplain?: (payload: SelectionExplainPayload) => void;
}

export default function WikiContent({ content, title, onExplain }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const [toolbar, setToolbar] = useState<{
    selection: string;
    surroundingText: string;
    top: number;
    left: number;
  } | null>(null);

  const clearToolbar = useCallback(() => setToolbar(null), []);

  // floating toolbar for text selection
  useEffect(() => {
    const root = ref.current;
    if (!root || !onExplain) return;

    function handleMouseUp() {
      const sel = window.getSelection();
      if (!sel || sel.isCollapsed || !root) {
        return;
      }
      const text = sel.toString().trim();
      if (!text || text.length > 200) {
        setToolbar(null);
        return;
      }
      // only when selection is inside wiki content
      const anchor = sel.anchorNode;
      if (!anchor || !root.contains(anchor)) {
        setToolbar(null);
        return;
      }
      const range = sel.getRangeAt(0);
      const rect = range.getBoundingClientRect();
      const rootRect = root.getBoundingClientRect();
      const surrounding = extractSurrounding(sel.anchorNode, text);

      setToolbar({
        selection: text,
        surroundingText: surrounding,
        top: rect.top - rootRect.top + root.scrollTop - 8,
        left: Math.min(
          Math.max(rect.left - rootRect.left + rect.width / 2, 40),
          rootRect.width - 40,
        ),
      });
    }

    function handleClickOutside(e: MouseEvent) {
      const t = e.target as HTMLElement;
      if (t.closest?.("[data-explain-toolbar]")) return;
      // delay so toolbar click still works
      setTimeout(() => {
        const sel = window.getSelection();
        if (!sel || sel.isCollapsed) setToolbar(null);
      }, 0);
    }

    root.addEventListener("mouseup", handleMouseUp);
    document.addEventListener("mousedown", handleClickOutside);
    return () => {
      root.removeEventListener("mouseup", handleMouseUp);
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, [onExplain]);

  // click inline <code> to explain
  useEffect(() => {
    const root = ref.current;
    if (!root || !onExplain) return;

    function handleClick(e: MouseEvent) {
      const target = e.target as HTMLElement;
      if (target.tagName !== "CODE") return;
      // skip code inside pre blocks
      if (target.closest("pre")) return;
      const selection = (target.textContent || "").trim();
      if (!selection || selection.length > 120) return;
      e.preventDefault();
      e.stopPropagation();
      clearToolbar();
      const surrounding =
        target.closest("p, li, h1, h2, h3, blockquote, div")?.textContent?.trim() ||
        selection;
      const rect = target.getBoundingClientRect();
      onExplain?.({
        selection,
        surroundingText: surrounding.slice(0, 1200),
        rect: { top: rect.top, left: rect.left, bottom: rect.bottom },
      });
    }

    root.addEventListener("click", handleClick);
    return () => root.removeEventListener("click", handleClick);
  }, [onExplain, clearToolbar]);

  const strippedContent = stripLeadingTitleHeading(content, title);
  const parts = splitMermaid(strippedContent);

  return (
    <div ref={ref} className="relative">
      {onExplain && (
        <p className="text-[12px] text-[var(--rs-muted)] mb-5">
          划选术语点「解释」，或点击行内{" "}
          <code className="px-1.5 py-0.5 rounded bg-black/[0.04] text-[var(--rs-ink-2)]">代码符号</code>
        </p>
      )}

      {toolbar && onExplain && (
        <div
          data-explain-toolbar
          className="absolute z-20 -translate-x-1/2 -translate-y-full"
          style={{ top: toolbar.top, left: toolbar.left }}
        >
          <button
            type="button"
            className="rs-btn rs-btn-primary h-8 px-3 text-[12px] shadow-lg"
            onMouseDown={(e) => e.preventDefault()}
            onClick={() => {
              onExplain({
                selection: toolbar.selection,
                surroundingText: toolbar.surroundingText,
                rect: { top: 0, left: 0, bottom: 0 },
              });
              clearToolbar();
              window.getSelection()?.removeAllRanges();
            }}
          >
            解释「
            {toolbar.selection.length > 24
              ? toolbar.selection.slice(0, 24) + "…"
              : toolbar.selection}
            」
          </button>
        </div>
      )}

      <article className="rs-prose">
        <h1 className="rs-page-title">{title}</h1>
        {parts.map((part, i) =>
          part.type === "mermaid" ? (
            <div
              key={i}
              className="my-5 rounded-xl border border-black/5 bg-[#fbfbfd] p-3 overflow-x-auto max-h-[420px]"
            >
              <MermaidDiagram code={part.content} />
            </div>
          ) : (
            <div key={i} dangerouslySetInnerHTML={{ __html: markdownToHtml(part.content) }} />
          ),
        )}
      </article>
    </div>
  );
}

function stripLeadingTitleHeading(content: string, title: string): string {
  const lines = content.replace(/^\uFEFF/, "").split(/\r?\n/);
  let i = 0;
  while (i < lines.length && lines[i].trim() === "") i += 1;
  if (i >= lines.length) return content;

  const first = lines[i].trim();
  const m = first.match(/^#\s+(.+)$/);
  if (!m) return content;

  const heading = m[1].trim().replace(/^`|`$/g, "");
  const normalizedTitle = title.trim().replace(/^`|`$/g, "");
  // Drop duplicate page title, or any leading H1 (page chrome already shows title).
  if (
    heading === normalizedTitle ||
    heading.toLowerCase() === normalizedTitle.toLowerCase() ||
    first.startsWith("# ")
  ) {
    i += 1;
    while (i < lines.length && lines[i].trim() === "") i += 1;
    return lines.slice(i).join("\n");
  }
  return content;
}

function extractSurrounding(node: Node | null, selected: string): string {
  if (!node) return selected;
  let el: HTMLElement | null =
    node.nodeType === Node.ELEMENT_NODE
      ? (node as HTMLElement)
      : node.parentElement;
  while (el && !/^(P|LI|H1|H2|H3|BLOCKQUOTE|DIV|TD|TH)$/i.test(el.tagName)) {
    el = el.parentElement;
  }
  const text = (el?.textContent || selected).trim();
  return text.slice(0, 1200);
}

interface ContentPart {
  type: "text" | "mermaid";
  content: string;
}

function splitMermaid(md: string): ContentPart[] {
  const parts: ContentPart[] = [];
  const regex = /```mermaid\n([\s\S]*?)```/g;
  let lastIdx = 0;
  let match;

  while ((match = regex.exec(md)) !== null) {
    if (match.index > lastIdx) {
      parts.push({ type: "text", content: md.slice(lastIdx, match.index) });
    }
    parts.push({ type: "mermaid", content: match[1].trim() });
    lastIdx = match.index + match[0].length;
  }

  if (lastIdx < md.length) {
    parts.push({ type: "text", content: md.slice(lastIdx) });
  }

  return parts;
}

function markdownToHtml(md: string): string {
  let html = md;

  // code blocks (non-mermaid)
  html = html.replace(/```(\w*)\n([\s\S]*?)```/g, (_, lang, code) => {
    return `<pre><code class="language-${lang || "text"}">${escapeHtml(code.trim())}</code></pre>`;
  });

  // headings
  html = html.replace(/^### (.+)$/gm, "<h3>$1</h3>");
  html = html.replace(/^## (.+)$/gm, "<h2>$1</h2>");
  html = html.replace(/^# (.+)$/gm, "<h1>$1</h1>");

  // blockquotes
  html = html.replace(/^> (.+)$/gm, "<blockquote>$1</blockquote>");

  // bold
  html = html.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");

  // inline code — clickable affordance
  html = html.replace(
    /`([^`]+)`/g,
    '<code class="cursor-pointer hover:bg-[rgba(0,113,227,0.12)] hover:text-[var(--rs-accent)] transition-colors" title="点击解释">$1</code>',
  );

  // links
  html = html.replace(/\[(.+?)\]\((.+?)\)/g, '<a href="$2">$1</a>');

  // list items
  html = html.replace(/^- (.+)$/gm, "<li>$1</li>");
  html = html.replace(/^\d+\. (.+)$/gm, "<li>$1</li>");

  // paragraphs
  html = html.replace(
    /^(?!<[hblup]|<li|<code|<pre|<div|<strong)(.+)$/gm,
    "<p>$1</p>",
  );

  return html;
}

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
