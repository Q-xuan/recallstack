import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import AppShell from "../components/AppShell";
import { tNow, useT } from "../lib/i18n";
import { Dashboard, Repository, recallstackApi } from "../lib/recallstackApi";

/**
 * Wiki-first home.
 *
 * The primary act is "open a wiki and read"; review queues and weak concepts
 * are a supporting band below, not the headline.
 */
export default function DashboardPage() {
  const t = useT();
  const [data, setData] = useState<Dashboard | null>(null);
  const [repos, setRepos] = useState<Repository[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [d, list] = await Promise.all([
          recallstackApi.dashboard(),
          recallstackApi.listRepositories().catch(() => [] as Repository[]),
        ]);
        if (cancelled) return;
        setData(d);
        setRepos(list);
      } catch (e: unknown) {
        if (!cancelled) setError(e instanceof Error ? e.message : tNow("加载失败", "Failed to load"));
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
      <AppShell title={t("今日", "Today")} subtitle={t("从调用栈，到知识栈。", "From call stack to knowledge stack.")}>
        <p className="text-[var(--rs-muted)]">{t("加载中…", "Loading…")}</p>
      </AppShell>
    );
  }
  if (error) {
    return (
      <AppShell title={t("今日", "Today")}>
        <div className="rs-alert">{error}</div>
      </AppShell>
    );
  }
  if (!data) {
    return (
      <AppShell title={t("今日", "Today")}>
        <p className="text-[var(--rs-muted)]">{t("暂无数据", "No data yet")}</p>
      </AppShell>
    );
  }

  const repo = data.current_repository;
  const repoHref = repo ? `/repositories/${repo.id}` : "/repositories";

  return (
    <AppShell
      title={t("读懂一个代码库", "Understand a codebase")}
      subtitle={t(
        "一次扫描，生成可阅读、可搜索、每条结论都能跳回源码的 Wiki。学习方法论在旁边帮你记住。",
        "One scan builds a readable, searchable wiki where every claim links back to source. Learning science on the side helps it stick.",
      )}
      actions={
        <Link to={repoHref} className="rs-btn rs-btn-primary h-11 px-6">
          {repo ? t(`打开 ${repo.name}`, `Open ${repo.name}`) : t("导入第一个仓库", "Import your first repository")}
        </Link>
      }
    >
      {/* Primary surface: the libraries themselves. */}
      <section className="mb-8">
        <div className="flex items-end justify-between gap-4 mb-3">
          <div className="rs-eyebrow">{t("你的知识库", "Your library")}</div>
          <Link to="/repositories" className="text-[13px] text-[var(--rs-accent)] hover:underline">
            {t("导入新仓库 →", "Import a repository →")}
          </Link>
        </div>

        {repos.length === 0 ? (
          <div className="rs-card p-8 text-center">
            <div className="rs-hero-mark mx-auto">⌘</div>
            <h2 className="rs-title text-[22px] font-semibold mt-4">{t("还没有仓库", "No repositories yet")}</h2>
            <p className="mt-2 text-[14px] text-[var(--rs-ink-2)] max-w-md mx-auto">
              {t(
                "指向一个本地目录或 GitHub 仓库，几分钟后你会得到一份带架构图、模块页与源码引用的 Wiki。",
                "Point at a local directory or GitHub repo and get a wiki with architecture diagrams, module pages and source citations in minutes.",
              )}
            </p>
            <Link to="/repositories" className="rs-btn rs-btn-primary mt-5 h-10 px-5">
              {t("导入仓库", "Import repository")}
            </Link>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {repos.map((r) => (
              <Link key={r.id} to={`/repositories/${r.id}`} className="rs-lib-card">
                <div className="flex items-start justify-between gap-3">
                  <div className="text-[16px] font-semibold tracking-tight truncate">{r.name}</div>
                  <span className="rs-chip shrink-0">{r.source_type}</span>
                </div>
                <div className="mt-1.5 text-[12px] text-[var(--rs-muted)] truncate font-mono">
                  {r.source_location}
                </div>
                <div className="mt-4 text-[13px] text-[var(--rs-accent)]">{t("打开 Wiki →", "Open wiki →")}</div>
              </Link>
            ))}
          </div>
        )}
      </section>

      {repo && (
        <section className="rs-card p-6 mb-8">
          <div className="flex items-end justify-between gap-4 flex-wrap">
            <div>
              <div className="rs-eyebrow">{t("当前进度", "Current progress")}</div>
              <div className="mt-1 text-[22px] font-semibold tracking-tight">{repo.name}</div>
              <div className="mt-1 text-[13px] text-[var(--rs-ink-2)] rs-tabular">
                {data.learning_concept_count}{t(" 个词条 · 已掌握 ", " concepts · mastered ")}{data.progress_percent}%
              </div>
            </div>
            <Link to={repoHref} className="rs-btn rs-btn-secondary h-9">
              {t("继续阅读", "Continue reading")}
            </Link>
          </div>
          <div className="rs-meter mt-5" aria-hidden>
            <span style={{ width: `${Math.min(100, Math.max(0, data.progress_percent))}%` }} />
          </div>
        </section>
      )}

      {/* Assistive band: spaced repetition supports the reading, not vice versa. */}
      <div className="rs-eyebrow mb-3">{t("辅助 · 学习方法论", "Assistive · learning science")}</div>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <section className="rs-card p-5">
          <div className="flex items-baseline justify-between">
            <h2 className="text-[14px] font-semibold tracking-tight">{t("到期复习", "Due for review")}</h2>
            <span className="text-[24px] font-semibold rs-tabular">{data.due_review_count}</span>
          </div>
          <p className="mt-1 text-[12.5px] text-[var(--rs-muted)]">
            {t("间隔重复把读过的内容留下来。", "Spaced repetition keeps what you read.")}
          </p>
          <Link to="/reviews" className="rs-btn rs-btn-ghost h-8 px-3 text-[12px] mt-4">
            {data.due_review_count ? t("开始复习", "Start reviewing") : t("查看队列", "View queue")}
          </Link>
        </section>

        <section className="rs-card p-5">
          <h2 className="text-[14px] font-semibold tracking-tight mb-3">{t("最近读过", "Recently read")}</h2>
          {data.recent_concepts.length === 0 ? (
            <p className="text-[12.5px] text-[var(--rs-muted)]">{t("还没有记录", "Nothing yet")}</p>
          ) : (
            <ul className="space-y-2">
              {data.recent_concepts.slice(0, 5).map((c) => (
                <li key={c.id} className="flex items-center justify-between gap-3">
                  <Link
                    className="text-[13.5px] text-[var(--rs-accent)] hover:underline truncate"
                    to={`/concepts/${c.id}`}
                  >
                    {c.title}
                  </Link>
                  <span className="text-[11.5px] text-[var(--rs-muted)] rs-tabular shrink-0">
                    {(c.mastery_score ?? 0).toFixed(2)}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="rs-card p-5">
          <h2 className="text-[14px] font-semibold tracking-tight mb-3">{t("值得重读", "Worth rereading")}</h2>
          {data.weak_concepts.length === 0 ? (
            <p className="text-[12.5px] text-[var(--rs-muted)]">{t("暂无薄弱项", "No weak spots")}</p>
          ) : (
            <ul className="space-y-2">
              {data.weak_concepts.slice(0, 5).map((c) => (
                <li key={c.id} className="flex items-center justify-between gap-3">
                  <Link
                    className="text-[13.5px] text-[var(--rs-ink)] hover:text-[var(--rs-accent)] truncate"
                    to={`/concepts/${c.id}`}
                  >
                    {c.title}
                  </Link>
                  <span className="text-[11.5px] text-[var(--rs-warning)] rs-tabular shrink-0">
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
