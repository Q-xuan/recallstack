import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import AppShell from "../components/AppShell";
import InlineProbe from "../components/InlineProbe";
import { tNow, useT } from "../lib/i18n";
import {
  Concept,
  ConceptEdge,
  LearningItem,
  SourceRef,
  recallstackApi,
} from "../lib/recallstackApi";

export default function ConceptPage() {
  const { id } = useParams();
  const t = useT();
  const [concept, setConcept] = useState<Concept | null>(null);
  const [items, setItems] = useState<LearningItem[]>([]);
  const [edges, setEdges] = useState<ConceptEdge[]>([]);
  const [allConcepts, setAllConcepts] = useState<Concept[]>([]);
  const [snippet, setSnippet] = useState<string | null>(null);
  const [snippetPath, setSnippetPath] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!id) return;
    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        const c = await recallstackApi.getConcept(id);
        const its = await recallstackApi.listItems(id);
        const g = await recallstackApi.concepts(c.repository_id);
        if (!cancelled) {
          setConcept(c);
          setItems(its);
          setEdges(g.edges);
          setAllConcepts(g.concepts);
        }
      } catch (e: unknown) {
        if (!cancelled) setError(e instanceof Error ? e.message : tNow("加载失败", "Failed to load"));
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [id]);

  const probeItem = useMemo(() => {
    return (
      items.find((i) => i.item_type === "active_recall") ||
      items[0] ||
      null
    );
  }, [items]);

  const prereqs = useMemo(() => {
    if (!concept) return [] as Concept[];
    const ids = edges
      .filter((e) => e.target_concept_id === concept.id && e.relation_type === "prerequisite")
      .map((e) => e.source_concept_id);
    return ids
      .map((cid) => allConcepts.find((c) => c.id === cid))
      .filter((x): x is Concept => Boolean(x));
  }, [concept, edges, allConcepts]);

  const related = useMemo(() => {
    if (!concept) return [] as Concept[];
    const ids = edges
      .filter(
        (e) =>
          (e.source_concept_id === concept.id || e.target_concept_id === concept.id) &&
          e.relation_type !== "prerequisite"
      )
      .map((e) =>
        e.source_concept_id === concept.id ? e.target_concept_id : e.source_concept_id
      );
    return [...new Set(ids)]
      .map((cid) => allConcepts.find((c) => c.id === cid))
      .filter((x): x is Concept => Boolean(x));
  }, [concept, edges, allConcepts]);

  async function openRef(ref: SourceRef) {
    if (!concept) return;
    try {
      const data = await recallstackApi.sourceSnippet({
        repository_id: concept.repository_id,
        path: ref.path,
        start_line: ref.start_line,
        end_line: ref.end_line,
      });
      setSnippetPath(`${data.path}:${data.start_line}-${data.end_line}`);
      setSnippet(data.content);
    } catch (e: unknown) {
      setSnippetPath(ref.path);
      setSnippet(
        `${tNow("无法加载源码：", "Could not load source: ")}${e instanceof Error ? e.message : "unknown error"}`,
      );
    }
  }

  if (loading) {
    return (
      <AppShell title={t("概念词条", "Concept")}>
        <p className="text-[var(--rs-muted)]">{t("加载中…", "Loading…")}</p>
      </AppShell>
    );
  }
  if (error || !concept) {
    return (
      <AppShell title={t("概念词条", "Concept")}>
        <p className="text-[var(--rs-danger)]">{error || t("概念不存在", "Concept not found")}</p>
      </AppShell>
    );
  }

  return (
    <AppShell>
      <div className="mb-4 text-sm text-[var(--rs-muted)] flex items-center justify-between gap-3 flex-wrap">
        <div className="flex gap-4">
          <Link
            to={`/repositories/${concept.repository_id}`}
            className="hover:underline text-[var(--rs-accent)]"
          >
            ← {t("返回仓库 Wiki", "Back to repository wiki")}
          </Link>
          {concept.wiki_page_id && (
            <Link
              to={`/repositories/${concept.repository_id}?page=${encodeURIComponent(concept.wiki_page_id)}`}
              className="hover:underline text-[var(--rs-ink-2)]"
            >
              {t("打开对应 Wiki 词条", "Open matching wiki page")}
            </Link>
          )}
        </div>
        <span className="text-xs text-[var(--rs-muted)]">{t("词条", "Entry")} · {concept.slug}</span>
      </div>

      <article className="rs-card rounded-2xl overflow-hidden">
        <header className="px-6 md:px-8 py-6 border-b border-[var(--rs-line)] bg-[var(--rs-surface-2)]">
          <div className="text-xs uppercase tracking-wide text-[var(--rs-muted)] mb-2">
            1 · {t("是什么", "What it is")}
          </div>
          <h1 className="text-3xl font-bold text-[var(--rs-ink)] mb-2">{concept.title}</h1>
          {concept.stale && (
            <div className="inline-block text-sm text-[var(--rs-warning)] bg-[var(--rs-warning-soft)] border border-[var(--rs-warning)] rounded-lg px-3 py-1.5 mb-2">
              {t("这个词条对应旧版本代码", "This entry matches an older version of the code")}
            </div>
          )}
          <p className="text-[var(--rs-ink-2)] leading-relaxed max-w-3xl">{concept.description}</p>
        </header>

        <div className="grid grid-cols-1 lg:grid-cols-[1fr_280px]">
          <div className="p-6 md:p-8 space-y-10">
            <section>
              <h2 className="text-lg font-semibold text-[var(--rs-ink)] mb-2">
                2 · {t("为什么重要", "Why it matters")}
              </h2>
              <p className="text-[var(--rs-ink-2)] leading-relaxed">
                {concept.why_learn ||
                  t(
                    "理解该概念有助于建立对仓库主流程的心智模型。",
                    "Understanding this concept helps you build a mental model of the repository’s main flow.",
                  )}
              </p>
            </section>

            <section>
              <h2 className="text-lg font-semibold text-[var(--rs-ink)] mb-2">
                3 · {t("源码证据", "Source evidence")}
              </h2>
              <p className="text-sm text-[var(--rs-muted)] mb-3">
                {t(
                  "Wiki 的可信度来自证据。先读这些位置，再做回忆。",
                  "The wiki is only as trustworthy as its evidence. Read these sites, then recall.",
                )}
              </p>
              <ul className="space-y-2">
                {(concept.source_references || []).map((ref, i) => (
                  <li key={`${ref.path}-${i}`}>
                    <button
                      className="w-full text-left font-mono text-sm px-3 py-2 rounded-lg border border-[var(--rs-line)] hover:border-[var(--rs-accent)] hover:bg-[var(--rs-accent-soft)] text-[var(--rs-ink)]"
                      onClick={() => openRef(ref)}
                    >
                      {ref.path}
                      {ref.start_line ? `:${ref.start_line}` : ""}
                      {ref.symbol ? ` ${ref.symbol}` : ""}
                    </button>
                  </li>
                ))}
              </ul>
              {snippet && (
                <div className="mt-4">
                  <div className="text-xs text-[var(--rs-muted)] mb-1">{snippetPath}</div>
                  <pre className="bg-[var(--rs-ink)] text-[var(--rs-surface)] text-xs rounded-xl p-4 overflow-auto max-h-96 whitespace-pre-wrap">
                    {snippet}
                  </pre>
                </div>
              )}
            </section>

            <section>
              <h2 className="text-lg font-semibold text-[var(--rs-ink)] mb-3">
                4 · {t("调用 / 依赖关系", "Calls / dependencies")}
              </h2>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="border border-[var(--rs-line)] rounded-xl p-4">
                  <h3 className="text-sm font-semibold text-[var(--rs-ink-2)] mb-2">
                    {t("先修概念", "Prerequisites")}
                  </h3>
                  {prereqs.length === 0 ? (
                    <p className="text-sm text-[var(--rs-muted)]">{t("无（可作为入口）", "None (this can be an entry)")}</p>
                  ) : (
                    <ul className="space-y-1">
                      {prereqs.map((c) => (
                        <li key={c.id}>
                          <Link className="text-sm text-[var(--rs-accent)] hover:underline" to={`/concepts/${c.id}`}>
                            {c.title}
                          </Link>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
                <div className="border border-[var(--rs-line)] rounded-xl p-4">
                  <h3 className="text-sm font-semibold text-[var(--rs-ink-2)] mb-2">
                    {t("相关概念", "Related concepts")}
                  </h3>
                  {related.length === 0 ? (
                    <p className="text-sm text-[var(--rs-muted)]">{t("无", "None")}</p>
                  ) : (
                    <ul className="space-y-1">
                      {related.map((c) => (
                        <li key={c.id}>
                          <Link className="text-sm text-[var(--rs-accent)] hover:underline" to={`/concepts/${c.id}`}>
                            {c.title}
                          </Link>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              </div>
            </section>

            <section>
              <h2 className="text-lg font-semibold text-[var(--rs-ink)] mb-3">
                5 · {t("30 秒自测", "30-second self-check")}
              </h2>
              <InlineProbe
                item={probeItem}
                onCompleted={(r) => {
                  setConcept((prev) =>
                    prev
                      ? {
                          ...prev,
                          mastery_score: r.mastery_score ?? prev.mastery_score,
                          next_review_at: r.next_review_at ?? prev.next_review_at,
                        }
                      : prev
                  );
                }}
              />
            </section>

            <section className="border-t border-[var(--rs-line)] pt-6">
              <div className="flex items-center justify-between gap-3 mb-2 flex-wrap">
                <h2 className="text-lg font-semibold text-[var(--rs-ink)]">
                  6 · {t("深入练习", "Deeper practice")}
                </h2>
                {items.length > 0 && (
                  <Link
                    to={`/session/${(probeItem || items[0]).id}`}
                    className="px-3 py-1.5 bg-[var(--rs-accent)] text-white rounded-lg text-sm"
                  >
                    {t(
                      `开始本概念会话（${items.length} 题）`,
                      `Start this concept session (${items.length} items)`,
                    )}
                  </Link>
                )}
              </div>
              <p className="text-sm text-[var(--rs-muted)] mb-3">
                {t(
                  "按 active_recall → code_trace → teach_back 顺序连续练习，提交后自动进入下一题。",
                  "Practice in order: active_recall → code_trace → teach_back. Submit to move to the next item.",
                )}
              </p>
              {items.length === 0 ? (
                <p className="text-sm text-[var(--rs-muted)]">{t("暂无练习题。", "No practice items yet.")}</p>
              ) : (
                <ul className="space-y-2">
                  {items.map((item, idx) => (
                    <li
                      key={item.id}
                      className="flex items-center justify-between gap-3 border border-[var(--rs-line)] rounded-xl px-4 py-3"
                    >
                      <div className="min-w-0">
                        <div className="text-[11px] uppercase tracking-wide text-[var(--rs-muted)] mb-1">
                          {idx + 1}. {item.item_type}
                        </div>
                        <div className="text-sm text-[var(--rs-ink)] line-clamp-2">{item.prompt}</div>
                      </div>
                      <Link
                        to={`/session/${item.id}`}
                        className="text-sm text-[var(--rs-accent)] hover:underline shrink-0"
                      >
                        {t("从这里开始", "Start here")}
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          </div>

          <aside className="border-t lg:border-t-0 lg:border-l border-[var(--rs-line)] p-6 bg-[var(--rs-surface-2)] space-y-4">
            <div className="text-xs font-semibold uppercase tracking-wide text-[var(--rs-muted)]">
              7 · {t("掌握与复习", "Mastery and review")}
            </div>
            <Meta
              label={t("掌握度", "Mastery")}
              value={
                concept.mastery_score == null
                  ? t("未练习", "Not practiced")
                  : concept.mastery_score.toFixed(2)
              }
            />
            <Meta
              label={t("下次复习", "Next review")}
              value={
                concept.next_review_at
                  ? new Date(concept.next_review_at).toLocaleString()
                  : t("完成自测后生成", "Set after you finish a self-check")
              }
            />
            <Meta label={t("难度", "Difficulty")} value={String(concept.difficulty)} />
            <Meta label={t("重要度", "Importance")} value={concept.importance.toFixed(2)} />
            <Meta
              label={t("预计学习", "Estimated time")}
              value={`${concept.estimated_minutes ?? 15} ${t("分钟", "min")}`}
            />
            {items.length > 0 && (
              <Link
                to={`/session/${(probeItem || items[0]).id}`}
                className="block text-center w-full px-4 py-2.5 bg-[var(--rs-accent)] text-white rounded-lg text-sm"
              >
                {t("开始练习会话", "Start practice session")}
              </Link>
            )}
            <Link
              to={`/repositories/${concept.repository_id}?mode=learn`}
              className="block text-center w-full px-4 py-2.5 border border-[var(--rs-line-strong)] rounded-lg text-sm text-[var(--rs-ink-2)]"
            >
              {t("回到学习路径", "Back to learning path")}
            </Link>
            <Link
              to="/reviews"
              className="block text-center w-full px-4 py-2.5 border border-[var(--rs-line-strong)] rounded-lg text-sm text-[var(--rs-ink-2)]"
            >
              {t("打开复习队列", "Open review queue")}
            </Link>
          </aside>
        </div>
      </article>
    </AppShell>
  );
}

function Meta({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-xs text-[var(--rs-muted)] mb-1">{label}</div>
      <div className="text-sm font-medium text-[var(--rs-ink)]">{value}</div>
    </div>
  );
}
