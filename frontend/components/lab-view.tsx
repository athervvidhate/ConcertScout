"use client";

import { Activity, ArrowRight, RefreshCw, ShieldCheck, SlidersHorizontal } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import {
  fetchLabSummary,
  formatCostCents,
  formatMs,
  formatPercent,
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
            Live anonymized latency, cost, and cache counters from Concert
            Scout&apos;s rolling{" "}
            <span className="lab-num">
              {summary?.window_size ?? 200}-Search
            </span>{" "}
            window, paired with our evaluation suite and architectural
            guarantees. Search text, Artist names, coordinates, and Spotify data
            never enter telemetry.
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
                  <h2 id="lab-telemetry-h">Rolling Search Telemetry</h2>
                  <p>
                    Bounded Redis ring buffer (latest{" "}
                    <span className="lab-num">{summary.window_size}</span>{" "}
                    Searches,{" "}
                    <span className="lab-num">{summary.retention_days}</span>
                    -day TTL). Numeric counts and timings only.
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
                  Live Redis counters are temporarily unavailable. Eval suite
                  coverage and architectural invariants below remain live.
                </p>
              )}

              {summary.telemetry_available && summary.sample_count === 0 && (
                <p role="status" className="lab-note">
                  No live Searches recorded in the current{" "}
                  {summary.retention_days}-day window yet. Run a Search on the
                  home page to populate real p50/p95 step timings and cache
                  rates.
                </p>
              )}

              <div className="lab-kpis">
                <article className="lab-kpi">
                  <span className="lab-kpi-label">Search latency</span>
                  <strong className="lab-kpi-value">
                    {formatMs(summary.p50_total_ms)}
                  </strong>
                  <span className="lab-kpi-sub">
                    p50 total · p95 {formatMs(summary.p95_total_ms)}
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
                      : "Awaiting priced runs"}
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
                    {summary.sample_count}
                    <span className="lab-kpi-denom">
                      /{summary.window_size}
                    </span>
                  </strong>
                  <span className="lab-kpi-sub">
                    {summary.avg_pool_total !== null &&
                    summary.avg_pool_total !== undefined
                      ? `Avg ${summary.avg_pool_total} pool → ${summary.avg_shortlist_total ?? 0} shortlist → ${summary.avg_picks_total ?? 0} picks`
                      : "Pool → shortlist → Poster"}
                  </span>
                </article>
              </div>
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

            <section className="lab-section" aria-labelledby="lab-invariants-h">
              <div className="lab-section-head">
                <div>
                  <h2 id="lab-invariants-h">
                    <ShieldCheck aria-hidden size={22} />
                    Architectural Invariants
                  </h2>
                  <p>
                    Promises enforced in application code and verified by
                    contract tests on every commit.
                  </p>
                </div>
              </div>
              <div className="lab-guarantees">
                {summary.guarantees.map((item) => (
                  <article key={item.id} className="lab-guarantee">
                    <span className="lab-guarantee-adr">{item.adr}</span>
                    <h3>{item.title}</h3>
                    <p>{item.summary}</p>
                    <p className="lab-guarantee-code">{item.enforced_by}</p>
                  </article>
                ))}
              </div>
            </section>
          </>
        )
      )}
    </div>
  );
}
