import { FormEvent, useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import AppShell from "../components/AppShell";
import ConceptPracticePanel from "../components/ConceptPracticePanel";
import FolderPicker from "../components/FolderPicker";
import WikiContent from "../components/WikiContent";
import {
  Concept,
  LearningPath,
  Repository,
  Version,
  Wiki,
  WikiPage,
  WikiSidebarItem,
  recallstackApi,
} from "../lib/recallstackApi";

type Mode = "read" | "learn";

export default function RepositoryPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const mode = (searchParams.get("mode") as Mode) || "read";
  const pageFromUrl = searchParams.get("page") || "index";

  const [repos, setRepos] = useState<Repository[]>([]);
  const [repo, setRepo] = useState<Repository | null>(null);
  const [version, setVersion] = useState<Version | null>(null);
  const [wiki, setWiki] = useState<Wiki | null>(null);
  const [concepts, setConcepts] = useState<Concept[]>([]);
  const [path, setPath] = useState<LearningPath | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [sourceLocation, setSourceLocation] = useState("");
  const [sourceType, setSourceType] = useState<"local" | "github">("local");
  const [pickerOpen, setPickerOpen] = useState(false);

  function setMode(next: Mode) {
    const sp = new URLSearchParams(searchParams);
    if (next === "read") sp.delete("mode");
    else sp.set("mode", next);
    setSearchParams(sp, { replace: true });
  }

  function openPage(pageId: string) {
    const sp = new URLSearchParams(searchParams);
    sp.set("page", pageId);
    if (mode !== "read") sp.delete("mode");
    setSearchParams(sp, { replace: true });
  }

  async function refreshList() {
    const list = await recallstackApi.listRepositories();
    setRepos(list);
  }

  async function loadRepo(repoId: string) {
    setLoading(true);
    setError(null);
    try {
      const r = await recallstackApi.getRepository(repoId);
      setRepo(r);
      try {
        const v = await recallstackApi.latestVersion(repoId);
        setVersion(v);
        setStatus(v.status);
      } catch {
        setVersion(null);
      }
      try {
        const w = await recallstackApi.wiki(repoId);
        setWiki(w);
      } catch {
        setWiki(null);
      }
      try {
        const g = await recallstackApi.concepts(repoId);
        setConcepts(g.concepts);
      } catch {
        setConcepts([]);
      }
      try {
        const p = await recallstackApi.learningPath(repoId);
        setPath(p);
      } catch {
        setPath(null);
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    refreshList().catch((e: unknown) =>
      setError(e instanceof Error ? e.message : "加载失败")
    );
  }, []);

  useEffect(() => {
    if (id) loadRepo(id);
    else {
      setRepo(null);
      setWiki(null);
      setConcepts([]);
      setPath(null);
      setVersion(null);
    }
  }, [id]);

  async function handleCreate(e: FormEvent) {
    e.preventDefault();
    if (!sourceLocation.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const created = await recallstackApi.createRepository({
        source_type: sourceType,
        source_location: sourceLocation.trim(),
      });
      await refreshList();
      navigate(`/repositories/${created.id}`);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "创建失败");
    } finally {
      setLoading(false);
    }
  }

  async function handleAnalyze() {
    if (!id) return;
    setLoading(true);
    setError(null);
    setStatus("pending");
    try {
      const v = await recallstackApi.analyze(id, true);
      setVersion(v);
      setStatus(v.status);
      await loadRepo(id);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "分析失败");
    } finally {
      setLoading(false);
    }
  }

  const currentPage: WikiPage | null = useMemo(() => {
    if (!wiki) return null;
    return wiki.pages.find((p) => p.id === pageFromUrl) || wiki.pages[0] || null;
  }, [wiki, pageFromUrl]);

  const conceptBySlug = useMemo(() => {
    const m: Record<string, Concept> = {};
    for (const c of concepts) m[c.slug] = c;
    return m;
  }, [concepts]);

  const boundConcept = useMemo(() => {
    if (!currentPage) return null;
    if (currentPage.concept_id) {
      return concepts.find((c) => c.id === currentPage.concept_id) || null;
    }
    if (currentPage.id.startsWith("concepts/")) {
      return conceptBySlug[currentPage.id.split("/")[1]] || null;
    }
    return null;
  }, [currentPage, concepts, conceptBySlug]);

  const ready = Boolean(wiki && wiki.pages.length > 0);

  // ── Import landing (no repo selected) ──────────────────────────────────
  if (!id) {
    return (
      <AppShell
        title="知识库"
        subtitle="导入一个代码仓库。一次扫描，同时得到可阅读 Wiki 与可练习概念。"
      >
        <section className="rs-card p-6 md:p-8">
          <div className="flex items-start justify-between gap-4 flex-wrap mb-6">
            <div>
              <div className="text-[12px] font-semibold tracking-[0.08em] uppercase text-[var(--rs-muted)]">
                Import
              </div>
              <h2 className="mt-1 text-[22px] font-semibold tracking-tight">导入仓库</h2>
              <p className="mt-1 text-[14px] text-[var(--rs-ink-2)] max-w-xl">
                本地目录或 GitHub HTTPS。分析后可在 DeepWiki 式阅读器中浏览架构与词条。
              </p>
            </div>
          </div>

          <form onSubmit={handleCreate} className="space-y-4">
            <div className="flex flex-col md:flex-row gap-3">
              <select
                value={sourceType}
                onChange={(e) => setSourceType(e.target.value as "local" | "github")}
                className="h-11 px-3 rounded-xl border border-black/10 bg-white text-[14px]"
              >
                <option value="local">本地目录</option>
                <option value="github">GitHub HTTPS</option>
              </select>
              <div className="flex-1 flex gap-2">
                <input
                  value={sourceLocation}
                  onChange={(e) => setSourceLocation(e.target.value)}
                  placeholder={
                    sourceType === "local"
                      ? "选择文件夹或粘贴绝对路径"
                      : "https://github.com/org/repo"
                  }
                  className="flex-1 h-11 px-3 rounded-xl border border-black/10 bg-white text-[14px] outline-none focus:border-[var(--rs-accent)] focus:ring-4 focus:ring-[rgba(0,113,227,0.12)]"
                  disabled={loading}
                />
                {sourceType === "local" && (
                  <button
                    type="button"
                    onClick={() => setPickerOpen(true)}
                    className="rs-btn rs-btn-ghost"
                  >
                    浏览…
                  </button>
                )}
              </div>
              <button
                type="submit"
                disabled={loading || !sourceLocation.trim()}
                className="rs-btn rs-btn-primary h-11 px-5"
              >
                创建
              </button>
            </div>
          </form>

          {error && (
            <div className="mt-4 rounded-xl border border-red-200 bg-red-50 text-red-700 px-4 py-3 text-sm">
              {error}
            </div>
          )}

          {repos.length > 0 && (
            <div className="mt-8">
              <div className="text-[12px] font-semibold tracking-[0.08em] uppercase text-[var(--rs-muted)] mb-3">
                Libraries
              </div>
              <ul className="divide-y divide-black/5 border border-black/5 rounded-2xl overflow-hidden">
                {repos.map((r) => (
                  <li key={r.id}>
                    <Link
                      to={`/repositories/${r.id}`}
                      className="flex items-center justify-between px-4 py-3.5 hover:bg-black/[0.02] transition-colors"
                    >
                      <div>
                        <div className="font-medium text-[15px]">{r.name}</div>
                        <div className="text-[12px] text-[var(--rs-muted)] mt-0.5 truncate max-w-[52vw]">
                          {r.source_location}
                        </div>
                      </div>
                      <span className="rs-chip">{r.source_type}</span>
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </section>

        <FolderPicker
          open={pickerOpen}
          onClose={() => setPickerOpen(false)}
          onSelect={(p) => {
            setSourceLocation(p);
            setPickerOpen(false);
          }}
        />
      </AppShell>
    );
  }

  // ── Immersive wiki workbench ───────────────────────────────────────────
  return (
    <AppShell flush>
      <div className="rs-wiki-shell">
        <div className="rs-wiki-topbar">
          <div className="flex items-center gap-3 min-w-0">
            <Link
              to="/repositories"
              className="rs-btn rs-btn-ghost h-8 px-3 text-[12px] shrink-0"
            >
              ← 知识库
            </Link>
            <div className="min-w-0">
              <div className="text-[14px] font-semibold tracking-tight truncate">
                {repo?.name || "仓库"}
              </div>
              <div className="text-[11px] text-[var(--rs-muted)] truncate rs-tabular">
                {version?.commit_sha
                  ? `${version.commit_sha.slice(0, 10)} · ${status || version.status}`
                  : status || "未分析"}
                {version?.has_wiki ? " · wiki ready" : ""}
              </div>
            </div>
          </div>

          <div className="flex items-center gap-2 shrink-0">
            <div className="rs-segmented hidden sm:inline-flex">
              <button
                type="button"
                className={mode === "read" ? "is-active" : ""}
                onClick={() => setMode("read")}
              >
                阅读
              </button>
              <button
                type="button"
                className={mode === "learn" ? "is-active" : ""}
                onClick={() => setMode("learn")}
              >
                路径
              </button>
            </div>
            <button
              type="button"
              onClick={handleAnalyze}
              disabled={loading}
              className="rs-btn rs-btn-primary h-8 px-3.5 text-[12px]"
            >
              {loading ? `分析中…` : ready ? "重新扫描" : "生成 Wiki"}
            </button>
            <Link to="/reviews" className="rs-btn rs-btn-ghost h-8 px-3 text-[12px]">
              复习
            </Link>
          </div>
        </div>

        {error && (
          <div className="mx-4 mt-3 rounded-xl border border-red-200 bg-red-50 text-red-700 px-4 py-3 text-sm">
            {error}
          </div>
        )}

        <div className="rs-wiki-body">
          <aside className="rs-wiki-sidebar hidden md:flex md:flex-col">
            <div className="px-4 pt-5 pb-3 border-b border-black/5">
              <div className="text-[11px] font-semibold tracking-[0.1em] uppercase text-[var(--rs-muted)]">
                {mode === "learn" ? "Learning Path" : "Contents"}
              </div>
              <div className="mt-1 text-[15px] font-semibold tracking-tight truncate">
                {wiki?.project_name || repo?.name || "Repository"}
              </div>
              {loading && status && (
                <div className="mt-2 text-[12px] text-[var(--rs-accent)] animate-pulse">
                  {status}
                </div>
              )}
            </div>

            <div className="flex-1 overflow-y-auto px-2 py-3">
              {mode === "learn" && path ? (
                <ol className="space-y-1">
                  {path.nodes.map((n, idx) => {
                    const slug = n.concept?.slug;
                    const pageId = slug ? `concepts/${slug}` : "";
                    const active = pageId && currentPage?.id === pageId;
                    return (
                      <li key={n.id}>
                        <button
                          type="button"
                          onClick={() => {
                            if (pageId) openPage(pageId);
                            else if (n.concept_id) navigate(`/concepts/${n.concept_id}`);
                          }}
                          className={`rs-wiki-nav-item ${active ? "is-active" : ""}`}
                        >
                          <span className="rs-tabular text-[var(--rs-muted)] w-5 shrink-0">
                            {idx + 1}
                          </span>
                          <span className="truncate">{n.concept?.title || n.concept_id}</span>
                        </button>
                      </li>
                    );
                  })}
                </ol>
              ) : wiki ? (
                <SidebarTree
                  items={wiki.sidebar}
                  currentId={currentPage?.id || ""}
                  onOpen={openPage}
                />
              ) : (
                <p className="px-3 text-[13px] text-[var(--rs-muted)]">尚未生成目录</p>
              )}
            </div>

            <div className="border-t border-black/5 p-3 space-y-2">
              {boundConcept && (
                <a
                  href="#practice"
                  className="rs-btn rs-btn-primary w-full text-[13px] text-center"
                >
                  Practice on this page
                </a>
              )}
              <div className="text-[11px] leading-relaxed text-[var(--rs-muted)] px-1">
                Wiki first · practice attached · same scan
              </div>
            </div>
          </aside>

          <main className="rs-wiki-main">
            {!ready ? (
              <div className="rs-wiki-article text-center py-24">
                <div className="inline-flex items-center justify-center w-14 h-14 rounded-2xl bg-black/[0.04] mb-5 text-[22px]">
                  ⌘
                </div>
                <h1 className="rs-title text-[28px] font-semibold tracking-tight">
                  生成这个仓库的知识 Wiki
                </h1>
                <p className="mt-3 text-[15px] text-[var(--rs-ink-2)] max-w-md mx-auto">
                  扫描依赖图、入口与模块，生成 Overview、Architecture、Reading Guide
                  以及可练习的概念词条。
                </p>
                <button
                  type="button"
                  onClick={handleAnalyze}
                  disabled={loading}
                  className="rs-btn rs-btn-primary mt-6 h-11 px-6"
                >
                  {loading ? `分析中 (${status || "..."})` : "开始分析"}
                </button>
              </div>
            ) : mode === "learn" && path && !currentPage?.id.startsWith("concepts/") ? (
              <div className="rs-wiki-article">
                <div className="rs-chip rs-chip-accent mb-4">Learning Path</div>
                <h1 className="rs-title text-[34px] font-semibold tracking-tight text-[var(--rs-ink)]">
                  {path.title}
                </h1>
                <p className="mt-3 text-[16px] leading-relaxed text-[var(--rs-ink-2)] max-w-2xl">
                  {path.description}
                </p>
                <div className="mt-2 text-[13px] text-[var(--rs-muted)] rs-tabular">
                  约 {path.estimated_minutes} 分钟 · {path.nodes.length} 个节点
                </div>

                <ol className="mt-10 space-y-3">
                  {path.nodes.map((n, idx) => {
                    const c = n.concept;
                    const pageId = c?.slug ? `concepts/${c.slug}` : "";
                    return (
                      <li
                        key={n.id}
                        className="group rounded-2xl border border-black/5 bg-white p-4 md:p-5 shadow-[var(--rs-shadow)] hover:border-black/10 transition-colors"
                      >
                        <div className="flex gap-4">
                          <div className="w-9 h-9 rounded-full bg-black text-white flex items-center justify-center text-[13px] font-semibold shrink-0 rs-tabular">
                            {idx + 1}
                          </div>
                          <div className="min-w-0 flex-1">
                            <button
                              type="button"
                              className="text-left text-[17px] font-semibold tracking-tight text-[var(--rs-ink)] hover:text-[var(--rs-accent)] transition-colors"
                              onClick={() => {
                                if (pageId) openPage(pageId);
                                else if (n.concept_id) navigate(`/concepts/${n.concept_id}`);
                              }}
                            >
                              {c?.title || n.concept_id}
                            </button>
                            <p className="mt-1.5 text-[14px] leading-relaxed text-[var(--rs-ink-2)]">
                              {n.reason}
                            </p>
                            <div className="mt-3 flex flex-wrap gap-2">
                              {pageId && (
                                <button
                                  type="button"
                                  onClick={() => openPage(pageId)}
                                  className="rs-btn rs-btn-secondary h-8 px-3 text-[12px]"
                                >
                                  打开词条
                                </button>
                              )}
                              {pageId && (
                                <button
                                  type="button"
                                  onClick={() => openPage(pageId)}
                                  className="rs-btn rs-btn-ghost h-8 px-3 text-[12px]"
                                >
                                  Read + practice
                                </button>
                              )}
                            </div>
                          </div>
                        </div>
                      </li>
                    );
                  })}
                </ol>
              </div>
            ) : currentPage ? (
              <div>
                <div className="sticky top-[52px] z-10 border-b border-black/5 bg-white/85 backdrop-blur-xl">
                  <div className="rs-wiki-article !py-2.5 flex flex-wrap items-center justify-between gap-3">
                    <div className="flex items-center gap-2 min-w-0">
                      <span className="rs-chip truncate max-w-[48vw]">
                        {currentPage.title || currentPage.id}
                      </span>
                      {boundConcept && <span className="rs-chip rs-chip-accent">可练习</span>}
                    </div>
                    {boundConcept && (
                      <a
                        href="#practice"
                        className="rs-btn rs-btn-primary h-8 px-3.5 text-[12px]"
                      >
                        Practice ↓
                      </a>
                    )}
                  </div>
                </div>
                <div className="rs-wiki-article !pt-6">
                  <WikiContent content={currentPage.content} title={currentPage.title} />
                  {boundConcept && (
                    <div id="practice">
                      <ConceptPracticePanel concept={boundConcept} />
                    </div>
                  )}
                </div>
              </div>
            ) : (
              <div className="rs-wiki-article text-[var(--rs-muted)]">请选择左侧页面</div>
            )}
          </main>
        </div>
      </div>

      <FolderPicker
        open={pickerOpen}
        onClose={() => setPickerOpen(false)}
        onSelect={(p) => {
          setSourceLocation(p);
          setPickerOpen(false);
        }}
      />
    </AppShell>
  );
}

function SidebarTree({
  items,
  currentId,
  onOpen,
  depth = 0,
}: {
  items: WikiSidebarItem[];
  currentId: string;
  onOpen: (id: string) => void;
  depth?: number;
}) {
  return (
    <ul className={depth === 0 ? "space-y-0.5" : "mt-0.5 space-y-0.5"}>
      {items.map((item) => {
        const active = item.page_id === currentId;
        return (
          <li key={item.page_id || item.title}>
            {item.page_id ? (
              <button
                type="button"
                onClick={() => onOpen(item.page_id)}
                className={`rs-wiki-nav-item ${active ? "is-active" : ""}`}
                style={{ paddingLeft: 10 + depth * 12 }}
              >
                {item.title}
              </button>
            ) : (
              <div
                className="px-2.5 pt-4 pb-1 text-[11px] font-semibold tracking-[0.08em] uppercase text-[var(--rs-muted)]"
                style={{ paddingLeft: 10 + depth * 12 }}
              >
                {item.title}
              </div>
            )}
            {item.children?.length > 0 && (
              <SidebarTree
                items={item.children}
                currentId={currentId}
                onOpen={onOpen}
                depth={depth + 1}
              />
            )}
          </li>
        );
      })}
    </ul>
  );
}
