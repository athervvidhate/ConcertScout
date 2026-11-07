import { useEffect, useState } from "react";

export const SEARCH_EXAMPLES = [
  "Khruangbin in Chicago next week",
  "UKG in SF this month",
  "Indie rock in Texas in December",
  "Jazz in New Orleans this weekend",
  "Four Tet and Caribou in London",
  "DnB in Philadelphia next month",
  "Dream pop in Seattle in January",
  "R&B in Atlanta this Friday",
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
