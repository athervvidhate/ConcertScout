"use client";

import { Button } from "@base-ui/react/button";
import { motion } from "motion/react";
import { type KeyboardEvent, Fragment, useEffect, useLayoutEffect, useRef, useState } from "react";

import { nameOf, Ticket } from "@/components/ticket";
import { flyIn } from "@/lib/fly-in";
import { formatDate } from "@/lib/format";
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

function tierOf(rank: number): number {
  if (rank === 0) return 1;
  return rank < 3 ? 2 : 3;
}

// Each stage starts from a real event. After `poster`, only presentation timing remains.
function useStage(candidates: Candidates | null, hasPoster: boolean, nameCount: number) {
  const [stage, setStage] = useState<Stage>("opening");
  const namesStarted = useRef(0);

  useEffect(() => {
    namesStarted.current = Date.now();
    const timer = setTimeout(() => setStage(candidates ? "names" : "opening"), 0);
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
  const decisions = useDecisions();
  const [notice, setNotice] = useState("");
  const wall = useRef<HTMLDivElement>(null);
  const poster = useRef<HTMLDivElement>(null);
  const showPoster = qualified && (stage === "fly" || stage === "ticket");
  useHeadlinerFit(poster, showPoster);

  useEffect(() => {
    const timer = setTimeout(() => {
      setSelected(0);
      setNotice("");
    }, 0);
    return () => clearTimeout(timer);
  }, [candidates]);

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
    try {
      if (decision === "saved") saveConcert(current);
      else skipConcert(current.concert.id);
    } catch {
      setNotice("This browser could not keep that choice. Allow local storage and try again.");
      return;
    }
    const done = decision === "saved" ? "saved on this device" : "skipped";
    setNotice(`${nameOf(current)} ${done}.`);
    const after = [...recommendations.slice(selected + 1), ...recommendations.slice(0, selected)];
    const next = after.find((r) => !decisions[r.concert.id]);
    if (next) setSelected(recommendations.indexOf(next));
  }

  function decideByKey(event: KeyboardEvent) {
    if (event.key === "ArrowRight") decide("saved");
    if (event.key === "ArrowLeft") decide("skipped");
  }

  function nameClass(rank: number) {
    const tier = rank === selected ? "selected" : "";
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
          <div className="poster" ref={poster}>
            {recommendations.map((recommendation, rank) => {
              const { concert } = recommendation;
              const name = nameOf(recommendation);
              const decision = decisions[concert.id];
              const repeated = recommendations.filter((r) => nameOf(r) === name).length > 1;
              const place = [concert.date && formatDate(concert.date), concert.venue].filter(Boolean);
              const label = [name, ...(repeated ? place : []), decision].filter(Boolean);
              return (
                <Fragment key={concert.id}>
                  <Button
                    type="button"
                    data-name={name}
                    onClick={() => setSelected(rank)}
                    aria-label={label.join(", ")}
                    aria-pressed={rank === selected}
                    className={nameClass(rank)}
                  >
                    <span>{name}</span>
                    <span className="pink" aria-hidden="true">
                      {name}
                    </span>
                    {repeated && <small>{place.join(" · ") || concert.name}</small>}
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
      {stage === "ticket" && current && (
        <div onKeyDown={decideByKey}>
          <motion.div
            key={current.concert.id}
            className="ticket-drag"
            drag="x"
            dragSnapToOrigin
            dragElastic={0.7}
            whileDrag={{ scale: 0.98 }}
            onDragEnd={(_, { offset, velocity }) => {
              const decision = swipeDecision(offset.x, velocity.x);
              if (decision) decide(decision);
            }}
          >
            <Ticket recommendation={current} rank={selected} />
          </motion.div>
          <p className="ticket-hint">Drag right to save, left to skip, or use the arrow keys.</p>
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
