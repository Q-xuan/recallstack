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
    [item, answer, submitting, result]
  );

  if (!item) {
    return (
      <div className="border border-dashed border-slate-300 rounded-xl p-4 text-sm text-slate-500">
        No probe item available yet.
      </div>
    );
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
    <div className="border border-indigo-200 bg-indigo-50/40 rounded-xl p-4 md:p-5">
      <div className="flex items-center justify-between gap-3 mb-2">
        <div>
          <div className="text-xs font-semibold uppercase tracking-wide text-indigo-700">
            30s probe · active recall
          </div>
          <p className="text-xs text-slate-500 mt-0.5">Recall first. Outline stays hidden until you submit.</p>
        </div>
        <span className="text-[11px] text-slate-400 uppercase">{item.item_type}</span>
      </div>

      <p className="text-slate-900 font-medium mb-3">{item.prompt}</p>

      {!result ? (
        <>
          <textarea
            value={answer}
            onChange={(e) => setAnswer(e.target.value)}
            rows={4}
            className="w-full border border-slate-300 rounded-lg p-3 text-sm bg-white focus:ring-2 focus:ring-indigo-200 outline-none"
            placeholder="Answer in your own words; name modules/symbols when you can…"
          />
          <div className="mt-3 flex flex-wrap items-center gap-3">
            <label className="text-sm text-slate-700">
              Confidence
              <select
                value={confidence}
                onChange={(e) => setConfidence(Number(e.target.value))}
                className="ml-2 border border-slate-300 rounded-md px-2 py-1 bg-white"
              >
                {[1, 2, 3, 4, 5].map((n) => (
                  <option key={n} value={n}>
                    {n}
                  </option>
                ))}
              </select>
            </label>
            <button
              onClick={submit}
              disabled={!canSubmit}
              className="px-4 py-2 bg-indigo-600 text-white rounded-lg text-sm disabled:opacity-50"
            >
              {submitting ? "Submitting…" : "Submit probe"}
            </button>
          </div>
          {error && <p className="mt-2 text-sm text-red-600">{error}</p>}
        </>
      ) : (
        <div className="bg-white border border-slate-200 rounded-lg p-4 space-y-2">
          <p className="text-sm text-slate-800">{result.evaluation.feedback}</p>
          <div className="text-xs text-slate-500 space-y-1">
            <div>Score {result.score.toFixed(2)} · FSRS {result.fsrs_rating}</div>
            <div>
              Mastery {result.mastery_score?.toFixed(2) ?? "—"} · next review{" "}
              {result.next_review_at ? new Date(result.next_review_at).toLocaleString() : "—"}
            </div>
            {result.evaluation.suggested_revision && (
              <div className="text-indigo-800">Next: {result.evaluation.suggested_revision}</div>
            )}
          </div>
          {result.expected_answer_outline && (
            <pre className="text-xs text-slate-600 whitespace-pre-wrap bg-slate-50 rounded-md p-3 mt-2">
              {result.expected_answer_outline}
            </pre>
          )}
        </div>
      )}
    </div>
  );
}
