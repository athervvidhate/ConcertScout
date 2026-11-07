import { EASE_OUT_CSS, flyDuration, GLIDE_GAP_MS, GLIDE_MS, GROW_MS } from "@/lib/poster-timing";

/**
 * Glides each Poster name from the wall to its spot at small size, then grows them together.
 * Reads the DOM once, animates only transform and opacity, and returns a cancel function.
 */
export function flyIn(wall: HTMLElement, poster: HTMLElement): () => void {
  const sources = Array.from(wall.querySelectorAll<HTMLElement>("[data-name]"));
  const targets = Array.from(poster.querySelectorAll<HTMLElement>("[data-name]"));
  const duration = flyDuration(targets.length);
  const growStart = (duration - GROW_MS) / duration;
  const sourceRects = new Map(sources.map((s) => [s.dataset.name, s.getBoundingClientRect()]));
  const targetRects = targets.map((target) => target.getBoundingClientRect());

  const animations = targets.flatMap((target, index) => {
    const to = targetRects[index];
    const from = sourceRects.get(target.dataset.name);
    const scale = from && to.width ? Math.min(1, from.width / to.width) : 1;
    const dx = from ? from.left + from.width / 2 - to.left - to.width / 2 : 0;
    const dy = from ? from.top + from.height / 2 - to.top - to.height / 2 : 0;
    const start = `translate(${dx}px, ${dy}px) scale(${scale})`;
    const land = `translate(0, 0) scale(${scale})`;
    const glideStart = (index * GLIDE_GAP_MS) / duration;
    const glideEnd = (index * GLIDE_GAP_MS + GLIDE_MS) / duration;

    target.style.willChange = "transform";
    const move = target.animate(
      [
        { transform: start, offset: 0 },
        { transform: start, offset: glideStart, easing: EASE_OUT_CSS },
        { transform: land, offset: glideEnd },
        { transform: land, offset: growStart, easing: EASE_OUT_CSS },
        { transform: "translate(0, 0) scale(1)", offset: 1 },
      ],
      { duration, fill: "both" },
    );
    move.onfinish = () => {
      target.style.willChange = "";
    };

    const pink = target.querySelector(".pink")!;
    const tint = pink.animate(
      index === 0
        ? [{ opacity: 1 }, { opacity: 1 }]
        : [
            { opacity: 1, offset: 0 },
            { opacity: 1, offset: growStart, easing: EASE_OUT_CSS },
            { opacity: 0, offset: 1 },
          ],
      { duration, fill: "both" },
    );
    // A pick past the 38 names on the wall has no name to fly from, so it fades in where it lands.
    const appear = from
      ? []
      : [
          target.animate(
            [
              { opacity: 0, offset: 0 },
              { opacity: 0, offset: glideStart, easing: EASE_OUT_CSS },
              { opacity: 1, offset: glideEnd },
              { opacity: 1, offset: 1 },
            ],
            { duration, fill: "both" },
          ),
        ];
    return [move, tint, ...appear];
  });

  return () => {
    animations.forEach((animation) => animation.cancel());
    targets.forEach((target) => {
      target.style.willChange = "";
    });
  };
}
