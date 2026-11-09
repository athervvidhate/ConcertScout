"use client";

import { Dialog } from "@base-ui/react/dialog";
import { LayoutGrid, List, X } from "lucide-react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import Image from "next/image";
import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { AnimatedCount } from "@/components/animated-count";
import { nameOf, Ticket } from "@/components/ticket";
import { WorkingSearch } from "@/components/working-search";
import { SaveButton } from "@/components/save-button";
import { dismissArtistHint, useArtistHint } from "@/lib/artist-hint";
import { Choreography, EXPO_OUT_CURVE } from "@/lib/choreography";
import {
  captureNames,
  revealPoster,
  type NameFrame,
} from "@/lib/poster-choreography";
import { useTicketMotion } from "@/lib/use-ticket-motion";
import { formatDate, formatConcertTime } from "@/lib/format";
import { removeSaved, saveConcert, useDecisions } from "@/lib/saved";
import type { Candidates, Recommendation } from "@/lib/search";
import { showTitle } from "@/lib/show-title";

type View = "grid" | "list";
const VIEW_KEY = "concert-scout-view";
const VIEWS = [
  { kind: "grid", label: "Grid view", Icon: LayoutGrid },
  { kind: "list", label: "List view", Icon: List },
] as const;

type Props = {
  candidates: Candidates | null;
  recommendations: Recommendation[];
  hasPoster: boolean;
  searching: boolean;
  status: string | null;
  step?: string | null;
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
  step,
  onWiderDates,
  onAnywhere,
  onChange,
}: Props) {
  const reduced = useReducedMotion();
  const [cached] = useState(!searching && hasPoster);
  const [stage, setStage] = useState<"working" | "picks" | "poster">("working");
  const [view, setView] = useState<View>(() => {
    try {
      return localStorage.getItem(VIEW_KEY) === "list" ? "list" : "grid";
    } catch {
      return "grid";
    }
  });
  const [results, setResults] = useState<HTMLDivElement | null>(null);
  const root = useRef<HTMLElement>(null);
  const source = useRef<HTMLElement>(null);
  const frames = useRef(new Map<string, NameFrame>());
  const revealed = useRef(false);
  const [selected, setSelected] = useState(0);
  const [open, setOpen] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const [notice, setNotice] = useState("");
  const [pending, setPending] = useState<Set<string>>(() => new Set());
  const decisions = useDecisions();
  const hint = useArtistHint();
  const current = recommendations[selected];
  const closed = useCallback(() => setOpen(false), []);
  const ticketMotion = useTicketMotion(
    open,
    current?.concert.id,
    source,
    closed,
  );
  const picked = useMemo(
    () =>
      new Set(
        recommendations.flatMap((r) => r.concert.artists.map((a) => a.name)),
      ),
    [recommendations],
  );
  const passed = candidates?.names.filter((n) => !picked.has(n)) ?? [];

  useEffect(() => {
    if (!notice || pending.size) return;
    const timer = setTimeout(() => setNotice(""), 4000);
    return () => clearTimeout(timer);
  }, [notice, pending.size]);

  useEffect(() => {
    if (!hasPoster) return;
    const scope = new Choreography();
    void (async () => {
      // Live Searches have already shown candidates; cached Posters replay their narrowing.
      if (cached && candidates && !revealed.current && !reduced)
        await scope.wait(1400);
      if (!scope.live) return;
      setStage("picks");
      if (!reduced) await scope.wait(recommendations.length ? 950 : 600);
      if (!scope.live) return;
      if (root.current) frames.current = captureNames(root.current);
      setStage("poster");
    })();
    return () => scope.cancel();
  }, [hasPoster, candidates, recommendations.length, reduced, cached]); // `searching` finishing must not restart the presentation.

  useLayoutEffect(() => {
    if (stage !== "poster" || !results || results.dataset.view !== view) return;
    if (reduced) {
      revealed.current = true;
      return;
    }
    const scope = new Choreography();
    const changing = revealed.current;
    revealed.current = true;
    return revealPoster(
      results,
      changing ? new Map() : frames.current,
      scope,
      changing,
    );
  }, [results, stage, view, reduced]);

  function chooseView(next: View) {
    setView(next);
    try {
      localStorage.setItem(VIEW_KEY, next);
    } catch {}
  }

  async function toggleSave(r = current) {
    if (!r || pending.has(r.concert.id)) return;
    const id = r.concert.id;
    const removing = decisions[id] === "saved";
    setPending((before) => new Set(before).add(id));
    try {
      if (removing) {
        await removeSaved(id);
        setNotice(`${nameOf(r)} removed from Saved Concerts.`);
      } else {
        const result = saveConcert(r);
        dismissArtistHint();
        if (result.where === "account") {
          setNotice(`Saving ${nameOf(r)} to your account…`);
          await result.done;
        }
        setNotice(
          `${nameOf(r)} saved ${result.where === "device" ? "on this device" : "to your account"}.`,
        );
      }
    } catch (error) {
      if (error instanceof DOMException)
        setNotice(
          "This browser could not keep that choice. Allow local storage and try again.",
        );
      else
        setNotice(
          `${nameOf(r)} could not be ${removing ? "removed from Saved Concerts" : "saved"}. Try again.`,
        );
    } finally {
      setPending((before) => {
        const next = new Set(before);
        next.delete(id);
        return next;
      });
    }
  }
  const rise = {
    hidden: { opacity: reduced ? 1 : 0, y: reduced ? 0 : 24 },
    shown: { opacity: 1, y: 0 },
  };
  const riseTiming = { duration: reduced ? 0 : 0.8, ease: EXPO_OUT_CURVE };

  function bookmark(r: Recommendation) {
    return (
      <SaveButton
        compact
        name={nameOf(r)}
        saved={decisions[r.concert.id] === "saved"}
        pending={pending.has(r.concert.id)}
        onToggle={() => void toggleSave(r)}
      />
    );
  }
  function photo(r: Recommendation, inDialog = false) {
    return r.concert.image ? (
      <div className={inDialog ? "dialog-photo" : "card-photo"}>
        <Image
          src={r.concert.image}
          alt=""
          fill
          unoptimized
          sizes="(max-width:640px) 100vw, 60vw"
          draggable={false}
        />
      </div>
    ) : null;
  }
  function choose(rank: number, event: React.MouseEvent<HTMLElement>) {
    source.current = event.currentTarget.closest<HTMLElement>(".concert-card");
    setSelected(rank);
  }

  return (
    <section
      className="fluid-poster"
      aria-label="Poster"
      ref={root}
      data-stage={stage}
    >
      {stage !== "poster" && (searching || hasPoster) && (
        <WorkingSearch
          candidates={candidates}
          status={
            hasPoster
              ? recommendations.length
                ? "Choosing the closest Concerts"
                : "Checking what fits"
              : (status ?? "Reading your Search")
          }
          step={hasPoster ? "rank" : step}
          picking={stage === "picks" || (hasPoster && !cached)}
          picked={picked}
          done={hasPoster}
        />
      )}
      {hasPoster && stage === "poster" && (
        <>
          {recommendations.length > 0 ? (
            <>
              <motion.header
                className="poster-head"
                initial={{ opacity: reduced ? 1 : 0, y: reduced ? 0 : 16 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{
                  duration: reduced ? 0 : 0.7,
                  ease: EXPO_OUT_CURVE,
                }}
              >
                <div>
                  <h2>
                    <AnimatedCount value={recommendations.length} />{" "}
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
                <div
                  className="views"
                  role="group"
                  aria-label="Poster view"
                  onKeyDown={(event) => {
                    if (
                      ![
                        "ArrowRight",
                        "ArrowLeft",
                        "ArrowUp",
                        "ArrowDown",
                      ].includes(event.key)
                    )
                      return;
                    event.preventDefault();
                    const next = view === "grid" ? "list" : "grid";
                    chooseView(next);
                    event.currentTarget
                      .querySelector<HTMLButtonElement>(
                        `button[data-view="${next}"]`,
                      )
                      ?.focus();
                  }}
                >
                  <motion.span
                    className="views-thumb"
                    animate={{ x: view === "grid" ? 0 : 46 }}
                    transition={{
                      duration: reduced ? 0 : 0.45,
                      ease: [0.2, 0.8, 0.2, 1],
                    }}
                  />
                  {VIEWS.map(({ kind, label, Icon }) => (
                    <button
                      key={kind}
                      data-view={kind}
                      aria-label={label}
                      title={label}
                      aria-pressed={view === kind}
                      onClick={() => chooseView(kind)}
                    >
                      <Icon aria-hidden />
                    </button>
                  ))}
                </div>
              </motion.header>
              <Dialog.Root
                open={open}
                onOpenChange={(next) => {
                  if (next) setOpen(true);
                  else ticketMotion.close();
                }}
              >
                <AnimatePresence mode="wait" initial={false}>
                  <motion.div
                    key={view}
                    ref={setResults}
                    className={`concerts-${view}`}
                    data-view={view}
                    data-count={recommendations.length}
                    initial={{ opacity: 1, y: 0 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: reduced ? 0 : -8 }}
                    transition={{ duration: reduced ? 0 : 0.2 }}
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
                      const bill = showTitle(concert, name);
                      if (recommendations.length === 1 && view === "grid")
                        return (
                          <article
                            className="solo concert-card"
                            key={concert.id}
                          >
                            <div className="solo-photo">
                              {photo(r)}
                              {bookmark(r)}
                            </div>
                            <div className="solo-body">
                              <Ticket
                                recommendation={r}
                                rank={rank}
                                artistHint={hint}
                                onArtistOpen={dismissArtistHint}
                                hidePhoto
                              />
                              <div className="solo-actions">
                                <SaveButton
                                  saved={decisions[concert.id] === "saved"}
                                  pending={pending.has(concert.id)}
                                  onToggle={() => void toggleSave(r)}
                                />
                                <Dialog.Trigger
                                  className="quiet"
                                  aria-label={`Open Ticket for ${name}`}
                                  onClick={(event) => choose(rank, event)}
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
                        <article
                          key={concert.id}
                          className={`concert-card rank-${rank} ${concert.image ? "has-photo" : "no-photo"}`}
                        >
                          {photo(r)}
                          <Dialog.Trigger
                            className="card-open"
                            aria-label={`Open Ticket for ${name}`}
                            onClick={(event) => choose(rank, event)}
                          />
                          {date && (
                            <time className="card-date" dateTime={concert.date}>
                              {date}
                            </time>
                          )}
                          {bookmark(r)}
                          <div className="card-body">
                            <h3 className="card-name">{name}</h3>
                            {bill && <p className="card-bill">{bill}</p>}
                            <p className="card-meta">{meta}</p>
                            {reason && <p className="card-why">{reason}</p>}
                          </div>
                        </article>
                      );
                    })}
                  </motion.div>
                </AnimatePresence>
                <Dialog.Portal>
                  <Dialog.Backdrop className="ticket-backdrop" />
                  <Dialog.Popup
                    className="ticket-dialog"
                    ref={(node) => {
                      ticketMotion.setElement(node);
                    }}
                  >
                    {current && (
                      <>
                        <Dialog.Title className="sr-only">
                          Ticket for {nameOf(current)}
                        </Dialog.Title>
                        <Dialog.Description className="sr-only">
                          Concert details and why it fits your Search.
                        </Dialog.Description>
                        {current.concert.image && (
                          <div className="dialog-media">
                            {photo(current, true)}
                          </div>
                        )}
                        <div className="dialog-details">
                          <Ticket
                            recommendation={current}
                            rank={selected}
                            artistHint={hint}
                            onArtistOpen={dismissArtistHint}
                            hidePhoto
                          />
                          <div className="dialog-actions">
                            <SaveButton
                              saved={decisions[current.concert.id] === "saved"}
                              pending={pending.has(current.concert.id)}
                              onToggle={() => void toggleSave()}
                            />
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
            <motion.div
              className="empty"
              initial="hidden"
              animate="shown"
              variants={{
                hidden: {},
                shown: { transition: { staggerChildren: reduced ? 0 : 0.1 } },
              }}
            >
              <motion.div variants={rise} transition={riseTiming}>
                <h2>Nothing here fits</h2>
                <p>
                  {candidates
                    ? `${candidates.total} Concerts considered. `
                    : ""}
                  Try wider dates, another place, or a different sound.
                </p>
              </motion.div>
              <motion.div
                className="empty-actions"
                variants={rise}
                transition={riseTiming}
              >
                {onWiderDates && (
                  <button onClick={onWiderDates}>
                    Look at the next three months
                  </button>
                )}
                {onAnywhere && (
                  <button onClick={onAnywhere}>Look anywhere</button>
                )}
                <button onClick={onChange}>Change the Search</button>
              </motion.div>
            </motion.div>
          )}
          {recommendations.length <= 3 && passed.length > 0 && (
            <motion.section
              className="passed"
              aria-label="Also playing, not picked"
              initial={{ opacity: reduced ? 1 : 0, y: reduced ? 0 : 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{
                duration: reduced ? 0 : 0.7,
                delay: reduced ? 0 : 0.8,
                ease: EXPO_OUT_CURVE,
              }}
            >
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
            </motion.section>
          )}
        </>
      )}
      {notice && !open && (view === "list" || recommendations.length !== 1) && (
        <p className="poster-notice" role="status">
          {notice}
        </p>
      )}
    </section>
  );
}
