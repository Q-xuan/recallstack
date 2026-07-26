import { useEffect, useRef, useState } from "react";
import WikiContent from "./WikiContent";
import { recallstackApi, type WikiAskResponse } from "../lib/recallstackApi";

interface Props {
  open: boolean;
  repositoryId: string;
  repositoryName: string;
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
 * DeepWiki-style "ask the repository": the reader types a question, the
 * backend retrieves the most relevant wiki pages and answers with citations.
 * Works without an LLM key too — the answer degrades to ranked pages.
 */
export default function AskPanel({
  open,
  repositoryId,
  repositoryName,
  onClose,
  onOpenPage,
}: Props) {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const logRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (open) window.setTimeout(() => inputRef.current?.focus(), 20);
  }, [open]);

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

  async function submit() {
    const question = draft.trim();
    if (!question || busy) return;
    setDraft("");
    setBusy(true);
    setTurns((prev) => [...prev, { question }]);
    try {
      const res = await recallstackApi.askWiki(repositoryId, question);
      setTurns((prev) =>
        prev.map((t, i) => (i === prev.length - 1 ? { ...t, answer: res } : t)),
      );
    } catch (e: unknown) {
      const message = e instanceof Error ? e.message : "提问失败";
      setTurns((prev) =>
        prev.map((t, i) => (i === prev.length - 1 ? { ...t, error: message } : t)),
      );
    } finally {
      setBusy(false);
      inputRef.current?.focus();
    }
  }

  function openCited(pageId: string) {
    onOpenPage(pageId);
    onClose();
  }

  return (
    <div className="rs-ask-backdrop" onMouseDown={onClose} role="presentation">
      <aside
        className="rs-ask-panel"
        onMouseDown={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label="向仓库提问"
      >
        <header className="rs-ask-head">
          <div className="min-w-0">
            <div className="rs-eyebrow">Ask</div>
            <div className="text-[15px] font-semibold tracking-tight truncate">
              向 {repositoryName} 提问
            </div>
          </div>
          <button type="button" className="rs-icon-btn" onClick={onClose} aria-label="关闭">
            ✕
          </button>
        </header>

        <div className="rs-ask-log" ref={logRef}>
          {turns.length === 0 && (
            <div className="rs-ask-hint">
              <p>基于生成的 Wiki 回答问题,并给出可点击的页面引用。</p>
              <ul>
                <li>这个项目的入口在哪?</li>
                <li>依赖图是怎么构建的?</li>
                <li>复习调度用了什么算法?</li>
              </ul>
            </div>
          )}

          {turns.map((turn, i) => (
            <div key={i} className="rs-ask-turn">
              <div className="rs-ask-q">{turn.question}</div>
              {turn.error ? (
                <div className="rs-alert">{turn.error}</div>
              ) : !turn.answer ? (
                <div className="rs-ask-thinking">思考中…</div>
              ) : (
                <div className="rs-ask-a">
                  <WikiContent
                    content={turn.answer.answer}
                    title=""
                    repositoryId={repositoryId}
                    onNavigatePage={openCited}
                  />
                  {turn.answer.sources.length > 0 && (
                    <div className="rs-ask-sources">
                      <span className="rs-ask-sources-label">
                        {turn.answer.engine === "llm" ? "引用页面" : "相关页面"}
                      </span>
                      {turn.answer.sources.map((s) => (
                        <button
                          key={s.page_id}
                          type="button"
                          className="rs-ask-source-chip"
                          onClick={() => openCited(s.page_id)}
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
            placeholder="问点什么…(Enter 发送,Shift+Enter 换行)"
            rows={2}
            disabled={busy}
          />
          <button
            type="button"
            className="rs-btn rs-btn-primary h-9 px-4 shrink-0"
            onClick={submit}
            disabled={busy || !draft.trim()}
          >
            {busy ? "…" : "发送"}
          </button>
        </footer>
      </aside>
    </div>
  );
}
