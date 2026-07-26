import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import AppShell from "../components/AppShell";
import AskPanel from "../components/AskPanel";
import CommandPalette from "../components/CommandPalette";
import ConceptPracticePanel from "../components/ConceptPracticePanel";
import FolderPicker from "../components/FolderPicker";
import TableOfContents from "../components/TableOfContents";
import WikiContent from "../components/WikiContent";
import type { TocEntry } from "../lib/markdown";
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

/** Human labels for the analyze pipeline's machine statuses. */
const STATUS_LABEL: Record<string, string> = {
  queued: "排队中",
  pending: "准备中",
  scanning: "扫描代码",
  generating_concepts: "抽取概念",
  generating_wiki: "生成 Wiki",
  llm_enriching: "模型润色",
  ready: "就绪",
  failed: "失败",
};

const RUNNING = new Set([
  "queued",
  "pending",
  "scanning",
  "generating_concepts",
  "generating_wiki",
  "llm_enriching",
]);

/** Flatten the sidebar tree into reading order, for prev/next navigation. */
function flattenSidebar(items: WikiSidebarItem[], out: WikiSidebarItem[] = []) {
  for (const item of items) {
    if (item.page_id) out.push(item);
    if (item.children?.length) flattenSidebar(item.children, out);
  }
  return out;
}

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

  // Reading surface state.
  const [toc, setToc] = useState<TocEntry[]>([]);
  const [filter, setFilter] = useState("");
  const [navOpen, setNavOpen] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [paletteSeed, setPaletteSeed] = useState<string>("");
  const [askOpen, setAskOpen] = useState(false);
  const [progress, setProgress] = useState(0);
  const articleRef = useRef<HTMLDivElement>(null);

  const analyzing = Boolean(status && RUNNING.has(status));

  function openPage(pageId: string) {
    const sp = new URLSearchParams(searchParams);
    sp.set("page", pageId);
    setSearchParams(sp, { replace: false });
    setNavOpen(false);
  }

  function setMode(next: Mode) {
    const sp = new URLSearchParams(searchParams);
    if (next === "read") sp.delete("mode");
    else sp.set("mode", next);
    setSearchParams(sp, { replace: true });
  }

  async function refreshList() {
    setRepos(await recallstackApi.listRepositories());
  }

  const loadRepo = useCallback(async (repoId: string) => {
    setLoading(true);
    setError(null);
    try {
      const r = await recallstackApi.getRepository(repoId);
      setRepo(r);
      const [v, w, g, p] = await Promise.all([
        recallstackApi.latestVersion(repoId).catch(() => null),
        recallstackApi.wiki(repoId).catch(() => null),
        recallstackApi.concepts(repoId).catch(() => null),
        recallstackApi.learningPath(repoId).catch(() => null),
      ]);
      setVersion(v);
      setStatus(v?.status ?? null);
      setWiki(w);
      setConcepts(g?.concepts ?? []);
      setPath(p);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refreshList().catch((e: unknown) => setError(e instanceof Error ? e.message : "加载失败"));
  }, []);

  useEffect(() => {
    if (id) loadRepo(id);
    else {
      setRepo(null);
      setWiki(null);
      setConcepts([]);
      setPath(null);
      setVersion(null);
      setStatus(null);
    }
  }, [id, loadRepo]);

  // Poll while a background analyze is in flight, so the reader watches the
  // pipeline advance instead of staring at a frozen button.
  useEffect(() => {
    if (!id || !analyzing) return;
    let cancelled = false;
    const timer = window.setInterval(async () => {
      try {
        const v = await recallstackApi.latestVersion(id);
        if (cancelled) return;
        setVersion(v);
        setStatus(v.status);
        if (!RUNNING.has(v.status)) {
          window.clearInterval(timer);
          if (v.status === "failed") setError(v.error_message || "分析失败");
          else await loadRepo(id);
        }
      } catch {
        /* transient; the next tick retries */
      }
    }, 1800);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [id, analyzing, loadRepo]);

  // ⌘K / Ctrl-K opens search from anywhere in the reader.
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPaletteSeed("");
        setPaletteOpen(true);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

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
    setError(null);
    setStatus("queued");
    try {
      // Background mode: the request returns immediately and the poller above
      // drives the UI. A blocking call would freeze the page for minutes.
      const v = await recallstackApi.analyze(id, false);
      setVersion(v);
      setStatus(v.status);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "分析失败");
      setStatus(version?.status ?? null);
    }
  }

  const currentPage: WikiPage | null = useMemo(() => {
    if (!wiki) return null;
    return wiki.pages.find((p) => p.id === pageFromUrl) || wiki.pages[0] || null;
  }, [wiki, pageFromUrl]);

  const flatPages = useMemo(() => (wiki ? flattenSidebar(wiki.sidebar) : []), [wiki]);

  const { prevPage, nextPage } = useMemo(() => {
    const i = flatPages.findIndex((p) => p.page_id === currentPage?.id);
    return {
      prevPage: i > 0 ? flatPages[i - 1] : null,
      nextPage: i >= 0 && i < flatPages.length - 1 ? flatPages[i + 1] : null,
    };
  }, [flatPages, currentPage]);

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

  // Reset scroll and outline when the page changes; deep links to #anchors win.
  useEffect(() => {
    setToc([]);
    setProgress(0);
    if (!window.location.hash) window.scrollTo({ top: 0 });
  }, [currentPage?.id]);

  // Reading progress across the article body.
  useEffect(() => {
    if (!ready) return;
    function update() {
      const el = articleRef.current;
      if (!el) return;
      const rect = el.getBoundingClientRect();
      const scrolled = -rect.top + window.innerHeight * 0.5;
      const pct = Math.max(0, Math.min(1, scrolled / Math.max(1, rect.height)));
      setProgress(pct);
    }
    update();
    window.addEventListener("scroll", update, { passive: true });
    window.addEventListener("resize", update);
    return () => {
      window.removeEventListener("scroll", update);
      window.removeEventListener("resize", update);
    };
  }, [ready, currentPage?.id]);

  // ── Import landing (no repo selected) ──────────────────────────────────
  if (!id) {
    return (
      <AppShell
        title="知识库"
        subtitle="导入一个代码仓库。一次扫描，生成可阅读、可搜索、可溯源的 Wiki。"
      >
        <section className="rs-card p-6 md:p-8">
          <div className="flex items-start justify-between gap-4 flex-wrap mb-6">
            <div>
              <div className="rs-eyebrow">Import</div>
              <h2 className="mt-1 text-[22px] font-semibold tracking-tight">导入仓库</h2>
              <p className="mt-1 text-[14px] text-[var(--rs-ink-2)] max-w-xl">
                本地目录或 GitHub HTTPS。分析后可在阅读器中浏览架构、模块与词条，并跳转到源码证据。
              </p>
            </div>
          </div>

          <form onSubmit={handleCreate} className="space-y-4">
            <div className="flex flex-col md:flex-row gap-3">
              <select
                value={sourceType}
                onChange={(e) => setSourceType(e.target.value as "local" | "github")}
                className="rs-input h-11 md:w-40"
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
                  className="rs-input flex-1 h-11"
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

          {error && <div className="rs-alert mt-4">{error}</div>}

          {repos.length > 0 && (
            <div className="mt-8">
              <div className="rs-eyebrow mb-3">Libraries</div>
              <ul className="rs-list">
                {repos.map((r) => (
                  <li key={r.id}>
                    <Link to={`/repositories/${r.id}`} className="rs-list-row">
                      <div className="min-w-0">
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

  const sidebar = (
    <>
      <div className="rs-wiki-sidebar-head">
        <div className="rs-eyebrow">{mode === "learn" ? "Learning Path" : "Contents"}</div>
        <div className="mt-1 text-[15px] font-semibold tracking-tight truncate">
          {wiki?.project_name || repo?.name || "Repository"}
        </div>
        <button type="button" className="rs-searchbox" onClick={() => setPaletteOpen(true)}>
          <span aria-hidden>⌕</span>
          <span className="flex-1 text-left">搜索 Wiki</span>
          <kbd className="rs-kbd">⌘K</kbd>
        </button>
        {ready && mode === "read" && (
          <input
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder="过滤目录…"
            className="rs-input h-8 mt-2 text-[12px]"
          />
        )}
      </div>

      <div className="rs-wiki-sidebar-scroll">
        {mode === "learn" && path ? (
          <ol className="space-y-0.5">
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
            filter={filter.trim().toLowerCase()}
          />
        ) : (
          <p className="px-3 text-[13px] text-[var(--rs-muted)]">尚未生成目录</p>
        )}
      </div>

      <div className="rs-wiki-sidebar-foot">
        <div className="rs-segmented w-full">
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
            disabled={!path}
          >
            学习路径
          </button>
        </div>
      </div>
    </>
  );

  // ── Immersive wiki workbench ───────────────────────────────────────────
  return (
    <AppShell flush>
      <div className="rs-wiki-shell">
        <div className="rs-progress" style={{ transform: `scaleX(${progress})` }} aria-hidden />

        <div className="rs-wiki-topbar">
          <div className="flex items-center gap-2 min-w-0">
            <button
              type="button"
              className="rs-icon-btn rs-only-narrow"
              onClick={() => setNavOpen(true)}
              aria-label="打开目录"
            >
              ☰
            </button>
            <Link to="/repositories" className="rs-btn rs-btn-ghost h-8 px-3 text-[12px] shrink-0">
              ← 知识库
            </Link>
            <div className="min-w-0">
              <div className="text-[14px] font-semibold tracking-tight truncate">
                {repo?.name || "仓库"}
              </div>
              <div className="text-[11px] text-[var(--rs-muted)] truncate rs-tabular">
                {version?.commit_sha ? `${version.commit_sha.slice(0, 10)} · ` : ""}
                {STATUS_LABEL[status || ""] || status || "未分析"}
              </div>
            </div>
          </div>

          <div className="flex items-center gap-2 shrink-0">
            <button
              type="button"
              className="rs-searchbox rs-searchbox-inline hidden lg:flex"
              onClick={() => setPaletteOpen(true)}
            >
              <span aria-hidden>⌕</span>
              <span>搜索</span>
              <kbd className="rs-kbd">⌘K</kbd>
            </button>
            {ready && (
              <button
                type="button"
                onClick={() => setAskOpen(true)}
                className="rs-btn rs-btn-secondary h-8 px-3.5 text-[12px]"
              >
                ✦ 提问
              </button>
            )}
            <button
              type="button"
              onClick={handleAnalyze}
              disabled={analyzing}
              className="rs-btn rs-btn-primary h-8 px-3.5 text-[12px]"
            >
              {analyzing ? STATUS_LABEL[status || ""] || "分析中…" : ready ? "重新扫描" : "生成 Wiki"}
            </button>
            <Link to="/reviews" className="rs-btn rs-btn-ghost h-8 px-3 text-[12px] hidden sm:flex">
              复习
            </Link>
          </div>
        </div>

        {error && <div className="rs-alert mx-4 mt-3">{error}</div>}

        <div className="rs-wiki-body">
          <aside className="rs-wiki-sidebar">{sidebar}</aside>

          {navOpen && (
            <div className="rs-drawer-backdrop rs-only-narrow" onClick={() => setNavOpen(false)}>
              <aside className="rs-wiki-sidebar rs-drawer" onClick={(e) => e.stopPropagation()}>
                {sidebar}
              </aside>
            </div>
          )}

          <main className="rs-wiki-main">
            {!ready ? (
              <div className="rs-wiki-article text-center py-24">
                <div className="rs-hero-mark">⌘</div>
                <h1 className="rs-title text-[28px] font-semibold tracking-tight mt-5">
                  {analyzing ? "正在生成 Wiki" : "生成这个仓库的知识 Wiki"}
                </h1>
                <p className="mt-3 text-[15px] text-[var(--rs-ink-2)] max-w-md mx-auto">
                  扫描依赖图、入口与模块，生成 Overview、Architecture、Reading Guide 与词条页，
                  每条结论都带源码引用。
                </p>
                {analyzing ? (
                  <div className="mt-7 max-w-sm mx-auto">
                    <PipelineSteps status={status || ""} detail={version?.progress_message} />
                  </div>
                ) : (
                  <button
                    type="button"
                    onClick={handleAnalyze}
                    className="rs-btn rs-btn-primary mt-6 h-11 px-6"
                  >
                    开始分析
                  </button>
                )}
              </div>
            ) : mode === "learn" && path && !currentPage?.id.startsWith("concepts/") ? (
              <div className="rs-wiki-article">
                <div className="rs-chip rs-chip-accent mb-4">辅助 · 学习路径</div>
                <h1 className="rs-title text-[34px] font-semibold tracking-tight">{path.title}</h1>
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
                      <li key={n.id} className="rs-step-card">
                        <div className="flex gap-4">
                          <div className="rs-step-num rs-tabular">{idx + 1}</div>
                          <div className="min-w-0 flex-1">
                            <button
                              type="button"
                              className="rs-step-title"
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
                            {pageId && (
                              <button
                                type="button"
                                onClick={() => openPage(pageId)}
                                className="rs-btn rs-btn-secondary h-8 px-3 text-[12px] mt-3"
                              >
                                打开词条 →
                              </button>
                            )}
                          </div>
                        </div>
                      </li>
                    );
                  })}
                </ol>
              </div>
            ) : currentPage ? (
              <div className="rs-reader">
                <article className="rs-wiki-article" ref={articleRef}>
                  <nav className="rs-breadcrumb" aria-label="面包屑">
                    <button type="button" onClick={() => openPage("index")}>
                      {wiki?.project_name || repo?.name || "Wiki"}
                    </button>
                    {currentPage.id.includes("/") && (
                      <>
                        <span aria-hidden>/</span>
                        <span>{currentPage.id.split("/")[0]}</span>
                      </>
                    )}
                    <span aria-hidden>/</span>
                    <span className="rs-breadcrumb-current">
                      {currentPage.title || currentPage.id}
                    </span>
                  </nav>

                  <WikiContent
                    content={currentPage.content}
                    title={currentPage.title}
                    repositoryId={id}
                    onNavigatePage={openPage}
                    onTocChange={setToc}
                    onLookup={({ selection }) => {
                      setPaletteSeed(selection);
                      setPaletteOpen(true);
                    }}
                  />

                  {boundConcept && <ConceptPracticePanel concept={boundConcept} />}

                  {(prevPage || nextPage) && (
                    <nav className="rs-pager" aria-label="上一页 / 下一页">
                      {prevPage ? (
                        <button type="button" onClick={() => openPage(prevPage.page_id)}>
                          <span className="rs-pager-dir">← 上一页</span>
                          <span className="rs-pager-title">{prevPage.title}</span>
                        </button>
                      ) : (
                        <span />
                      )}
                      {nextPage && (
                        <button
                          type="button"
                          className="rs-pager-next"
                          onClick={() => openPage(nextPage.page_id)}
                        >
                          <span className="rs-pager-dir">下一页 →</span>
                          <span className="rs-pager-title">{nextPage.title}</span>
                        </button>
                      )}
                    </nav>
                  )}
                </article>

                <aside className="rs-wiki-aside hidden xl:block">
                  <TableOfContents entries={toc} />
                </aside>
              </div>
            ) : (
              <div className="rs-wiki-article text-[var(--rs-muted)]">请选择左侧页面</div>
            )}
          </main>
        </div>
      </div>

      <CommandPalette
        open={paletteOpen}
        repositoryId={id}
        initialQuery={paletteSeed}
        onClose={() => setPaletteOpen(false)}
        onOpenPage={openPage}
      />

      <AskPanel
        open={askOpen}
        repositoryId={id}
        repositoryName={wiki?.project_name || repo?.name || "仓库"}
        onClose={() => setAskOpen(false)}
        onOpenPage={openPage}
      />

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

const PIPELINE: { key: string; label: string }[] = [
  { key: "scanning", label: "扫描代码" },
  { key: "generating_concepts", label: "抽取概念" },
  { key: "generating_wiki", label: "生成 Wiki" },
  { key: "llm_enriching", label: "模型润色" },
];

function PipelineSteps({ status, detail }: { status: string; detail?: string | null }) {
  const index = PIPELINE.findIndex((s) => s.key === status);
  return (
    <ol className="rs-pipeline">
      {PIPELINE.map((step, i) => {
        const state = index < 0 ? "wait" : i < index ? "done" : i === index ? "now" : "wait";
        return (
          <li key={step.key} className={`rs-pipeline-step is-${state}`}>
            <span className="rs-pipeline-dot" aria-hidden />
            <span>{step.label}</span>
            {/* The LLM stage runs for minutes; without its per-module counter
                the whole panel looks frozen. */}
            {state === "now" && detail && <span className="rs-pipeline-detail">{detail}</span>}
          </li>
        );
      })}
    </ol>
  );
}

/** True when the item or any descendant matches the filter. */
function matchesFilter(item: WikiSidebarItem, filter: string): boolean {
  if (!filter) return true;
  if (item.title.toLowerCase().includes(filter)) return true;
  if (item.page_id?.toLowerCase().includes(filter)) return true;
  return (item.children || []).some((c) => matchesFilter(c, filter));
}

function SidebarTree({
  items,
  currentId,
  onOpen,
  filter = "",
  depth = 0,
}: {
  items: WikiSidebarItem[];
  currentId: string;
  onOpen: (id: string) => void;
  filter?: string;
  depth?: number;
}) {
  const visible = items.filter((item) => matchesFilter(item, filter));
  if (!visible.length) {
    return depth === 0 ? (
      <p className="px-3 py-2 text-[13px] text-[var(--rs-muted)]">没有匹配的页面</p>
    ) : null;
  }
  return (
    <ul className="space-y-0.5">
      {visible.map((item) => {
        const active = item.page_id === currentId;
        return (
          <li key={item.page_id || item.title}>
            {item.page_id ? (
              <button
                type="button"
                onClick={() => onOpen(item.page_id)}
                className={`rs-wiki-nav-item ${active ? "is-active" : ""}`}
                style={{ paddingLeft: 10 + depth * 12 }}
                aria-current={active ? "page" : undefined}
              >
                <span className="truncate">{item.title}</span>
              </button>
            ) : (
              <div
                className="rs-wiki-nav-group"
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
                filter={filter}
                depth={depth + 1}
              />
            )}
          </li>
        );
      })}
    </ul>
  );
}
