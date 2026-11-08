"use client";

import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { useEffect, useState } from "react";

const LINES = [
  "Tame Impala in London",
  "Jazz in New Orleans",
  "Dreamy bands in SoCal",
];
export function HomeHero({ onCycle }: { onCycle: (index: number) => void }) {
  const [line, setLine] = useState(0);
  const reduced = useReducedMotion();
  useEffect(() => {
    if (reduced) return;
    let index = 0;
    const timer = setInterval(() => {
      index = (index + 1) % LINES.length;
      setLine(index);
      onCycle(index);
    }, 4200);
    return () => clearInterval(timer);
  }, [reduced, onCycle]);
  return (
    <h1 className="headline">
      <span className="headline-lead">Find a night of</span>
      <span className="roll" aria-live="off">
        <AnimatePresence mode="wait" initial={false}>
          <motion.span
            className="hero-line"
            key={line}
            initial={{ opacity: 0, y: reduced ? 0 : 25 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: reduced ? 0 : -25 }}
            transition={{ duration: reduced ? 0 : 0.35 }}
          >
            {LINES[line]}
          </motion.span>
        </AnimatePresence>
      </span>
    </h1>
  );
}
