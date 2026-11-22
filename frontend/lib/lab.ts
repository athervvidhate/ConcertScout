import { API_URL, type Grade, type Reading } from "@/lib/search";

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
  source?: "ticketmaster" | "jambase";
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

export type ArchitectureGuarantee = {
  id: string;
  adr: string;
  title: string;
  summary: string;
  enforced_by: string;
};

export type LabSummary = {
  sample_count: number;
  window_size: number;
  retention_days: number;
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
  eval_benchmarks: EvalSuiteSummary;
  guarantees: ArchitectureGuarantee[];
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
  if (ms === null || ms === undefined || !Number.isFinite(ms)) return "—";
  if (ms < 0) return "0 ms";
  if (ms > 0 && ms < 1) return "< 1 ms";
  if (ms < 1000) return `${Math.round(ms)} ms`;
  return `${(ms / 1000).toFixed(2)} s`;
}

export function formatCostCents(usd?: number | null): string {
  if (usd === null || usd === undefined || !Number.isFinite(usd)) return "—";
  if (usd <= 0) return "0.00¢";
  const cents = usd * 100;
  if (cents < 0.01) return "< 0.01¢";
  if (cents < 100) return `${cents.toFixed(2)}¢`;
  return `$${usd.toFixed(2)}`;
}

export function formatPercent(rate?: number | null): string {
  if (rate === null || rate === undefined || !Number.isFinite(rate)) return "—";
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
