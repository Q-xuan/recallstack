import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import AppShell from "../components/AppShell";
import {
  AttemptResult,
  LearningItem,
  SessionQueue,
  recallstackApi,
} from "../lib/recallstackApi";

export default function LearningSessionPage() {
  const { itemId } = useParams();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const mode = searchParams.get("mode") === "review" ? "review" : "concept";

  const [queue, setQueue] = useState<SessionQueue | null>(null);
  const [item, setItem] = useState<LearningItem | null>(null);
  const [answer, setAnswer] = useState("");
  const [confidence, setConfidence] = useState(3);
  const [hintsUsed, setHintsUsed] = useState<Array<Record<string, any>>>([]);
  const [hintText, setHintText] = useState<string | null>(null);
  const [currentLevel, setCurrentLevel] = useState(0);
  const [result, setResult] = useState<AttemptResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [startedAt, setStartedAt] = useState(() => Date.now());
  const [revealed, setRevealed] = useState(false);
  const [evidenceOpen, setEvidenceOpen] = useState(false);

  const resetLocalState = useCallback(() => {
    setAnswer("");
    setConfidence(3);
    setHintsUsed([]);
    setHintText(null);
    setCurrentLevel(0);
    setResult(null);
    setError(null);
    setSubmitting(false);
    setRevealed(false);
    setEvidenceOpen(false);
    setStartedAt(Date.now());
  }, []);

  useEffect(() => {
    if (!itemId) return;
    let cancelled = false;
    (async () => {
      setLoading(true);
      resetLocalState();
      try {
        const session = await recallstackApi.itemSession(itemId, mode);
        if (cancelled) return;
        setQueue(session);
        setItem(session.current_item || (await recallstackApi.getItem(itemId)));
      } catch (e: unknown) {
        if (!cancelled) setError(e instanceof Error ? e.message : "加载失败");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [itemId, mode, resetLocalState]);

  const canSubmit = useMemo(
    () => answer.trim().length > 0 && !submitting && !result,
    [answer, submitting, result]
  );

  const progressLabel = queue
    ? `第 ${queue.position}/${queue.total} 题 · ${queue.concept_title}`
    : "练习会话";

  async function requestHint() {
    if (!itemId || result) return;
    setError(null);
    try {
      const h = await recallstackApi.hint(itemId, {
        current_level: currentLevel,
        hints_used: hintsUsed,
      });
      const entry = {
        level: h.level,
        content: h.content,
        at: new Date().toISOString(),
      };
      setHintsUsed((prev) => [...prev, entry]);
      setCurrentLevel(h.level);
      setHintText(h.content);
    } catch (e: any) {
      setError(e.message || "获取提示失败");
    }
  }

  async function revealAnswer() {
    if (!itemId || result) return;
    try {
      const h = await recallstackApi.reveal(itemId, {
        current_level: currentLevel,
        hints_used: hintsUsed,
      });
      const entry = {
        level: h.level,
        content: h.content,
        at: new Date().toISOString(),
        reveal_answer: true,
      };
      setHintsUsed((prev) => [...prev, entry]);
      setCurrentLevel(h.level);
      setHintText(h.content);
      setRevealed(true);
    } catch (e: any) {
      setError(e.message || "显示解释失败");
    }
  }

  async function submit() {
    if (!itemId || !canSubmit) return;
    setSubmitting(true);
    setError(null);
    try {
      const duration = Math.max(1, Math.round((Date.now() - startedAt) / 1000));
      const r = await recallstackApi.submitAttempt(
        itemId,
        {
          answer,
          confidence,
          hints_used: hintsUsed,
          duration_seconds: duration,
          revealed_answer: revealed,
        },
        mode
      );
      setResult(r);
      if (r.session) setQueue(r.session);
    } catch (e: any) {
      setError(e.message || "提交失败");
    } finally {
      setSubmitting(false);
    }
  }

  function goNext() {
    const nextId = result?.next_item_id || queue?.next_item_id;
    if (!nextId) {
      if (item?.concept_id) navigate(`/concepts/${item.concept_id}`);
      return;
    }
    navigate(`/session/${nextId}${mode === "review" ? "?mode=review" : ""}`);
  }

  if (loading) {
    return (
      <AppShell title="练习会话">
        <p className="text-slate-500">加载题目…</p>
      </AppShell>
    );
  }
  if (error && !item) {
    return (
      <AppShell title="练习会话">
        <p className="text-red-600">{error}</p>
      </AppShell>
    );
  }
  if (!item) {
    return (
      <AppShell title="练习会话">
        <p className="text-slate-500">题目不存在</p>
      </AppShell>
    );
  }

  const nextId = result?.next_item_id || queue?.next_item_id || null;
  const isLast = !nextId;

  return (
    <AppShell title="练习会话" subtitle={progressLabel}>
      <div className="mb-4 text-sm text-slate-500 flex items-center justify-between gap-3 flex-wrap">
        <div className="flex gap-3 items-center">
          <Link to={`/concepts/${item.concept_id}`} className="hover:underline text-indigo-700">
            返回词条
          </Link>
          {queue && (
            <span className="text-xs text-slate-400">
              已完成 {queue.completed_count}/{queue.total}
              {mode === "review" ? " · 复习模式" : ""}
            </span>
          )}
        </div>
        <span className="text-xs uppercase tracking-wide text-slate-400">{item.item_type}</span>
      </div>

      {queue && queue.items.length > 1 && (
        <div className="mb-4 flex flex-wrap gap-1.5">
          {queue.items.map((q, idx) => {
            const active = q.id === item.id;
            const done = q.attempted || (result && q.id === item.id);
            return (
              <button
                key={q.id}
                type="button"
                onClick={() =>
                  navigate(`/session/${q.id}${mode === "review" ? "?mode=review" : ""}`)
                }
                className={[
                  "h-2.5 w-8 rounded-full transition-colors",
                  active ? "bg-indigo-600" : done ? "bg-emerald-400" : "bg-slate-200",
                ].join(" ")}
                title={`${idx + 1}. ${q.item_type}`}
              />
            );
          })}
        </div>
      )}

      {item.stale && (
        <div className="mb-4 text-sm text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2">
          这个题目对应旧版本代码。
        </div>
      )}

      <div className="bg-white border border-slate-200 rounded-xl p-5 mb-4">
        <h1 className="text-xl font-semibold text-slate-900 mb-2">问题</h1>
        <p className="text-slate-800 whitespace-pre-wrap">{item.prompt}</p>
      </div>

      {(item.evidence_snippets?.length || item.source_references?.length) ? (
        <div className="bg-slate-50 border border-slate-200 rounded-xl p-4 mb-4">
          <button
            type="button"
            className="w-full flex items-center justify-between text-left"
            onClick={() => setEvidenceOpen((v) => !v)}
          >
            <div>
              <h2 className="text-sm font-semibold text-slate-800">可引用证据</h2>
              <p className="text-xs text-slate-500 mt-0.5">
                先主动回忆；卡住再展开。作答请点名文件或符号。
              </p>
            </div>
            <span className="text-xs text-indigo-700 shrink-0 ml-3">
              {evidenceOpen ? "收起" : "展开"}
            </span>
          </button>
          {evidenceOpen && (
            <ul className="space-y-3 mt-3">
              {(item.evidence_snippets?.length
                ? item.evidence_snippets
                : item.source_references.map((r) => ({
                    ...r,
                    snippet: "",
                    available: false,
                  }))
              ).map((ref, i) => (
                <li key={`${ref.path}-${i}`} className="text-sm">
                  <div className="font-mono text-xs text-indigo-800 mb-1">
                    {ref.path}
                    {ref.start_line ? `:${ref.start_line}` : ""}
                    {ref.end_line && ref.end_line !== ref.start_line ? `-${ref.end_line}` : ""}
                    {ref.symbol ? ` · ${ref.symbol}` : ""}
                  </div>
                  {ref.snippet ? (
                    <pre className="text-xs bg-white border border-slate-200 rounded-lg p-3 overflow-x-auto text-slate-700 whitespace-pre">
                      {ref.snippet}
                    </pre>
                  ) : (
                    <p className="text-xs text-slate-400">
                      {ref.available === false
                        ? "本地片段暂不可用（可能是远程仓库或路径失效）"
                        : "仅路径引用"}
                    </p>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>
      ) : null}

      {!result ? (
        <>
          <label className="block text-sm font-medium text-slate-700 mb-2">你的回答</label>
          <textarea
            value={answer}
            onChange={(e) => setAnswer(e.target.value)}
            rows={8}
            className="w-full border border-slate-300 rounded-xl p-3 text-slate-800 focus:ring-2 focus:ring-indigo-200 outline-none"
            placeholder="用自己的话作答，尽量引用源码中的模块/符号…"
          />

          <div className="mt-4 flex flex-wrap items-center gap-4">
            <label className="text-sm text-slate-700">
              自信度
              <select
                value={confidence}
                onChange={(e) => setConfidence(Number(e.target.value))}
                className="ml-2 border border-slate-300 rounded-lg px-2 py-1"
              >
                {[1, 2, 3, 4, 5].map((n) => (
                  <option key={n} value={n}>
                    {n}
                  </option>
                ))}
              </select>
            </label>
            <div className="text-sm text-slate-500">提示等级：{currentLevel}/5</div>
          </div>

          {hintText && (
            <div className="mt-4 bg-indigo-50 border border-indigo-100 rounded-xl p-4 text-sm text-slate-700 whitespace-pre-wrap">
              {hintText}
            </div>
          )}

          {error && <p className="mt-3 text-sm text-red-600">{error}</p>}

          <div className="mt-5 flex flex-wrap gap-3">
            <button
              onClick={requestHint}
              className="px-4 py-2 border border-slate-300 rounded-lg text-sm hover:bg-slate-50"
              disabled={currentLevel >= 5}
            >
              申请提示
            </button>
            <button
              onClick={revealAnswer}
              className="px-4 py-2 border border-amber-300 text-amber-800 rounded-lg text-sm hover:bg-amber-50"
            >
              显示完整解释
            </button>
            <button
              onClick={submit}
              disabled={!canSubmit}
              className="px-4 py-2 bg-indigo-600 text-white rounded-lg text-sm disabled:opacity-50"
            >
              {submitting ? "提交中…" : "提交回答"}
            </button>
          </div>
        </>
      ) : (
        <div className="space-y-4">
          <div className="bg-white border border-slate-200 rounded-xl p-5">
            <div className="flex items-center justify-between gap-3 mb-2">
              <h2 className="font-semibold text-slate-900">评价</h2>
              {result.evaluation_source && (
                <span className="text-[11px] uppercase tracking-wide text-slate-400">
                  {result.evaluation_source === "llm" ? "LLM + rubric" : "deterministic"}
                </span>
              )}
            </div>
            <p className="text-slate-800 mb-2">{result.evaluation.feedback}</p>
            <div className="text-sm text-slate-600 space-y-1">
              <div>得分：{result.score.toFixed(2)}</div>
              <div>FSRS Rating：{result.fsrs_rating}</div>
              <div>掌握度：{result.mastery_score?.toFixed(2) ?? "—"}</div>
              <div>
                下次复习：
                {result.next_review_at
                  ? new Date(result.next_review_at).toLocaleString()
                  : "—"}
              </div>
              <div>覆盖点：{(result.evaluation.covered_points || []).join(", ") || "—"}</div>
              <div>遗漏点：{(result.evaluation.missing_points || []).join(", ") || "—"}</div>
            </div>
            {result.evaluation.suggested_revision && (
              <p className="mt-3 text-sm text-indigo-800">
                改进建议：{result.evaluation.suggested_revision}
              </p>
            )}
            {result.evaluation.follow_up_question && (
              <p className="mt-2 text-sm text-slate-600">
                追问：{result.evaluation.follow_up_question}
              </p>
            )}
          </div>

          <div className="bg-white border border-slate-200 rounded-xl p-5">
            <h2 className="font-semibold text-slate-900 mb-2">源码证据</h2>
            <ul className="text-sm text-slate-700 space-y-1">
              {(result.evaluation.source_evidence || []).map((ref, i) => (
                <li key={i}>
                  {ref.path}
                  {ref.start_line ? `:${ref.start_line}` : ""}
                  {ref.symbol ? ` (${ref.symbol})` : ""}
                </li>
              ))}
            </ul>
          </div>

          {result.expected_answer_outline && (
            <div className="bg-slate-50 border border-slate-200 rounded-xl p-5">
              <h2 className="font-semibold text-slate-900 mb-2">答案提纲</h2>
              <pre className="text-sm text-slate-700 whitespace-pre-wrap">
                {result.expected_answer_outline}
              </pre>
            </div>
          )}

          <div className="flex flex-wrap gap-3">
            {!isLast ? (
              <button
                type="button"
                onClick={goNext}
                className="px-4 py-2 bg-indigo-600 text-white rounded-lg text-sm"
              >
                下一题
              </button>
            ) : (
              <Link
                to={`/concepts/${item.concept_id}`}
                className="px-4 py-2 bg-indigo-600 text-white rounded-lg text-sm"
              >
                完成本轮 · 返回词条
              </Link>
            )}
            <Link
              to={`/concepts/${item.concept_id}`}
              className="px-4 py-2 border border-slate-300 rounded-lg text-sm"
            >
              返回词条
            </Link>
            <Link
              to="/reviews"
              className="px-4 py-2 border border-slate-300 rounded-lg text-sm"
            >
              查看复习队列
            </Link>
          </div>
        </div>
      )}
    </AppShell>
  );
}
