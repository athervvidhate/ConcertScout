"use client";

import { Dialog } from "@base-ui/react/dialog";
import { LayoutGrid, List, X, Check, Bookmark, AudioLines } from "lucide-react";
import {
  AnimatePresence,
  LayoutGroup,
  motion,
  useReducedMotion,
} from "motion/react";
import Image from "next/image";
import { useId, useState } from "react";

import { nameOf, Ticket } from "@/components/ticket";
import { dismissArtistHint, useArtistHint } from "@/lib/artist-hint";
import { formatDate, formatConcertTime } from "@/lib/format";
import { saveConcert, useDecisions } from "@/lib/saved";
import type { Candidates, Recommendation } from "@/lib/search";
import { showTitle } from "@/lib/show-title";

type Props = {
  candidates: Candidates | null;
  recommendations: Recommendation[];
  hasPoster: boolean;
  searching: boolean;
  status: string | null;
  onWiderDates?: () => void;
  onAnywhere?: () => void;
  onChange?: () => void;
};

export function Poster({
  candidates,
  recommendations,
  hasPoster,
  searching,
  status,
  onWiderDates,
  onAnywhere,
  onChange,
}: Props) {
  const group = useId();
  const reduced = useReducedMotion();
  const [view, setView] = useState<"grid" | "list">("grid");
  const [selected, setSelected] = useState(0);
  const [open, setOpen] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const [notice, setNotice] = useState("");
  const decisions = useDecisions();
  const hint = useArtistHint();
  const current = recommendations[selected];
  const picked = new Set(
    recommendations.flatMap((r) => r.concert.artists.map((a) => a.name)),
  );
  const passed = candidates?.names.filter((n) => !picked.has(n)) ?? [];
  const duration = reduced ? 0 : 0.45;

  function save(recommendation = current) {
    if (!recommendation) return;
    try {
      const saving = saveConcert(recommendation);
      dismissArtistHint();
      setNotice(
        `${nameOf(recommendation)} saved ${saving.where === "device" ? "on this device" : "to your account"}.`,
      );
      if (saving.where === "account")
        saving.done.catch(() =>
          setNotice(
            `${nameOf(recommendation)} could not be saved to your account. Try again.`,
          ),
        );
    } catch {
      setNotice(
        "This browser could not keep that choice. Allow local storage and try again.",
      );
    }
  }

  function photo(r: Recommendation, inDialog = false) {
    if (!r.concert.image) return null;
    return (
      <motion.div
        className={inDialog ? "dialog-photo" : "card-photo"}
        layoutId={`photo-${r.concert.id}`}
        transition={{ duration, ease: [0.2, 0.8, 0.2, 1] }}
      >
        <Image
          src={r.concert.image}
          alt=""
          fill
          unoptimized
          sizes="(max-width:640px) 100vw, 60vw"
          draggable={false}
        />
      </motion.div>
    );
  }

  return (
    <LayoutGroup id={group}>
      <section className="fluid-poster" aria-label="Poster">
        {!hasPoster && searching && (
          <div className="run-card">
            <div className="run-head">
              <AudioLines aria-hidden />
              <p role="status">{status ?? "Reading your Search"}</p>
            </div>
            {candidates && (
              <>
                <p className="cloud-head">
                  Choosing from {candidates.total} Concerts
                </p>
                <div className="cloud" aria-label="Candidate Artists">
                  {candidates.names.slice(0, 40).map((name) => (
                    <motion.span
                      className="name"
                      layoutId={`name-${name}`}
                      key={name}
                    >
                      {name}
                    </motion.span>
                  ))}
                </div>
              </>
            )}
          </div>
        )}
        {hasPoster && (
          <>
            {recommendations.length > 0 ? (
              <>
                <header className="poster-head">
                  <div>
                    <h2>
                      {recommendations.length}{" "}
                      {recommendations.length === 1 ? "Concert" : "Concerts"}{" "}
                      worth going out for
                    </h2>
                    {candidates && (
                      <p>
                        {recommendations.length} picks from {candidates.total}{" "}
                        Concerts considered
                      </p>
                    )}
                  </div>
                  <div className="views" role="group" aria-label="Poster view">
                    <button
                      aria-label="Grid view"
                      title="Grid view"
                      aria-pressed={view === "grid"}
                      onClick={() => setView("grid")}
                    >
                      <LayoutGrid aria-hidden />
                    </button>
                    <button
                      aria-label="List view"
                      title="List view"
                      aria-pressed={view === "list"}
                      onClick={() => setView("list")}
                    >
                      <List aria-hidden />
                    </button>
                  </div>
                </header>
                <Dialog.Root open={open} onOpenChange={setOpen}>
                  <AnimatePresence mode="wait" initial={false}>
                    <motion.div
                      key={view}
                      className={`concerts-${view}`}
                      data-count={recommendations.length}
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      exit={{ opacity: 0 }}
                      transition={{ duration: reduced ? 0 : 0.12 }}
                    >
                      {recommendations.map((r, rank) => {
                        const { concert, reason } = r;
                        const name = nameOf(r);
                        const date = concert.date
                          ? formatDate(concert.date)
                          : null;
                        const meta = [
                          concert.venue,
                          concert.city,
                          formatConcertTime(concert),
                        ]
                          .filter(Boolean)
                          .join(" · ");
                        if (recommendations.length === 1 && view === "grid")
                          return (
                            <article
                              className="solo concert-card"
                              key={concert.id}
                            >
                              <div className="solo-photo">{photo(r)}</div>
                              <div className="solo-body">
                                <Ticket
                                  recommendation={r}
                                  rank={rank}
                                  artistHint={hint}
                                  onArtistOpen={dismissArtistHint}
                                  hidePhoto
                                />
                                <div className="solo-actions">
                                  <button
                                    className="primary"
                                    onClick={() => save(r)}
                                    disabled={decisions[concert.id] === "saved"}
                                  >
                                    {decisions[concert.id] === "saved"
                                      ? "Saved"
                                      : "Save"}
                                  </button>
                                  <Dialog.Trigger
                                    className="quiet"
                                    aria-label={`Open Ticket for ${name}`}
                                    onClick={() => setSelected(rank)}
                                  >
                                    Open Ticket
                                  </Dialog.Trigger>
                                </div>
                                <p role="status" className="decision-status">
                                  {notice}
                                </p>
                              </div>
                            </article>
                          );
                        return (
                          <motion.article
                            key={concert.id}
                            className={`concert-card rank-${rank} ${concert.image ? "has-photo" : "no-photo"}`}
                            initial={{ opacity: 0, y: reduced ? 0 : 12 }}
                            animate={{ opacity: 1, y: 0 }}
                            transition={{
                              duration: reduced ? 0 : 0.3,
                              delay: reduced ? 0 : Math.min(rank * 0.035, 0.18),
                            }}
                          >
                            {photo(r)}
                            <Dialog.Trigger
                              className="card-open"
                              aria-label={`Open Ticket for ${name}`}
                              onClick={() => setSelected(rank)}
                            />
                            {date && (
                              <time
                                className="card-date"
                                dateTime={concert.date}
                              >
                                {date}
                              </time>
                            )}
                            {decisions[concert.id] === "saved" && (
                              <span className="card-saved">
                                <Check aria-hidden size={16} /> Saved
                              </span>
                            )}
                            <div className="card-body">
                              <motion.h3
                                className="card-name"
                                layoutId={`name-${name}`}
                                transition={{ duration }}
                              >
                                {name}
                              </motion.h3>
                              {showTitle(concert, name) && (
                                <p className="card-bill">
                                  {showTitle(concert, name)}
                                </p>
                              )}
                              <p className="card-meta">{meta}</p>
                              {reason && <p className="card-why">{reason}</p>}
                            </div>
                          </motion.article>
                        );
                      })}
                    </motion.div>
                  </AnimatePresence>
                  <Dialog.Portal>
                    <Dialog.Backdrop className="ticket-backdrop" />
                    <Dialog.Popup className="ticket-dialog">
                      {current && (
                        <>
                          <Dialog.Title className="sr-only">
                            Ticket for {nameOf(current)}
                          </Dialog.Title>
                          <Dialog.Description className="sr-only">
                            Concert details and why it fits your Search.
                          </Dialog.Description>
                          {photo(current, true)}
                          <div className="dialog-details">
                            <Ticket
                              recommendation={current}
                              rank={selected}
                              artistHint={hint}
                              onArtistOpen={dismissArtistHint}
                              hidePhoto
                            />
                            <div className="dialog-actions">
                              <button
                                className="primary"
                                onClick={() => save()}
                                disabled={
                                  decisions[current.concert.id] === "saved"
                                }
                              >
                                {decisions[current.concert.id] === "saved" ? (
                                  <Check aria-hidden size={19} />
                                ) : (
                                  <Bookmark aria-hidden size={19} />
                                )}
                                {decisions[current.concert.id] === "saved"
                                  ? "Saved"
                                  : "Save"}
                              </button>
                            </div>
                            <p className="decision-status" role="status">
                              {notice}
                            </p>
                          </div>
                          <Dialog.Close
                            className="dialog-close"
                            aria-label="Close Ticket"
                          >
                            <X aria-hidden />
                          </Dialog.Close>
                        </>
                      )}
                    </Dialog.Popup>
                  </Dialog.Portal>
                </Dialog.Root>
              </>
            ) : (
              <div className="empty">
                <div>
                  <h2>Nothing here fits</h2>
                  <p>
                    {candidates
                      ? `${candidates.total} Concerts considered. `
                      : ""}
                    Try wider dates, another place, or a different sound.
                  </p>
                </div>
                <div className="empty-actions">
                  {onWiderDates && (
                    <button onClick={onWiderDates}>
                      Look at the next three months
                    </button>
                  )}
                  {onAnywhere && (
                    <button onClick={onAnywhere}>Look anywhere</button>
                  )}
                  <button onClick={onChange}>Change the Search</button>
                </div>
              </div>
            )}
            {recommendations.length <= 3 && passed.length > 0 && (
              <section className="passed" aria-label="Also playing, not picked">
                <h3>Also playing, not picked</h3>
                <p>These Artists had Concerts in the shortlist.</p>
                <div className="cloud">
                  {passed.slice(0, expanded ? undefined : 18).map((n) => (
                    <span className="name" key={n}>
                      {n}
                    </span>
                  ))}
                  {!expanded && passed.length > 18 && (
                    <button className="name" onClick={() => setExpanded(true)}>
                      Show {passed.length - 18} more
                    </button>
                  )}
                </div>
              </section>
            )}
          </>
        )}
      </section>
    </LayoutGroup>
  );
}
