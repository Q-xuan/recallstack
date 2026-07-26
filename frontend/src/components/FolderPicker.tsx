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
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="w-full max-w-2xl bg-white rounded-2xl shadow-xl border border-slate-200 overflow-hidden">
        <div className="px-5 py-4 border-b border-slate-200 flex items-center justify-between">
          <div>
            <h2 className="text-lg font-semibold text-slate-900">选择本地文件夹</h2>
            <p className="text-xs text-slate-500 mt-1">
              浏览器不能直接打开系统文件夹对话框，这里通过本机后端浏览目录。
            </p>
          </div>
          <button onClick={onClose} className="text-slate-500 hover:text-slate-800 text-sm">
            关闭
          </button>
        </div>

        <div className="px-5 py-3 border-b border-slate-100 flex flex-wrap gap-2">
          {roots.map((r) => (
            <button
              key={r.path}
              onClick={() => load(r.path)}
              className="px-2.5 py-1 text-xs rounded-full border border-slate-300 text-slate-700 hover:bg-slate-50"
            >
              {r.name}
            </button>
          ))}
        </div>

        <div className="px-5 py-3 bg-slate-50 border-b border-slate-100">
          <div className="text-xs text-slate-500 mb-1">当前路径</div>
          <div className="font-mono text-sm text-slate-800 break-all">{current || "…"}</div>
        </div>

        <div className="max-h-80 overflow-y-auto px-2 py-2">
          {loading && <p className="px-3 py-2 text-sm text-slate-500">加载中…</p>}
          {error && <p className="px-3 py-2 text-sm text-red-600">{error}</p>}
          {!loading && listing?.parent && (
            <button
              className="w-full text-left px-3 py-2 rounded-lg hover:bg-slate-50 text-sm text-slate-700"
              onClick={() => load(listing.parent || undefined)}
            >
              ↑ 上级目录
            </button>
          )}
          {!loading &&
            dirs.map((d: FsEntry) => (
              <button
                key={d.path}
                className="w-full text-left px-3 py-2 rounded-lg hover:bg-indigo-50 text-sm text-slate-800 flex items-center gap-2"
                onClick={() => load(d.path)}
                onDoubleClick={() => load(d.path)}
              >
                <span className="text-indigo-600">📁</span>
                <span className="truncate">{d.name}</span>
              </button>
            ))}
          {!loading && dirs.length === 0 && !error && (
            <p className="px-3 py-2 text-sm text-slate-400">此目录下没有可见子文件夹</p>
          )}
          {!loading && files.length > 0 && (
            <div className="mt-2 px-3 pt-2 border-t border-slate-100">
              <div className="text-xs text-slate-400 mb-1">文件预览（不可选）</div>
              {files.slice(0, 8).map((f) => (
                <div key={f.path} className="text-xs text-slate-400 py-0.5 truncate">
                  📄 {f.name}
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="px-5 py-4 border-t border-slate-200 flex items-center justify-between gap-3">
          <div className="text-xs text-slate-500 truncate">将导入：{current || "未选择"}</div>
          <div className="flex gap-2 shrink-0">
            <button
              onClick={onClose}
              className="px-4 py-2 text-sm rounded-lg border border-slate-300 text-slate-700"
            >
              取消
            </button>
            <button
              disabled={!current}
              onClick={() => current && onSelect(current)}
              className="px-4 py-2 text-sm rounded-lg bg-indigo-600 text-white disabled:opacity-50"
            >
              选择此文件夹
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
