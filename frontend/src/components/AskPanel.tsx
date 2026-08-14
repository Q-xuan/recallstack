import { useEffect, useRef, useState } from "react";
import WikiContent from "./WikiContent";
import { tNow, useT } from "../lib/i18n";
import { recallstackApi, type WikiAskResponse } from "../lib/recallstackApi";

interface Props {
  open: boolean;
  repositoryId: string;
  repositoryName: string;
  /** Seed from 选中即问; changes while open replace the draft. */
  initialQuestion?: string;
  questionKey?: number;
  /** Suggested chips stay live whenever the wiki exists. */
  canAsk?: boolean;
  /** From this wiki (entry / loop / ACP / pager). Never host-product leftovers. */
  suggestions?: string[];
  onClose: () => void;
  /** Citations in answers are wiki page ids; clicking one opens the page. */
  onOpenPage: (pageId: string) => void;
}

interface Turn {
  question: string;
  answer?: WikiAskResponse;
  error?: string;
}


/**
 * DeepWiki-style "ask the repository": a right-hand column, not a modal.
 * The reading pane stays selectable so 选中即问 can keep sending text here.
 */
export default function AskPanel({
  open,
  repositoryId,
  repositoryName,
  initialQuestion,
  questionKey,
  canAsk = true,
  suggestions = [],
  onClose,
  onOpenPage,
}: Props) {
  const t = useT();
  const [turns, setTurns] = useState<Turn[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const logRef = useRef<HTMLDivElement>(null);
  const wasOpen = useRef(false);

  useEffect(() => {
    if (!open) {
      wasOpen.current = false;
      return;
    }
    if (initialQuestion) setDraft(initialQuestion);
    if (!wasOpen.current) {
      wasOpen.current = true;
      window.setTimeout(() => inputRef.current?.focus(), 20);
    }
  }, [open, initialQuestion, questionKey]);

  // Keep the latest exchange in view as answers stream in.
  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight });
  }, [turns, busy]);

  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  async function submit(raw?: string) {
    const question = (raw ?? draft).trim();
    if (!question || busy || !canAsk) return;
    setDraft("");
    setBusy(true);
    // Completed turns become conversation context so follow-ups can say "it".
    const history = turns
      .filter((t) => t.answer)
      .slice(-4)
      .map((t) => ({ question: t.question, answer: t.answer!.answer.slice(0, 4000) }));
    setTurns((prev) => [...prev, { question }]);
    try {
      const res = await recallstackApi.askWiki(repositoryId, question, history);
      setTurns((prev) =>
        prev.map((t, i) => (i === prev.length - 1 ? { ...t, answer: res } : t)),
      );
    } catch (e: unknown) {
      const message = e instanceof Error ? e.message : tNow("提问失败", "Request failed");
      setTurns((prev) =>
        prev.map((t, i) => (i === prev.length - 1 ? { ...t, error: message } : t)),
      );
    } finally {
      setBusy(false);
      inputRef.current?.focus();
    }
  }

  return (
    <aside className="rs-ask-panel" role="complementary" aria-label={t("向仓库提问", "Ask the repository")}>
      <header className="rs-ask-head">
        <div className="min-w-0">
          <div className="rs-eyebrow">Ask</div>
          <div className="text-[15px] font-semibold tracking-tight truncate">
            {t("向", "Ask")} {repositoryName}
            {t(" 提问", "")}
          </div>
        </div>
        <button type="button" className="rs-icon-btn" onClick={onClose} aria-label={t("关闭", "Close")}>
          ✕
        </button>
      </header>

      <div className="rs-ask-log" ref={logRef}>
        {turns.length === 0 && (
          <div className="rs-ask-hint">
            <p>
              {t(
                "基于生成的 Wiki 回答问题,并给出可点击的页面引用。",
                "Answers are grounded in the generated wiki, with clickable page citations.",
              )}
            </p>
            {suggestions.length > 0 && (
              <div className="rs-ask-suggests">
                {suggestions.slice(0, 3).map((label) => (
                  <button
                    key={label}
                    type="button"
                    className="rs-ask-suggest"
                    disabled={!canAsk || busy}
                    onClick={() => submit(label)}
                  >
                    {label}
                  </button>
                ))}
              </div>
            )}
          </div>
        )}

        {turns.map((turn, i) => (
          <div key={i} className="rs-ask-turn">
            <div className="rs-ask-q">{turn.question}</div>
            {turn.error ? (
              <div className="rs-alert">{turn.error}</div>
            ) : !turn.answer ? (
              <div className="rs-ask-thinking">{t("思考中…", "Thinking…")}</div>
            ) : (
              <div className="rs-ask-a">
                <WikiContent
                  content={turn.answer.answer}
                  title=""
                  repositoryId={repositoryId}
                  onNavigatePage={onOpenPage}
                />
                {turn.answer.sources.length > 0 && (
                  <div className="rs-ask-sources">
                    <span className="rs-ask-sources-label">
                      {turn.answer.engine === "llm" ? t("引用页面", "Cited pages") : t("相关页面", "Related pages")}
                    </span>
                    {turn.answer.sources.map((s) => (
                      <button
                        key={s.page_id}
                        type="button"
                        className="rs-ask-source-chip"
                        onClick={() => onOpenPage(s.page_id)}
                        title={s.snippet}
                      >
                        {s.title}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        ))}
      </div>

      <footer className="rs-ask-foot">
        <textarea
          ref={inputRef}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              submit();
            }
          }}
          placeholder={t(
            "问点什么…(Enter 发送,Shift+Enter 换行)",
            "Ask anything… (Enter to send, Shift+Enter for newline)",
          )}
          rows={2}
          disabled={busy || !canAsk}
        />
        <button
          type="button"
          className="rs-btn rs-btn-primary h-9 px-4 shrink-0"
          onClick={() => submit()}
          disabled={busy || !canAsk || !draft.trim()}
        >
          {busy ? "…" : t("发送", "Send")}
        </button>
      </footer>
    </aside>
  );
}
