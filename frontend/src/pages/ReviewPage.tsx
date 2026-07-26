import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import AppShell from "../components/AppShell";
import { DueReview, recallstackApi } from "../lib/recallstackApi";

export default function ReviewPage() {
  const [items, setItems] = useState<DueReview[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const dueCount = items.filter((i) => !i.is_new).length;
  const newCount = items.length - dueCount;
  const firstItem = items.find((i) => i.item_id)?.item_id ?? null;

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const due = await recallstackApi.dueReviews();
        if (!cancelled) setItems(due);
      } catch (e: unknown) {
        if (!cancelled) setError(e instanceof Error ? e.message : "加载失败");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <AppShell
      title="复习模式"
      subtitle="按概念调度，不打断 Wiki 证据链。完成后可回到词条继续阅读。"
    >
      {loading && <p className="text-[var(--rs-muted)]">加载中…</p>}
      {error && <p className="text-[var(--rs-danger)]">{error}</p>}
      {!loading && !error && items.length === 0 && (
        <div className="bg-white border border-[var(--rs-line)] rounded-2xl p-6 text-[var(--rs-muted)]">
          队列是空的——先分析一个仓库,系统会把重要概念排进来。
          <div className="mt-4">
            <Link to="/repositories" className="text-[var(--rs-accent)] hover:underline">
              打开仓库 Wiki
            </Link>
          </div>
        </div>
      )}

      {items.length > 0 && firstItem && (
        <div className="mb-5 flex items-center justify-between gap-4 flex-wrap">
          <div className="text-sm text-[var(--rs-muted)]">
            {dueCount > 0 ? `${dueCount} 个到期复习` : "没有到期复习"}
            {newCount > 0 ? ` · ${newCount} 个新概念待首次学习` : ""}
          </div>
          <Link
            to={`/session/${firstItem}?mode=review`}
            className="px-4 py-2 bg-[var(--rs-accent)] text-white rounded-lg text-sm font-medium"
          >
            开始复习 →
          </Link>
        </div>
      )}

      <ul className="space-y-3">
        {items.map((item) => (
          <li
            key={item.concept_id}
            className="bg-white border border-[var(--rs-line)] rounded-2xl p-4 flex items-center justify-between gap-4"
          >
            <div>
              <div className="font-medium text-[var(--rs-ink)] flex items-center gap-2">
                {item.title}
                {item.is_new && (
                  <span className="text-[11px] px-1.5 py-0.5 rounded bg-[var(--rs-accent)]/10 text-[var(--rs-accent)] font-medium">
                    新概念
                  </span>
                )}
              </div>
              <div className="text-xs text-[var(--rs-muted)] mt-1">
                {item.is_new
                  ? "尚未学习 · 首次自测后进入间隔复习"
                  : `mastery ${item.mastery_score.toFixed(2)}`}
                {!item.is_new && item.next_review_at
                  ? ` · due ${new Date(item.next_review_at).toLocaleString()}`
                  : ""}
                {item.stale ? " · 旧版本" : ""}
              </div>
            </div>
            <div className="flex gap-2 shrink-0">
              <Link
                to={`/concepts/${item.concept_id}`}
                className="px-3 py-2 border border-[var(--rs-line-strong)] rounded-lg text-sm"
              >
                先看词条
              </Link>
              {item.item_id ? (
                <Link
                  to={`/session/${item.item_id}?mode=review`}
                  className="px-3 py-2 bg-[var(--rs-accent)] text-white rounded-lg text-sm"
                >
                  {item.is_new ? "开始学习" : "开始复习"}
                </Link>
              ) : null}
            </div>
          </li>
        ))}
      </ul>
    </AppShell>
  );
}
