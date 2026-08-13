import { parseRef, type ParsedRef } from "./SourcePeek";
import { SOURCE_REF_RE } from "../lib/markdown";
import { useT } from "../lib/i18n";

interface Props {
  content: string;
  onOpen: (reference: string) => void;
}

interface SourceNode {
  name: string;
  loc?: string;
  children: SourceNode[];
}

const BACKTICK_RE = /`([^`]+)`/g;

/** Unique path citations from the open page, nested by directory like zread 来源. */
export function collectSourceLocs(content: string): string[] {
  const found: string[] = [];
  const seen = new Set<string>();
  const push = (raw: string) => {
    const loc = raw.trim();
    if (!loc || seen.has(loc) || !SOURCE_REF_RE.test(loc.split(/\s/)[0] || "")) {
      return;
    }
    const parsed = parseRef(loc);
    if (!parsed) return;
    const key = parsed.path;
    if (seen.has(key)) return;
    seen.add(key);
    seen.add(loc);
    found.push(loc);
  };
  let match: RegExpExecArray | null;
  const re = new RegExp(BACKTICK_RE);
  while ((match = re.exec(content || ""))) {
    push(match[1]);
  }
  const dataRef = /data-(?:ref|path)="([^"]+)"/g;
  while ((match = dataRef.exec(content || ""))) {
    push(match[1]);
  }
  return found;
}

function nestLocs(locs: string[]): SourceNode[] {
  const root: SourceNode = { name: "", children: [] };

  function ensure(parts: string[], loc: string) {
    let node = root;
    for (let i = 0; i < parts.length; i += 1) {
      const name = parts[i];
      let child = node.children.find((c) => c.name === name);
      if (!child) {
        child = { name, children: [] };
        node.children.push(child);
      }
      node = child;
      if (i === parts.length - 1) node.loc = loc;
    }
  }

  for (const loc of locs) {
    const parsed = parseRef(loc);
    if (!parsed) continue;
    const parts = parsed.path.replace(/\\/g, "/").split("/").filter(Boolean);
    if (!parts.length) continue;
    ensure(parts, loc);
  }
  return root.children;
}

function Tree({
  nodes,
  onOpen,
  depth = 0,
}: {
  nodes: SourceNode[];
  onOpen: (reference: string) => void;
  depth?: number;
}) {
  return (
    <ul className={depth === 0 ? "rs-sources-tree" : undefined}>
      {nodes.map((node) => (
        <li key={`${node.name}:${node.loc || ""}`}>
          {node.loc ? (
            <button type="button" className="rs-sources-file" onClick={() => onOpen(node.loc!)}>
              {node.name}
              {rangeLabel(node.loc)}
            </button>
          ) : (
            <div className="rs-sources-dir">{node.name}</div>
          )}
          {node.children.length > 0 && (
            <Tree nodes={node.children} onOpen={onOpen} depth={depth + 1} />
          )}
        </li>
      ))}
    </ul>
  );
}

function rangeLabel(loc: string): string {
  const parsed: ParsedRef | null = parseRef(loc);
  if (!parsed?.startLine) return "";
  if (parsed.endLine && parsed.endLine !== parsed.startLine) {
    return `:${parsed.startLine}–${parsed.endLine}`;
  }
  return `:${parsed.startLine}`;
}

export default function SourceRail({ content, onOpen }: Props) {
  const t = useT();
  const locs = collectSourceLocs(content);
  if (!locs.length) return null;
  const tree = nestLocs(locs);
  return (
    <nav className="rs-sources" aria-label={t("来源", "Sources")}>
      <div className="rs-toc-title">{t("来源", "Sources")}</div>
      <Tree nodes={tree} onOpen={onOpen} />
    </nav>
  );
}
