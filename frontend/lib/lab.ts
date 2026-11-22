import { useSyncExternalStore } from "react";

import { readSearch } from "@/lib/search-session";
import { API_URL, type Grade, type Reading } from "@/lib/search";

const INSPECTOR_PREF_KEY = "concert-scout-inspector-enabled";
const inspectorListeners = new Set<() => void>();

export type MatchSignal =
  | "seed"
  | "one_hop"
  | "two_hops"
  | "co_billed"
  | "semantic"
  | "tags"
  | "genre";

export type InspectPick = {
  concert_id: string;
  artist: string;
  concert_name: string;
  signal?: MatchSignal | null;
  via?: string | null;
  styles?: string[];
  match_score?: number | null;
  support?: number | null;
  grade?: Grade | null;
  jev_level?: number | null;
  lineup_match_count?: number;
  source?: "ticketmaster" | "jambase" | "venue_calendar" | "eventbrite";
};

export type SearchInspect = {
  reading: Reading;
  pool_total: number;
  shortlist_total: number;
  steps_ms?: Record<string, number>;
  picks: InspectPick[];
};

export type StepLatency = {
  step: string;
  label: string;
  samples: number;
  p50_ms: number;
  p95_ms: number;
};

export type EvalTier = {
  id: "tags_only" | "cobilling" | "hybrid_pgvector_jev";
  name: string;
  signals: string[];
  ranker: string;
  status: "baseline" | "shipped_offline_ready" | "pending_live_eval";
  status_label: string;
  summary: string;
  notes: string;
};

export type EvalSuiteSummary = {
  source_file: string;
  total_cases: number;
  judged_cases: number;
  unjudged_cases: number;
  snapshot_cases: number;
  must_labels: number;
  good_labels: number;
  bad_labels: number;
  categories: Record<string, number>;
  targets: Record<string, string>;
  tiers: EvalTier[];
  measurement_note: string;
};

export type TelemetryBaseline = {
  sample_count: number;
  p50_total_ms: number;
  p95_total_ms: number;
  first_date: string;
  last_date: string;
  note: string;
};

export type LabSummary = {
  sample_count: number;
  all_time_count: number;
  window_size: number;
  retention_days?: number | null;
  storage_backend: "postgres" | "redis";
  p50_total_ms?: number | null;
  p95_total_ms?: number | null;
  avg_cost_usd?: number | null;
  cost_complete_samples: number;
  cache_hits: number;
  cache_misses: number;
  cache_hit_rate?: number | null;
  avg_pool_total?: number | null;
  avg_shortlist_total?: number | null;
  avg_picks_total?: number | null;
  latest_bucket?: string | null;
  steps: StepLatency[];
  baseline?: TelemetryBaseline | null;
  eval_benchmarks: EvalSuiteSummary;
  telemetry_available: boolean;
};

const SIGNAL_LABELS: Record<MatchSignal, string> = {
  seed: "Seed",
  one_hop: "1-hop",
  two_hops: "2-hop",
  co_billed: "Co-billed",
  semantic: "Semantic",
  tags: "Tags",
  genre: "Genre",
};

const JEV_LABELS: Record<number, string> = {
  0: "0 · Unrelated",
  1: "1 · Stretch",
  2: "2 · Fair fit",
  3: "3 · Strong fit",
};

export const STEP_ORDER = [
  "interpret",
  "refine",
  "resolve_place",
  "resolve_artists",
  "pool",
  "cobilling",
  "embed_query",
  "semantic",
  "match",
  "rank",
  "elsewhere",
] as const;

const STEP_LABELS: Record<string, string> = {
  interpret: "Interpret",
  refine: "Refine",
  resolve_place: "Geocode",
  resolve_artists: "Artist graph",
  pool: "Concert pool",
  cobilling: "Co-billing",
  embed_query: "Embed Taste",
  semantic: "pgvector",
  match: "Match",
  rank: "Jev & reasons",
  elsewhere: "Elsewhere",
};

export function formatMs(ms?: number | null): string {
  if (ms === null || ms === undefined || !Number.isFinite(ms)) return "-";
  if (ms < 0) return "0 ms";
  if (ms > 0 && ms < 1) return "< 1 ms";
  if (ms < 1000) return `${Math.round(ms)} ms`;
  return `${(ms / 1000).toFixed(2)} s`;
}

export function formatCostCents(usd?: number | null): string {
  if (usd === null || usd === undefined || !Number.isFinite(usd)) return "-";
  if (usd <= 0) return "0.00¢";
  const cents = usd * 100;
  if (cents < 0.01) return "< 0.01¢";
  if (cents < 100) return `${cents.toFixed(2)}¢`;
  return `$${usd.toFixed(2)}`;
}

export function formatPercent(rate?: number | null): string {
  if (rate === null || rate === undefined || !Number.isFinite(rate)) return "-";
  return `${Math.round(Math.max(0, Math.min(1, rate)) * 100)}%`;
}

export function signalLabel(signal?: MatchSignal | null): string {
  if (!signal) return "Notable";
  return SIGNAL_LABELS[signal] ?? signal;
}

export function jevLevelLabel(level?: number | null): string {
  if (level === null || level === undefined) return "Ungraded";
  return JEV_LABELS[level] ?? `Level ${level}`;
}

export function stepLabel(step: string): string {
  return STEP_LABELS[step] ?? step;
}

export function orderedStepTimings(
  stepsMs?: Record<string, number> | null,
): Array<{ step: string; label: string; ms: number }> {
  if (!stepsMs) return [];
  const rank = new Map<string, number>(
    STEP_ORDER.map((step, index) => [step, index]),
  );
  return Object.entries(stepsMs)
    .filter(([, ms]) => Number.isFinite(ms))
    .sort(([a], [b]) => {
      const ra = rank.get(a) ?? 999;
      const rb = rank.get(b) ?? 999;
      return ra === rb ? a.localeCompare(b) : ra - rb;
    })
    .map(([step, ms]) => ({ step, label: stepLabel(step), ms }));
}

export function readInspectorEnabled(): boolean {
  if (typeof window === "undefined") return false;
  try {
    if (new URLSearchParams(window.location.search).get("inspect") === "1") {
      return true;
    }
    return localStorage.getItem(INSPECTOR_PREF_KEY) === "1";
  } catch {
    return false;
  }
}

export function setInspectorEnabled(enabled: boolean): void {
  try {
    if (enabled) localStorage.setItem(INSPECTOR_PREF_KEY, "1");
    else localStorage.removeItem(INSPECTOR_PREF_KEY);
  } catch {
    /* Storage unavailable. */
  }
  inspectorListeners.forEach((listener) => listener());
}

function subscribeInspectorPref(listener: () => void): () => void {
  inspectorListeners.add(listener);
  const onStorage = (event: StorageEvent) => {
    if (event.key === null || event.key === INSPECTOR_PREF_KEY) listener();
  };
  if (typeof window !== "undefined") {
    window.addEventListener("storage", onStorage);
  }
  return () => {
    inspectorListeners.delete(listener);
    if (typeof window !== "undefined") {
      window.removeEventListener("storage", onStorage);
    }
  };
}

/** Whether this browser opted into showing the inline Ranking Inspector toggle on Posters. */
export function useInspectorEnabled(): boolean {
  return useSyncExternalStore(
    subscribeInspectorPref,
    readInspectorEnabled,
    () => false,
  );
}

let cachedInspectRaw: string | null = null;
let cachedInspectValue: SearchInspect | null = null;

/** Read the latest Search's inspect breakdown kept in this browser tab, if any. */
export function readLatestInspect(): SearchInspect | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = sessionStorage.getItem("concert-scout-search");
    if (raw === cachedInspectRaw) return cachedInspectValue;
    cachedInspectRaw = raw;
    const kept = readSearch<{ inspect?: SearchInspect | null }>();
    cachedInspectValue = kept?.inspect ?? null;
    return cachedInspectValue;
  } catch {
    return null;
  }
}

function subscribeLatestInspect(listener: () => void): () => void {
  if (typeof window === "undefined") return () => {};
  window.addEventListener("focus", listener);
  return () => window.removeEventListener("focus", listener);
}

export function useLatestInspect(): SearchInspect | null {
  return useSyncExternalStore(
    subscribeLatestInspect,
    readLatestInspect,
    () => null,
  );
}

export async function fetchLabSummary(
  signal?: AbortSignal,
): Promise<LabSummary> {
  const response = await fetch(`${API_URL}/lab`, {
    cache: "no-store",
    signal,
  });
  if (!response.ok) {
    throw new Error(`Engineering Lab API answered ${response.status}`);
  }
  return (await response.json()) as LabSummary;
}
