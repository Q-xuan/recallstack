/**
 * Mermaid 11's `useMaxWidth` writes `width="100%"` plus an inline
 * `max-width: <natural>px`, and often omits `height`. Combined with a flex
 * box that has `max-height`, the SVG viewport becomes a tall empty shell
 * while the nodes stay at their natural size in the corner.
 *
 * These helpers strip that lock and, once the SVG is in the layout, crop
 * the viewBox to the painted content so the figure hugs the diagram.
 */

const SVG_OPEN_RE = /<svg\b([^>]*)>/i;

/** Shortest inline height (px) we still treat as readable after shrinking. */
export const MERMAID_MIN_READABLE_HEIGHT = 72;

const VIEWBOX_PAD = 12;

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

function parseViewBox(svg: SVGSVGElement): { x: number; y: number; w: number; h: number } | null {
  const raw = svg.getAttribute("viewBox");
  if (!raw) return null;
  const parts = raw.trim().split(/[\s,]+/).map(Number);
  if (parts.length !== 4 || parts.some((n) => !Number.isFinite(n))) return null;
  const [x, y, w, h] = parts;
  if (w <= 0 || h <= 0) return null;
  return { x, y, w, h };
}

/**
 * Crop leftover viewBox slack and pick a width: fill the article column
 * when the diagram is shallow enough to stay readable; otherwise keep the
 * natural width so a wide/complex chart can scroll instead of shrinking.
 */
export function fitMermaidSvg(svg: SVGSVGElement, containerWidth: number): void {
  let boxW = 0;
  let boxH = 0;

  try {
    const bbox = svg.getBBox();
    if (bbox.width > 0 && bbox.height > 0) {
      const current = parseViewBox(svg);
      const slack =
        current &&
        (bbox.width + VIEWBOX_PAD * 2 < current.w * 0.85 ||
          bbox.height + VIEWBOX_PAD * 2 < current.h * 0.85);
      if (!current || slack) {
        svg.setAttribute(
          "viewBox",
          `${bbox.x - VIEWBOX_PAD} ${bbox.y - VIEWBOX_PAD} ${bbox.width + VIEWBOX_PAD * 2} ${
            bbox.height + VIEWBOX_PAD * 2
          }`,
        );
      }
      boxW = bbox.width + VIEWBOX_PAD * 2;
      boxH = bbox.height + VIEWBOX_PAD * 2;
    }
  } catch {
    // getBBox throws if the SVG is not yet in the document.
  }

  if (!boxW || !boxH) {
    const current = parseViewBox(svg);
    if (current) {
      boxW = current.w;
      boxH = current.h;
    }
  }

  svg.removeAttribute("height");
  svg.style.removeProperty("max-width");
  svg.style.removeProperty("max-height");
  svg.style.removeProperty("width");
  svg.style.removeProperty("height");
  svg.style.height = "auto";

  const column = Math.max(0, containerWidth);
  const scaledHeight = boxW > 0 && column > 0 ? boxH * (column / boxW) : boxH;
  const shouldScroll =
    boxW > column && column > 0 && scaledHeight < MERMAID_MIN_READABLE_HEIGHT;

  if (shouldScroll) {
    svg.setAttribute("width", String(Math.ceil(boxW)));
    svg.style.maxWidth = "none";
  } else {
    svg.setAttribute("width", "100%");
    svg.style.maxWidth = "100%";
  }
}
