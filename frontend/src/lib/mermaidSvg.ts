/**
 * Mermaid 11's `useMaxWidth` writes `width="100%"` plus an inline
 * `max-width: <natural>px`, and often omits `height`. Combined with a flex
 * box that has `max-height`, the SVG viewport becomes a tall empty shell
 * while the nodes stay at their natural size in the corner.
 *
 * These helpers strip that lock and, once the SVG is in the layout, crop
 * the viewBox to the painted content so the figure hugs the diagram.
 *
 * Shallow `flowchart LR` charts are the usual leftover-shell case: mermaid
 * keeps a tall viewBox (or a full-bleed background rect that makes
 * `svg.getBBox()` match it). Crop on any leftover slack, not a 15% threshold,
 * and measure painted nodes/edges when the root bbox is just the canvas.
 */

const SVG_OPEN_RE = /<svg\b([^>]*)>/i;

/** Shortest inline height (px) we still treat as readable after shrinking. */
export const MERMAID_MIN_READABLE_HEIGHT = 72;

export const VIEWBOX_PAD = 12;

/** Painted mermaid bits. Root `getBBox()` often includes the empty canvas. */
const MERMAID_PAINT_SELECTOR = [
  ".node",
  ".edgePath",
  ".edgeLabel",
  ".cluster",
  ".label",
  ".actor",
  ".messageLine0",
  ".messageLine1",
  ".section",
  ".task",
  ".pieCircle",
  ".mindmap-node",
  "foreignObject",
].join(",");

export type MermaidBox = { x: number; y: number; w: number; h: number };

export function stripMermaidViewportLock(svg: string): string {
  return svg.replace(SVG_OPEN_RE, (_match, attrs: string) => {
    let next = attrs
      .replace(/\swidth(?:="[^"]*")?/gi, "")
      .replace(/\sheight(?:="[^"]*")?/gi, "")
      .replace(/\sstyle="([^"]*)"/i, (_style, value: string) => {
        const cleaned = value
          .split(";")
          .map((part) => part.trim())
          .filter((part) => part && !/^(max-width|max-height|width|height)\s*:/i.test(part))
          .join("; ");
        return cleaned ? ` style="${cleaned}"` : "";
      });
    return `<svg${next} width="100%">`;
  });
}

export function parseViewBoxAttr(raw: string | null): MermaidBox | null {
  if (!raw) return null;
  const parts = raw.trim().split(/[\s,]+/).map(Number);
  if (parts.length !== 4 || parts.some((n) => !Number.isFinite(n))) return null;
  const [x, y, w, h] = parts;
  if (w <= 0 || h <= 0) return null;
  return { x, y, w, h };
}

function parseViewBox(svg: SVGSVGElement): MermaidBox | null {
  return parseViewBoxAttr(svg.getAttribute("viewBox"));
}

export function paddedContentBox(box: MermaidBox, pad = VIEWBOX_PAD): MermaidBox {
  return {
    x: box.x - pad,
    y: box.y - pad,
    w: box.w + pad * 2,
    h: box.h + pad * 2,
  };
}

/**
 * Crop whenever mermaid's canvas is larger than the ink, including the
 * common "wide LR strip on a tall viewBox" leftover (far below the old 15%
 * slack gate, which left shallow charts sitting on an empty shell).
 */
export function viewBoxNeedsCrop(
  viewBox: MermaidBox,
  content: MermaidBox,
  pad = VIEWBOX_PAD,
): boolean {
  const next = paddedContentBox(content, pad);
  return next.w < viewBox.w - 1 || next.h < viewBox.h - 1;
}

export function mermaidShouldScroll(
  boxW: number,
  boxH: number,
  containerWidth: number,
  minReadable = MERMAID_MIN_READABLE_HEIGHT,
): boolean {
  const column = Math.max(0, containerWidth);
  const scaledHeight = boxW > 0 && column > 0 ? boxH * (column / boxW) : boxH;
  return boxW > column && column > 0 && scaledHeight < minReadable;
}

function isFullBleedRect(el: Element, viewBox: MermaidBox): boolean {
  if (el.tagName.toLowerCase() !== "rect") return false;
  const w = Number.parseFloat(el.getAttribute("width") || "");
  const h = Number.parseFloat(el.getAttribute("height") || "");
  return Number.isFinite(w) && Number.isFinite(h) && w >= viewBox.w * 0.95 && h >= viewBox.h * 0.95;
}

function unionGraphicsBox(nodes: ArrayLike<Element>): MermaidBox | null {
  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;
  let found = false;
  for (let i = 0; i < nodes.length; i += 1) {
    const el = nodes[i] as SVGGraphicsElement;
    if (typeof el.getBBox !== "function") continue;
    try {
      const b = el.getBBox();
      if (!(b.width > 0 || b.height > 0)) continue;
      found = true;
      minX = Math.min(minX, b.x);
      minY = Math.min(minY, b.y);
      maxX = Math.max(maxX, b.x + b.width);
      maxY = Math.max(maxY, b.y + b.height);
    } catch {
      // Not in the document yet.
    }
  }
  if (!found) return null;
  return { x: minX, y: minY, w: maxX - minX, h: maxY - minY };
}

function measureWithoutFullBleed(svg: SVGSVGElement): MermaidBox | null {
  const viewBox = parseViewBox(svg);
  const root = (svg.querySelector(":scope > g") || svg) as Element;
  const kids = root.children;
  if (!kids || kids.length === 0) return null;
  const usable: Element[] = [];
  for (let i = 0; i < kids.length; i += 1) {
    const child = kids[i];
    const tag = child.tagName.toLowerCase();
    if (tag === "style" || tag === "defs" || tag === "title" || tag === "desc") continue;
    if (viewBox && isFullBleedRect(child, viewBox)) continue;
    usable.push(child);
  }
  return usable.length ? unionGraphicsBox(usable) : null;
}

/**
 * Tight box around painted mermaid content. Falls back to the root bbox /
 * viewBox when labels have not laid out yet (caller should retry).
 */
export function measureMermaidContent(svg: SVGSVGElement): MermaidBox | null {
  try {
    const painted = svg.querySelectorAll(MERMAID_PAINT_SELECTOR);
    const ink = painted && painted.length ? unionGraphicsBox(painted) : null;
    if (ink && ink.w > 0 && ink.h > 0) return ink;
  } catch {
    // querySelectorAll may be mocked without CSS support.
  }

  const stripped = measureWithoutFullBleed(svg);
  if (stripped && stripped.w > 0 && stripped.h > 0) return stripped;

  try {
    const bbox = svg.getBBox();
    if (bbox.width > 0 && bbox.height > 0) {
      return { x: bbox.x, y: bbox.y, w: bbox.width, h: bbox.height };
    }
  } catch {
    // getBBox throws if the SVG is not yet in the document.
  }

  return parseViewBox(svg);
}

/**
 * Crop leftover viewBox slack and pick a width: fill the article column
 * when the diagram is shallow enough to stay readable; otherwise keep the
 * natural width so a wide/complex chart can scroll instead of shrinking.
 *
 * Returns true when the size came from painted content (not only the canvas
 * viewBox), so the viewer can retry after fonts / foreignObject layout.
 */
export function fitMermaidSvg(svg: SVGSVGElement, containerWidth: number): boolean {
  const viewBox = parseViewBox(svg);
  const content = measureMermaidContent(svg);
  let boxW = 0;
  let boxH = 0;
  let fromContent = false;

  if (content && content.w > 0 && content.h > 0) {
    const next = paddedContentBox(content);
    if (!viewBox || viewBoxNeedsCrop(viewBox, content)) {
      svg.setAttribute("viewBox", `${next.x} ${next.y} ${next.w} ${next.h}`);
    }
    boxW = next.w;
    boxH = next.h;
    fromContent = true;
  } else if (viewBox) {
    boxW = viewBox.w;
    boxH = viewBox.h;
  }

  svg.removeAttribute("height");
  svg.style.removeProperty("max-width");
  svg.style.removeProperty("max-height");
  svg.style.removeProperty("width");
  svg.style.removeProperty("height");
  svg.style.height = "auto";
  svg.setAttribute("preserveAspectRatio", "xMinYMin meet");

  if (boxW > 0 && boxH > 0) {
    svg.style.aspectRatio = `${boxW} / ${boxH}`;
  }

  const shouldScroll = mermaidShouldScroll(boxW, boxH, containerWidth);

  if (shouldScroll) {
    svg.setAttribute("width", String(Math.ceil(boxW)));
    svg.style.maxWidth = "none";
  } else {
    svg.setAttribute("width", "100%");
    svg.style.maxWidth = "100%";
  }

  return fromContent;
}
