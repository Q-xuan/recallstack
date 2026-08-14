import { useEffect, useMemo, useState } from "react";
import { tNow, useT } from "../lib/i18n";
import { recallstackApi, type SourceAnnotation } from "../lib/recallstackApi";

interface Props {
  repositoryId?: string;
  reference: string;
  onClose: () => void;
  /** Learning-path slug so 过关 / 先回到原理 can ground the overlay notes. */
  slug?: string;
}

export interface ParsedRef {
  path: string;
  startLine?: number;
  endLine?: number;
}

/** Parse the `path/to/file.py:12-40` citation format emitted by the wiki. */
export function parseRef(raw: string): ParsedRef | null {
  // Strip a trailing TypeName so `path:line Symbol` / `path Symbol` still resolve.
  const loc = (raw || "").trim().replace(/\s+\S.*$/, "");
  const match = /^(.+?)(?::(\d+)(?:-(\d+))?)?$/.exec(loc);
  if (!match) return null;
  const path = match[1];
  if (!path.includes(".")) return null;
  return {
    path,
    startLine: match[2] ? Number(match[2]) : undefined,
    endLine: match[3] ? Number(match[3]) : undefined,
  };
}

/**
 * Inline source viewer for a wiki / 学习路径 citation.
 *
 * Teaching notes are an overlay (CodeTour-shaped `{path, line, note}`). They
 * are never written into the scanned repo.
 */
export default function SourcePeek({ repositoryId, reference, onClose, slug }: Props) {
  const t = useT();
  const parsed = parseRef(reference);
  const [code, setCode] = useState<string | null>(null);
  const [range, setRange] = useState<{ start: number; end: number } | null>(null);
  const [notes, setNotes] = useState<SourceAnnotation[]>([]);
  const [error, setError] = useState<string | null>(null);
  const missing = tNow("找不到工作副本里的这个文件", "This file is not in the scanned working copy.");

  useEffect(() => {
    let cancelled = false;
    setCode(null);
    setRange(null);
    setNotes([]);
    if (!parsed) {
      setError(missing);
      return;
    }
    setError(null);
    if (!repositoryId) {
      setError(missing);
      return;
    }
    (async () => {
      try {
        const res = await recallstackApi.sourceSnippet({
          repository_id: repositoryId,
          path: parsed.path,
          start_line: parsed.startLine,
          end_line: parsed.endLine,
          slug,
        });
        if (cancelled) return;
        setCode(res.content);
        setRange({ start: res.start_line, end: res.end_line });
        setNotes(res.annotations || []);
      } catch (e: unknown) {
        if (!cancelled) {
          setError(e instanceof Error && e.message ? e.message : missing);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [repositoryId, reference, slug]);

  const lines = useMemo(() => (code == null ? [] : code.split("\n")), [code]);
  const noteByLine = useMemo(() => {
    const map = new Map<number, string>();
    for (const item of notes) {
      if (item.line && item.note) map.set(item.line, item.note);
    }
    return map;
  }, [notes]);

  const pathLabel = parsed?.path || reference;
  const start = range?.start ?? 1;

  return (
    <div className="rs-peek">
      <div className="rs-peek-head">
        <div className="min-w-0">
          <div className="rs-peek-path" title={pathLabel}>
            {pathLabel}
          </div>
          {range && (
            <div className="rs-peek-range rs-tabular">
              {t("行", "Lines")} {range.start}–{range.end}
            </div>
          )}
        </div>
        <button type="button" className="rs-btn rs-btn-ghost h-7 px-2.5 text-[12px]" onClick={onClose}>
          {t("收起", "Collapse")}
        </button>
      </div>
      {error ? (
        <p className="rs-peek-error">{error}</p>
      ) : code === null ? (
        <p className="rs-peek-loading">
          {slug ? t("在标关键行…", "Marking the load-bearing lines…") : t("读取源码…", "Reading source…")}
        </p>
      ) : (
        <div className="rs-peek-body">
          {lines.map((src, i) => {
            const lineNo = start + i;
            const note = noteByLine.get(lineNo);
            return (
              <div key={lineNo} className={note ? "rs-peek-row is-noted" : "rs-peek-row"}>
                <span className="rs-peek-ln rs-tabular">{lineNo}</span>
                <code className="rs-peek-src">{src || " "}</code>
                {note ? <aside className="rs-peek-note">{note}</aside> : null}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
