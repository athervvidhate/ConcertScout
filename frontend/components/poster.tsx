"use client";

import { Button } from "@base-ui/react/button";
import { Fragment, useEffect, useLayoutEffect, useRef, useState } from "react";
import { flyDuration, GLIDE_GAP_MS, GLIDE_MS, GROW_MS, MAX_CANDIDATE_NAMES, namesDuration, PICK_READ_MS } from "@/lib/poster-timing";
import type { Candidates, Recommendation } from "@/lib/search";
import { formatDate, formatPrice, formatTime } from "@/lib/format";

type Props = { candidates: Candidates | null; recommendations: Recommendation[]; hasPoster: boolean; searching: boolean };
const nameOf = (r: Recommendation) => r.concert.artists[0]?.name ?? r.concert.name;

export function Poster({ candidates, recommendations, hasPoster, searching }: Props) {
  const [stage, setStage] = useState<"opening" | "names" | "picks" | "fly" | "ticket">("opening");
  const [selected, setSelected] = useState(0);
  const [decisions, setDecisions] = useState<Record<string, "saved" | "skipped">>({});
  const [notice, setNotice] = useState("");
  const namesStarted = useRef(0);
  const wall = useRef<HTMLDivElement>(null);
  const poster = useRef<HTMLDivElement>(null);
  const names = candidates?.names.slice(0, MAX_CANDIDATE_NAMES) ?? [];
  useEffect(() => {
    namesStarted.current = Date.now();
    const timer = setTimeout(() => { setStage(candidates ? "names" : "opening"); setSelected(0);
      setNotice("");
      try {
        const saved: Recommendation[] = JSON.parse(localStorage.getItem("concert-scout-saved") ?? "[]");
        setDecisions(Object.fromEntries(saved.map(r => [r.concert.id, "saved"])));
      } catch { setDecisions({}); }
    }, 0);
    return () => clearTimeout(timer);
  }, [candidates]);
  useEffect(() => {
    if (!hasPoster) return;
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const timer = setTimeout(() => setStage(reduced || !candidates ? "ticket" : "picks"), reduced || !candidates ? 0 : Math.max(0, namesDuration(names.length) - (Date.now() - namesStarted.current)));
    return () => clearTimeout(timer);
  }, [candidates, hasPoster, names.length]);
  useEffect(() => {
    if (stage !== "picks") return;
    const timer = setTimeout(() => setStage("fly"), PICK_READ_MS);
    return () => clearTimeout(timer);
  }, [stage]);
  useLayoutEffect(() => {
    if (stage !== "fly" && stage !== "ticket") return;
    const headliner = poster.current?.querySelector<HTMLElement>(".tier-1");
    if (!headliner) return;
    const fit = () => {
      headliner.style.fontSize = "";
      const text = headliner.firstElementChild as HTMLElement;
      const width = text.getBoundingClientRect().width;
      if (width > headliner.clientWidth) {
        headliner.style.fontSize = `${parseFloat(getComputedStyle(headliner).fontSize) * headliner.clientWidth / width}px`;
      }
    };
    fit();
    window.addEventListener("resize", fit);
    return () => window.removeEventListener("resize", fit);
  }, [stage, recommendations]);
  useEffect(() => {
    if (stage !== "fly" || !wall.current || !poster.current) return;
    const sources = Array.from(wall.current.querySelectorAll<HTMLElement>("[data-name]"));
    const targets = Array.from(poster.current.querySelectorAll<HTMLElement>("[data-name]"));
    const duration = flyDuration(targets.length);
    const sourceRects = sources.map(source => ({ name: source.dataset.name, rect: source.getBoundingClientRect() }));
    const targetRects = targets.map(target => target.getBoundingClientRect());
    const animations = targets.flatMap((target, i) => {
      const b = targetRects[i];
      const a = sourceRects.find(source => source.name === target.dataset.name)?.rect ?? b;
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
      const pink = target.querySelector(".pink")!;
      const growStart = (duration - GROW_MS) / duration;
      const tint = pink.animate(i === 0 ? [{ opacity: 1 }, { opacity: 1 }] : [
        { opacity: 1, offset: 0 }, { opacity: 1, offset: growStart }, { opacity: 0, offset: 1 },
      ], { duration, fill: "both" });
      return [animation, tint];
    });
    const timer = setTimeout(() => setStage("ticket"), duration);
    return () => { clearTimeout(timer); animations.forEach(animation => animation.cancel()); targets.forEach(target => { target.style.willChange = ""; }); };
  }, [stage]);
  const showPoster = stage === "fly" || stage === "ticket";
  const current = recommendations[selected];
  function decide(decision: "saved" | "skipped") {
    if (!current) return;
    if (decision === "saved") {
      try {
        const saved: Recommendation[] = JSON.parse(localStorage.getItem("concert-scout-saved") ?? "[]");
        localStorage.setItem("concert-scout-saved", JSON.stringify([...saved.filter(r => r.concert.id !== current.concert.id), current]));
      } catch {
        setNotice("This browser could not save the Concert. Allow local storage and try again.");
        return;
      }
    }
    setDecisions(previous => ({ ...previous, [current.concert.id]: decision }));
    setNotice(`${nameOf(current)} ${decision === "saved" ? "saved on this device" : "skipped"}.`);
    const next = recommendations.findIndex((r, i) => i !== selected && !decisions[r.concert.id]);
    if (next >= 0) setSelected(next);
  }
  return <section className="poster-area">
    <div className="poster-stage">
      {searching && !candidates && <div className="equalizer" aria-hidden="true"><i/><i/><i/><i/><i/></div>}
      {candidates && <div ref={wall} className={`wall ${showPoster ? "wall-hidden" : ""}`}>{names.map((name, i) => <span key={name} data-name={name} className={stage === "picks" ? (recommendations.some(r => nameOf(r) === name) ? "pick" : "faded") : ""} style={{ animationDelay: `${i * 32}ms` }}>{name}</span>)}</div>}
      {showPoster && <div className="poster" ref={poster}>{recommendations.map((r, i) => {
        const duplicate = recommendations.filter(other => nameOf(other) === nameOf(r)).length > 1;
        return <Fragment key={r.concert.id}>
          <Button type="button" data-name={nameOf(r)} onClick={() => setSelected(i)} aria-label={[nameOf(r), duplicate && r.concert.date && formatDate(r.concert.date), duplicate && r.concert.venue, decisions[r.concert.id]].filter(Boolean).join(", ")} aria-pressed={i === selected} className={`poster-name tier-${i === 0 ? 1 : i < 3 ? 2 : 3} ${i === selected ? "selected" : ""} ${decisions[r.concert.id] ?? ""}`}>
            <span>{nameOf(r)}</span><span className="pink" aria-hidden="true">{nameOf(r)}</span>
            {duplicate && <small>{[r.concert.date && formatDate(r.concert.date), r.concert.venue].filter(Boolean).join(" · ") || r.concert.name}</small>}
            {decisions[r.concert.id] === "saved" && <small>saved</small>}
          </Button>{i === 2 && <span className="poster-break" aria-hidden="true" />}
        </Fragment>;
      })}</div>}
    </div>
    <p className="loader-status" aria-live="polite">{!candidates && searching ? "Reading your request" : candidates && (!hasPoster || stage === "names" || stage === "opening") ? `${candidates.total} close matches, ranking them` : candidates && hasPoster ? `${recommendations.length} picks from ${candidates.total} close matches` : ""}</p>
    {stage === "ticket" && current && <>
      <article className="ticket" key={current.concert.id}>
        <div className="ticket-main">
          {current.concert.date && <time className="date" dateTime={current.concert.date} title={formatDate(current.concert.date)} aria-label={formatDate(current.concert.date)}>{new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", timeZone: "UTC" }).format(new Date(`${current.concert.date}T00:00:00Z`))}</time>}
          <h2>{nameOf(current)}</h2>{current.reason && <p>{current.reason}</p>}
          <p className="venue">{[current.concert.venue, current.concert.city, current.concert.region, current.concert.date && new Intl.DateTimeFormat("en-US", { weekday: "short", timeZone: "UTC" }).format(new Date(`${current.concert.date}T00:00:00Z`)), current.concert.time && formatTime(current.concert.time)].filter(Boolean).join(", ")}</p>
        </div>
        <div className="ticket-stub"><span>Admit one</span>
          {current.concert.price && <span className="price" style={{ fontSize: `min(46px, ${140 / Math.max(...formatPrice(current.concert.price, true).split(" to ").map(part => part.length))}cqw)` }}>{formatPrice(current.concert.price, true).split(" to ").map((part, i) => <Fragment key={part + i}>{i > 0 && <span className="price-to"> to </span>}<span className="price-value">{part}</span></Fragment>)}</span>}
          <a href={current.concert.url} aria-label={`Tickets for ${current.concert.name}`}>Tickets</a>
        </div>
      </article>
      <div className="ticket-controls"><Button type="button" onClick={() => decide("skipped")}>Skip</Button><Button type="button" onClick={() => decide("saved")}>Save</Button></div>
      <p className="decision-status" role="status">{notice}</p>
    </>}
  </section>;
}
