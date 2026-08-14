import { useEffect, useMemo, useState } from "react";
import { useT } from "../lib/i18n";
import {
  SCAN_PHASES,
  elapsedSeconds,
  formatElapsed,
  parseScanProgress,
  type ScanPhase,
} from "../lib/scanProgress";

const PHASE_LABEL: Record<ScanPhase, [string, string]> = {
  scan: ["扫描", "Scan"],
  outline: ["大纲", "Outline"],
  write: ["撰写", "Write"],
  cite: ["核验", "Cite"],
  polish: ["润色", "Polish"],
};

const RUNNING = new Set([
  "queued",
  "pending",
  "scanning",
  "generating_concepts",
  "generating_wiki",
  "llm_enriching",
]);

export default function ScanHeaderProgress({
  commitSha,
  status,
  progressMessage,
  createdAt,
  idleLabel,
}: {
  commitSha?: string | null;
  status: string | null;
  progressMessage?: string | null;
  createdAt?: string | null;
  idleLabel: string;
}) {
  const t = useT();
  const analyzing = Boolean(status && RUNNING.has(status));
  const parsed = useMemo(
    () => parseScanProgress(status, progressMessage),
    [status, progressMessage],
  );
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    if (!analyzing) return;
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, [analyzing]);

  const hash = commitSha ? commitSha.slice(0, analyzing ? 7 : 10) : "";
  const elapsed = analyzing ? elapsedSeconds(createdAt, now) : null;

  if (!analyzing) {
    return (
      <div className="text-[11px] text-[var(--rs-muted)] truncate rs-tabular">
        {hash ? `${hash} · ` : ""}
        {idleLabel}
      </div>
    );
  }

  return (
    <>
      <div className="rs-scan-meta">
        <div className="rs-scan-phases">
          {hash ? <span className="rs-scan-hash">{hash} · </span> : null}
          {SCAN_PHASES.map((phase, i) => {
            const active = phase === parsed.phase;
            const frac =
              active && parsed.current != null && parsed.total != null
                ? ` ${parsed.current}/${parsed.total}`
                : "";
            return (
              <span key={phase}>
                {i > 0 ? <span className="rs-scan-arrow">→</span> : null}
                <span
                  className={`rs-scan-phase${active ? " is-now" : ""}${
                    active && !frac ? " is-pulse" : ""
                  }`}
                >
                  {t(...PHASE_LABEL[phase])}
                  {frac}
                </span>
              </span>
            );
          })}
        </div>
        {elapsed != null ? <span className="rs-scan-elapsed">{formatElapsed(elapsed)}</span> : null}
      </div>
      {status !== "ready" ? (
        <div
          className={`rs-scan-bar${parsed.determinate ? "" : " is-indeterminate"}`}
          role="progressbar"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={parsed.determinate && parsed.percent != null ? parsed.percent : undefined}
          aria-label={
            parsed.phase
              ? `${t(...PHASE_LABEL[parsed.phase])}${
                  parsed.current != null && parsed.total != null
                    ? ` ${parsed.current}/${parsed.total}`
                    : ""
                }`
              : t("扫描中", "Scanning")
          }
        >
          <div
            className="rs-scan-bar-fill"
            style={
              parsed.determinate && parsed.percent != null
                ? { width: `${parsed.percent}%` }
                : undefined
            }
          />
        </div>
      ) : null}
    </>
  );
}
