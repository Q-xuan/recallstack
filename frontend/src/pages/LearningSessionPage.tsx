import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import AppShell from "../components/AppShell";
import { tNow, useT } from "../lib/i18n";
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
  const t = useT();
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
        if (!cancelled) setError(e instanceof Error ? e.message : tNow("加载失败", "Failed to load"));
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
    ? t(
        `第 ${queue.position}/${queue.total} 题 · ${queue.concept_title}`,
        `Item ${queue.position}/${queue.total} · ${queue.concept_title}`,
      )
    : t("练习会话", "Practice session");

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
      setError(e.message || tNow("获取提示失败", "Failed to get a hint"));
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
      setError(e.message || tNow("显示解释失败", "Failed to show the explanation"));
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
      setError(e.message || tNow("提交失败", "Submit failed"));
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
      <AppShell title={t("练习会话", "Practice session")}>
        <p className="text-[var(--rs-muted)]">{t("加载题目…", "Loading item…")}</p>
      </AppShell>
    );
  }
  if (error && !item) {
    return (
      <AppShell title={t("练习会话", "Practice session")}>
        <p className="text-[var(--rs-danger)]">{error}</p>
      </AppShell>
    );
  }
  if (!item) {
    return (
      <AppShell title={t("练习会话", "Practice session")}>
        <p className="text-[var(--rs-muted)]">{t("题目不存在", "Item not found")}</p>
      </AppShell>
    );
  }

  const nextId = result?.next_item_id || queue?.next_item_id || null;
  const isLast = !nextId;

  return (
    <AppShell title={t("练习会话", "Practice session")} subtitle={progressLabel}>
      <div className="mb-4 text-sm text-[var(--rs-muted)] flex items-center justify-between gap-3 flex-wrap">
        <div className="flex gap-3 items-center">
          <Link to={`/concepts/${item.concept_id}`} className="hover:underline text-[var(--rs-accent)]">
            {t("返回词条", "Back to entry")}
          </Link>
          {queue && (
            <span className="text-xs text-[var(--rs-muted)]">
              {t("已完成", "Completed")} {queue.completed_count}/{queue.total}
              {mode === "review" ? t(" · 复习模式", " · review mode") : ""}
            </span>
          )}
        </div>
        <span className="text-xs uppercase tracking-wide text-[var(--rs-muted)]">{item.item_type}</span>
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
                  active ? "bg-[var(--rs-accent)]" : done ? "bg-[var(--rs-success)]" : "bg-[var(--rs-surface-3)]",
                ].join(" ")}
                title={`${idx + 1}. ${q.item_type}`}
              />
            );
          })}
        </div>
      )}

      {item.stale && (
        <div className="mb-4 text-sm text-[var(--rs-warning)] bg-[var(--rs-warning-soft)] border border-[var(--rs-warning)] rounded-lg px-3 py-2">
          {t("这个题目对应旧版本代码。", "This item matches an older version of the code.")}
        </div>
      )}

      <div className="rs-card rounded-xl p-5 mb-4">
        <h1 className="text-xl font-semibold text-[var(--rs-ink)] mb-2">{t("问题", "Question")}</h1>
        <p className="text-[var(--rs-ink)] whitespace-pre-wrap">{item.prompt}</p>
      </div>

      {(item.evidence_snippets?.length || item.source_references?.length) ? (
        <div className="bg-[var(--rs-surface-2)] border border-[var(--rs-line)] rounded-xl p-4 mb-4">
          <button
            type="button"
            className="w-full flex items-center justify-between text-left"
            onClick={() => setEvidenceOpen((v) => !v)}
          >
            <div>
              <h2 className="text-sm font-semibold text-[var(--rs-ink)]">{t("可引用证据", "Citable evidence")}</h2>
              <p className="text-xs text-[var(--rs-muted)] mt-0.5">
                {t(
                  "先主动回忆；卡住再展开。作答请点名文件或符号。",
                  "Recall first; open this if you are stuck. Name a file or symbol in your answer.",
                )}
              </p>
            </div>
            <span className="text-xs text-[var(--rs-accent)] shrink-0 ml-3">
              {evidenceOpen ? t("收起", "Collapse") : t("展开", "Expand")}
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
                  <div className="font-mono text-xs text-[var(--rs-accent)] mb-1">
                    {ref.path}
                    {ref.start_line ? `:${ref.start_line}` : ""}
                    {ref.end_line && ref.end_line !== ref.start_line ? `-${ref.end_line}` : ""}
                    {ref.symbol ? ` · ${ref.symbol}` : ""}
                  </div>
                  {ref.snippet ? (
                    <pre className="text-xs bg-[var(--rs-surface-2)] border border-[var(--rs-line)] rounded-lg p-3 overflow-x-auto text-[var(--rs-ink-2)] whitespace-pre">
                      {ref.snippet}
                    </pre>
                  ) : (
                    <p className="text-xs text-[var(--rs-muted)]">
                      {ref.available === false
                        ? t(
                            "本地片段暂不可用（可能是远程仓库或路径失效）",
                            "Local snippet is unavailable (remote repo or a stale path)",
                          )
                        : t("仅路径引用", "Path reference only")}
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
          <label className="block text-sm font-medium text-[var(--rs-ink-2)] mb-2">
            {t("你的回答", "Your answer")}
          </label>
          <textarea
            value={answer}
            onChange={(e) => setAnswer(e.target.value)}
            rows={8}
            className="w-full border border-[var(--rs-line-strong)] rounded-xl p-3 text-[var(--rs-ink)] focus:ring-2 focus:ring-[var(--rs-accent-soft)] outline-none"
            placeholder={t(
              "用自己的话作答，尽量引用源码中的模块/符号…",
              "Answer in your own words. Name a module or symbol from the source…",
            )}
          />

          <div className="mt-4 flex flex-wrap items-center gap-4">
            <label className="text-sm text-[var(--rs-ink-2)]">
              {t("自信度", "Confidence")}
              <select
                value={confidence}
                onChange={(e) => setConfidence(Number(e.target.value))}
                className="ml-2 border border-[var(--rs-line-strong)] rounded-lg px-2 py-1"
              >
                {[1, 2, 3, 4, 5].map((n) => (
                  <option key={n} value={n}>
                    {n}
                  </option>
                ))}
              </select>
            </label>
            <div className="text-sm text-[var(--rs-muted)]">
              {t("提示等级：", "Hint level: ")}
              {currentLevel}/5
            </div>
          </div>

          {hintText && (
            <div className="mt-4 bg-[var(--rs-accent-soft)] border border-[var(--rs-line)] rounded-xl p-4 text-sm text-[var(--rs-ink-2)] whitespace-pre-wrap">
              {hintText}
            </div>
          )}

          {error && <p className="mt-3 text-sm text-[var(--rs-danger)]">{error}</p>}

          <div className="mt-5 flex flex-wrap gap-3">
            <button
              onClick={requestHint}
              className="px-4 py-2 border border-[var(--rs-line-strong)] rounded-lg text-sm hover:bg-[var(--rs-hover)]"
              disabled={currentLevel >= 5}
            >
              {t("申请提示", "Request a hint")}
            </button>
            <button
              onClick={revealAnswer}
              className="px-4 py-2 border border-[var(--rs-warning)] text-[var(--rs-warning)] rounded-lg text-sm hover:bg-[var(--rs-warning-soft)]"
            >
              {t("显示完整解释", "Show full explanation")}
            </button>
            <button
              onClick={submit}
              disabled={!canSubmit}
              className="px-4 py-2 bg-[var(--rs-accent)] text-white rounded-lg text-sm disabled:opacity-50"
            >
              {submitting ? t("提交中…", "Submitting…") : t("提交回答", "Submit answer")}
            </button>
          </div>
        </>
      ) : (
        <div className="space-y-4">
          <div className="rs-card rounded-xl p-5">
            <div className="flex items-center justify-between gap-3 mb-2">
              <h2 className="font-semibold text-[var(--rs-ink)]">{t("评价", "Evaluation")}</h2>
              {result.evaluation_source && (
                <span className="text-[11px] uppercase tracking-wide text-[var(--rs-muted)]">
                  {result.evaluation_source === "llm" ? "LLM + rubric" : "deterministic"}
                </span>
              )}
            </div>
            <p className="text-[var(--rs-ink)] mb-2">{result.evaluation.feedback}</p>
            <div className="text-sm text-[var(--rs-ink-2)] space-y-1">
              <div>{t("得分：", "Score: ")}{result.score.toFixed(2)}</div>
              <div>{t("FSRS Rating：", "FSRS Rating: ")}{result.fsrs_rating}</div>
              <div>{t("掌握度：", "Mastery: ")}{result.mastery_score?.toFixed(2) ?? "—"}</div>
              <div>
                {t("下次复习：", "Next review: ")}
                {result.next_review_at
                  ? new Date(result.next_review_at).toLocaleString()
                  : "—"}
              </div>
              <div>{t("覆盖点：", "Covered: ")}{(result.evaluation.covered_points || []).join(", ") || "—"}</div>
              <div>{t("遗漏点：", "Missing: ")}{(result.evaluation.missing_points || []).join(", ") || "—"}</div>
            </div>
            {result.evaluation.suggested_revision && (
              <p className="mt-3 text-sm text-[var(--rs-accent)]">
                {t("改进建议：", "Suggested revision: ")}
                {result.evaluation.suggested_revision}
              </p>
            )}
            {result.evaluation.follow_up_question && (
              <p className="mt-2 text-sm text-[var(--rs-ink-2)]">
                {t("追问：", "Follow-up: ")}
                {result.evaluation.follow_up_question}
              </p>
            )}
          </div>

          <div className="rs-card rounded-xl p-5">
            <h2 className="font-semibold text-[var(--rs-ink)] mb-2">{t("源码证据", "Source evidence")}</h2>
            <ul className="text-sm text-[var(--rs-ink-2)] space-y-1">
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
            <div className="bg-[var(--rs-surface-2)] border border-[var(--rs-line)] rounded-xl p-5">
              <h2 className="font-semibold text-[var(--rs-ink)] mb-2">{t("答案提纲", "Answer outline")}</h2>
              <pre className="text-sm text-[var(--rs-ink-2)] whitespace-pre-wrap">
                {result.expected_answer_outline}
              </pre>
            </div>
          )}

          <div className="flex flex-wrap gap-3">
            {!isLast ? (
              <button
                type="button"
                onClick={goNext}
                className="px-4 py-2 bg-[var(--rs-accent)] text-white rounded-lg text-sm"
              >
                {t("下一题", "Next item")}
              </button>
            ) : (
              <Link
                to={`/concepts/${item.concept_id}`}
                className="px-4 py-2 bg-[var(--rs-accent)] text-white rounded-lg text-sm"
              >
                {t("完成本轮 · 返回词条", "Round done · back to entry")}
              </Link>
            )}
            <Link
              to={`/concepts/${item.concept_id}`}
              className="px-4 py-2 border border-[var(--rs-line-strong)] rounded-lg text-sm"
            >
              {t("返回词条", "Back to entry")}
            </Link>
            <Link
              to="/reviews"
              className="px-4 py-2 border border-[var(--rs-line-strong)] rounded-lg text-sm"
            >
              {t("查看复习队列", "View review queue")}
            </Link>
          </div>
        </div>
      )}
    </AppShell>
  );
}
