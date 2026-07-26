import { useMemo, useState } from "react";
import { tNow, useT } from "../lib/i18n";
import { AttemptResult, LearningItem, recallstackApi } from "../lib/recallstackApi";

type Props = {
  item: LearningItem | null;
  onCompleted?: (result: AttemptResult) => void;
};

export default function InlineProbe({ item, onCompleted }: Props) {
  const t = useT();
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
    return <div className="rs-probe-empty">{t("暂无自测题。", "No practice questions yet.")}</div>;
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
      setError(e instanceof Error ? e.message : tNow("提交失败", "Submit failed"));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="rs-probe">
      <div className="flex items-start justify-between gap-3 mb-2">
        <div className="rs-eyebrow">{t("30 秒自测 · 主动回忆", "30-second probe · active recall")}</div>
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
            placeholder={t("用自己的话作答；能说出模块或符号名更好…", "Answer in your own words; naming modules or symbols is even better…")}
          />
          <div className="mt-3 flex flex-wrap items-center gap-3">
            <label className="text-[13px] text-[var(--rs-ink-2)] flex items-center gap-2">
              {t("信心", "Confidence")}
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
              {submitting ? t("提交中…", "Submitting…") : t("提交答案", "Submit answer")}
            </button>
          </div>
          {error && <div className="rs-alert mt-3">{error}</div>}
        </>
      ) : (
        <div className="rs-probe-result">
          <p className="text-[13.5px] text-[var(--rs-ink)]">{result.evaluation.feedback}</p>
          <div className="text-[12px] text-[var(--rs-muted)] rs-tabular space-y-1 mt-2">
            <div>
              {t("得分", "Score")} {result.score.toFixed(2)} · FSRS {result.fsrs_rating}
            </div>
            <div>
              {t("掌握度", "Mastery")} {result.mastery_score?.toFixed(2) ?? "—"} · {t("下次复习", "next review")}{" "}
              {result.next_review_at ? new Date(result.next_review_at).toLocaleString() : "—"}
            </div>
            {result.evaluation.suggested_revision && (
              <div className="text-[var(--rs-accent)]">
                {t("下一步：", "Next: ")}{result.evaluation.suggested_revision}
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
