import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import AppShell from "../components/AppShell";
import InlineProbe from "../components/InlineProbe";
import {
  Concept,
  ConceptEdge,
  LearningItem,
  SourceRef,
  recallstackApi,
} from "../lib/recallstackApi";

export default function ConceptPage() {
  const { id } = useParams();
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
        // graph for relations
        const g = await recallstackApi.concepts(c.repository_id);
        if (!cancelled) {
          setConcept(c);
          setItems(its);
          setEdges(g.edges);
          setAllConcepts(g.concepts);
        }
      } catch (e: unknown) {
        if (!cancelled) setError(e instanceof Error ? e.message : "加载失败");
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
      setSnippet(`无法加载源码：${e instanceof Error ? e.message : "unknown error"}`);
    }
  }

  if (loading) {
    return (
      <AppShell title="概念词条">
        <p className="text-slate-500">加载中…</p>
      </AppShell>
    );
  }
  if (error || !concept) {
    return (
      <AppShell title="概念词条">
        <p className="text-red-600">{error || "概念不存在"}</p>
      </AppShell>
    );
  }

  return (
    <AppShell>
      <div className="mb-4 text-sm text-slate-500 flex items-center justify-between gap-3 flex-wrap">
        <div className="flex gap-4">
          <Link
            to={`/repositories/${concept.repository_id}`}
            className="hover:underline text-indigo-700"
          >
            ← 返回仓库 Wiki
          </Link>
          {concept.wiki_page_id && (
            <Link
              to={`/repositories/${concept.repository_id}?page=${encodeURIComponent(concept.wiki_page_id)}`}
              className="hover:underline text-slate-600"
            >
              打开对应 Wiki 词条
            </Link>
          )}
        </div>
        <span className="text-xs text-slate-400">词条 · {concept.slug}</span>
      </div>

      <article className="bg-white border border-slate-200 rounded-2xl overflow-hidden">
        {/* 1. 是什么 */}
        <header className="px-6 md:px-8 py-6 border-b border-slate-100 bg-gradient-to-r from-slate-50 to-indigo-50">
          <div className="text-xs uppercase tracking-wide text-slate-400 mb-2">1 · 是什么</div>
          <h1 className="text-3xl font-bold text-slate-900 mb-2">{concept.title}</h1>
          {concept.stale && (
            <div className="inline-block text-sm text-amber-800 bg-amber-50 border border-amber-200 rounded-lg px-3 py-1.5 mb-2">
              这个词条对应旧版本代码
            </div>
          )}
          <p className="text-slate-700 leading-relaxed max-w-3xl">{concept.description}</p>
        </header>

        <div className="grid grid-cols-1 lg:grid-cols-[1fr_280px]">
          <div className="p-6 md:p-8 space-y-10">
            {/* 2. 为什么重要 */}
            <section>
              <h2 className="text-lg font-semibold text-slate-900 mb-2">2 · 为什么重要</h2>
              <p className="text-slate-700 leading-relaxed">
                {concept.why_learn || "理解该概念有助于建立对仓库主流程的心智模型。"}
              </p>
            </section>

            {/* 3. 源码证据 */}
            <section>
              <h2 className="text-lg font-semibold text-slate-900 mb-2">3 · 源码证据</h2>
              <p className="text-sm text-slate-500 mb-3">
                Wiki 的可信度来自证据。先读这些位置，再做回忆。
              </p>
              <ul className="space-y-2">
                {(concept.source_references || []).map((ref, i) => (
                  <li key={`${ref.path}-${i}`}>
                    <button
                      className="w-full text-left font-mono text-sm px-3 py-2 rounded-lg border border-slate-200 hover:border-indigo-300 hover:bg-indigo-50 text-slate-800"
                      onClick={() => openRef(ref)}
                    >
                      {ref.path}
                      {ref.start_line ? `:${ref.start_line}` : ""}
                      {ref.symbol ? `  (${ref.symbol})` : ""}
                    </button>
                  </li>
                ))}
              </ul>
              {snippet && (
                <div className="mt-4">
                  <div className="text-xs text-slate-500 mb-1">{snippetPath}</div>
                  <pre className="bg-slate-900 text-slate-100 text-xs rounded-xl p-4 overflow-auto max-h-96 whitespace-pre-wrap">
                    {snippet}
                  </pre>
                </div>
              )}
            </section>

            {/* 4. 关系 */}
            <section>
              <h2 className="text-lg font-semibold text-slate-900 mb-3">4 · 调用 / 依赖关系</h2>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="border border-slate-200 rounded-xl p-4">
                  <h3 className="text-sm font-semibold text-slate-700 mb-2">先修概念</h3>
                  {prereqs.length === 0 ? (
                    <p className="text-sm text-slate-400">无（可作为入口）</p>
                  ) : (
                    <ul className="space-y-1">
                      {prereqs.map((c) => (
                        <li key={c.id}>
                          <Link className="text-sm text-indigo-700 hover:underline" to={`/concepts/${c.id}`}>
                            {c.title}
                          </Link>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
                <div className="border border-slate-200 rounded-xl p-4">
                  <h3 className="text-sm font-semibold text-slate-700 mb-2">相关概念</h3>
                  {related.length === 0 ? (
                    <p className="text-sm text-slate-400">无</p>
                  ) : (
                    <ul className="space-y-1">
                      {related.map((c) => (
                        <li key={c.id}>
                          <Link className="text-sm text-indigo-700 hover:underline" to={`/concepts/${c.id}`}>
                            {c.title}
                          </Link>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              </div>
            </section>

            {/* 5. 30 秒自测 */}
            <section>
              <h2 className="text-lg font-semibold text-slate-900 mb-3">5 · 30 秒自测</h2>
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

            {/* 6. 深入练习 */}
            <section className="border-t border-slate-100 pt-6">
              <div className="flex items-center justify-between gap-3 mb-2 flex-wrap">
                <h2 className="text-lg font-semibold text-slate-900">6 · 深入练习</h2>
                {items.length > 0 && (
                  <Link
                    to={`/session/${(probeItem || items[0]).id}`}
                    className="px-3 py-1.5 bg-indigo-600 text-white rounded-lg text-sm"
                  >
                    开始本概念会话（{items.length} 题）
                  </Link>
                )}
              </div>
              <p className="text-sm text-slate-500 mb-3">
                按 active_recall → code_trace → teach_back 顺序连续练习，提交后自动进入下一题。
              </p>
              {items.length === 0 ? (
                <p className="text-sm text-slate-400">暂无练习题。</p>
              ) : (
                <ul className="space-y-2">
                  {items.map((item, idx) => (
                    <li
                      key={item.id}
                      className="flex items-center justify-between gap-3 border border-slate-200 rounded-xl px-4 py-3"
                    >
                      <div className="min-w-0">
                        <div className="text-[11px] uppercase tracking-wide text-slate-400 mb-1">
                          {idx + 1}. {item.item_type}
                        </div>
                        <div className="text-sm text-slate-800 line-clamp-2">{item.prompt}</div>
                      </div>
                      <Link
                        to={`/session/${item.id}`}
                        className="text-sm text-indigo-700 hover:underline shrink-0"
                      >
                        从这里开始
                      </Link>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          </div>

          {/* 7. 掌握度 */}
          <aside className="border-t lg:border-t-0 lg:border-l border-slate-100 p-6 bg-slate-50 space-y-4">
            <div className="text-xs font-semibold uppercase tracking-wide text-slate-400">
              7 · 掌握与复习
            </div>
            <Meta
              label="掌握度"
              value={
                concept.mastery_score == null ? "未练习" : concept.mastery_score.toFixed(2)
              }
            />
            <Meta
              label="下次复习"
              value={
                concept.next_review_at
                  ? new Date(concept.next_review_at).toLocaleString()
                  : "完成自测后生成"
              }
            />
            <Meta label="难度" value={String(concept.difficulty)} />
            <Meta label="重要度" value={concept.importance.toFixed(2)} />
            <Meta label="预计学习" value={`${concept.estimated_minutes ?? 15} 分钟`} />
            {items.length > 0 && (
              <Link
                to={`/session/${(probeItem || items[0]).id}`}
                className="block text-center w-full px-4 py-2.5 bg-indigo-600 text-white rounded-lg text-sm"
              >
                开始练习会话
              </Link>
            )}
            <Link
              to={`/repositories/${concept.repository_id}?mode=learn`}
              className="block text-center w-full px-4 py-2.5 border border-slate-300 rounded-lg text-sm text-slate-700"
            >
              回到学习路径
            </Link>
            <Link
              to="/reviews"
              className="block text-center w-full px-4 py-2.5 border border-slate-300 rounded-lg text-sm text-slate-700"
            >
              打开复习队列
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
      <div className="text-xs text-slate-500 mb-1">{label}</div>
      <div className="text-sm font-medium text-slate-900">{value}</div>
    </div>
  );
}
