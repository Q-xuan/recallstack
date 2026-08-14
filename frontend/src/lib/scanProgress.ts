/** Map analyze `status` + `progress_message` to a compact header strip.
 *
 * Keep in sync with `src/recallstack/learning/scan_progress.py`.
 */

export type ScanPhase = "scan" | "outline" | "write" | "cite" | "polish";

export const SCAN_PHASES: readonly ScanPhase[] = ["scan", "outline", "write", "cite", "polish"];

export type ScanProgress = {
  phase: ScanPhase | null;
  current: number | null;
  total: number | null;
  determinate: boolean;
  percent: number | null;
};

const FRACTION = /(\d+)\s*\/\s*(\d+)/;

/** Write 7/16 lands near 55% — the in-flight example Jake asked for. */
const PHASE_START: Record<ScanPhase, number> = {
  scan: 0,
  outline: 12,
  write: 32,
  cite: 84,
  polish: 92,
};

const PHASE_SPAN: Record<ScanPhase, number> = {
  scan: 12,
  outline: 20,
  write: 52,
  cite: 8,
  polish: 8,
};

function phaseFromMessage(message: string): ScanPhase | null {
  if (/核验|verifying citations|citation/i.test(message)) return "cite";
  if (/大纲|outlining/i.test(message)) return "outline";
  if (/wrote topic|wrote module|已撰写|撰写专题|writing\s*\d+/i.test(message)) return "write";
  if (/润色|enrich/i.test(message)) return "polish";
  if (/analyzed module|已分析|preparing file|analyzing\s*\d+|扫描|正在分析|ingesting/i.test(message)) {
    return "scan";
  }
  if (/概览|overview|规划/i.test(message)) return "outline";
  if (/架构|architecture|阅读指南|reading guide/i.test(message)) return "write";
  return null;
}

function phaseFromStatus(status: string): ScanPhase | null {
  switch (status) {
    case "queued":
    case "pending":
    case "scanning":
      return "scan";
    case "generating_concepts":
      return "outline";
    case "generating_wiki":
      return "write";
    case "llm_enriching":
      return "polish";
    default:
      return null;
  }
}

export function parseScanProgress(
  status: string | null | undefined,
  message: string | null | undefined,
): ScanProgress {
  const st = (status || "").trim();
  const msg = (message || "").trim();

  if (st === "ready") {
    return { phase: null, current: null, total: null, determinate: false, percent: null };
  }

  let current: number | null = null;
  let total: number | null = null;
  const frac = msg.match(FRACTION);
  if (frac) {
    current = Number.parseInt(frac[1], 10);
    total = Number.parseInt(frac[2], 10);
    if (!Number.isFinite(current) || !Number.isFinite(total) || total <= 0) {
      current = null;
      total = null;
    }
  }

  const phase = (msg ? phaseFromMessage(msg) : null) || phaseFromStatus(st);
  const queuedUnknown = (st === "queued" || st === "pending" || !st) && !msg;

  if (!phase || queuedUnknown) {
    return {
      phase: phase || (queuedUnknown ? "scan" : null),
      current,
      total,
      determinate: false,
      percent: null,
    };
  }

  const start = PHASE_START[phase];
  const span = PHASE_SPAN[phase];
  const ratio =
    current != null && total != null ? Math.min(1, Math.max(0, current / total)) : 0.4;
  return {
    phase,
    current,
    total,
    determinate: true,
    percent: Math.round(start + span * ratio),
  };
}

export function elapsedSeconds(iso: string | null | undefined, nowMs = Date.now()): number | null {
  if (!iso) return null;
  const then = Date.parse(iso);
  if (Number.isNaN(then)) return null;
  return Math.max(0, Math.floor((nowMs - then) / 1000));
}

export function formatElapsed(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds));
  const m = Math.floor(s / 60);
  const r = s % 60;
  if (m >= 60) {
    const h = Math.floor(m / 60);
    return `${h}:${String(m % 60).padStart(2, "0")}:${String(r).padStart(2, "0")}`;
  }
  return `${m}:${String(r).padStart(2, "0")}`;
}
