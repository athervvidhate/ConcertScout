"use client";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { useEffect, useState } from "react";
const LINES = [
  { lead: "Tame Impala in ", accent: "London" },
  { lead: "Jazz in ", accent: "New Orleans" },
  { lead: "Dreamy bands in ", accent: "SoCal" },
];
export function HomeHero({
  onCycle,
  returning,
}: {
  onCycle: (index: number) => void;
  returning: boolean;
}) {
  const [cycled, setCycled] = useState(false);
  const [line, setLine] = useState(0),
    reduced = useReducedMotion();
  useEffect(() => {
    if (reduced) return;
    let index = 0;
    const timer = setInterval(() => {
      index = (index + 1) % LINES.length;
      setCycled(true);
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
      <span className="roll" aria-live="off">
        <AnimatePresence initial={!returning}>
          <motion.span
            className="hero-line"
            key={line}
            initial={{ y: reduced ? 0 : "100%", opacity: reduced ? 1 : 0 }}
            animate={{
              y: 0,
              opacity: 1,
              transition: {
                duration: reduced ? 0 : returning || cycled ? 0.8 : 1,
                delay: reduced ? 0 : returning || cycled ? 0.18 : 0.12,
                ease: [0.16, 1, 0.3, 1],
              },
            }}
            exit={{
              y: reduced ? 0 : "-100%",
              opacity: 0,
              transition: {
                duration: reduced ? 0 : 0.5,
                ease: [0.7, 0, 0.84, 0],
              },
            }}
          >
            {LINES[line].lead}
            <b>{LINES[line].accent}</b>
          </motion.span>
        </AnimatePresence>
      </span>
    </motion.h1>
  );
}
