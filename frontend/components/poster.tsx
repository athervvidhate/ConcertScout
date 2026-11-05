"use client";

import { useEffect, useRef, useState } from "react";
import { flyDuration, GLIDE_GAP_MS, GLIDE_MS, GROW_MS, MAX_CANDIDATE_NAMES, namesDuration, PICK_READ_MS } from "@/lib/poster-timing";
import type { Candidates, Recommendation } from "@/lib/search";
import { formatDate, formatPrice, formatTime } from "@/lib/format";

type Props = { candidates: Candidates | null; recommendations: Recommendation[]; hasPoster: boolean; searching: boolean };
const nameOf = (r: Recommendation) => r.concert.artists[0]?.name ?? r.concert.name;

export function Poster({ candidates, recommendations, hasPoster, searching }: Props) {
  const [stage, setStage] = useState<"opening" | "names" | "picks" | "fly" | "ticket">("opening");
  const [selected, setSelected] = useState(0);
  const wall = useRef<HTMLDivElement>(null);
  const poster = useRef<HTMLDivElement>(null);
  const names = candidates?.names.slice(0, MAX_CANDIDATE_NAMES) ?? [];
  useEffect(() => {
    const timer = setTimeout(() => { setStage(candidates ? "names" : "opening"); setSelected(0); }, 0);
    return () => clearTimeout(timer);
  }, [candidates]);
  useEffect(() => {
    if (!candidates || !hasPoster) return;
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const timer = setTimeout(() => setStage(reduced ? "ticket" : "picks"), reduced ? 0 : namesDuration(names.length));
    return () => clearTimeout(timer);
  }, [candidates, hasPoster, names.length]);
  useEffect(() => {
    if (stage !== "picks") return;
    const timer = setTimeout(() => setStage("fly"), PICK_READ_MS);
    return () => clearTimeout(timer);
  }, [stage]);
  useEffect(() => {
    if (stage !== "fly" || !wall.current || !poster.current) return;
    const sources = Array.from(wall.current.querySelectorAll<HTMLElement>("[data-name]"));
    const targets = Array.from(poster.current.querySelectorAll<HTMLElement>("[data-name]"));
    const duration = flyDuration(targets.length);
    const animations = targets.map((target, i) => {
      const b = target.getBoundingClientRect();
      const a = sources.find(source => source.dataset.name === target.dataset.name)?.getBoundingClientRect() ?? b;
      const scale = b.width ? Math.min(1, a.width / b.width) : 1;
      const from = `translate(${a.left + a.width / 2 - b.left - b.width / 2}px, ${a.top + a.height / 2 - b.top - b.height / 2}px) scale(${scale})`;
      const land = `translate(0, 0) scale(${scale})`;
      target.style.willChange = "transform";
      const animation = target.animate([
        { transform: from, offset: 0 },
        { transform: from, offset: i * GLIDE_GAP_MS / duration, easing: "cubic-bezier(.65,0,.35,1)" },
        { transform: land, offset: (i * GLIDE_GAP_MS + GLIDE_MS) / duration },
        { transform: land, offset: (duration - GROW_MS) / duration, easing: "cubic-bezier(.22,.61,.36,1)" },
        { transform: "translate(0,0) scale(1)", offset: 1 },
      ], { duration, fill: "both" });
      animation.onfinish = () => { target.style.willChange = ""; };
      return animation;
    });
    const timer = setTimeout(() => setStage("ticket"), duration);
    return () => { clearTimeout(timer); animations.forEach(animation => animation.cancel()); };
  }, [stage]);
  const showPoster = stage === "fly" || stage === "ticket";
  const current = recommendations[selected];
  return <section className="poster-area">
    <div className="poster-stage">
      {searching && !candidates && <div className="equalizer" aria-hidden="true"><i/><i/><i/><i/><i/></div>}
      {candidates && <div ref={wall} className={`wall ${showPoster ? "wall-hidden" : ""}`}>{names.map((name, i) => <span key={name} data-name={name} className={stage === "picks" ? (recommendations.some(r => nameOf(r) === name) ? "pick" : "faded") : ""} style={{ animationDelay: `${i * 32}ms` }}>{name}</span>)}</div>}
      {showPoster && <div className="poster" ref={poster}>{recommendations.map((r, i) => <button type="button" key={r.concert.id} data-name={nameOf(r)} onClick={() => setSelected(i)} className={`poster-name tier-${Math.min(i + 1, 3)} ${i === selected ? "selected" : ""}`}><span>{nameOf(r)}</span><span className="pink" aria-hidden="true">{nameOf(r)}</span></button>)}</div>}
    </div>
    <p className="loader-status" aria-live="polite">{!candidates && searching ? "Reading your request" : candidates && !hasPoster ? `${candidates.total} close matches` : candidates && hasPoster && stage !== "ticket" ? `${recommendations.length} picks from ${candidates.total} close matches` : ""}</p>
    {stage === "ticket" && current && <article className="ticket" key={current.concert.id}>
      {current.concert.date && <div className="date">{formatDate(current.concert.date)}</div>}
      <h2>{nameOf(current)}</h2><p>{current.reason}</p>
      <p>{[current.concert.venue, current.concert.city, current.concert.region].filter(Boolean).join(", ")}</p>
      {current.concert.time && <p>{formatTime(current.concert.time)}</p>}
      {current.concert.price && <p className="date">{formatPrice(current.concert.price)}</p>}
      <a href={current.concert.url}>Tickets ↗</a>
    </article>}
  </section>;
}
