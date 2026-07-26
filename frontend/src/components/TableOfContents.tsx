import { useEffect, useState } from "react";
import type { TocEntry } from "../lib/markdown";
import { useT } from "../lib/i18n";

interface Props {
  entries: TocEntry[];
  /** Scroll container that owns the article, used for offset calculations. */
  scrollRoot?: HTMLElement | null;
}

/**
 * "On this page" rail with scroll-spy.
 *
 * Generated wiki pages are long and section-heavy; without an outline the
 * reader has no map of the page they are in.
 */
export default function TableOfContents({ entries, scrollRoot }: Props) {
  const t = useT();
  const [activeId, setActiveId] = useState<string>("");

  useEffect(() => {
    if (!entries.length) return;
    const root = scrollRoot ?? null;

    function update() {
      // The active heading is the last one whose top edge is above the
      // reading line (a third of the way down the viewport).
      const line = (root ? root.getBoundingClientRect().top : 0) + window.innerHeight / 3;
      let current = entries[0]?.id ?? "";
      for (const entry of entries) {
        const el = document.getElementById(entry.id);
        if (!el) continue;
        if (el.getBoundingClientRect().top <= line) current = entry.id;
        else break;
      }
      setActiveId(current);
    }

    update();
    const target: HTMLElement | Window = root ?? window;
    target.addEventListener("scroll", update, { passive: true });
    window.addEventListener("resize", update);
    return () => {
      target.removeEventListener("scroll", update);
      window.removeEventListener("resize", update);
    };
  }, [entries, scrollRoot]);

  if (entries.length < 2) return null;

  return (
    <nav className="rs-toc" aria-label={t("页面目录", "Page outline")}>
      <div className="rs-toc-title">{t("本页目录", "On this page")}</div>
      <ul>
        {entries.map((entry) => (
          <li key={entry.id}>
            <a
              href={`#${entry.id}`}
              className={`rs-toc-link ${entry.level > 2 ? "is-sub" : ""} ${
                activeId === entry.id ? "is-active" : ""
              }`}
              onClick={(e) => {
                e.preventDefault();
                const el = document.getElementById(entry.id);
                if (!el) return;
                el.scrollIntoView({ behavior: "smooth", block: "start" });
                // Keep the URL shareable without triggering a jump.
                history.replaceState(null, "", `#${entry.id}`);
                setActiveId(entry.id);
              }}
            >
              {entry.text}
            </a>
          </li>
        ))}
      </ul>
    </nav>
  );
}
