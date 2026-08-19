import { useEffect, useLayoutEffect, useRef, useState } from "react";
import mermaid from "mermaid";
import { useT } from "../lib/i18n";
import { normalizeMermaidSource } from "../lib/markdown";
import { fitMermaidSvg, stripMermaidViewportLock } from "../lib/mermaidSvg";
import { readTheme } from "../lib/theme";

const mermaidSize = { useMaxWidth: false as const };

function mermaidConfig(theme: "default" | "dark") {
  return {
    startOnLoad: false,
    theme,
    themeVariables: { fontFamily: "inherit" },
    flowchart: mermaidSize,
    sequence: mermaidSize,
    class: mermaidSize,
    state: mermaidSize,
    er: mermaidSize,
    gantt: mermaidSize,
    pie: mermaidSize,
    gitGraph: mermaidSize,
    journey: mermaidSize,
    mindmap: mermaidSize,
    timeline: mermaidSize,
  };
}

mermaid.initialize(mermaidConfig("default"));

let mermaidId = 0;

interface Props {
  code: string;
}

/**
 * Architecture diagrams are the fastest way to read a codebase's shape, so they
 * get a real viewer: theme-aware, expandable, and sized to the article column
 * instead of mermaid's natural (often tiny) viewport.
 */
export default function MermaidDiagram({ code }: Props) {
  const t = useT();
  const [error, setError] = useState("");
  const [svg, setSvg] = useState("");
  const [lightboxSvg, setLightboxSvg] = useState("");
  const [zoomed, setZoomed] = useState(false);
  const bodyRef = useRef<HTMLDivElement>(null);
  // Mermaid bakes colors into the SVG at render time, so a theme switch needs a
  // full re-render rather than a CSS variable change.
  const [themeTick, setThemeTick] = useState(0);

  useEffect(() => {
    const observer = new MutationObserver(() => setThemeTick((n) => n + 1));
    observer.observe(document.documentElement, { attributeFilter: ["data-theme"] });
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    let cancelled = false;
    mermaid.initialize(mermaidConfig(readTheme() === "dark" ? "dark" : "default"));
    const id = `mermaid-${++mermaidId}`;
    const source = normalizeMermaidSource(code);
    mermaid
      .render(id, source)
      .then(({ svg: raw }) => {
        if (cancelled) return;
        setSvg(stripMermaidViewportLock(raw));
        setError("");
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        setError(e instanceof Error ? e.message : "render failed");
        setSvg("");
      });
    return () => {
      cancelled = true;
    };
  }, [code, themeTick]);

  useLayoutEffect(() => {
    const container = bodyRef.current;
    if (!container || !svg) {
      setLightboxSvg("");
      return;
    }

    const apply = () => {
      const el = container.querySelector("svg");
      if (!el) return;
      fitMermaidSvg(el, container.clientWidth);
      setLightboxSvg(el.outerHTML);
    };

    apply();
    const ro = new ResizeObserver(apply);
    ro.observe(container);
    return () => ro.disconnect();
  }, [svg]);

  useEffect(() => {
    if (!zoomed) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setZoomed(false);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [zoomed]);

  if (error) {
    // A broken diagram must not hide the source it was generated from.
    return (
      <div className="rs-diagram-error">
        <p>{t("图表渲染失败：", "Diagram failed to render: ")}{error}</p>
        <pre>{normalizeMermaidSource(code)}</pre>
      </div>
    );
  }

  if (!svg) {
    return <div className="rs-diagram-loading">{t("图表加载中…", "Loading diagram…")}</div>;
  }

  return (
    <>
      <figure className="rs-diagram">
        <div
          ref={bodyRef}
          className="rs-diagram-body"
          dangerouslySetInnerHTML={{ __html: svg }}
        />
        <button type="button" className="rs-diagram-zoom" onClick={() => setZoomed(true)}>
          {t("放大", "Zoom")}
        </button>
      </figure>

      {zoomed && (
        <div className="rs-lightbox" onClick={() => setZoomed(false)} role="presentation">
          <div
            className="rs-lightbox-inner"
            onClick={(e) => e.stopPropagation()}
            dangerouslySetInnerHTML={{ __html: lightboxSvg || svg }}
          />
          <button type="button" className="rs-lightbox-close" onClick={() => setZoomed(false)}>
            {t("关闭 (esc)", "Close (esc)")}
          </button>
        </div>
      )}
    </>
  );
}
