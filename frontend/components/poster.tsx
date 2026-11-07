"use client";

import { Button } from "@base-ui/react/button";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { Fragment, useEffect, useLayoutEffect, useRef, useState } from "react";

import { PosterDone } from "@/components/poster-done";
import { nameOf, Ticket } from "@/components/ticket";
import { dismissArtistHint, useArtistHint } from "@/lib/artist-hint";
import { flyIn } from "@/lib/fly-in";
import { flyDuration, MAX_CANDIDATE_NAMES, namesDuration, PICK_READ_MS } from "@/lib/poster-timing";
import { type Decision, saveConcert, skipConcert, useDecisions } from "@/lib/saved";
import type { Candidates, Recommendation } from "@/lib/search";
import { swipeDecision } from "@/lib/swipe";

type Props = {
  candidates: Candidates | null;
  recommendations: Recommendation[];
  hasPoster: boolean;
  searching: boolean;
  status: string | null;
};
type Stage = "opening" | "names" | "picks" | "fly" | "ticket";

const TICKET_MOTION = {
  enter: { opacity: 0, scale: 0.96 },
  rest: { opacity: 1, scale: 1, x: 0, rotate: 0 },
  // A decided Ticket keeps travelling the way it was thrown, from wherever the drag left it.
  gone: (direction: number) => ({
    x: direction * Math.max(window.innerWidth, 1000),
    rotate: direction * 14,
    opacity: 0,
    pointerEvents: "none" as const,
  }),
};

function tierOf(rank: number): number {
  if (rank === 0) return 1;
  return rank < 3 ? 2 : 3;
}

// Each stage starts from a real event. After `poster`, only presentation timing remains.
function useStage(candidates: Candidates | null, hasPoster: boolean, nameCount: number) {
  const [stage, setStage] = useState<Stage>("opening");
  const namesStarted = useRef(0);

  useEffect(() => {
    if (!candidates) return;
    namesStarted.current = Date.now();
    const timer = setTimeout(() => setStage("names"), 0);
    return () => clearTimeout(timer);
  }, [candidates]);

  useEffect(() => {
    if (!hasPoster) return;
    const direct = window.matchMedia("(prefers-reduced-motion: reduce)").matches || !candidates;
    const namesLeft = namesDuration(nameCount) - (Date.now() - namesStarted.current);
    const timer = setTimeout(
      () => setStage(direct ? "ticket" : "picks"),
      direct ? 0 : Math.max(0, namesLeft),
    );
    return () => clearTimeout(timer);
  }, [candidates, hasPoster, nameCount]);

  useEffect(() => {
    if (stage !== "picks") return;
    const timer = setTimeout(() => setStage("fly"), PICK_READ_MS);
    return () => clearTimeout(timer);
  }, [stage]);

  return [stage, setStage] as const;
}

function useHeadlinerFit(poster: React.RefObject<HTMLDivElement | null>, visible: boolean) {
  useLayoutEffect(() => {
    if (!visible) return;
    const headliner = poster.current?.querySelector<HTMLElement>(".tier-1");
    if (!headliner) return;
    const fit = () => {
      headliner.style.fontSize = "";
      const width = headliner.firstElementChild!.getBoundingClientRect().width;
      if (width > headliner.clientWidth) {
        const size = parseFloat(getComputedStyle(headliner).fontSize);
        headliner.style.fontSize = `${(size * headliner.clientWidth) / width}px`;
      }
    };
    fit();
    window.addEventListener("resize", fit);
    return () => window.removeEventListener("resize", fit);
  }, [poster, visible]);
}

function statusText({ candidates, recommendations, hasPoster, searching, status }: Props) {
  if (!hasPoster) return searching ? (status ?? "Reading your request") : "";
  if (!recommendations.length) return "";
  const picks = `${recommendations.length} ${recommendations.length === 1 ? "pick" : "picks"}`;
  return candidates ? `${picks} from ${candidates.total} Concerts considered` : picks;
}

export function Poster(props: Props) {
  const { candidates, recommendations, hasPoster, searching } = props;
  // A name reveal only begins once there are Recommendations to reveal. Keep a small
  // Poster proportionate, and include every chosen name so each has a place to fly from.
  const qualified = hasPoster && recommendations.length > 0;
  const names = qualified && candidates
    ? [...new Set([...recommendations.map(nameOf), ...candidates.names])]
      .slice(0, Math.min(MAX_CANDIDATE_NAMES, Math.max(8, recommendations.length * 3)))
    : [];
  const reveal = qualified ? candidates : null;
  const [stage, setStage] = useStage(reveal, qualified, names.length);
  const [selected, setSelected] = useState(0);
  const [finished, setFinished] = useState(false);
  const artistHint = useArtistHint();
  const decisions = useDecisions();
  const [notice, setNotice] = useState("");
  const [thrown, setThrown] = useState({ count: 0, direction: 1 });
  const dragged = useRef(false);
  const stillTicket = useReducedMotion();
  const wall = useRef<HTMLDivElement>(null);
  const poster = useRef<HTMLDivElement>(null);
  const showPoster = qualified && (stage === "fly" || stage === "ticket");
  useHeadlinerFit(poster, showPoster);

  useEffect(() => {
    if (stage !== "fly" || !wall.current || !poster.current) return;
    const cancel = flyIn(wall.current, poster.current);
    const timer = setTimeout(() => setStage("ticket"), flyDuration(recommendations.length));
    return () => {
      clearTimeout(timer);
      cancel();
    };
  }, [recommendations.length, setStage, stage]);

  const current = recommendations[selected];

  function decide(decision: Decision) {
    if (!current) return;
    try {
      if (decision === "saved") saveConcert(current);
      else skipConcert(current.concert.id);
    } catch {
      setNotice("This browser could not keep that choice. Allow local storage and try again.");
      return;
    }
    dismissArtistHint();
    const done = decision === "saved" ? "saved on this device" : "skipped";
    setNotice(`${nameOf(current)} ${done}.`);
    setThrown(({ count }) => ({ count: count + 1, direction: decision === "saved" ? 1 : -1 }));
    const after = [...recommendations.slice(selected + 1), ...recommendations.slice(0, selected)];
    const next = after.find((r) => !decisions[r.concert.id]);
    if (next) setSelected(recommendations.indexOf(next));
    else setFinished(true);
  }

  function nameClass(rank: number) {
    const tier = rank === selected && !finished ? "selected" : "";
    return `poster-name tier-${tierOf(rank)} ${tier} ${decisions[recommendations[rank].concert.id] ?? ""}`;
  }

  function wallClass(name: string) {
    if (stage !== "picks") return "";
    return recommendations.some((r) => nameOf(r) === name) ? "pick" : "faded";
  }

  return (
    <section className={`poster-area ${hasPoster && recommendations.length <= 3 ? "poster-compact" : ""}`}>
      <div className="poster-stage">
        {searching && !qualified && (
          <div className="equalizer" aria-hidden="true">
            <i />
            <i />
            <i />
            <i />
            <i />
          </div>
        )}
        {qualified && candidates && (
          <div ref={wall} className={`wall ${showPoster ? "wall-hidden" : ""}`}>
            {names.map((name, index) => (
              <span
                key={name}
                data-name={name}
                className={wallClass(name)}
                style={{ animationDelay: `${index * 32}ms` }}
              >
                {name}
              </span>
            ))}
          </div>
        )}
        {showPoster && (
          <div className={`poster ${stage === "ticket" ? "poster-settled" : ""}`} ref={poster}>
            {recommendations.map((recommendation, rank) => {
              const { concert } = recommendation;
              const name = nameOf(recommendation);
              const decision = decisions[concert.id];
              return (
                <Fragment key={concert.id}>
                  <Button
                    type="button"
                    data-name={name}
                    onClick={() => {
                      setSelected(rank);
                      setFinished(false);
                    }}
                    aria-label={[name, decision].filter(Boolean).join(", ")}
                    aria-pressed={rank === selected && !finished}
                    className={nameClass(rank)}
                  >
                    <span>{name}</span>
                    <span className="pink" aria-hidden="true">
                      {name}
                    </span>
                    {decision === "saved" && <small>saved</small>}
                  </Button>
                  {rank === 2 && <span className="poster-break" aria-hidden="true" />}
                </Fragment>
              );
            })}
          </div>
        )}
      </div>
      <p className="loader-status" aria-live="polite">
        {statusText(props)}
      </p>
      {stage === "ticket" && finished && (
        <PosterDone saved={recommendations.filter((r) => decisions[r.concert.id] === "saved")} />
      )}
      {stage === "ticket" && current && !finished && (
        <div>
          <div className="ticket-deck">
            <AnimatePresence initial={false} mode="popLayout" custom={thrown.direction}>
              <motion.div
                key={`${current.concert.id}:${thrown.count}`}
                className="ticket-drag"
                custom={thrown.direction}
                variants={TICKET_MOTION}
                initial="enter"
                animate="rest"
                exit="gone"
                transition={{ duration: stillTicket ? 0 : 0.3, ease: "easeOut" }}
                drag="x"
                dragSnapToOrigin
                dragElastic={0.7}
                whileDrag={{ scale: 0.98 }}
                onPointerDownCapture={() => {
                  // A touch drag ends with no click, so each press starts clean.
                  dragged.current = false;
                }}
                onDragStart={() => {
                  dragged.current = true;
                }}
                onDragEnd={(_, { offset, velocity }) => {
                  const decision = swipeDecision(offset.x, velocity.x);
                  if (decision) decide(decision);
                }}
                onClickCapture={(event) => {
                  // Letting go over a link or the Artist's name must not also press it.
                  if (!dragged.current) return;
                  event.preventDefault();
                  event.stopPropagation();
                }}
              >
                <Ticket
                  recommendation={current}
                  rank={selected}
                  artistHint={artistHint}
                  onArtistOpen={dismissArtistHint}
                />
              </motion.div>
            </AnimatePresence>
          </div>
          <p className="ticket-hint">Drag right to save, left to skip.</p>
          <div className="ticket-controls">
            <Button type="button" onClick={() => decide("skipped")}>
              Skip
            </Button>
            <Button type="button" onClick={() => decide("saved")}>
              Save
            </Button>
          </div>
          <p className="decision-status" role="status">
            {notice}
          </p>
        </div>
      )}
    </section>
  );
}
