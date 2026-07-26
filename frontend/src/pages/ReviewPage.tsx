import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import AppShell from "../components/AppShell";
import { DueReview, recallstackApi } from "../lib/recallstackApi";

export default function ReviewPage() {
  const [items, setItems] = useState<DueReview[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

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
      {loading && <p className="text-slate-500">加载中…</p>}
      {error && <p className="text-red-600">{error}</p>}
      {!loading && !error && items.length === 0 && (
        <div className="bg-white border border-slate-200 rounded-2xl p-6 text-slate-500">
          今天没有到期复习。去读一个词条并完成 30 秒自测吧。
          <div className="mt-4">
            <Link to="/repositories" className="text-indigo-700 hover:underline">
              打开仓库 Wiki
            </Link>
          </div>
        </div>
      )}

      <ul className="space-y-3">
        {items.map((item) => (
          <li
            key={item.concept_id}
            className="bg-white border border-slate-200 rounded-2xl p-4 flex items-center justify-between gap-4"
          >
            <div>
              <div className="font-medium text-slate-900">{item.title}</div>
              <div className="text-xs text-slate-500 mt-1">
                mastery {item.mastery_score.toFixed(2)}
                {item.next_review_at
                  ? ` · due ${new Date(item.next_review_at).toLocaleString()}`
                  : ""}
                {item.stale ? " · 旧版本" : ""}
              </div>
            </div>
            <div className="flex gap-2 shrink-0">
              <Link
                to={`/concepts/${item.concept_id}`}
                className="px-3 py-2 border border-slate-300 rounded-lg text-sm"
              >
                先看词条
              </Link>
              {item.item_id ? (
                <Link
                  to={`/session/${item.item_id}?mode=review`}
                  className="px-3 py-2 bg-indigo-600 text-white rounded-lg text-sm"
                >
                  开始复习会话
                </Link>
              ) : null}
            </div>
          </li>
        ))}
      </ul>
    </AppShell>
  );
}
