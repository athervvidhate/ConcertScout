"use client";

import { ArrowUpRight, SlidersHorizontal, X } from "lucide-react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import Link from "next/link";
import { useEffect } from "react";

import { EXPO_OUT_CURVE } from "@/lib/choreography";
import { gradeLabel } from "@/lib/grade";
import {
  formatMs,
  jevLevelLabel,
  orderedStepTimings,
  type SearchInspect,
  signalLabel,
} from "@/lib/lab";

type Props = {
  inspect: SearchInspect;
  open: boolean;
  onClose: () => void;
  /** When embedded inside `/lab`, renders inline without a close button or self-link. */
  embedded?: boolean;
};

function sourceLabel(source?: SearchInspect["picks"][number]["source"]): string {
  switch (source) {
    case "jambase":
      return "JamBase";
    case "venue_calendar":
      return "Underground room";
    case "eventbrite":
      return "Curated promoter";
    default:
      return "Ticketmaster";
  }
}

export function RankingInspector({
  inspect,
  open,
  onClose,
  embedded = false,
}: Props) {
  const reduced = useReducedMotion();
  const timings = orderedStepTimings(inspect.steps_ms);
  const maxSupport = Math.max(
    1,
    ...inspect.picks.map((pick) => pick.support ?? pick.match_score ?? 0),
  );

  useEffect(() => {
    if (!open || embedded) return;
    function onKeyDown(event: KeyboardEvent) {
      if (event.key !== "Escape") return;
      // Leave Escape to a Ticket or Artist dialog if one is open above the Poster.
      if (document.querySelector('[role="dialog"]')) return;
      event.preventDefault();
      onClose();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open, embedded, onClose]);

  const readingParts: Array<{ label: string; value: string }> = [];
  if (inspect.reading.artists.length > 0) {
    readingParts.push({
      label: "Artists",
      value: inspect.reading.artists.join(", "),
    });
  }
  const sounds = [
    ...(inspect.reading.descriptors ?? []),
    ...(inspect.reading.tags ?? []),
  ];
  if (sounds.length > 0) {
    readingParts.push({ label: "Sound", value: sounds.join(", ") });
  }
  if (inspect.reading.genres.length > 0) {
    readingParts.push({
      label: "Genres",
      value: inspect.reading.genres.join(", "),
    });
  }
  if (inspect.reading.region || inspect.reading.place) {
    const placeText = inspect.reading.region
      ? `${inspect.reading.region} (${inspect.reading.radius_miles ?? 50} mi)`
      : (inspect.reading.place ?? "");
    readingParts.push({ label: "Place", value: placeText });
  }
  if (inspect.reading.start || inspect.reading.end) {
    readingParts.push({
      label: "Dates",
      value: `${inspect.reading.start ?? "Any"} → ${inspect.reading.end ?? "Any"}`,
    });
  }
  if (inspect.reading.max_price) {
    readingParts.push({
      label: "Max price",
      value: `$${inspect.reading.max_price}`,
    });
  }
  if (inspect.reading.weekends_only) {
    readingParts.push({ label: "Filter", value: "Weekends only" });
  }

  return (
    <AnimatePresence initial={false}>
      {open && (
        <motion.section
          id="ranking-inspector"
          className="inspector-panel"
          aria-label="Ranking inspector"
          initial={{
            opacity: reduced ? 1 : 0,
            y: reduced ? 0 : -10,
          }}
          animate={{ opacity: 1, y: 0 }}
          exit={{
            opacity: reduced ? 1 : 0,
            y: reduced ? 0 : -8,
          }}
          transition={{ duration: reduced ? 0 : 0.24, ease: EXPO_OUT_CURVE }}
        >
          <div className="inspector-head">
            <div className="inspector-title">
              <span className="inspector-badge">
                <SlidersHorizontal aria-hidden size={14} />
                Under the hood
              </span>
              <h3>Ranking Inspector</h3>
            </div>
            {!embedded && (
              <div className="inspector-head-actions">
                <Link href="/lab" className="inspector-lab-link">
                  Engineering Lab
                  <ArrowUpRight aria-hidden size={15} />
                </Link>
                <button
                  type="button"
                  className="inspector-close"
                  aria-label="Close ranking inspector"
                  onClick={onClose}
                >
                  <X aria-hidden size={18} />
                </button>
              </div>
            )}
          </div>

          <div className="inspector-summary">
            <div className="inspector-funnel" aria-label="Search funnel">
              <div className="inspector-metric">
                <span className="inspector-metric-label">Concert pool</span>
                <strong>{inspect.pool_total}</strong>
              </div>
              <span className="inspector-arrow" aria-hidden="true">
                →
              </span>
              <div className="inspector-metric">
                <span className="inspector-metric-label">Shortlist</span>
                <strong>{inspect.shortlist_total}</strong>
              </div>
              <span className="inspector-arrow" aria-hidden="true">
                →
              </span>
              <div className="inspector-metric">
                <span className="inspector-metric-label">Poster picks</span>
                <strong>{inspect.picks.length}</strong>
              </div>
            </div>

            {readingParts.length > 0 && (
              <dl className="inspector-reading">
                {readingParts.map((part) => (
                  <div key={part.label}>
                    <dt>{part.label}</dt>
                    <dd>{part.value}</dd>
                  </div>
                ))}
              </dl>
            )}
          </div>

          {timings.length > 0 && (
            <div className="inspector-timings" aria-label="Step timings">
              {timings.map((item) => (
                <span key={item.step} className="inspector-time-chip">
                  <span>{item.label}</span>
                  <strong>{formatMs(item.ms)}</strong>
                </span>
              ))}
            </div>
          )}

          {inspect.picks.length > 0 ? (
            <div className="inspector-picks">
              {inspect.picks.map((pick, index) => {
                const support = pick.support ?? pick.match_score ?? 0;
                const widthPct = Math.min(
                  100,
                  Math.max(support > 0 ? 6 : 0, (support / maxSupport) * 100),
                );
                const gradeText = gradeLabel(pick.grade) ?? "Ungraded";
                return (
                  <div key={pick.concert_id} className="inspector-row">
                    <div className="inspector-pick-main">
                      <span className="inspector-rank">#{index + 1}</span>
                      <div className="inspector-pick-copy">
                        <div className="inspector-pick-names">
                          <strong>{pick.artist}</strong>
                          {pick.concert_name &&
                            pick.concert_name.toLowerCase() !==
                              pick.artist.toLowerCase() && (
                              <span className="inspector-concert-name">
                                {pick.concert_name}
                              </span>
                            )}
                        </div>
                        <div className="inspector-pick-tags">
                          <span
                            className="inspector-signal"
                            data-signal={pick.signal ?? "notable"}
                          >
                            {signalLabel(pick.signal)}
                          </span>
                          {pick.via && pick.signal !== "seed" && (
                            <span className="inspector-via">
                              via {pick.via}
                            </span>
                          )}
                          {(pick.styles ?? []).slice(0, 3).map((style) => (
                            <span key={style} className="inspector-style">
                              {style}
                            </span>
                          ))}
                          {pick.lineup_match_count ? (
                            <span className="inspector-style">
                              {pick.lineup_match_count} lineup{" "}
                              {pick.lineup_match_count === 1
                                ? "match"
                                : "matches"}
                            </span>
                          ) : null}
                          <span className="inspector-source">
                            {sourceLabel(pick.source)}
                          </span>
                        </div>
                      </div>
                    </div>

                    <div className="inspector-pick-scores">
                      <div className="inspector-support">
                        <div className="inspector-support-head">
                          <span>Support</span>
                          <strong>
                            {pick.support !== null && pick.support !== undefined
                              ? pick.support.toFixed(2)
                              : "-"}
                          </strong>
                        </div>
                        <div
                          className="inspector-support-bar"
                          aria-hidden="true"
                        >
                          <span style={{ width: `${widthPct}%` }} />
                        </div>
                      </div>
                      <div className="inspector-grade">
                        <span
                          className="inspector-grade-pill"
                          data-grade={pick.grade ?? "none"}
                        >
                          {gradeText}
                        </span>
                        <span className="inspector-jev">
                          Jev: {jevLevelLabel(pick.jev_level)}
                        </span>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          ) : (
            <p className="inspector-empty">
              No Concerts cleared the ranking threshold for this Reading.
            </p>
          )}
        </motion.section>
      )}
    </AnimatePresence>
  );
}
