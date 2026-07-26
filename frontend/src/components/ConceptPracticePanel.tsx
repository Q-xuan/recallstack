import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import InlineProbe from "./InlineProbe";
import { tNow, useT } from "../lib/i18n";
import { AttemptResult, Concept, LearningItem, recallstackApi } from "../lib/recallstackApi";

type Props = {
  concept: Concept;
  compact?: boolean;
};

/**
 * Learning attached to a wiki concept page — not a separate product.
 *
 * Collapsed by default: the wiki article is what the reader came for, and an
 * always-open quiz below every page turns reading into homework. Opening it is
 * one click, and the choice sticks for the session.
 */
export default function ConceptPracticePanel({ concept, compact = false }: Props) {
  const t = useT();
  const [items, setItems] = useState<LearningItem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState(() => sessionStorage.getItem("rs_practice_open") === "1");
  const [mastery, setMastery] = useState<number | null | undefined>(concept.mastery_score);
  const [nextReview, setNextReview] = useState<string | null | undefined>(concept.next_review_at);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        const list = await recallstackApi.listItems(concept.id);
        if (!cancelled) setItems(list);
      } catch (e: unknown) {
        if (!cancelled) setError(e instanceof Error ? e.message : tNow("练习加载失败", "Failed to load practice"));
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
    [items],
  );

  function toggle() {
    setOpen((prev) => {
      sessionStorage.setItem("rs_practice_open", prev ? "0" : "1");
      return !prev;
    });
  }

  function onCompleted(r: AttemptResult) {
    setMastery(r.mastery_score ?? mastery);
    setNextReview(r.next_review_at ?? nextReview);
  }

  if (loading || error || !items.length) return null;

  return (
    <section className="rs-practice" id="practice">
      <button type="button" className="rs-practice-head" onClick={toggle} aria-expanded={open}>
        <span className={`rs-practice-caret ${open ? "is-open" : ""}`} aria-hidden>
          ›
        </span>
        <span className="min-w-0 flex-1 text-left">
          <span className="rs-practice-title">{t("检验一下是否真的读懂了", "Check you actually understood this")}</span>
          <span className="rs-practice-sub">
            {items.length}{t(" 道自测 · 掌握度 ", " questions · mastery ")}{mastery == null ? "—" : Number(mastery).toFixed(2)}
            {nextReview ? t(` · 下次复习 ${new Date(nextReview).toLocaleDateString()}`, ` · next review ${new Date(nextReview).toLocaleDateString()}`) : ""}
          </span>
        </span>
        <span className="rs-chip">{open ? t("收起", "Collapse") : t("展开", "Expand")}</span>
      </button>

      {open && (
        <div className="rs-practice-body">
          <p className="rs-practice-hint">
            {t("证据就在上文。先在脑中合上文章，再作答——回忆比重读更能留下记忆。", "The evidence is above. Close the article in your mind first, then answer — recall beats rereading.")}
          </p>
          <InlineProbe item={probeItem} onCompleted={onCompleted} />
          {!compact && (
            <div className="mt-4 flex flex-wrap gap-2">
              <Link
                to={`/session/${probeItem?.id || items[0].id}`}
                className="rs-btn rs-btn-secondary h-9 px-4 text-[13px]"
              >
                {t("完整练习", "Full practice")}（{items.length}）
              </Link>
              <Link
                to={`/concepts/${concept.id}`}
                className="rs-btn rs-btn-ghost h-9 px-4 text-[13px]"
              >
                {t("概念详情", "Concept details")}
              </Link>
            </div>
          )}
        </div>
      )}
    </section>
  );
}
