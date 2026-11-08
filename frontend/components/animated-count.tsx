"use client";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { useLayoutEffect, useRef } from "react";
import { Choreography } from "@/lib/choreography";

export function AnimatedCount({ value }: { value: number }) {
  const element = useRef<HTMLSpanElement>(null),
    reduced = useReducedMotion();
  useLayoutEffect(() => {
    if (!element.current || reduced) return;
    const scope = new Choreography();
    scope.count(value, 900, (n) => {
      if (element.current) element.current.textContent = String(n);
    });
    return () => scope.cancel();
  }, [value, reduced]);
  return (
    <>
      <span aria-hidden ref={element}>
        {value}
      </span>
      <span className="sr-only">{value}</span>
    </>
  );
}
export function SavedCount({ value }: { value: number }) {
  const reduced = useReducedMotion();
  return (
    <AnimatePresence initial={false}>
      {value > 0 && (
        <motion.span
          className="saved-count"
          aria-label={`${value} saved`}
          initial={{ scale: reduced ? 1 : 0 }}
          animate={{ scale: 1 }}
          exit={{ scale: reduced ? 1 : 0 }}
          transition={{
            duration: reduced ? 0 : 0.6,
            ease: [0.34, 1.56, 0.64, 1],
          }}
        >
          <AnimatePresence mode="popLayout" initial={false}>
            <motion.span
              key={value}
              initial={{ y: reduced ? 0 : "100%", opacity: reduced ? 1 : 0 }}
              animate={{ y: 0, opacity: 1 }}
              exit={{ y: reduced ? 0 : "-100%", opacity: 0 }}
              transition={{
                duration: reduced ? 0 : 0.45,
                ease: [0.16, 1, 0.3, 1],
              }}
            >
              {value}
            </motion.span>
          </AnimatePresence>
        </motion.span>
      )}
    </AnimatePresence>
  );
}
