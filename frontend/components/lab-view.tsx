"use client";

import { Activity, ArrowRight, RefreshCw, SlidersHorizontal } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { RankingInspector } from "@/components/ranking-inspector";
import {
  fetchLabSummary,
  formatCostCents,
  formatMs,
  formatPercent,
  setInspectorEnabled,
  useInspectorEnabled,
  useLatestInspect,
  type LabSummary,
} from "@/lib/lab";

const PIPELINE_STAGES = [
  { step: "interpret", label: "Interpret Search" },
  { step: "resolve_place", label: "Geocode place" },
  { step: "resolve_artists", label: "Artist similarity graph" },
  { step: "pool", label: "Concert pool" },
  { step: "cobilling", label: "Live co-billing lookup" },
  { step: "embed_query", label: "Embed Taste query" },
  { step: "semantic", label: "pgvector cosine lookup" },
  { step: "match", label: "Match & shortlist" },
  { step: "rank", label: "Jev grading & reasons" },
];

export function LabView() {
  const [summary, setSummary] = useState<LabSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const latestInspect = useLatestInspect();
  const inspectorEnabled = useInspectorEnabled();

  useEffect(() => {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 8000);
    fetchLabSummary(controller.signal)
      .then((data) => {
        if (!controller.signal.aborted) {
          setSummary(data);
          setError(null);
        }
      })
      .catch((caught: unknown) => {
        if (!controller.signal.aborted) {
          setError(
            caught instanceof Error
              ? caught.message
              : "Engineering Lab telemetry could not be reached.",
          );
        }
      })
      .finally(() => {
        clearTimeout(timer);
        if (!controller.signal.aborted) {
          setLoading(false);
        }
      });
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, []);

  const refresh = useCallback(async () => {
    setRefreshing(true);
    setError(null);
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 8000);
    try {
      const data = await fetchLabSummary(controller.signal);
      setSummary(data);
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "Engineering Lab telemetry could not be reached.",
      );
    } finally {
      clearTimeout(timer);
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  const maxP95 = Math.max(
    1,
    ...(summary?.steps.map((step) => Math.max(step.p95_ms, step.p50_ms)) ?? [1]),
  );

  const hasLiveSamples = (summary?.sample_count ?? 0) > 0;
  const baseline = summary?.baseline ?? null;
  const displayedP50 = hasLiveSamples
    ? summary?.p50_total_ms
    : baseline?.p50_total_ms;
  const displayedP95 = hasLiveSamples
    ? summary?.p95_total_ms
    : baseline?.p95_total_ms;

  return (
    <div className="lab-wrap">
      <section className="lab-hero" aria-labelledby="lab-title">
        <div className="lab-hero-copy">
          <p className="lab-eyebrow">
            <Activity aria-hidden size={14} />
            Public telemetry · Zero PII
          </p>
          <h1 id="lab-title">Engineering Lab</h1>
          <p className="lab-lead">
            Anonymized latency, cost, and cache metrics from Concert Scout&apos;s
            Search pipeline, paired with our evaluation suite and an under-the-hood
            ranking inspector. Search text, Artist names, coordinates, and Spotify
            data never enter telemetry.
          </p>
        </div>
        <div className="lab-hero-actions">
          <Link href="/" className="lab-cta">
            Run a Search
            <ArrowRight aria-hidden size={18} />
          </Link>
          <button
            type="button"
            className="lab-refresh"
            disabled={loading || refreshing}
            onClick={() => void refresh()}
          >
            <RefreshCw
              aria-hidden
              size={16}
              className={refreshing ? "lab-spin" : undefined}
            />
            {refreshing ? "Refreshing…" : "Refresh"}
          </button>
        </div>
      </section>

      {error && (
        <div role="alert" className="lab-alert">
          <p>{error}</p>
          <button type="button" onClick={() => void refresh()}>
            Try again
          </button>
        </div>
      )}

      {loading && !summary ? (
        <section className="lab-section" aria-label="Loading telemetry">
          <div className="lab-kpis">
            {[0, 1, 2, 3].map((slot) => (
              <div key={slot} className="lab-kpi lab-skeleton">
                <span className="lab-kpi-label">Loading…</span>
                <strong className="lab-kpi-value">—</strong>
              </div>
            ))}
          </div>
        </section>
      ) : (
        summary && (
          <>
            <section className="lab-section" aria-labelledby="lab-telemetry-h">
              <div className="lab-section-head">
                <div>
                  <h2 id="lab-telemetry-h">Search Telemetry</h2>
                  <p>
                    {summary.storage_backend === "postgres" ? (
                      <>
                        Persisted in Postgres (aggregating up to the latest{" "}
                        <span className="lab-num">{summary.window_size}</span>{" "}
                        Searches out of{" "}
                        <span className="lab-num">{summary.all_time_count}</span>{" "}
                        all-time). Numeric counts and timings only.
                      </>
                    ) : (
                      <>
                        Bounded Redis ring buffer (latest{" "}
                        <span className="lab-num">{summary.window_size}</span>{" "}
                        Searches,{" "}
                        <span className="lab-num">
                          {summary.retention_days ?? 7}
                        </span>
                        -day TTL). Numeric counts and timings only.
                      </>
                    )}
                  </p>
                </div>
                {summary.latest_bucket && (
                  <p className="lab-bucket">
                    Latest hour bucket:{" "}
                    <span className="lab-num">{summary.latest_bucket}</span>
                  </p>
                )}
              </div>

              {!summary.telemetry_available && (
                <p role="status" className="lab-note">
                  Live telemetry counters are temporarily unavailable. Eval suite
                  coverage and recorded baseline metrics below remain available.
                </p>
              )}

              {summary.telemetry_available && summary.sample_count === 0 && (
                <p role="status" className="lab-note">
                  {baseline
                    ? `No new live Searches persisted yet — showing the ${baseline.sample_count}-Search cold-capture baseline (${baseline.first_date} to ${baseline.last_date}) below until live production runs accumulate.`
                    : "No live Searches recorded yet. Run a Search on the home page to populate real p50/p95 step timings and cache rates."}
                </p>
              )}

              <div className="lab-kpis">
                <article className="lab-kpi">
                  <span className="lab-kpi-label">
                    {hasLiveSamples
                      ? "Search latency"
                      : "Cold baseline latency"}
                  </span>
                  <strong className="lab-kpi-value">
                    {formatMs(displayedP50)}
                  </strong>
                  <span className="lab-kpi-sub">
                    p50 total · p95 {formatMs(displayedP95)}
                    {!hasLiveSamples && baseline
                      ? ` (${baseline.sample_count} cold captures)`
                      : ""}
                  </span>
                </article>
                <article className="lab-kpi">
                  <span className="lab-kpi-label">Avg cost / Search</span>
                  <strong className="lab-kpi-value">
                    {formatCostCents(summary.avg_cost_usd)}
                  </strong>
                  <span className="lab-kpi-sub">
                    {summary.cost_complete_samples > 0
                      ? `${summary.cost_complete_samples} priced samples`
                      : "Awaiting live priced runs"}
                  </span>
                </article>
                <article className="lab-kpi">
                  <span className="lab-kpi-label">Cache hit rate</span>
                  <strong className="lab-kpi-value">
                    {formatPercent(summary.cache_hit_rate)}
                  </strong>
                  <span className="lab-kpi-sub">
                    {summary.cache_hits + summary.cache_misses > 0
                      ? `${summary.cache_hits} hits / ${summary.cache_hits + summary.cache_misses} model checks`
                      : "No cache checks yet"}
                  </span>
                </article>
                <article className="lab-kpi">
                  <span className="lab-kpi-label">Searches observed</span>
                  <strong className="lab-kpi-value">
                    {summary.all_time_count || summary.sample_count}
                    {summary.storage_backend === "redis" && (
                      <span className="lab-kpi-denom">
                        /{summary.window_size}
                      </span>
                    )}
                  </strong>
                  <span className="lab-kpi-sub">
                    {summary.avg_pool_total !== null &&
                    summary.avg_pool_total !== undefined
                      ? `Avg ${summary.avg_pool_total} pool → ${summary.avg_shortlist_total ?? 0} shortlist → ${summary.avg_picks_total ?? 0} picks`
                      : baseline
                        ? `${baseline.sample_count} cold baseline captures`
                        : "Pool → shortlist → Poster"}
                  </span>
                </article>
              </div>

              {hasLiveSamples && baseline && (
                <p className="lab-baseline-strip">
                  <strong>Cold-capture baseline</strong> ({baseline.sample_count}{" "}
                  unwarmed snapshots,{" "}
                  <span className="lab-num">
                    {baseline.first_date} – {baseline.last_date}
                  </span>
                  ): p50{" "}
                  <span className="lab-num">
                    {formatMs(baseline.p50_total_ms)}
                  </span>{" "}
                  · p95{" "}
                  <span className="lab-num">
                    {formatMs(baseline.p95_total_ms)}
                  </span>
                </p>
              )}
            </section>

            <section className="lab-section" aria-labelledby="lab-steps-h">
              <div className="lab-section-head">
                <div>
                  <h2 id="lab-steps-h">Pipeline Step Latency</h2>
                  <p>
                    Median (p50) and tail (p95) milliseconds per stage. Place,
                    Artist graph, co-billing, and Taste embedding run in
                    parallel behind the Concert pool fetch.
                  </p>
                </div>
                <div className="lab-legend" aria-hidden="true">
                  <span className="lab-legend-item">
                    <span className="lab-swatch lab-swatch-p50" /> p50
                  </span>
                  <span className="lab-legend-item">
                    <span className="lab-swatch lab-swatch-p95" /> p95
                  </span>
                </div>
              </div>

              {summary.steps.length > 0 ? (
                <div className="lab-bars">
                  {summary.steps.map((step) => {
                    const p50Pct = Math.min(
                      100,
                      Math.max(2, (step.p50_ms / maxP95) * 100),
                    );
                    const p95Pct = Math.min(
                      100,
                      Math.max(p50Pct, (step.p95_ms / maxP95) * 100),
                    );
                    return (
                      <div key={step.step} className="lab-bar-row">
                        <div className="lab-bar-meta">
                          <span className="lab-bar-name">{step.label}</span>
                          <span className="lab-bar-count">
                            n={step.samples}
                          </span>
                        </div>
                        <div
                          className="lab-bar-track"
                          role="img"
                          aria-label={`${step.label}: p50 ${formatMs(step.p50_ms)}, p95 ${formatMs(step.p95_ms)}`}
                        >
                          <span
                            className="lab-bar-p95"
                            style={{ width: `${p95Pct}%` }}
                          />
                          <span
                            className="lab-bar-p50"
                            style={{ width: `${p50Pct}%` }}
                          />
                        </div>
                        <div className="lab-bar-nums">
                          <span>{formatMs(step.p50_ms)}</span>
                          <span className="lab-bar-nums-p95">
                            {formatMs(step.p95_ms)}
                          </span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <div className="lab-bars lab-bars-empty">
                  {PIPELINE_STAGES.map((stage) => (
                    <div key={stage.step} className="lab-bar-row">
                      <div className="lab-bar-meta">
                        <span className="lab-bar-name">{stage.label}</span>
                        <span className="lab-bar-count">n=0</span>
                      </div>
                      <div className="lab-bar-track" aria-hidden="true" />
                      <div className="lab-bar-nums">
                        <span>—</span>
                        <span className="lab-bar-nums-p95">—</span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </section>

            <section className="lab-section" aria-labelledby="lab-inspector-h">
              <div className="lab-section-head">
                <div>
                  <h2 id="lab-inspector-h">
                    <SlidersHorizontal aria-hidden size={22} />
                    Search Ranking Inspector
                  </h2>
                  <p>
                    Inspect the exact Reading, pool funnel, match signals, and
                    Jev grade levels for your latest Search in this tab—kept out
                    of everyday Posters unless you opt in below.
                  </p>
                </div>
                <button
                  type="button"
                  role="switch"
                  aria-checked={inspectorEnabled}
                  className="lab-switch"
                  onClick={() => setInspectorEnabled(!inspectorEnabled)}
                >
                  <span className="lab-switch-track" aria-hidden="true">
                    <span className="lab-switch-thumb" />
                  </span>
                  <span className="lab-switch-label">
                    Show Inspect button on Posters (this browser)
                  </span>
                </button>
              </div>

              {latestInspect ? (
                <RankingInspector
                  inspect={latestInspect}
                  open
                  embedded
                  onClose={() => {}}
                />
              ) : (
                <div className="lab-inspector-empty">
                  <p>
                    Run any Search on the home page in this tab, then return
                    here to inspect its Reading, match signals, and Jev grades—or
                    flip the switch above to show the inline{" "}
                    <strong>Inspect ranking</strong> toggle directly on Posters.
                  </p>
                  <Link href="/" className="lab-cta">
                    Run a Search
                    <ArrowRight aria-hidden size={18} />
                  </Link>
                </div>
              )}
            </section>

            <section className="lab-section" aria-labelledby="lab-evals-h">
              <div className="lab-section-head">
                <div>
                  <h2 id="lab-evals-h">
                    <SlidersHorizontal aria-hidden size={22} />
                    Retrieval Eval Suite
                  </h2>
                  <p>
                    Human-judged Searches in{" "}
                    <code>{summary.eval_benchmarks.source_file}</code> covering
                    seed Artists, sparse electronic scenes, plain descriptions,
                    and edge cases.
                  </p>
                </div>
              </div>

              <div className="lab-suite-stats">
                <div className="lab-stat-pill">
                  <strong>{summary.eval_benchmarks.total_cases}</strong>
                  <span>eval Searches</span>
                </div>
                <div className="lab-stat-pill">
                  <strong>{summary.eval_benchmarks.judged_cases}</strong>
                  <span>human-judged</span>
                </div>
                <div className="lab-stat-pill">
                  <strong>{summary.eval_benchmarks.snapshot_cases}</strong>
                  <span>frozen snapshots</span>
                </div>
                <div className="lab-stat-pill">
                  <strong>{summary.eval_benchmarks.must_labels}</strong>
                  <span>must picks</span>
                </div>
                <div className="lab-stat-pill">
                  <strong>{summary.eval_benchmarks.good_labels}</strong>
                  <span>good picks</span>
                </div>
                <div className="lab-stat-pill">
                  <strong>{summary.eval_benchmarks.bad_labels}</strong>
                  <span>bad rejections</span>
                </div>
              </div>

              <div className="lab-cat-row" aria-label="Eval suite categories">
                {Object.entries(summary.eval_benchmarks.categories).map(
                  ([category, count]) => (
                    <span key={category} className="lab-cat-chip">
                      {category} · <strong>{count}</strong>
                    </span>
                  ),
                )}
              </div>

              <div className="lab-tiers">
                {summary.eval_benchmarks.tiers.map((tier) => (
                  <article key={tier.id} className="lab-tier">
                    <div className="lab-tier-top">
                      <h3>{tier.name}</h3>
                      <span
                        className="lab-tier-status"
                        data-status={tier.status}
                      >
                        {tier.status_label}
                      </span>
                    </div>
                    <p className="lab-tier-summary">{tier.summary}</p>
                    <dl className="lab-tier-meta">
                      <div>
                        <dt>Signals</dt>
                        <dd className="lab-tier-signals">
                          {tier.signals.map((sig) => (
                            <code key={sig}>{sig}</code>
                          ))}
                        </dd>
                      </div>
                      <div>
                        <dt>Ranking stage</dt>
                        <dd>{tier.ranker}</dd>
                      </div>
                    </dl>
                    <p className="lab-tier-notes">{tier.notes}</p>
                  </article>
                ))}
              </div>

              <div className="lab-targets">
                <h3>Quality targets (Spec 06)</h3>
                <ul>
                  {Object.entries(summary.eval_benchmarks.targets).map(
                    ([key, target]) => (
                      <li key={key}>{target}</li>
                    ),
                  )}
                </ul>
                <p className="lab-measurement-note">
                  {summary.eval_benchmarks.measurement_note}
                </p>
              </div>
            </section>
          </>
        )
      )}
    </div>
  );
}
