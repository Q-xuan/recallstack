import { useCallback, useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { getWiki, getPage } from "../lib/api";
import { useWikiStore } from "../stores/wiki";
import WikiSidebar from "../components/WikiSidebar";
import WikiContent, { type SelectionExplainPayload } from "../components/WikiContent";
import AssistDrawer, { type AssistContext } from "../components/AssistDrawer";

export default function WikiView() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { wiki, setWiki, currentPageId, setCurrentPage } = useWikiStore();
  const [pageContent, setPageContent] = useState("");
  const [pageTitle, setPageTitle] = useState("");
  const [loading, setLoading] = useState(false);
  const [assistOpen, setAssistOpen] = useState(false);
  const [assistContext, setAssistContext] = useState<AssistContext | null>(null);
  const requestSeq = useState(0);

  // load wiki structure if not already loaded
  useEffect(() => {
    if (!wiki && id) {
      getWiki(id).then((w) => {
        if ("error" in w) {
          navigate("/");
          return;
        }
        setWiki(w);
      });
    }
  }, [id, wiki, navigate, setWiki]);

  // load page content when currentPageId changes
  useEffect(() => {
    if (!id || !currentPageId) return;
    setLoading(true);
    getPage(id, currentPageId).then((p) => {
      if ("error" in p) {
        setPageContent("Page not found");
        setPageTitle("Error");
      } else {
        setPageContent(p.content);
        setPageTitle(p.title);
      }
      setLoading(false);
    });
  }, [id, currentPageId]);

  const openAssist = useCallback(
    (payload?: Partial<AssistContext>) => {
      requestSeq[1]((n) => n + 1);
      const nextId = requestSeq[0] + 1;
      setAssistContext({
        requestId: nextId,
        wikiPageId: currentPageId,
        wikiPageTitle: pageTitle,
        selection: payload?.selection,
        question: payload?.question,
        surroundingText: payload?.surroundingText,
      });
      setAssistOpen(true);
    },
    [currentPageId, pageTitle, requestSeq],
  );

  const handleExplain = useCallback(
    (payload: SelectionExplainPayload) => {
      openAssist({
        selection: payload.selection,
        surroundingText: payload.surroundingText,
      });
    },
    [openAssist],
  );

  if (!wiki) {
    return (
      <div className="min-h-screen flex items-center justify-center text-slate-500">
        Loading wiki...
      </div>
    );
  }

  return (
    <div className="flex h-screen bg-white">
      <WikiSidebar
        sidebar={wiki.sidebar}
        currentPageId={currentPageId}
        projectName={wiki.project_name}
        onNavigate={(pageId) => setCurrentPage(pageId)}
        onChat={() => {
          // open drawer for page-level Q&A instead of leaving wiki
          openAssist({
            question: "",
            selection: "",
          });
          setAssistOpen(true);
          // if no auto-query, just open empty drawer
          setAssistContext((prev) => ({
            requestId: prev?.requestId ?? 0,
            wikiPageId: currentPageId,
            wikiPageTitle: pageTitle,
          }));
        }}
        onHome={() => navigate("/")}
      />

      <div className="flex-1 overflow-y-auto min-w-0">
        {loading ? (
          <div className="p-12 text-slate-400 animate-pulse">Loading page...</div>
        ) : (
          <WikiContent
            content={pageContent}
            title={pageTitle}
            onExplain={handleExplain}
          />
        )}
      </div>

      {id && (
        <AssistDrawer
          open={assistOpen}
          projectId={id}
          context={assistContext}
          onClose={() => setAssistOpen(false)}
          onExpandChat={() => navigate(`/project/${id}/chat`)}
        />
      )}
    </div>
  );
}
