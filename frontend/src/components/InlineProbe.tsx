import { useMemo, useState } from "react";
import { AttemptResult, LearningItem, recallstackApi } from "../lib/recallstackApi";

type Props = {
  item: LearningItem | null;
  onCompleted?: (result: AttemptResult) => void;
};

export default function InlineProbe({ item, onCompleted }: Props) {
  const [answer, setAnswer] = useState("");
  const [confidence, setConfidence] = useState(3);
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<AttemptResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [startedAt] = useState(() => Date.now());

  const canSubmit = useMemo(
    () => Boolean(item) && answer.trim().length > 0 && !submitting && !result,
    [item, answer, submitting, result],
  );

  if (!item) {
    return <div className="rs-probe-empty">暂无自测题。</div>;
  }

  async function submit() {
    if (!item || !canSubmit) return;
    setSubmitting(true);
    setError(null);
    try {
      const duration = Math.max(1, Math.round((Date.now() - startedAt) / 1000));
      const r = await recallstackApi.submitAttempt(item.id, {
        answer,
        confidence,
        hints_used: [],
        duration_seconds: duration,
        revealed_answer: false,
      });
      setResult(r);
      onCompleted?.(r);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "提交失败");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="rs-probe">
      <div className="flex items-start justify-between gap-3 mb-2">
        <div className="rs-eyebrow">30 秒自测 · 主动回忆</div>
        <span className="rs-chip">{item.item_type}</span>
      </div>

      <p className="rs-probe-prompt">{item.prompt}</p>

      {!result ? (
        <>
          <textarea
            value={answer}
            onChange={(e) => setAnswer(e.target.value)}
            rows={4}
            className="rs-input rs-textarea"
            placeholder="用自己的话作答；能说出模块或符号名更好…"
          />
          <div className="mt-3 flex flex-wrap items-center gap-3">
            <label className="text-[13px] text-[var(--rs-ink-2)] flex items-center gap-2">
              信心
              <select
                value={confidence}
                onChange={(e) => setConfidence(Number(e.target.value))}
                className="rs-input h-8 w-auto text-[13px]"
              >
                {[1, 2, 3, 4, 5].map((n) => (
                  <option key={n} value={n}>
                    {n}
                  </option>
                ))}
              </select>
            </label>
            <button
              type="button"
              onClick={submit}
              disabled={!canSubmit}
              className="rs-btn rs-btn-primary h-9 px-4 text-[13px]"
            >
              {submitting ? "提交中…" : "提交答案"}
            </button>
          </div>
          {error && <div className="rs-alert mt-3">{error}</div>}
        </>
      ) : (
        <div className="rs-probe-result">
          <p className="text-[13.5px] text-[var(--rs-ink)]">{result.evaluation.feedback}</p>
          <div className="text-[12px] text-[var(--rs-muted)] rs-tabular space-y-1 mt-2">
            <div>
              得分 {result.score.toFixed(2)} · FSRS {result.fsrs_rating}
            </div>
            <div>
              掌握度 {result.mastery_score?.toFixed(2) ?? "—"} · 下次复习{" "}
              {result.next_review_at ? new Date(result.next_review_at).toLocaleString() : "—"}
            </div>
            {result.evaluation.suggested_revision && (
              <div className="text-[var(--rs-accent)]">
                下一步：{result.evaluation.suggested_revision}
              </div>
            )}
          </div>
          {result.expected_answer_outline && (
            <pre className="rs-probe-outline">{result.expected_answer_outline}</pre>
          )}
        </div>
      )}
    </div>
  );
}
