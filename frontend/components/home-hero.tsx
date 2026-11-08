"use client";
import dynamic from "next/dynamic";
import { motion, useReducedMotion } from "motion/react";
import { useEffect, useState, useSyncExternalStore } from "react";
const LINES = [
  { lead: "Tame Impala in ", accent: "London" },
  { lead: "Jazz in ", accent: "New Orleans" },
  { lead: "Dreamy bands in ", accent: "SoCal" },
];
// LongFlap supplies the two-stage, clipped 3D mechanics; the page supplies its own type and palette.
const FLAPS = LINES.map((item, id) => ({
  id,
  component: (
    <span className="hero-phrase">
      {item.lead}
      <b>{item.accent}</b>
    </span>
  ),
}));
const HeroFlap = dynamic(
  () => import("react-split-flap").then((module) => module.LongFlap),
  {
    ssr: false,
    loading: () => (
      <span className="hero-phrase">
        {LINES[0].lead}
        <b>{LINES[0].accent}</b>
      </span>
    ),
  },
);
const subscribeHydration = () => () => {};
const clientHydration = () => true;
const serverHydration = () => false;
export function HomeHero({
  onCycle,
  returning,
}: {
  onCycle: (index: number) => void;
  returning: boolean;
}) {
  const hydrated = useSyncExternalStore(
    subscribeHydration,
    clientHydration,
    serverHydration,
  );
  const [line, setLine] = useState(0),
    reduced = useReducedMotion();
  useEffect(() => {
    if (reduced) return;
    let index = 0;
    const timer = setInterval(() => {
      index = (index + 1) % LINES.length;
      setLine(index);
      onCycle(index);
    }, 3600);
    return () => clearInterval(timer);
  }, [reduced, onCycle]);
  return (
    <motion.h1
      className="headline"
      initial={returning ? { opacity: 0, y: reduced ? 0 : 20 } : false}
      animate={{ opacity: 1, y: 0 }}
      exit={{
        opacity: 0,
        y: reduced ? 0 : -14,
        transition: { duration: reduced ? 0 : 0.28 },
      }}
      transition={{
        duration: reduced ? 0 : 0.8,
        delay: reduced ? 0 : 0.3,
        ease: [0.16, 1, 0.3, 1],
      }}
    >
      <motion.span
        className="headline-lead"
        initial={
          returning ? false : { opacity: reduced ? 1 : 0, y: reduced ? 0 : 16 }
        }
        animate={{ opacity: 1, y: 0 }}
        transition={{
          duration: reduced ? 0 : 0.8,
          delay: reduced ? 0 : 0.05,
          ease: [0.16, 1, 0.3, 1],
        }}
      >
        Find a night of
      </motion.span>{" "}
      <span className="sr-only">
        {LINES[line].lead}
        {LINES[line].accent}
      </span>
      <div className="roll hero-flap" aria-hidden="true" data-hero-index={line}>
        {!hydrated || reduced ? (
          <span className="hero-phrase">
            {LINES[0].lead}
            <b>{LINES[0].accent}</b>
          </span>
        ) : (
          <HeroFlap
            flaps={FLAPS}
            displayId={line}
            animateOnMount={false}
            digitHeight={0}
            duration={640}
            timing={80}
            hinge={false}
            background="var(--bg)"
            fontColor="var(--ink)"
          />
        )}
      </div>
    </motion.h1>
  );
}
