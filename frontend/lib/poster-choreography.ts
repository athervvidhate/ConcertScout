import { Choreography, EXPO_IN_OUT } from "@/lib/choreography";

export type NameFrame = {
  rect: DOMRect;
  fontSize: number;
  padding: number;
  color: string;
  background: string;
  text: string;
};
export function captureNames(root: HTMLElement): Map<string, NameFrame> {
  return new Map(
    [...root.querySelectorAll<HTMLElement>(".name.pick")].map((el) => {
      const style = getComputedStyle(el);
      return [
        el.textContent ?? "",
        {
          rect: el.getBoundingClientRect(),
          fontSize: parseFloat(style.fontSize),
          padding: parseFloat(style.paddingLeft),
          color: style.color,
          background: style.backgroundColor,
          text: el.textContent ?? "",
        },
      ];
    }),
  );
}

/** Same two-type pill flight and crop reveal as the approved study, using native timelines. */
export function revealPoster(
  root: HTMLElement,
  from: Map<string, NameFrame>,
  scope: Choreography,
  viewChange = false,
) {
  const cleanups: (() => void)[] = [];
  root.querySelectorAll<HTMLElement>(".concert-card").forEach((card, index) => {
    const delay = (viewChange ? 0 : 100) + index * (viewChange ? 40 : 70);
    if (viewChange)
      void scope.animate(
        card,
        [
          { opacity: 0, transform: "translateY(16px)" },
          { opacity: 1, transform: "none" },
        ],
        550,
        delay,
      );
    else
      void scope
        .animate(
          card,
          [
            { clipPath: "inset(0 0 100% 0 round 16px)" },
            { clipPath: "inset(0 0 0% 0 round 16px)" },
          ],
          1000,
          delay,
          EXPO_IN_OUT,
        )
        .then(() => {
          if (scope.live) card.style.clipPath = "";
        });
    const img = card.querySelector(".card-photo img");
    if (img)
      void scope.animate(
        img,
        [
          { transform: `scale(${viewChange ? 1.06 : 1.18})` },
          { transform: "none" },
        ],
        viewChange ? 800 : 1400,
        delay,
      );
    const title = card.querySelector<HTMLElement>(
      ".card-name, .solo-body .ticket-main h2",
    );
    if (!title) return;
    const start = from.get(title.textContent ?? "");
    if (!start || viewChange) {
      void scope.animate(
        title,
        [
          { opacity: 0, transform: "translateY(16px)" },
          { opacity: 1, transform: "none" },
        ],
        700,
        500 + index * 70,
      );
      return;
    }
    const end = title.getBoundingClientRect(),
      style = getComputedStyle(title);
    const range = document.createRange();
    range.selectNodeContents(title);
    const text = range.getBoundingClientRect();
    const titleSize = parseFloat(style.fontSize),
      k = (start.fontSize * 1.15) / titleSize,
      pad = start.padding / k;
    const endX = titleSize * 0.18,
      endY = titleSize * 0.08;
    const fly = document.createElement("div");
    fly.className = "name-flight";
    fly.setAttribute("aria-hidden", "true");
    const pill = document.createElement("span"),
      display = document.createElement("span");
    pill.className = "as-pill";
    display.className = "as-title";
    pill.textContent = start.text;
    display.textContent = title.textContent;
    Object.assign(pill.style, {
      left: `${pad}px`,
      fontSize: `${start.fontSize / k}px`,
      color: start.color,
    });
    Object.assign(display.style, {
      left: `${pad}px`,
      width: `${Math.ceil(text.width) + 1}px`,
      font: style.font,
      textTransform: style.textTransform,
      letterSpacing: style.letterSpacing,
      color: style.color,
      opacity: "0",
    });
    const initial = {
      left: `${start.rect.left}px`,
      top: `${start.rect.top}px`,
      width: `${start.rect.width / k}px`,
      height: `${start.rect.height / k}px`,
      transform: `scale(${k})`,
    };
    Object.assign(fly.style, initial, { backgroundColor: start.background });
    fly.append(pill, display);
    document.body.append(fly);
    title.style.opacity = "0";
    const cleanup = () => {
      title.style.opacity = "";
      fly.remove();
    };
    cleanups.push(cleanup);
    const timing = 120 + index * 60;
    void Promise.all([
      scope.animate(
        fly,
        [
          initial,
          {
            left: `${end.left - endX}px`,
            top: `${end.top - endY}px`,
            width: `${text.width + endX * 2}px`,
            height: `${text.height + endY * 2}px`,
            transform: "scale(1)",
          },
        ],
        950,
        timing,
        EXPO_IN_OUT,
      ),
      scope.animate(
        display,
        [{ left: `${pad}px` }, { left: `${endX}px` }],
        950,
        timing,
        EXPO_IN_OUT,
      ),
      scope.animate(
        pill,
        [{ opacity: 1 }, { opacity: 0 }],
        114,
        timing,
        "linear",
      ),
      scope.animate(
        display,
        [{ opacity: 0 }, { opacity: 1 }],
        133,
        timing + 76,
        "linear",
      ),
      scope.animate(
        fly,
        [
          { backgroundColor: start.background },
          { backgroundColor: "rgba(0,0,0,0)" },
        ],
        380,
        timing + 427,
        "ease-in-out",
      ),
    ]).then(cleanup);
  });
  return () => {
    scope.cancel();
    cleanups.forEach((cleanup) => cleanup());
  };
}
