import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import AppShell from "../components/AppShell";
import { tNow, useT } from "../lib/i18n";
import AskPanel from "../components/AskPanel";
import CommandPalette from "../components/CommandPalette";
import ConceptPracticePanel from "../components/ConceptPracticePanel";
import FolderPicker from "../components/FolderPicker";
import ScanHeaderProgress from "../components/ScanHeaderProgress";
import SourcePeek, { parseRef } from "../components/SourcePeek";
import SourceRail from "../components/SourceRail";
import TableOfContents from "../components/TableOfContents";
import WikiContent from "../components/WikiContent";
import type { TocEntry } from "../lib/markdown";
import { localizeBreadcrumbSegment, localizeSidebarTitle } from "../lib/wikiTitles";
import { PATH_MISSION, corePathNodes, stepTask } from "../lib/learningPath";
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
const STATUS_LABEL: Record<string, [string, string]> = {
  queued: ["排队中", "Queued"],
  pending: ["准备中", "Preparing"],
  scanning: ["扫描代码", "Scanning code"],
  generating_concepts: ["抽取概念", "Extracting concepts"],
  generating_wiki: ["生成 Wiki", "Building wiki"],
  llm_enriching: ["模型润色", "LLM enriching"],
  ready: ["就绪", "Ready"],
  failed: ["失败", "Failed"],
};

function statusLabel(status: string | null, t: (zh: string, en: string) => string): string {
  const pair = STATUS_LABEL[status || ""];
  return pair ? t(...pair) : status || t("未分析", "Not analyzed");
}

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
    const title = (item.title || "").trim().toLowerCase();
    if (!item.page_id && (title === "按目录" || title === "by directory")) {
      continue;
    }
    if (item.page_id) out.push(item);
    if (item.children?.length) flattenSidebar(item.children, out);
  }
  return out;
}

function pathPageId(node: { concept?: { slug?: string; wiki_page_id?: string | null } | null }): string {
  const wikiId = node.concept?.wiki_page_id;
  if (wikiId) return wikiId;
  const slug = node.concept?.slug;
  return slug ? `concepts/${slug}` : "";
}

export default function RepositoryPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const mode = (searchParams.get("mode") as Mode) || "read";
  const pageFromUrl = searchParams.get("page") || "index";

  const t = useT();
  const [repos, setRepos] = useState<Repository[]>([]);
  const [repo, setRepo] = useState<Repository | null>(null);
  const [version, setVersion] = useState<Version | null>(null);
  const [wiki, setWiki] = useState<Wiki | null>(null);
  const [concepts, setConcepts] = useState<Concept[]>([]);
  const [path, setPath] = useState<LearningPath | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  /** Repo id whose /wiki + version fetch has settled. First paint and id
   *  switches stay `opening` until this matches, so we never flash the
   *  empty-state CTA over a wiki that is still in flight. */
  const [hydratedId, setHydratedId] = useState<string | null>(null);
  const loadGen = useRef(0);
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
  const [askSeed, setAskSeed] = useState("");
  const [askSeedKey, setAskSeedKey] = useState(0);
  const [progress, setProgress] = useState(0);
  const [peekRef, setPeekRef] = useState<string | null>(null);
  const articleRef = useRef<HTMLDivElement>(null);

  const analyzing = Boolean(status && RUNNING.has(status));
  const opening = Boolean(id) && hydratedId !== id;

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
    const gen = ++loadGen.current;
    setLoading(true);
    setError(null);
    try {
      const r = await recallstackApi.getRepository(repoId);
      const [v, w, g, p] = await Promise.all([
        recallstackApi.latestVersion(repoId).catch(() => null),
        recallstackApi.wiki(repoId).catch(() => null),
        recallstackApi.concepts(repoId).catch(() => null),
        recallstackApi.learningPath(repoId).catch(() => null),
      ]);
      if (gen !== loadGen.current) return;
      setRepo(r);
      setVersion(v);
      setStatus(v?.status ?? null);
      setWiki(w);
      setConcepts(g?.concepts ?? []);
      setPath(p);
    } catch (e: unknown) {
      if (gen !== loadGen.current) return;
      setRepo(null);
      setWiki(null);
      setVersion(null);
      setStatus(null);
      setConcepts([]);
      setPath(null);
      setError(e instanceof Error ? e.message : tNow("加载失败", "Failed to load"));
    } finally {
      if (gen === loadGen.current) {
        setHydratedId(repoId);
        setLoading(false);
      }
    }
  }, []);

  useEffect(() => {
    refreshList().catch((e: unknown) => setError(e instanceof Error ? e.message : tNow("加载失败", "Failed to load")));
  }, []);

  useEffect(() => {
    if (!id || !path?.nodes?.length) return;
    const node = path.nodes[0];
    const parsed = parseRef(node.evidence_chip || "");
    if (!parsed) return;
    recallstackApi
      .sourceSnippet({
        repository_id: id,
        path: parsed.path,
        start_line: parsed.startLine,
        slug: node.concept?.slug,
      })
      .catch(() => undefined);
  }, [id, path?.id]);

  useEffect(() => {
    if (id) loadRepo(id);
    else {
      loadGen.current += 1;
      setHydratedId(null);
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
        if (RUNNING.has(v.status)) {
          setStatus(v.status);
          return;
        }
        window.clearInterval(timer);
        if (v.status === "failed") {
          setStatus(v.status);
          setError(v.error_message || tNow("分析失败", "Analysis failed"));
        } else {
          // Stay on the analyzing surface until wiki lands — flipping
          // status to ready first would flash the empty-state CTA.
          await loadRepo(id);
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

  async function createFromLocation(
    location: string,
    type: "local" | "github" = sourceType,
  ) {
    const loc = location.trim();
    if (!loc) return;
    setLoading(true);
    setError(null);
    try {
      const created = await recallstackApi.createRepository({
        source_type: type,
        source_location: loc,
      });
      await refreshList();
      navigate(`/repositories/${created.id}`);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : tNow("创建失败", "Create failed"));
    } finally {
      setLoading(false);
    }
  }

  async function handleCreate(e: FormEvent) {
    e.preventDefault();
    await createFromLocation(sourceLocation);
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
      setError(err instanceof Error ? err.message : tNow("分析失败", "Analysis failed"));
      setStatus(version?.status ?? null);
    }
  }

  const currentPage: WikiPage | null = useMemo(() => {
    if (!wiki) return null;
    return wiki.pages.find((p) => p.id === pageFromUrl) || wiki.pages[0] || null;
  }, [wiki, pageFromUrl]);

  const flatPages = useMemo(() => (wiki ? flattenSidebar(wiki.sidebar) : []), [wiki]);

  const learnNodes = useMemo(() => (path ? corePathNodes(path.nodes) : []), [path]);

  const currentPathNode = useMemo(() => {
    if (!currentPage) return null;
    return learnNodes.find((n) => pathPageId(n) === currentPage.id) || null;
  }, [learnNodes, currentPage]);

  const { prevPage, nextPage } = useMemo(() => {
    if (mode === "learn" && learnNodes.length) {
      const i = learnNodes.findIndex((n) => pathPageId(n) === currentPage?.id);
      const prev = i > 0 ? learnNodes[i - 1] : null;
      const next = i >= 0 && i < learnNodes.length - 1 ? learnNodes[i + 1] : null;
      return {
        prevPage: prev
          ? { page_id: pathPageId(prev), title: prev.concept?.title || prev.concept_id }
          : null,
        nextPage: next
          ? { page_id: pathPageId(next), title: next.concept?.title || next.concept_id }
          : null,
      };
    }
    const i = flatPages.findIndex((p) => p.page_id === currentPage?.id);
    return {
      prevPage: i > 0 ? flatPages[i - 1] : null,
      nextPage: i >= 0 && i < flatPages.length - 1 ? flatPages[i + 1] : null,
    };
  }, [flatPages, currentPage, mode, learnNodes]);

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
    return concepts.find((c) => c.wiki_page_id === currentPage.id) || null;
  }, [currentPage, concepts, conceptBySlug]);

  const currentStepTask = useMemo(() => {
    if (currentPathNode?.worksheet) return "";
    if (currentPathNode?.reason) return currentPathNode.reason;
    if (!boundConcept) return "";
    return stepTask(t, boundConcept.slug, boundConcept.title);
  }, [boundConcept, currentPathNode, t]);

  const ready = Boolean(wiki && wiki.pages.length > 0);

  // Reset scroll and outline when the page changes; deep links to #anchors win.
  useEffect(() => {
    setToc([]);
    setProgress(0);
    setPeekRef(null);
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
        title={t("知识库", "Library")}
        subtitle={t(
          "导入一个代码仓库。一次扫描，生成可阅读、可搜索、可溯源的 Wiki。",
          "Import a repository. One scan builds a readable, searchable, source-cited wiki.",
        )}
      >
        <section className="rs-card p-6 md:p-8">
          <div className="flex items-start justify-between gap-4 flex-wrap mb-6">
            <div>
              <div className="rs-eyebrow">Import</div>
              <h2 className="mt-1 text-[22px] font-semibold tracking-tight">{t("导入仓库", "Import a repository")}</h2>
              <p className="mt-1 text-[14px] text-[var(--rs-ink-2)] max-w-xl">
                {t(
                  "本地目录或 GitHub HTTPS。分析后可在阅读器中浏览架构、模块与词条，并跳转到源码证据。",
                  "A local directory or GitHub HTTPS URL. After analysis, browse architecture, modules and concepts with jumps into the source.",
                )}
              </p>
            </div>
          </div>

          <form onSubmit={handleCreate} className="space-y-4">
            <div className="rs-import-row">
              <select
                value={sourceType}
                onChange={(e) => setSourceType(e.target.value as "local" | "github")}
                className="rs-input rs-import-source"
                aria-label={t("来源", "Source")}
              >
                <option value="local">{t("本地目录", "Local directory")}</option>
                <option value="github">GitHub HTTPS</option>
              </select>
              <input
                value={sourceLocation}
                onChange={(e) => setSourceLocation(e.target.value)}
                placeholder={
                  sourceType === "local"
                    ? t("选择文件夹或粘贴绝对路径", "Pick a folder or paste an absolute path")
                    : "https://github.com/org/repo"
                }
                className="rs-input rs-import-path"
                disabled={loading}
              />
              <button
                type="button"
                onClick={() => setPickerOpen(true)}
                className="rs-btn rs-btn-ghost rs-import-browse"
                hidden={sourceType !== "local"}
                disabled={sourceType !== "local" || loading}
              >
                {t("浏览…", "Browse…")}
              </button>
              <button
                type="submit"
                disabled={loading || !sourceLocation.trim()}
                className="rs-btn rs-btn-primary rs-import-create"
              >
                {t("创建", "Create")}
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
            setSourceType("local");
            setPickerOpen(false);
            void createFromLocation(p, "local");
          }}
        />
      </AppShell>
    );
  }

  const sidebar = (
    <>
      <div className="rs-wiki-sidebar-head">
        <div className="rs-eyebrow">{mode === "learn" ? t("学习路径", "Learning Path") : t("目录", "Contents")}</div>
        <div className="mt-1 text-[15px] font-semibold tracking-tight truncate">
          {opening
            ? t("正在打开这份知识", "Opening this knowledge")
            : wiki?.project_name || repo?.name || "Repository"}
        </div>
        <button type="button" className="rs-searchbox" onClick={() => setPaletteOpen(true)}>
          <span aria-hidden>⌕</span>
          <span className="flex-1 text-left">{t("搜索 Wiki", "Search wiki")}</span>
          <kbd className="rs-kbd">⌘K</kbd>
        </button>
        {ready && !opening && mode === "read" && (
          <input
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder={t("过滤目录…", "Filter contents…")}
            className="rs-input h-8 mt-2 text-[12px]"
          />
        )}
      </div>

      <div className="rs-wiki-sidebar-scroll">
        {opening ? (
          <SidebarOpening />
        ) : mode === "learn" && path ? (
          <ol className="space-y-0.5">
            {path.nodes.map((n, idx) => {
              const pageId = pathPageId(n);
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
          <p className="px-3 text-[13px] text-[var(--rs-muted)]">{t("尚未生成目录", "No contents yet")}</p>
        )}
      </div>

      <div className="rs-wiki-sidebar-foot">
        <div className="rs-segmented w-full">
          <button
            type="button"
            className={mode === "read" ? "is-active" : ""}
            onClick={() => setMode("read")}
          >
            {t("阅读", "Read")}
          </button>
          <button
            type="button"
            className={mode === "learn" ? "is-active" : ""}
            onClick={() => setMode("learn")}
            disabled={!path || opening}
          >
            {t("学习路径", "Learning path")}
          </button>
        </div>
      </div>
    </>
  );

  // ── Immersive wiki workbench ───────────────────────────────────────────
  return (
    <AppShell flush>
      <div className={`rs-wiki-shell${askOpen ? " is-asking" : ""}`}>
        {!analyzing && (
          <div className="rs-progress" style={{ transform: `scaleX(${progress})` }} aria-hidden />
        )}

        <div className="rs-wiki-topbar">
          <div className="flex items-center gap-2 min-w-0">
            <button
              type="button"
              className="rs-icon-btn rs-only-narrow"
              onClick={() => setNavOpen(true)}
              aria-label={t("打开目录", "Open contents")}
            >
              ☰
            </button>
            <Link to="/repositories" className="rs-btn rs-btn-ghost h-8 px-3 text-[12px] shrink-0">
              ← {t("知识库", "Library")}
            </Link>
            <div className="min-w-0">
              <div className="text-[14px] font-semibold tracking-tight truncate">
                {opening ? t("仓库", "Repository") : repo?.name || t("仓库", "Repository")}
              </div>
              <ScanHeaderProgress
                commitSha={opening ? null : version?.commit_sha}
                status={opening ? null : status}
                progressMessage={opening ? null : version?.progress_message}
                createdAt={opening ? null : version?.created_at}
                idleLabel={
                  opening
                    ? t("正在打开这份知识", "Opening this knowledge")
                    : statusLabel(status, t)
                }
              />
            </div>
          </div>

          <div className="flex items-center gap-2 shrink-0">
            <button
              type="button"
              className="rs-searchbox rs-searchbox-inline hidden lg:flex"
              onClick={() => setPaletteOpen(true)}
            >
              <span aria-hidden>⌕</span>
              <span>{t("搜索", "Search")}</span>
              <kbd className="rs-kbd">⌘K</kbd>
            </button>
            {ready && !opening && (
              <button
                type="button"
                onClick={() => {
                  setAskSeed("");
                  setAskOpen(true);
                }}
                className="rs-btn rs-btn-secondary h-8 px-3.5 text-[12px]"
              >
                ✦ {t("提问", "Ask")}
              </button>
            )}
            {!opening && (
              <button
                type="button"
                onClick={handleAnalyze}
                disabled={analyzing}
                className="rs-btn rs-btn-primary h-8 px-3.5 text-[12px]"
              >
                {analyzing
                  ? t("你发起的分析", "Your analysis")
                  : ready
                    ? t("你在重扫这份知识", "You are rescanning this knowledge")
                    : t("发起你的分析", "Start your analysis")}
              </button>
            )}
            <Link to="/reviews" className="rs-btn rs-btn-ghost h-8 px-3 text-[12px] hidden sm:flex">
              {t("复习", "Review")}
            </Link>
          </div>
        </div>

        {error && !opening && <div className="rs-alert mx-4 mt-3">{error}</div>}

        <div className={`rs-wiki-body${askOpen ? " is-asking" : ""}`}>
          <aside className="rs-wiki-sidebar">{sidebar}</aside>

          {navOpen && (
            <div className="rs-drawer-backdrop rs-only-narrow" onClick={() => setNavOpen(false)}>
              <aside className="rs-wiki-sidebar rs-drawer" onClick={(e) => e.stopPropagation()}>
                {sidebar}
              </aside>
            </div>
          )}

          <main className="rs-wiki-main">
            {opening ? (
              <WikiOpening />
            ) : !ready ? (
              <div className="rs-wiki-article text-center py-24">
                <div className="rs-hero-mark">⌘</div>
                <h1 className="rs-title text-[28px] font-semibold tracking-tight mt-5">
                  {analyzing
                    ? t("你发起的分析正在跑", "The analysis you started is running")
                    : t("你还没发起这份知识的分析", "You have not started this knowledge yet")}
                </h1>
                <p className="mt-3 text-[15px] text-[var(--rs-ink-2)] max-w-md mx-auto">
                  {t(
                    "你发起之后，扫描依赖图、入口与模块，生成 Overview、Architecture、Reading Guide 与词条页。相位看得见，产品不替你做主。",
                    "After you start it, the scan walks the graph, entry points and modules. Phases stay visible. The product does not decide for you.",
                  )}
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
                    {t("发起你的分析", "Start your analysis")}
                  </button>
                )}
              </div>
            ) : mode === "learn" && path && !learnNodes.some((n) => pathPageId(n) === currentPage?.id) ? (
              <div className="rs-wiki-article">
                <div className="rs-chip rs-chip-accent mb-4">{t("你要签字的路径", "The path you sign off")}</div>
                <h1 className="rs-title text-[34px] font-semibold tracking-tight">{path.title}</h1>
                <p className="mt-3 text-[16px] leading-relaxed text-[var(--rs-ink-2)] max-w-2xl">
                  {t(PATH_MISSION[0], PATH_MISSION[1])}
                </p>
                <div className="mt-2 text-[13px] text-[var(--rs-muted)] rs-tabular">
                  {t(`约 ${path.estimated_minutes} 分钟 · ${learnNodes.length} 个节点`, `~${path.estimated_minutes} min · ${learnNodes.length} steps`)}
                </div>

                <ol className="mt-10 space-y-3">
                  {learnNodes.map((n, idx) => {
                    const c = n.concept;
                    const pageId = pathPageId(n);
                    const task = c ? stepTask(t, c.slug, c.title) : n.reason;
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
                            <p className="mt-1.5 text-[13px] font-medium text-[var(--rs-accent)]">
                              {t("你这周的职责", "Your job this week")}
                            </p>
                            <p className="mt-1 text-[14px] leading-relaxed text-[var(--rs-ink-2)]">
                              {task || n.reason}
                            </p>
                            {pageId && (
                              <button
                                type="button"
                                onClick={() => openPage(pageId)}
                                className="rs-btn rs-btn-secondary h-8 px-3 text-[12px] mt-3"
                              >
                                {t("去签字这一步 →", "Go sign this step →")}
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
                  <nav className="rs-breadcrumb" aria-label={t("面包屑", "Breadcrumb")}>
                    <button type="button" onClick={() => openPage("index")}>
                      {wiki?.project_name || repo?.name || "Wiki"}
                    </button>
                    {currentPage.id.includes("/") && (
                      <>
                        <span aria-hidden>/</span>
                        <span>{localizeBreadcrumbSegment(currentPage.id.split("/")[0], t)}</span>
                      </>
                    )}
                    <span aria-hidden>/</span>
                    <span className="rs-breadcrumb-current">
                      {localizeSidebarTitle(
                        { title: currentPage.title || currentPage.id, page_id: currentPage.id },
                        t,
                      )}
                    </span>
                  </nav>

                  {mode === "learn" && currentStepTask && (
                    <div className="mb-6 rounded-[12px] border border-[var(--rs-line)] bg-[var(--rs-surface-2)] px-4 py-3">
                      <div className="text-[12px] font-medium text-[var(--rs-accent)]">
                        {t("你这周的职责", "Your job this week")}
                      </div>
                      <p className="mt-1 text-[14px] leading-relaxed text-[var(--rs-ink-2)]">
                        {currentStepTask}
                      </p>
                    </div>
                  )}

                  <WikiContent
                    content={
                      mode === "learn" && currentPathNode?.worksheet
                        ? currentPathNode.worksheet
                        : currentPage.content
                    }
                    title={
                      mode === "learn" && currentPathNode?.concept?.title
                        ? currentPathNode.concept.title
                        : currentPage.title
                    }
                    repositoryId={id}
                    learnSlug={mode === "learn" ? currentPathNode?.concept?.slug : undefined}
                    onNavigatePage={openPage}
                    onTocChange={setToc}
                    onLookup={({ selection }) => {
                      setAskSeed(selection);
                      setAskSeedKey((k) => k + 1);
                      setAskOpen(true);
                    }}
                  />

                  {mode === "learn" && boundConcept && (
                    <ConceptPracticePanel concept={boundConcept} />
                  )}

                  {(prevPage || nextPage) && (
                    <nav className="rs-pager" aria-label={t("上一页 / 下一页", "Previous / next page")}>
                      {prevPage ? (
                        <button type="button" onClick={() => openPage(prevPage.page_id)}>
                          <span className="rs-pager-dir">← {t("上一页", "Previous")}</span>
                          <span className="rs-pager-title">
                            {localizeSidebarTitle({ title: prevPage.title, page_id: prevPage.page_id }, t)}
                          </span>
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
                          <span className="rs-pager-dir">{t("下一页", "Next")} →</span>
                          <span className="rs-pager-title">
                            {localizeSidebarTitle({ title: nextPage.title, page_id: nextPage.page_id }, t)}
                          </span>
                        </button>
                      )}
                    </nav>
                  )}
                </article>

                <aside className="rs-wiki-aside hidden xl:block">
                  {currentPage && (
                    <SourceRail content={currentPage.content} onOpen={setPeekRef} />
                  )}
                  {peekRef && id && (
                    <SourcePeek
                      repositoryId={id}
                      reference={peekRef}
                      onClose={() => setPeekRef(null)}
                    />
                  )}
                  <TableOfContents entries={toc} />
                </aside>
              </div>
            ) : (
              <div className="rs-wiki-article text-[var(--rs-muted)]">{t("请选择左侧页面", "Pick a page on the left")}</div>
            )}
          </main>
          {id ? (
            <AskPanel
              open={askOpen}
              repositoryId={id}
              repositoryName={wiki?.project_name || repo?.name || t("仓库", "repository")}
              initialQuestion={askSeed}
              questionKey={askSeedKey}
              canAsk={ready}
              suggestions={wiki?.suggested_questions || []}
              onClose={() => setAskOpen(false)}
              onOpenPage={openPage}
            />
          ) : null}
        </div>
      </div>

      <CommandPalette
        open={paletteOpen}
        repositoryId={id}
        initialQuery={paletteSeed}
        onClose={() => setPaletteOpen(false)}
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

function SidebarOpening() {
  const t = useT();
  return (
    <div className="rs-wiki-opening-nav" aria-busy="true" aria-live="polite">
      <p className="px-3 text-[13px] text-[var(--rs-muted)]">
        {t("正在打开这份知识", "Opening this knowledge")}
      </p>
      <div className="rs-skel rs-skel-nav" />
      <div className="rs-skel rs-skel-nav is-mid" />
      <div className="rs-skel rs-skel-nav is-short" />
      <div className="rs-skel rs-skel-nav" />
      <div className="rs-skel rs-skel-nav is-mid" />
    </div>
  );
}

function WikiOpening() {
  const t = useT();
  return (
    <div className="rs-wiki-article rs-wiki-opening" aria-busy="true" aria-live="polite">
      <p className="rs-wiki-opening-copy">{t("正在打开这份知识", "Opening this knowledge")}</p>
      <div className="rs-skel rs-skel-title" />
      <div className="rs-skel rs-skel-line" />
      <div className="rs-skel rs-skel-line" />
      <div className="rs-skel rs-skel-line is-short" />
      <div className="rs-skel rs-skel-line" />
      <div className="rs-skel rs-skel-line is-mid" />
    </div>
  );
}

const PIPELINE = ["scanning", "generating_concepts", "generating_wiki", "llm_enriching"];

function PipelineSteps({ status, detail }: { status: string; detail?: string | null }) {
  const t = useT();
  const index = PIPELINE.indexOf(status);
  return (
    <ol className="rs-pipeline">
      {PIPELINE.map((step, i) => {
        const state = index < 0 ? "wait" : i < index ? "done" : i === index ? "now" : "wait";
        return (
          <li key={step} className={`rs-pipeline-step is-${state}`}>
            <span className="rs-pipeline-dot" aria-hidden />
            <span>{statusLabel(step, t)}</span>
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
function matchesFilter(
  item: WikiSidebarItem,
  filter: string,
  t: (zh: string, en: string) => string,
): boolean {
  if (!filter) return true;
  const shown = localizeSidebarTitle(item, t).toLowerCase();
  if (shown.includes(filter)) return true;
  if (item.title.toLowerCase().includes(filter)) return true;
  if (item.page_id?.toLowerCase().includes(filter)) return true;
  return (item.children || []).some((c) => matchesFilter(c, filter, t));
}

function isDirectoryGroup(item: WikiSidebarItem): boolean {
  if (item.page_id) return false;
  const raw = item.title.trim().toLowerCase();
  return raw === "按目录" || raw === "by directory" || raw === "模块" || raw === "modules";
}

function containsPage(item: WikiSidebarItem, pageId: string): boolean {
  if (!pageId) return false;
  if (item.page_id === pageId) return true;
  return (item.children || []).some((child) => containsPage(child, pageId));
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
  const t = useT();
  const visible = items.filter((item) => matchesFilter(item, filter, t));
  if (!visible.length) {
    return depth === 0 ? (
      <p className="px-3 py-2 text-[13px] text-[var(--rs-muted)]">{t("没有匹配的页面", "No matching pages")}</p>
    ) : null;
  }
  return (
    <ul className="space-y-0.5">
      {visible.map((item) => (
        <SidebarNode
          key={item.page_id || item.title}
          item={item}
          currentId={currentId}
          onOpen={onOpen}
          filter={filter}
          depth={depth}
        />
      ))}
    </ul>
  );
}

function SidebarNode({
  item,
  currentId,
  onOpen,
  filter,
  depth,
}: {
  item: WikiSidebarItem;
  currentId: string;
  onOpen: (id: string) => void;
  filter: string;
  depth: number;
}) {
  const t = useT();
  const directoryGroup = isDirectoryGroup(item);
  const [open, setOpen] = useState(
    () => !directoryGroup || containsPage(item, currentId),
  );
  const active = item.page_id === currentId;
  const label = localizeSidebarTitle(item, t);
  const showChildren =
    Boolean(item.children?.length) &&
    (Boolean(filter) || !directoryGroup || open || containsPage(item, currentId));

  return (
    <li>
      {item.page_id ? (
        <button
          type="button"
          onClick={() => onOpen(item.page_id)}
          className={`rs-wiki-nav-item ${active ? "is-active" : ""}`}
          style={{ paddingLeft: 10 + depth * 12 }}
          aria-current={active ? "page" : undefined}
        >
          <span className="truncate">{label}</span>
        </button>
      ) : directoryGroup ? (
        <button
          type="button"
          className="rs-wiki-nav-group rs-wiki-nav-disclosure"
          style={{ paddingLeft: 10 + depth * 12 }}
          aria-expanded={showChildren}
          onClick={() => setOpen((value) => !value)}
        >
          <span aria-hidden>{showChildren ? "▾" : "▸"}</span>
          <span>{label}</span>
        </button>
      ) : (
        <div
          className="rs-wiki-nav-group"
          style={{ paddingLeft: 10 + depth * 12 }}
        >
          {label}
        </div>
      )}
      {showChildren && (
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
}
