import { useEffect, useState } from "react";
import CodeBlock from "./CodeBlock";
import { recallstackApi } from "../lib/recallstackApi";

interface Props {
  repositoryId: string;
  reference: string;
  onClose: () => void;
}

export interface ParsedRef {
  path: string;
  startLine?: number;
  endLine?: number;
}

/** Parse the `path/to/file.py:12-40` citation format emitted by the wiki. */
export function parseRef(raw: string): ParsedRef | null {
  const match = /^(.+?)(?::(\d+)(?:-(\d+))?)?$/.exec(raw.trim());
  if (!match) return null;
  const path = match[1];
  if (!path.includes(".")) return null;
  return {
    path,
    startLine: match[2] ? Number(match[2]) : undefined,
    endLine: match[3] ? Number(match[3]) : undefined,
  };
}

const EXT_TO_LANG: Record<string, string> = {
  ts: "typescript",
  tsx: "tsx",
  js: "javascript",
  jsx: "jsx",
  py: "python",
  rs: "rust",
  go: "go",
  java: "java",
  rb: "ruby",
  php: "php",
  cs: "csharp",
  c: "c",
  h: "c",
  cpp: "cpp",
  hpp: "cpp",
  kt: "kotlin",
  swift: "swift",
  sh: "bash",
  bash: "bash",
  yml: "yaml",
  yaml: "yaml",
  json: "json",
  toml: "toml",
  sql: "sql",
  css: "css",
  html: "html",
  md: "markdown",
};

function langFor(path: string): string {
  const ext = path.split(".").pop()?.toLowerCase() || "";
  return EXT_TO_LANG[ext] || "text";
}

/**
 * Inline source viewer for a wiki citation.
 *
 * Every concept claim in this wiki is backed by a file reference; being able to
 * open the actual lines without leaving the article is what makes the evidence
 * worth citing.
 */
export default function SourcePeek({ repositoryId, reference, onClose }: Props) {
  const parsed = parseRef(reference);
  const [code, setCode] = useState<string | null>(null);
  const [range, setRange] = useState<{ start: number; end: number } | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!parsed) return;
    let cancelled = false;
    setCode(null);
    setError(null);
    (async () => {
      try {
        const res = await recallstackApi.sourceSnippet({
          repository_id: repositoryId,
          path: parsed.path,
          start_line: parsed.startLine,
          end_line: parsed.endLine,
        });
        if (cancelled) return;
        setCode(res.content);
        setRange({ start: res.start_line, end: res.end_line });
      } catch (e: unknown) {
        if (!cancelled) setError(e instanceof Error ? e.message : "无法读取源码");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [repositoryId, reference]);

  if (!parsed) return null;

  return (
    <div className="rs-peek">
      <div className="rs-peek-head">
        <div className="min-w-0">
          <div className="rs-peek-path" title={parsed.path}>
            {parsed.path}
          </div>
          {range && (
            <div className="rs-peek-range rs-tabular">
              行 {range.start}–{range.end}
            </div>
          )}
        </div>
        <button type="button" className="rs-btn rs-btn-ghost h-7 px-2.5 text-[12px]" onClick={onClose}>
          收起
        </button>
      </div>
      {error ? (
        <p className="rs-peek-error">{error}</p>
      ) : code === null ? (
        <p className="rs-peek-loading">读取源码…</p>
      ) : (
        <CodeBlock code={code} lang={langFor(parsed.path)} />
      )}
    </div>
  );
}
