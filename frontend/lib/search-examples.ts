import { useEffect, useState } from "react";

// Each shows a different way to Search. Keep the dates relative so the examples do not go stale.
export const SEARCH_EXAMPLES = [
  "Tame Impala in London next summer",
  "Jazz in New Orleans this weekend",
  "Dreamy bands in SoCal next month",
  "Like Four Tet and Caribou in NYC",
];

export function useSearchExample(active: boolean) {
  const [example, setExample] = useState(0);
  const [length, setLength] = useState(SEARCH_EXAMPLES[0].length);
  const [deleting, setDeleting] = useState(false);
  useEffect(() => {
    const motion = window.matchMedia("(prefers-reduced-motion: reduce)");
    if (!active || motion.matches) return;
    const full = SEARCH_EXAMPLES[example];
    const delay = length === full.length && !deleting ? 2400 : deleting ? 32 : 65;
    const timer = setTimeout(() => {
      if (length === full.length && !deleting) setDeleting(true);
      else if (length === 0 && deleting) {
        setExample((example + 1) % SEARCH_EXAMPLES.length);
        setDeleting(false);
      } else setLength(length + (deleting ? -1 : 1));
    }, delay);
    return () => clearTimeout(timer);
  }, [active, deleting, example, length]);
  return SEARCH_EXAMPLES[example].slice(0, length);
}
