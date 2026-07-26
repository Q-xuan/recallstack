import { useEffect, useState } from "react";
import { FsEntry, FsListResult, FsRoot, recallstackApi } from "../lib/recallstackApi";

type Props = {
  open: boolean;
  onClose: () => void;
  onSelect: (path: string) => void;
  initialPath?: string;
};

export default function FolderPicker({ open, onClose, onSelect, initialPath }: Props) {
  const [roots, setRoots] = useState<FsRoot[]>([]);
  const [listing, setListing] = useState<FsListResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function load(path?: string) {
    setLoading(true);
    setError(null);
    try {
      const data = await recallstackApi.listFsDirectory(path);
      setListing(data);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "无法读取目录");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    (async () => {
      try {
        const r = await recallstackApi.listFsRoots();
        if (!cancelled) setRoots(r.roots);
      } catch {
        // roots optional
      }
      if (!cancelled) await load(initialPath);
    })();
    return () => {
      cancelled = true;
    };
  }, [open, initialPath]);

  if (!open) return null;

  const current = listing?.path || "";
  const dirs = listing?.directories || [];
  const files = listing?.files || [];

  return (
    <div className="rs-modal-backdrop">
      <div className="rs-modal">
        <div className="rs-modal-head">
          <div>
            <h2 className="rs-modal-title">选择本地文件夹</h2>
            <p className="rs-modal-sub">
              浏览器不能直接打开系统文件夹对话框，这里通过本机后端浏览目录。
            </p>
          </div>
          <button onClick={onClose} className="rs-btn rs-btn-ghost h-8 px-3 text-[12px]">
            关闭
          </button>
        </div>

        <div className="rs-modal-roots">
          {roots.map((r) => (
            <button
              key={r.path}
              onClick={() => load(r.path)}
              className="rs-btn rs-btn-ghost h-7 px-3 text-[12px]"
            >
              {r.name}
            </button>
          ))}
        </div>

        <div className="rs-modal-path">
          <div className="rs-eyebrow mb-1">当前路径</div>
          <div className="rs-modal-pathvalue">{current || "…"}</div>
        </div>

        <div className="rs-modal-body">
          {loading && <p className="px-3 py-2 text-[13px] text-[var(--rs-muted)]">加载中…</p>}
          {error && <p className="rs-alert m-2">{error}</p>}
          {!loading && listing?.parent && (
            <button
              className="rs-fs-row"
              onClick={() => load(listing.parent || undefined)}
            >
              ↑ 上级目录
            </button>
          )}
          {!loading &&
            dirs.map((d: FsEntry) => (
              <button
                key={d.path}
                className="rs-fs-row"
                onClick={() => load(d.path)}
                onDoubleClick={() => load(d.path)}
              >
                <span aria-hidden>📁</span>
                <span className="truncate">{d.name}</span>
              </button>
            ))}
          {!loading && dirs.length === 0 && !error && (
            <p className="px-3 py-2 text-[13px] text-[var(--rs-muted)]">此目录下没有可见子文件夹</p>
          )}
          {!loading && files.length > 0 && (
            <div className="mt-2 px-3 pt-2 border-t border-[var(--rs-line)]">
              <div className="rs-eyebrow mb-1">文件预览（不可选）</div>
              {files.slice(0, 8).map((f) => (
                <div key={f.path} className="text-[12px] text-[var(--rs-muted)] py-0.5 truncate">
                  📄 {f.name}
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="rs-modal-foot">
          <div className="text-[12px] text-[var(--rs-muted)] truncate">将导入：{current || "未选择"}</div>
          <div className="flex gap-2 shrink-0">
            <button
              onClick={onClose}
              className="rs-btn rs-btn-ghost"
            >
              取消
            </button>
            <button
              disabled={!current}
              onClick={() => current && onSelect(current)}
              className="rs-btn rs-btn-primary"
            >
              选择此文件夹
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
