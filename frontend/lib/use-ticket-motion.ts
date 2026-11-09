import {
  useCallback,
  useLayoutEffect,
  useRef,
  useState,
  type RefObject,
} from "react";
import { useReducedMotion } from "motion/react";
import { Choreography, EXPO_IN_OUT, BACK_OUT } from "@/lib/choreography";

function rectangle(rect: DOMRect, radius: string) {
  return {
    left: `${rect.left}px`,
    top: `${rect.top}px`,
    width: `${rect.width}px`,
    height: `${rect.height}px`,
    borderRadius: radius,
  };
}
function frame(source: HTMLElement) {
  const box = source.querySelector<HTMLElement>(".card-photo") ?? source;
  return {
    rect: box.getBoundingClientRect(),
    radius: source.closest(".concerts-list")
      ? getComputedStyle(box).borderRadius
      : getComputedStyle(source).borderRadius,
  };
}
function clip(sheet: HTMLElement, photo: HTMLElement) {
  const s = sheet.getBoundingClientRect(),
    p = photo.getBoundingClientRect(),
    radius = getComputedStyle(sheet).borderRadius,
    stacked = p.width >= s.width - 1;
  return {
    photo: `inset(${Math.max(0, p.top - s.top)}px ${Math.max(0, s.right - p.right)}px ${Math.max(0, s.bottom - p.bottom)}px ${Math.max(0, p.left - s.left)}px round ${radius})`,
    whole: `inset(0px 0px 0px 0px round ${radius})`,
    radius: stacked ? `${radius} ${radius} 0 0` : `${radius} 0 0 ${radius}`,
    stacked,
  };
}

export function useTicketMotion(
  open: boolean,
  concertId: string | undefined,
  source: RefObject<HTMLElement | null>,
  onClosed: () => void,
) {
  const element = useRef<HTMLDivElement | null>(null);
  const [mounted, setMounted] = useState(false);
  const setElement = useCallback((node: HTMLDivElement | null) => {
    element.current = node;
    setMounted(Boolean(node));
  }, []);
  const reduced = useReducedMotion();
  const sequence = useRef<Choreography | null>(null);
  const flying = useRef<HTMLImageElement | null>(null);
  const closing = useRef(false);
  const restore = useRef<(() => void) | null>(null);

  useLayoutEffect(() => {
    const sheet = element.current;
    if (!open || !sheet) return;
    const scope = new Choreography();
    sequence.current = scope;
    closing.current = false;
    const photo = sheet.querySelector<HTMLElement>(".dialog-photo"),
      target = photo?.querySelector<HTMLImageElement>("img"),
      origin =
        source.current?.querySelector<HTMLImageElement>(".card-photo img");
    const details = [
      ...sheet.querySelectorAll<HTMLElement>(
        ".ticket-main > *, .ticket-stub, .dialog-actions, .decision-status",
      ),
    ];
    const close = sheet.querySelector<HTMLElement>(".dialog-close")!;
    const scrim = document.querySelector<HTMLElement>(".ticket-backdrop");
    const finish = () => {
      Object.assign(sheet.style, { opacity: "1", clipPath: "none" });
      details.forEach((e) =>
        Object.assign(e.style, { opacity: "1", transform: "none" }),
      );
      Object.assign(close.style, { opacity: "1", transform: "none" });
      if (target) target.style.opacity = "1";
      flying.current?.remove();
      flying.current = null;
      sheet.dataset.motionPhase = "open";
    };
    restore.current = () => {
      sequence.current?.cancel();
      origin?.style.removeProperty("opacity");
      flying.current?.remove();
      flying.current = null;
    };
    if (photo)
      sheet.style.setProperty(
        "--ticket-photo-height",
        `${photo.getBoundingClientRect().height}px`,
      );
    sheet.scrollTop = 0;
    sheet.dataset.motionPhase = "opening";
    if (reduced || !photo || !target || !origin || !source.current) {
      finish();
      return () => restore.current?.();
    }
    const from = frame(source.current),
      to = photo.getBoundingClientRect(),
      shape = clip(sheet, photo);
    const fly = document.createElement("img");
    fly.className = "photo-flight";
    fly.src = origin.currentSrc || origin.src;
    fly.alt = "";
    fly.setAttribute("aria-hidden", "true");
    Object.assign(fly.style, rectangle(from.rect, from.radius));
    document.body.append(fly);
    flying.current = fly;
    origin.style.opacity = "0";
    target.style.opacity = "0";
    Object.assign(sheet.style, { opacity: "0", clipPath: shape.photo });
    details.forEach((e) => (e.style.opacity = "0"));
    Object.assign(close.style, {
      opacity: "0",
      transform: "scale(0) rotate(-90deg)",
    });
    if (scrim) void scope.animate(scrim, [{ opacity: 0 }, { opacity: 1 }], 450);
    void (async () => {
      await scope.animate(
        fly,
        [rectangle(from.rect, from.radius), rectangle(to, shape.radius)],
        700,
        0,
        EXPO_IN_OUT,
      );
      if (!scope.live) return;
      target.style.opacity = "1";
      fly.remove();
      flying.current = null;
      sheet.style.opacity = "1";
      sheet.dataset.motionPhase = "unfolding";
      void scope.animate(
        sheet,
        [{ clipPath: shape.photo }, { clipPath: shape.whole }],
        600,
      );
      details.forEach(
        (el, i) =>
          void scope.animate(
            el,
            [
              {
                opacity: 0,
                transform: shape.stacked
                  ? "translateY(-16px)"
                  : "translateX(-24px)",
              },
              { opacity: 1, transform: "none" },
            ],
            550,
            20 + i * 40,
          ),
      );
      void scope.animate(
        close,
        [
          { opacity: 0, transform: "scale(0) rotate(-90deg)" },
          { opacity: 1, transform: "none" },
        ],
        500,
        150,
        BACK_OUT,
      );
      await scope.wait(Math.max(650, 570 + details.length * 40));
      if (scope.live) finish();
    })();
    const resize = () => {
      if (sheet.dataset.motionPhase !== "open" && !closing.current) {
        scope.cancel();
        finish();
      }
    };
    window.addEventListener("resize", resize);
    return () => {
      window.removeEventListener("resize", resize);
      restore.current?.();
    };
  }, [open, mounted, concertId, reduced, source]);

  const close = useCallback(() => {
    const sheet = element.current;
    if (closing.current) return;
    closing.current = true;
    const photo = sheet?.querySelector<HTMLElement>(".dialog-photo"),
      target = photo?.querySelector<HTMLImageElement>("img"),
      origin =
        source.current?.querySelector<HTMLImageElement>(".card-photo img");
    if (reduced || !sheet || !photo || !target || !origin || !source.current) {
      restore.current?.();
      onClosed();
      return;
    }
    const currentFly = flying.current,
      currentRect = currentFly?.getBoundingClientRect(),
      currentRadius = currentFly
        ? getComputedStyle(currentFly).borderRadius
        : null,
      currentClip = getComputedStyle(sheet).clipPath;
    sequence.current?.cancel();
    const scope = new Choreography();
    sequence.current = scope;
    sheet.dataset.motionPhase = "closing";
    const shape = clip(sheet, photo),
      to = frame(source.current),
      scrim = document.querySelector<HTMLElement>(".ticket-backdrop");
    void (async () => {
      if (!currentFly) {
        sheet
          .querySelectorAll<HTMLElement>(
            ".dialog-details > *, .ticket-main > *",
          )
          .forEach(
            (el) =>
              void scope.animate(el, [{ opacity: 1 }, { opacity: 0 }], 180),
          );
        await scope.animate(
          sheet,
          [
            { clipPath: currentClip === "none" ? shape.whole : currentClip },
            { clipPath: shape.photo },
          ],
          320,
          0,
          "ease-in",
        );
        if (!scope.live) return;
      }
      let fly = currentFly;
      const from = currentRect ?? photo.getBoundingClientRect();
      if (!fly) {
        fly = document.createElement("img");
        fly.className = "photo-flight";
        fly.src = target.currentSrc || target.src;
        fly.alt = "";
        fly.setAttribute("aria-hidden", "true");
        document.body.append(fly);
      }
      flying.current = fly;
      Object.assign(fly.style, rectangle(from, currentRadius ?? shape.radius));
      sheet.style.opacity = "0";
      if (scrim)
        void scope.animate(
          scrim,
          [{ opacity: 1 }, { opacity: 0 }],
          500,
          0,
          "ease-in-out",
        );
      await scope.animate(
        fly,
        [
          rectangle(from, currentRadius ?? shape.radius),
          rectangle(to.rect, to.radius),
        ],
        600,
        0,
        EXPO_IN_OUT,
      );
      if (scope.live) {
        origin.style.opacity = "";
        fly.remove();
        flying.current = null;
        onClosed();
      }
    })();
  }, [reduced, source, onClosed]);
  return { setElement, close };
}
