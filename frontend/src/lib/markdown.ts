/**
 * A small CommonMark-ish renderer for generated wiki pages.
 *
 * The previous implementation was a flat chain of regex replacements, which
 * produced invalid HTML (bare `<li>` with no list wrapper, so bullets and
 * numbering silently vanished) and had no support for tables, nesting, or
 * emphasis. Wiki pages are the product here, so they need a real parser.
 *
 * Output is a list of blocks rather than one HTML string: code and diagrams
 * become React components (syntax highlighting, copy buttons, Mermaid) while
 * prose stays cheap innerHTML.
 */

export type MarkdownBlock =
  | { kind: "html"; html: string }
  | { kind: "code"; lang: string; code: string }
  | { kind: "mermaid"; code: string };

export interface TocEntry {
  id: string;
  text: string;
  level: number;
}

export interface RenderedMarkdown {
  blocks: MarkdownBlock[];
  toc: TocEntry[];
}

/** Matches `src/foo/bar.py`, optionally with `:12` or `:12-40`. */
const SOURCE_REF_RE = /^[A-Za-z0-9_@][A-Za-z0-9_./\\-]*\.[A-Za-z0-9]+(:\d+(-\d+)?)?$/;

/** README chrome that should never render as raw tags in a wiki article. */
const HTML_CHROME_RE = /<(div|picture|source|img)\b|srcset\s*=/i;

export function isHtmlChrome(text: string): boolean {
  return HTML_CHROME_RE.test(text);
}

const FENCE_RE = /^ {0,3}(`{3,}|~{3,})\s*([^\s`]*)\s*$/;
const HEADING_RE = /^ {0,3}(#{1,6})\s+(.*?)\s*#*\s*$/;
const HR_RE = /^ {0,3}([-*_])(\s*\1){2,}\s*$/;
const BLOCKQUOTE_RE = /^ {0,3}> ?(.*)$/;
const UL_RE = /^(\s*)[-*+]\s+(.*)$/;
const OL_RE = /^(\s*)(\d+)[.)]\s+(.*)$/;
const TABLE_DIVIDER_RE = /^\s*\|?\s*:?-{1,}:?\s*(\|\s*:?-{1,}:?\s*)*\|?\s*$/;

export function escapeHtml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

/** GitHub-style heading anchor, deduplicated by the caller. */
export function slugify(text: string): string {
  const base = text
    .toLowerCase()
    .replace(/[`*_~[\]()]/g, "")
    .trim()
    .replace(/[^\p{L}\p{N}]+/gu, "-")
    .replace(/^-+|-+$/g, "");
  return base || "section";
}

/**
 * Render inline markdown.
 *
 * Code spans are pulled out before escaping so their contents can never be
 * reinterpreted as emphasis or links, then restored at the end.
 */
function renderInline(src: string): string {
  const spans: string[] = [];
  // \u0000 cannot appear in the source and survives HTML escaping untouched.
  let text = src.replace(/(`+)([\s\S]*?)\1/g, (_, _ticks, body: string) => {
    const content = body.trim();
    const isRef = SOURCE_REF_RE.test(content);
    const attrs = isRef
      ? ` class="rs-ref" data-ref="${escapeHtml(content)}" role="button" tabindex="0"`
      : "";
    spans.push(`<code${attrs}>${escapeHtml(content)}</code>`);
    return `\u0000${spans.length - 1}\u0000`;
  });

  text = escapeHtml(text);

  // Images before links — the syntaxes differ only by a leading `!`.
  text = text.replace(
    /!\[([^\]]*)\]\(([^)\s]+)(?:\s+&quot;[^&]*&quot;)?\)/g,
    (_, alt: string, src2: string) =>
      `<img src="${encodeURI(src2)}" alt="${alt}" loading="lazy" />`,
  );

  text = text.replace(
    /\[([^\]]+)\]\(([^)\s]+)(?:\s+&quot;[^&]*&quot;)?\)/g,
    (_, label: string, href: string) => {
      const safe = sanitizeHref(href);
      if (!safe) return label;
      return `<a href="${safe}">${label}</a>`;
    },
  );

  text = text.replace(/(^|[\s(])(https?:\/\/[^\s<)]+)/g, (_, lead: string, url: string) => {
    return `${lead}<a href="${encodeURI(url)}">${url}</a>`;
  });

  text = text.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  text = text.replace(/__([^_]+)__/g, "<strong>$1</strong>");
  text = text.replace(/(^|[^*\w])\*([^*\n]+)\*(?![*\w])/g, "$1<em>$2</em>");
  text = text.replace(/(^|[^_\w])_([^_\n]+)_(?![_\w])/g, "$1<em>$2</em>");
  text = text.replace(/~~([^~]+)~~/g, "<del>$1</del>");

  return text.replace(/\u0000(\d+)\u0000/g, (_, index: string) => spans[Number(index)] ?? "");
}

/** Block `javascript:`/`data:` and anything else that is not a plain link. */
function sanitizeHref(href: string): string | null {
  const trimmed = href.trim();
  if (!trimmed) return null;
  if (/^(https?:|mailto:|#|\/)/i.test(trimmed)) return encodeURI(trimmed);
  if (/^[a-z][a-z0-9+.-]*:/i.test(trimmed)) return null; // unknown scheme
  return encodeURI(trimmed); // relative link — resolved as a wiki page id
}

interface ListItem {
  indent: number;
  ordered: boolean;
  start: number;
  lines: string[];
}

/** Collect a run of list lines, then render them as a properly nested tree. */
function parseList(lines: string[], from: number): { html: string; next: number } {
  const items: ListItem[] = [];
  let i = from;

  while (i < lines.length) {
    const line = lines[i];
    const ul = UL_RE.exec(line);
    const ol = OL_RE.exec(line);
    if (ul) {
      items.push({ indent: ul[1].length, ordered: false, start: 1, lines: [ul[2]] });
      i += 1;
    } else if (ol) {
      items.push({
        indent: ol[1].length,
        ordered: true,
        start: Number(ol[2]) || 1,
        lines: [ol[3]],
      });
      i += 1;
    } else if (items.length && line.trim() && /^\s{2,}/.test(line)) {
      // Lazy continuation of the previous item.
      items[items.length - 1].lines.push(line.trim());
      i += 1;
    } else if (!line.trim() && i + 1 < lines.length && (UL_RE.test(lines[i + 1]) || OL_RE.test(lines[i + 1]))) {
      i += 1; // blank line between items of the same list
    } else {
      break;
    }
  }

  return { html: renderListLevel(items, 0).html, next: i };
}

function renderListLevel(
  items: ListItem[],
  index: number,
): { html: string; consumed: number } {
  if (index >= items.length) return { html: "", consumed: 0 };

  const baseIndent = items[index].indent;
  const ordered = items[index].ordered;
  const parts: string[] = [];
  let i = index;

  while (i < items.length && items[i].indent >= baseIndent) {
    if (items[i].indent > baseIndent) {
      const nested = renderListLevel(items, i);
      // Attach the nested list to the item that opened it.
      parts[parts.length - 1] = parts[parts.length - 1].replace(
        /<\/li>$/,
        `${nested.html}</li>`,
      );
      i += nested.consumed;
      continue;
    }
    if (items[i].ordered !== ordered) break;
    parts.push(`<li>${renderInline(items[i].lines.join(" "))}</li>`);
    i += 1;
  }

  const startAttr = ordered && items[index].start !== 1 ? ` start="${items[index].start}"` : "";
  const tag = ordered ? "ol" : "ul";
  return { html: `<${tag}${startAttr}>${parts.join("")}</${tag}>`, consumed: i - index };
}

function parseTable(lines: string[], from: number): { html: string; next: number } | null {
  const header = lines[from];
  const divider = lines[from + 1];
  if (!header?.includes("|") || !divider || !TABLE_DIVIDER_RE.test(divider)) return null;

  const cells = (row: string) =>
    row
      .trim()
      .replace(/^\||\|$/g, "")
      .split("|")
      .map((c) => c.trim());

  const aligns = cells(divider).map((spec) => {
    const left = spec.startsWith(":");
    const right = spec.endsWith(":");
    if (left && right) return "center";
    if (right) return "right";
    return left ? "left" : "";
  });

  const head = cells(header)
    .map((c, idx) => {
      const align = aligns[idx] ? ` style="text-align:${aligns[idx]}"` : "";
      return `<th${align}>${renderInline(c)}</th>`;
    })
    .join("");

  const body: string[] = [];
  let i = from + 2;
  while (i < lines.length && lines[i].includes("|") && lines[i].trim()) {
    const row = cells(lines[i])
      .map((c, idx) => {
        const align = aligns[idx] ? ` style="text-align:${aligns[idx]}"` : "";
        return `<td${align}>${renderInline(c)}</td>`;
      })
      .join("");
    body.push(`<tr>${row}</tr>`);
    i += 1;
  }

  return {
    html: `<div class="rs-table-wrap"><table><thead><tr>${head}</tr></thead><tbody>${body.join(
      "",
    )}</tbody></table></div>`,
    next: i,
  };
}

/** Render one fence-free segment to HTML, appending any headings to `toc`. */
function renderSegment(md: string, toc: TocEntry[], usedIds: Set<string>): string {
  const lines = md.split("\n");
  const out: string[] = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];

    if (!line.trim()) {
      i += 1;
      continue;
    }

    const heading = HEADING_RE.exec(line);
    if (heading) {
      const level = heading[1].length;
      const raw = heading[2];
      let id = slugify(raw);
      let n = 2;
      while (usedIds.has(id)) id = `${slugify(raw)}-${n++}`;
      usedIds.add(id);
      // Only h2/h3 drive the table of contents; deeper levels add noise.
      if (level >= 2 && level <= 3) {
        toc.push({ id, level, text: raw.replace(/[`*_]/g, "") });
      }
      out.push(
        `<h${level} id="${id}" class="rs-heading"><a class="rs-anchor" href="#${id}" aria-label="anchor">#</a>${renderInline(
          raw,
        )}</h${level}>`,
      );
      i += 1;
      continue;
    }

    if (HR_RE.test(line)) {
      out.push("<hr />");
      i += 1;
      continue;
    }

    if (BLOCKQUOTE_RE.test(line)) {
      const quoted: string[] = [];
      while (i < lines.length && BLOCKQUOTE_RE.test(lines[i])) {
        quoted.push(BLOCKQUOTE_RE.exec(lines[i])![1]);
        i += 1;
      }
      const joined = quoted.join(" ");
      if (!isHtmlChrome(joined)) {
        out.push(`<blockquote>${renderInline(joined)}</blockquote>`);
      }
      continue;
    }

    if (UL_RE.test(line) || OL_RE.test(line)) {
      const list = parseList(lines, i);
      out.push(list.html);
      i = list.next;
      continue;
    }

    if (line.includes("|")) {
      const table = parseTable(lines, i);
      if (table) {
        out.push(table.html);
        i = table.next;
        continue;
      }
    }

    // Paragraph: consume until a blank line or the start of another block.
    const para: string[] = [];
    while (
      i < lines.length &&
      lines[i].trim() &&
      !HEADING_RE.test(lines[i]) &&
      !HR_RE.test(lines[i]) &&
      !BLOCKQUOTE_RE.test(lines[i]) &&
      !UL_RE.test(lines[i]) &&
      !OL_RE.test(lines[i])
    ) {
      if (isHtmlChrome(lines[i])) {
        i += 1;
        continue;
      }
      para.push(lines[i].trim());
      i += 1;
    }
    if (para.length) {
      const joined = para.join(" ");
      if (!isHtmlChrome(joined)) {
        out.push(`<p>${renderInline(joined)}</p>`);
      }
    }
  }

  return out.join("\n");
}

export function renderMarkdown(md: string): RenderedMarkdown {
  const blocks: MarkdownBlock[] = [];
  const toc: TocEntry[] = [];
  const usedIds = new Set<string>();
  const lines = (md || "").replace(/^﻿/, "").replace(/\r\n?/g, "\n").split("\n");

  let buffer: string[] = [];
  const flush = () => {
    if (!buffer.length) return;
    const html = renderSegment(buffer.join("\n"), toc, usedIds);
    if (html.trim()) blocks.push({ kind: "html", html });
    buffer = [];
  };

  let i = 0;
  while (i < lines.length) {
    const fence = FENCE_RE.exec(lines[i]);
    if (fence) {
      flush();
      const marker = fence[1];
      const lang = (fence[2] || "").toLowerCase();
      const code: string[] = [];
      i += 1;
      while (i < lines.length && !lines[i].trimEnd().startsWith(marker)) {
        code.push(lines[i]);
        i += 1;
      }
      i += 1; // closing fence (or end of input)
      const body = code.join("\n").replace(/\s+$/, "");
      if (body) {
        blocks.push(
          lang === "mermaid"
            ? { kind: "mermaid", code: body }
            : { kind: "code", lang: lang || "text", code: body },
        );
      }
      continue;
    }
    buffer.push(lines[i]);
    i += 1;
  }
  flush();

  return { blocks, toc };
}

/**
 * Drop a page's leading `# Title` — the reader chrome already renders it, so
 * keeping it duplicates the title on every page.
 */
export function stripLeadingTitle(content: string, title: string): string {
  const lines = (content || "").replace(/^﻿/, "").split(/\r?\n/);
  let i = 0;
  while (i < lines.length && !lines[i].trim()) i += 1;
  const match = HEADING_RE.exec(lines[i] ?? "");
  if (!match || match[1].length !== 1) return content;

  const heading = match[2].trim().replace(/^`|`$/g, "");
  const normalized = (title || "").trim().replace(/^`|`$/g, "");
  if (heading.toLowerCase() !== normalized.toLowerCase() && normalized) return content;

  i += 1;
  while (i < lines.length && !lines[i].trim()) i += 1;
  return lines.slice(i).join("\n");
}
