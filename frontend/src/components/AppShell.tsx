import { Link, useLocation } from "react-router-dom";
import { useLang, useT } from "../lib/i18n";
import { useTheme } from "../lib/theme";

type Props = {
  children: React.ReactNode;
  title?: string;
  subtitle?: string;
  actions?: React.ReactNode;
  /** Full-bleed content without max-width container (used by immersive wiki). */
  flush?: boolean;
};

const NAV = [
  { to: "/", zh: "今日", en: "Today", match: (p: string) => p === "/" || p === "/learn" },
  {
    to: "/repositories",
    zh: "知识库",
    en: "Library",
    match: (p: string) =>
      p.startsWith("/repositories") ||
      p.startsWith("/concepts") ||
      p.startsWith("/session") ||
      p.startsWith("/learn"),
  },
  {
    to: "/reviews",
    zh: "复习",
    en: "Review",
    match: (p: string) => p.startsWith("/reviews") || p.startsWith("/learn/reviews"),
  },
];

export default function AppShell({ children, title, subtitle, actions, flush }: Props) {
  const { pathname } = useLocation();
  const [theme, toggleTheme] = useTheme();
  const [lang, setLang] = useLang();
  const t = useT();

  return (
    <div className="min-h-screen">
      <header className="rs-appbar">
        <div
          className={`h-[52px] flex items-center justify-between gap-4 px-4 md:px-6 ${
            flush ? "max-w-none" : "max-w-6xl mx-auto"
          }`}
        >
          <div className="flex items-center gap-7 min-w-0">
            <Link to="/" className="shrink-0 group">
              <span className="text-[17px] font-semibold tracking-tight text-[var(--rs-ink)]">
                Recall<span className="text-[var(--rs-accent)]">Stack</span>
              </span>
              <span className="ml-2 text-[11px] font-medium text-[var(--rs-muted)] tracking-wide">
                {t("回栈", "wiki + recall")}
              </span>
            </Link>
            <nav className="hidden sm:flex items-center gap-1">
              {NAV.map((item) => {
                const active = item.match(pathname);
                return (
                  <Link
                    key={item.to}
                    to={item.to}
                    className={`rs-navlink ${active ? "is-active" : ""}`}
                  >
                    {t(item.zh, item.en)}
                  </Link>
                );
              })}
            </nav>
          </div>
          <div className="flex items-center gap-3 shrink-0">
            <div className="hidden lg:block text-[12px] text-[var(--rs-muted)] truncate">
              {t("从调用栈，到知识栈", "From call stack to knowledge stack")}
            </div>
            <button
              type="button"
              onClick={() => setLang(lang === "zh" ? "en" : "zh")}
              className="rs-icon-btn text-[12px] font-medium"
              title={lang === "zh" ? "Switch to English" : "切换到中文"}
              aria-label={lang === "zh" ? "Switch to English" : "切换到中文"}
            >
              {lang === "zh" ? "EN" : "中"}
            </button>
            <button
              type="button"
              onClick={toggleTheme}
              className="rs-icon-btn"
              title={
                theme === "dark" ? t("切换到浅色", "Light mode") : t("切换到深色", "Dark mode")
              }
              aria-label={
                theme === "dark" ? t("切换到浅色", "Light mode") : t("切换到深色", "Dark mode")
              }
            >
              {theme === "dark" ? "☀" : "☾"}
            </button>
          </div>
        </div>
      </header>

      <main className={flush ? "" : "max-w-6xl mx-auto px-4 md:px-6 py-8"}>
        {(title || actions) && !flush && (
          <div className="mb-8 flex items-end justify-between gap-4 flex-wrap">
            <div className="max-w-2xl">
              {title && (
                <h1 className="rs-title text-[32px] md:text-[40px] font-semibold leading-[1.1] text-[var(--rs-ink)]">
                  {title}
                </h1>
              )}
              {subtitle && (
                <p className="mt-2 text-[15px] leading-relaxed text-[var(--rs-ink-2)] text-pretty">
                  {subtitle}
                </p>
              )}
            </div>
            {actions}
          </div>
        )}
        {children}
      </main>
    </div>
  );
}
