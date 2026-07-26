import { Link, useLocation } from "react-router-dom";

type Props = {
  children: React.ReactNode;
  title?: string;
  subtitle?: string;
  actions?: React.ReactNode;
  /** Full-bleed content without max-width container (used by immersive wiki). */
  flush?: boolean;
};

const NAV = [
  { to: "/", label: "今日", match: (p: string) => p === "/" || p === "/learn" },
  {
    to: "/repositories",
    label: "知识库",
    match: (p: string) =>
      p.startsWith("/repositories") ||
      p.startsWith("/concepts") ||
      p.startsWith("/session") ||
      p.startsWith("/learn"),
  },
  {
    to: "/reviews",
    label: "复习",
    match: (p: string) => p.startsWith("/reviews") || p.startsWith("/learn/reviews"),
  },
];

export default function AppShell({ children, title, subtitle, actions, flush }: Props) {
  const { pathname } = useLocation();

  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-30 border-b border-black/5 bg-white/75 backdrop-blur-xl">
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
                回栈
              </span>
            </Link>
            <nav className="hidden sm:flex items-center gap-1">
              {NAV.map((item) => {
                const active = item.match(pathname);
                return (
                  <Link
                    key={item.to}
                    to={item.to}
                    className={`px-3 py-1.5 rounded-full text-[13px] transition-colors ${
                      active
                        ? "bg-black/[0.06] text-[var(--rs-ink)] font-semibold"
                        : "text-[var(--rs-ink-2)] hover:bg-black/[0.04]"
                    }`}
                  >
                    {item.label}
                  </Link>
                );
              })}
            </nav>
          </div>
          <div className="hidden md:block text-[12px] text-[var(--rs-muted)] truncate">
            从调用栈，到知识栈
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
