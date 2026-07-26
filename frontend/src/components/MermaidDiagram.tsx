import { useEffect, useState } from "react";
import mermaid from "mermaid";
import { readTheme } from "../lib/theme";

mermaid.initialize({ startOnLoad: false, theme: "default" });

let mermaidId = 0;

interface Props {
  code: string;
}

/**
 * Architecture diagrams are the fastest way to read a codebase's shape, so they
 * get a real viewer: theme-aware, expandable, and never silently clipped.
 */
export default function MermaidDiagram({ code }: Props) {
  const [error, setError] = useState("");
  const [svg, setSvg] = useState("");
  const [zoomed, setZoomed] = useState(false);
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
    mermaid.initialize({
      startOnLoad: false,
      theme: readTheme() === "dark" ? "dark" : "default",
      themeVariables: { fontFamily: "inherit" },
    });
    const id = `mermaid-${++mermaidId}`;
    mermaid
      .render(id, code)
      .then(({ svg }) => {
        if (cancelled) return;
        setSvg(svg);
        setError("");
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        setError(e instanceof Error ? e.message : "渲染失败");
        setSvg("");
      });
    return () => {
      cancelled = true;
    };
  }, [code, themeTick]);

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
        <p>图表渲染失败：{error}</p>
        <pre>{code}</pre>
      </div>
    );
  }

  return (
    <>
      <figure className="rs-diagram">
        <div className="rs-diagram-body" dangerouslySetInnerHTML={{ __html: svg }} />
        <button type="button" className="rs-diagram-zoom" onClick={() => setZoomed(true)}>
          放大
        </button>
      </figure>

      {zoomed && (
        <div className="rs-lightbox" onClick={() => setZoomed(false)} role="presentation">
          <div
            className="rs-lightbox-inner"
            onClick={(e) => e.stopPropagation()}
            dangerouslySetInnerHTML={{ __html: svg }}
          />
          <button type="button" className="rs-lightbox-close" onClick={() => setZoomed(false)}>
            关闭 (esc)
          </button>
        </div>
      )}
    </>
  );
}
