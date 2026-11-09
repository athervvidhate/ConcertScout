"use client";
import {
  AlignLeft,
  MapPin,
  Ticket,
  AudioLines,
  Star,
  Check,
} from "lucide-react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { useLayoutEffect, useRef } from "react";
import { BACK_OUT, Choreography, EXPO_OUT_CURVE } from "@/lib/choreography";
import type { Candidates } from "@/lib/search";

const STEPS = ["interpret", "resolve", "pool", "match", "rank"];
const ICONS = {
  interpret: AlignLeft,
  resolve: MapPin,
  pool: Ticket,
  match: AudioLines,
  rank: Star,
  done: Check,
};
export function WorkingSearch({
  candidates,
  status,
  step = "interpret",
  picking,
  picked,
  done,
}: {
  candidates: Candidates | null;
  status: string;
  step?: string | null;
  picking: boolean;
  picked: Set<string>;
  done: boolean;
}) {
  const root = useRef<HTMLDivElement>(null);
  const reduced = useReducedMotion();
  useLayoutEffect(() => {
    if (reduced || !root.current) return;
    const scope = new Choreography();
    void scope.animate(
      root.current,
      [
        { opacity: 0, transform: "translateY(30px)" },
        { opacity: 1, transform: "none" },
      ],
      800,
      280,
    );
    return () => scope.cancel();
  }, [reduced]);
  useLayoutEffect(() => {
    if (!root.current || !candidates) return;
    const scope = new Choreography();
    const pills = [...root.current.querySelectorAll<HTMLElement>(".name")];
    pills.forEach((el, i) => {
      const pick = picking && picked.has(el.textContent ?? "");
      el.classList.toggle("pick", pick);
      if (reduced) {
        el.style.opacity = picking && !pick ? ".18" : "1";
        return;
      }
      if (picking)
        void scope.animate(
          el,
          [
            { opacity: 1, transform: pick ? "scale(1.12)" : "scale(1)" },
            {
              opacity: pick ? 1 : 0.18,
              transform: pick ? "scale(1)" : "scale(.94)",
            },
          ],
          500,
          0,
          pick ? BACK_OUT : undefined,
        );
      else
        void scope.animate(
          el,
          [
            { opacity: 0, transform: "translateY(10px) scale(.9)" },
            { opacity: 1, transform: "none" },
          ],
          500,
          i * 18,
        );
    });
    return () => scope.cancel();
  }, [candidates, picking, picked, reduced]);
  const kind = done
    ? "done"
    : step && step in ICONS
      ? (step as keyof typeof ICONS)
      : "interpret";
  const Icon = ICONS[kind];
  const swap = {
    initial: { y: "110%", opacity: 0 },
    animate: {
      y: 0,
      opacity: 1,
      transition: {
        duration: reduced ? 0 : 0.6,
        delay: reduced ? 0 : 0.1,
        ease: EXPO_OUT_CURVE,
      },
    },
    exit: {
      y: "-110%",
      opacity: 0,
      transition: {
        duration: reduced ? 0 : 0.35,
        ease: [0.55, 0.085, 0.68, 0.53] as const,
      },
    },
  };
  return (
    <div
      className="run-card"
      ref={root}
      data-motion-phase={picking ? "picks" : "working"}
    >
      <div className="run-head">
        <div className="run-icon">
          <AnimatePresence initial={false}>
            <motion.span key={kind} {...swap}>
              <Icon aria-hidden size={22} />
            </motion.span>
          </AnimatePresence>
        </div>
        <div className="run-text" role="status">
          <AnimatePresence initial={false}>
            <motion.span key={status} {...swap}>
              {status}
            </motion.span>
          </AnimatePresence>
        </div>
      </div>
      <div className="run-bar" aria-hidden>
        {STEPS.map((s, i) => (
          <i
            key={s}
            className={
              done || i <= STEPS.indexOf(step ?? "interpret") ? "done" : ""
            }
          />
        ))}
      </div>
      {candidates && (
        <>
          <p className="cloud-head">{candidates.total} Concerts considered</p>
          <div className="cloud" aria-label="Candidate Artists">
            {candidates.names.slice(0, 40).map((name) => (
              <span className="name" key={name}>
                {name}
              </span>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
