import { useEffect, useRef, useState } from "react";
import { streamChat, type CodeReference } from "../lib/api";

export interface AssistContext {
  selection?: string;
  question?: string;
  wikiPageId?: string;
  wikiPageTitle?: string;
  surroundingText?: string;
  /** bump to re-trigger even with same selection */
  requestId: number;
}

interface Message {
  role: "user" | "assistant";
  content: string;
  references?: CodeReference[];
}

interface Props {
  open: boolean;
  projectId: string;
  context: AssistContext | null;
  onClose: () => void;
  onExpandChat: () => void;
}

export default function AssistDrawer({
  open,
  projectId,
  context,
  onClose,
  onExpandChat,
}: Props) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const lastRequestRef = useRef<number>(0);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streaming]);

  // auto-run when parent sends a new explain request
  useEffect(() => {
    if (!open || !context || !projectId) return;
    if (context.requestId === lastRequestRef.current) return;
    lastRequestRef.current = context.requestId;

    const selection = (context.selection || "").trim();
    const question = (context.question || "").trim();
    if (!selection && !question) return;

    const userLabel = selection
      ? question
        ? `解释「${selection}」：${question}`
        : `解释「${selection}」`
      : question;

    runExplain({
      selection,
      question: question || (selection ? `在本仓库中，「${selection}」是什么意思？` : ""),
      userLabel,
      wikiPageId: context.wikiPageId,
      wikiPageTitle: context.wikiPageTitle,
      surroundingText: context.surroundingText,
      append: false,
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, context?.requestId, projectId]);

  function runExplain(opts: {
    selection?: string;
    question: string;
    userLabel: string;
    wikiPageId?: string;
    wikiPageTitle?: string;
    surroundingText?: string;
    append: boolean;
  }) {
    if (streaming) return;
    setError(null);
    setStreaming(true);

    setMessages((prev) => {
      const base = opts.append ? prev : [];
      return [
        ...base,
        { role: "user", content: opts.userLabel },
        { role: "assistant", content: "", references: [] },
      ];
    });

    streamChat(
      projectId,
      {
        mode: "inline_explain",
        selection: opts.selection || "",
        question: opts.question,
        wiki_page_id: opts.wikiPageId || "",
        wiki_page_title: opts.wikiPageTitle || "",
        surrounding_text: opts.surroundingText || "",
      },
      (data) => {
        if (data.references) {
          setMessages((prev) => {
            const msgs = [...prev];
            const last = msgs[msgs.length - 1];
            if (last?.role === "assistant") {
              msgs[msgs.length - 1] = { ...last, references: data.references };
            }
            return msgs;
          });
        }
        if (data.content) {
          setMessages((prev) => {
            const msgs = [...prev];
            const last = msgs[msgs.length - 1];
            if (last?.role === "assistant") {
              msgs[msgs.length - 1] = {
                ...last,
                content: last.content + data.content,
              };
            }
            return msgs;
          });
        }
      },
      () => setStreaming(false),
      (message) => {
        setError(message);
        setMessages((prev) => {
          const msgs = [...prev];
          const last = msgs[msgs.length - 1];
          if (last?.role === "assistant" && !last.content) {
            msgs[msgs.length - 1] = {
              ...last,
              content: `（无法回答：${message}）`,
            };
          }
          return msgs;
        });
      },
    );
  }

  function handleFollowUp() {
    const q = input.trim();
    if (!q || streaming) return;
    setInput("");
    const lastSelection = context?.selection || "";
    runExplain({
      selection: lastSelection,
      question: q,
      userLabel: q,
      wikiPageId: context?.wikiPageId,
      wikiPageTitle: context?.wikiPageTitle,
      surroundingText: context?.surroundingText,
      append: true,
    });
  }

  if (!open) return null;

  return (
    <aside className="w-[380px] max-w-[90vw] border-l border-slate-200 bg-slate-50 flex flex-col h-full shrink-0">
      <div className="flex items-center justify-between px-4 py-3 border-b border-slate-200 bg-white">
        <div>
          <div className="text-sm font-semibold text-slate-800">阅读助教</div>
          <div className="text-xs text-slate-500">选中术语即可解释 · 不离开 Wiki</div>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={onExpandChat}
            className="text-xs text-blue-600 hover:text-blue-800 px-2 py-1 rounded hover:bg-blue-50"
            title="打开完整问答页"
          >
            完整对话
          </button>
          <button
            type="button"
            onClick={onClose}
            className="text-slate-400 hover:text-slate-700 text-lg leading-none px-1"
            aria-label="关闭"
          >
            ×
          </button>
        </div>
      </div>

      {context?.selection && (
        <div className="px-4 py-2 bg-indigo-50 border-b border-indigo-100 text-xs text-indigo-800">
          当前选中：
          <span className="font-mono font-medium ml-1">{context.selection}</span>
          {context.wikiPageTitle && (
            <span className="text-indigo-500 ml-2">· {context.wikiPageTitle}</span>
          )}
        </div>
      )}

      <div className="flex-1 overflow-y-auto px-3 py-3 space-y-3">
        {messages.length === 0 && !streaming && (
          <div className="text-sm text-slate-500 px-1 py-6 space-y-2">
            <p>在左侧 Wiki 中：</p>
            <ul className="list-disc ml-5 space-y-1">
              <li>划选术语，点「解释」</li>
              <li>或点击行内 <code className="bg-slate-200 px-1 rounded">代码</code></li>
              <li>也可在下方直接追问当前页</li>
            </ul>
          </div>
        )}

        {messages.map((msg, i) => (
          <div
            key={i}
            className={`text-sm ${msg.role === "user" ? "ml-6" : "mr-2"}`}
          >
            <div
              className={`rounded-lg px-3 py-2 ${
                msg.role === "user"
                  ? "bg-blue-600 text-white"
                  : "bg-white border border-slate-200 text-slate-700"
              }`}
            >
              <pre className="whitespace-pre-wrap font-sans text-[13px] leading-relaxed">
                {msg.content || (streaming && i === messages.length - 1 ? "…" : "")}
              </pre>
            </div>
            {msg.role === "assistant" && msg.references && msg.references.length > 0 && (
              <div className="mt-1.5 space-y-1">
                <div className="text-[11px] text-slate-400 px-1">源码证据</div>
                {msg.references.slice(0, 4).map((ref, ri) => (
                  <div
                    key={ri}
                    className="text-[11px] font-mono bg-white border border-slate-100 rounded px-2 py-1 text-slate-600"
                    title={ref.snippet}
                  >
                    {ref.path}
                    {ref.line_start > 0 && (
                      <span className="text-slate-400">
                        :{ref.line_start}
                        {ref.line_end > ref.line_start ? `-${ref.line_end}` : ""}
                      </span>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        ))}
        <div ref={bottomRef} />
      </div>

      {error && (
        <div className="px-3 py-2 text-xs text-amber-800 bg-amber-50 border-t border-amber-100">
          {error}
          {error.toLowerCase().includes("api key") && (
            <span className="block mt-1 text-amber-700">
              请在首页 Settings 配置 API Key 后重试。
            </span>
          )}
        </div>
      )}

      <div className="p-3 border-t border-slate-200 bg-white">
        <div className="flex gap-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleFollowUp()}
            placeholder={
              context?.selection
                ? `继续追问「${context.selection}」…`
                : "基于当前页提问…"
            }
            disabled={streaming}
            className="flex-1 px-3 py-2 text-sm border border-slate-300 rounded-lg focus:border-blue-500 focus:ring-1 focus:ring-blue-200 outline-none disabled:opacity-50"
          />
          <button
            type="button"
            onClick={handleFollowUp}
            disabled={streaming || !input.trim()}
            className="px-3 py-2 bg-blue-600 text-white text-sm rounded-lg hover:bg-blue-700 disabled:opacity-50"
          >
            发送
          </button>
        </div>
      </div>
    </aside>
  );
}
