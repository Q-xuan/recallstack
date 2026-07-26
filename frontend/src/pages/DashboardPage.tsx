import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import AppShell from "../components/AppShell";
import { Dashboard, recallstackApi } from "../lib/recallstackApi";

export default function DashboardPage() {
  const [data, setData] = useState<Dashboard | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const d = await recallstackApi.dashboard();
        if (!cancelled) setData(d);
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

  if (loading) {
    return (
      <AppShell title="今日" subtitle="从调用栈，到知识栈。">
        <p className="text-[var(--rs-muted)]">加载中…</p>
      </AppShell>
    );
  }
  if (error) {
    return (
      <AppShell title="今日">
        <p className="text-red-600">{error}</p>
      </AppShell>
    );
  }
  if (!data) {
    return (
      <AppShell title="今日">
        <p className="text-[var(--rs-muted)]">暂无数据</p>
      </AppShell>
    );
  }

  const repo = data.current_repository;
  const repoHref = repo ? `/repositories/${repo.id}` : "/repositories";
  const learnHref = repo ? `/repositories/${repo.id}?mode=learn` : "/repositories";
  const reviewHref = "/reviews";

  return (
    <AppShell
      title="今日"
      subtitle="把代码仓库变成可阅读、可练习、可复习的知识系统。"
      actions={
        <div className="flex flex-wrap gap-2">
          <Link to={repoHref} className="rs-btn rs-btn-primary">
            {repo ? "打开知识库" : "导入仓库"}
          </Link>
          <Link to={reviewHref} className="rs-btn rs-btn-ghost">
            复习 · {data.due_review_count}
          </Link>
        </div>
      }
    >
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
        <FlowCard
          step="01"
          title="阅读 Wiki"
          value={data.learning_concept_count}
          desc="架构地图与概念词条"
          href={repoHref}
        />
        <FlowCard
          step="02"
          title="主动回忆"
          value={data.code_trace_count}
          desc="源码追踪与自测"
          href={learnHref}
        />
        <FlowCard
          step="03"
          title="间隔复习"
          value={data.interval_review_count}
          desc="到期 FSRS 卡片"
          href={reviewHref}
        />
      </div>

      <section className="rs-card p-6 mb-6">
        <div className="flex items-end justify-between gap-4 flex-wrap">
          <div>
            <div className="text-[11px] font-semibold tracking-[0.1em] uppercase text-[var(--rs-muted)]">
              Current Library
            </div>
            <div className="mt-1 text-[24px] font-semibold tracking-tight">
              {repo?.name || "尚未导入仓库"}
            </div>
            <div className="mt-1 text-[14px] text-[var(--rs-ink-2)] rs-tabular">
              学习进度 {data.progress_percent}%
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <Link to={repoHref} className="rs-btn rs-btn-secondary h-9">
              阅读
            </Link>
            <Link to={learnHref} className="rs-btn rs-btn-secondary h-9">
              路径
            </Link>
            <Link to={reviewHref} className="rs-btn rs-btn-secondary h-9">
              复习
            </Link>
          </div>
        </div>
        <p className="mt-5 text-[14px] leading-relaxed text-[var(--rs-ink-2)] max-w-3xl">
          建议路径：打开知识库 → 按导读路径阅读词条 → 词条内 30 秒自测 → 到期进入复习队列。
        </p>
      </section>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <section className="rs-card p-5">
          <h2 className="text-[15px] font-semibold tracking-tight mb-3">最近阅读 / 练习</h2>
          {data.recent_concepts.length === 0 ? (
            <p className="text-[13px] text-[var(--rs-muted)]">还没有学习记录</p>
          ) : (
            <ul className="space-y-2.5">
              {data.recent_concepts.map((c) => (
                <li key={c.id} className="flex items-center justify-between gap-3">
                  <Link
                    className="text-[14px] text-[var(--rs-accent)] hover:underline"
                    to={`/concepts/${c.id}`}
                  >
                    {c.title}
                  </Link>
                  <span className="text-[12px] text-[var(--rs-muted)] rs-tabular">
                    {(c.mastery_score ?? 0).toFixed(2)}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </section>
        <section className="rs-card p-5">
          <h2 className="text-[15px] font-semibold tracking-tight mb-3">薄弱概念</h2>
          {data.weak_concepts.length === 0 ? (
            <p className="text-[13px] text-[var(--rs-muted)]">暂无薄弱项</p>
          ) : (
            <ul className="space-y-2.5">
              {data.weak_concepts.map((c) => (
                <li key={c.id} className="flex items-center justify-between gap-3">
                  <Link
                    className="text-[14px] text-rose-600 hover:underline"
                    to={`/concepts/${c.id}`}
                  >
                    {c.title}
                  </Link>
                  <span className="text-[12px] text-[var(--rs-muted)] rs-tabular">
                    {(c.mastery_score ?? 0).toFixed(2)}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </AppShell>
  );
}

function FlowCard({
  step,
  title,
  value,
  desc,
  href,
}: {
  step: string;
  title: string;
  value: number;
  desc: string;
  href: string;
}) {
  return (
    <Link
      to={href}
      className="rs-card p-5 block hover:border-black/10 transition-colors group"
    >
      <div className="flex items-center justify-between">
        <span className="text-[11px] font-semibold tracking-[0.12em] uppercase text-[var(--rs-muted)]">
          {step}
        </span>
        <span className="text-[28px] font-semibold tracking-tight rs-tabular text-[var(--rs-ink)] group-hover:text-[var(--rs-accent)] transition-colors">
          {value}
        </span>
      </div>
      <div className="mt-4 text-[16px] font-semibold tracking-tight">{title}</div>
      <div className="mt-1 text-[13px] text-[var(--rs-ink-2)]">{desc}</div>
    </Link>
  );
}
