import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import InlineProbe from "./InlineProbe";
import {
  AttemptResult,
  Concept,
  LearningItem,
  recallstackApi,
} from "../lib/recallstackApi";

type Props = {
  concept: Concept;
  compact?: boolean;
};

/**
 * Learning attached to a wiki concept page — not a separate product.
 * Read evidence in the wiki article above, then probe / open a session.
 */
export default function ConceptPracticePanel({ concept, compact = false }: Props) {
  const [items, setItems] = useState<LearningItem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [mastery, setMastery] = useState<number | null | undefined>(concept.mastery_score);
  const [nextReview, setNextReview] = useState<string | null | undefined>(
    concept.next_review_at
  );

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        const list = await recallstackApi.listItems(concept.id);
        if (!cancelled) setItems(list);
      } catch (e: unknown) {
        if (!cancelled) setError(e instanceof Error ? e.message : "Failed to load practice");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [concept.id]);

  const probeItem = useMemo(
    () => items.find((i) => i.item_type === "active_recall") || items[0] || null,
    [items]
  );

  function onCompleted(r: AttemptResult) {
    setMastery(r.mastery_score ?? mastery);
    setNextReview(r.next_review_at ?? nextReview);
  }

  if (loading) {
    return (
      <div className="mt-10 rounded-2xl border border-black/5 bg-black/[0.02] p-5 text-sm text-[var(--rs-muted)]">
        Loading practice…
      </div>
    );
  }
  if (error) {
    return (
      <div className="mt-10 rounded-2xl border border-red-200 bg-red-50 p-5 text-sm text-red-700">
        {error}
      </div>
    );
  }
  if (!items.length) {
    return null;
  }

  return (
    <section className="mt-10 border-t border-black/5 pt-8">
      <div className="flex flex-wrap items-end justify-between gap-3 mb-4">
        <div>
          <div className="text-[11px] font-semibold tracking-[0.12em] uppercase text-[var(--rs-muted)]">
            Practice · attached to this page
          </div>
          <h2 className="mt-1 text-[20px] font-semibold tracking-tight text-[var(--rs-ink)]">
            Active recall
          </h2>
          <p className="mt-1 text-[13px] text-[var(--rs-ink-2)] max-w-xl">
            Evidence is above. Close the article in your head, then answer. Deeper items stay in a
            session so reading remains primary.
          </p>
        </div>
        <div className="text-right text-[12px] text-[var(--rs-muted)] rs-tabular">
          <div>Mastery {mastery == null ? "—" : Number(mastery).toFixed(2)}</div>
          <div>
            Next review{" "}
            {nextReview ? new Date(nextReview).toLocaleString() : "after first attempt"}
          </div>
        </div>
      </div>

      <InlineProbe item={probeItem} onCompleted={onCompleted} />

      {!compact && (
        <div className="mt-4 flex flex-wrap gap-2">
          <Link
            to={`/session/${probeItem?.id || items[0].id}`}
            className="rs-btn rs-btn-primary h-9 px-4 text-[13px]"
          >
            Full session ({items.length})
          </Link>
          <Link
            to={`/concepts/${concept.id}`}
            className="rs-btn rs-btn-ghost h-9 px-4 text-[13px]"
          >
            Concept detail
          </Link>
        </div>
      )}
    </section>
  );
}
