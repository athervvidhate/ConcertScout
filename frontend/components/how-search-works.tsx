"use client";

import { useInView, useReducedMotion } from "motion/react";
import Image from "next/image";
import { useEffect, useLayoutEffect, useRef } from "react";
import { SearchChips } from "@/components/search-chips";
import { nameOf } from "@/components/ticket";
import { Choreography, BACK_OUT, EXPO_OUT } from "@/lib/choreography";
import { HOW_EXAMPLE as example } from "@/lib/how-example";
import { formatDayShort, formatMonthDay } from "@/lib/format";

const picks = example.poster.recommendations;
const candidates = example.candidates!;
const picked = new Set(
  picks.flatMap((r) => r.concert.artists.map((a) => a.name)),
);
const sample = [
  ...new Set([
    ...picks
      .flatMap((r) => r.concert.artists.map((a) => a.name))
      .filter((n) => candidates.names.includes(n)),
    ...candidates.names,
  ]),
]
  .slice(0, 16)
  .sort((a, b) => candidates.names.indexOf(a) - candidates.names.indexOf(b));

export function HowSearchWorks() {
  const root = useRef<HTMLElement>(null);
  const visible = useInView(root, { margin: "-20% 0px -30% 0px" });
  const reduced = useReducedMotion();
  useLayoutEffect(() => {
    const section = root.current!;
    const panels = [
      ...section.querySelectorAll<HTMLElement>("[data-how-panel]"),
    ];
    let width = 0;
    const measure = () => {
      const heights = panels.map((panel) => {
        const ghost = panel.cloneNode(true) as HTMLElement;
        Object.assign(ghost.style, {
          position: "absolute",
          visibility: "hidden",
          height: "auto",
          width: `${panel.offsetWidth}px`,
        });
        ghost
          .querySelectorAll<HTMLElement>("[data-demo-part]")
          .forEach((el) =>
            Object.assign(el.style, { opacity: "1", transform: "none" }),
          );
        const words = ghost.querySelector("[data-typed]");
        if (words) words.textContent = example.text;
        const count = ghost.querySelector("[data-count]");
        if (count) count.textContent = String(candidates.total);
        panel.after(ghost);
        const height = ghost.offsetHeight;
        ghost.remove();
        return height;
      });
      const tops = panels.map((p) =>
        Math.round(p.parentElement!.getBoundingClientRect().top),
      );
      const oneRow = tops.every((t) => t === tops[0]);
      panels.forEach(
        (p, i) =>
          (p.style.height = `${oneRow ? Math.max(...heights) : heights[i]}px`),
      );
    };
    measure();
    void document.fonts.ready.then(() => {
      if (section.isConnected) measure();
    });
    const observer = new ResizeObserver((entries) => {
      const next = entries[0].contentRect.width;
      if (next !== width) {
        width = next;
        measure();
      }
    });
    observer.observe(section);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const section = root.current!;
    const scope = new Choreography();
    const parts = [
      ...section.querySelectorAll<HTMLElement>("[data-demo-part]"),
    ];
    const steps = [...section.querySelectorAll<HTMLElement>(".how-step")];
    const words = section.querySelector<HTMLElement>("[data-typed]")!;
    const chips = [
      ...section.querySelectorAll<HTMLElement>(".demo-chips .chip"),
    ];
    const names = [
      ...section.querySelectorAll<HTMLElement>(".demo-names .name"),
    ];
    const rows = [...section.querySelectorAll<HTMLElement>(".demo-picks > *")];
    const counter = section.querySelector<HTMLElement>("[data-count]")!;
    const mark = (step: number) => {
      section.dataset.phase =
        step < 0 ? "reset" : ["typing", "candidates", "picks", "hold"][step];
      steps.forEach((el, i) => {
        el.classList.toggle("active", i === step);
        el.classList.toggle("done", i < step);
      });
    };
    const reset = () => {
      parts.forEach((el) =>
        Object.assign(el.style, { opacity: "1", transform: "none" }),
      );
      [...chips, ...names, ...rows].forEach((el) =>
        Object.assign(el.style, { opacity: "0", transform: "none" }),
      );
      names.forEach((el) => el.classList.remove("pick"));
      words.textContent = "";
      counter.textContent = "";
      section.querySelector<HTMLElement>(".demo-count")!.style.opacity = "0";
    };
    if (reduced) {
      section.querySelector<HTMLElement>(".demo-count")!.style.opacity = "1";
      words.textContent = example.text;
      counter.textContent = String(candidates.total);
      parts.forEach((el) =>
        Object.assign(el.style, { opacity: "1", transform: "none" }),
      );
      [...chips, ...rows].forEach((el) => (el.style.opacity = "1"));
      names.forEach((el) => {
        el.classList.toggle("pick", picked.has(el.textContent ?? ""));
        el.style.opacity = picked.has(el.textContent ?? "") ? "1" : ".25";
      });
      mark(3);
      return () => scope.cancel();
    }
    if (!visible) {
      if (section.dataset.phase === "ready") reset();
      return () => scope.cancel();
    }
    async function loop() {
      reset();
      while (scope.live) {
        mark(0);
        for (let i = 1; i <= example.text.length && scope.live; i++) {
          words.textContent = example.text.slice(0, i);
          await scope.wait(34);
        }
        if (!scope.live) return;
        chips.forEach(
          (el, i) =>
            void scope.animate(
              el,
              [
                { opacity: 0, transform: "translateY(10px) scale(.85)" },
                { opacity: 1, transform: "none" },
              ],
              600,
              i * 100,
              BACK_OUT,
            ),
        );
        await scope.wait(1100);
        if (!scope.live) return;
        mark(1);
        section.querySelector<HTMLElement>(".demo-count")!.style.opacity = "1";
        scope.count(
          candidates.total,
          1200,
          (n) => (counter.textContent = String(n)),
        );
        names.forEach(
          (el, i) =>
            void scope.animate(
              el,
              [
                { opacity: 0, transform: "translateY(8px)" },
                { opacity: 1, transform: "none" },
              ],
              450,
              i * 40,
              EXPO_OUT,
            ),
        );
        await scope.wait(1700);
        if (!scope.live) return;
        section.dataset.phase = "narrowing";
        const narrowing: Promise<void>[] = [];
        names.forEach((el) => {
          const selected = picked.has(el.textContent ?? "");
          el.classList.toggle("pick", selected);
          if (!selected)
            narrowing.push(
              scope.animate(el, [{ opacity: 1 }, { opacity: 0.25 }], 500),
            );
        });
        await Promise.all(narrowing);
        if (!scope.live) return;
        await scope.wait(200);
        if (!scope.live) return;
        mark(2);
        rows.forEach(
          (el, i) =>
            void scope.animate(
              el,
              [
                { opacity: 0, transform: "translateY(14px)" },
                { opacity: 1, transform: "none" },
              ],
              700,
              i * 120,
            ),
        );
        await scope.wait(900);
        if (!scope.live) return;
        mark(3);
        await scope.wait(2400);
        if (!scope.live) return;
        mark(-1);
        await Promise.all(
          parts.map((el) =>
            scope.animate(
              el,
              [
                { opacity: 1, transform: "none" },
                { opacity: 0, transform: "translateY(-8px)" },
              ],
              600,
              0,
              "ease-in-out",
            ),
          ),
        );
        if (!scope.live) return;
        reset();
        await scope.wait(350);
      }
    }
    void loop();
    return () => scope.cancel();
  }, [visible, reduced]);

  return (
    <section
      className="how"
      aria-labelledby="home-how"
      ref={root}
      data-phase="ready"
    >
      <div className="how-inner">
        <header className="how-head">
          <h2 id="home-how">How a Search works</h2>
          <p>
            One real Search, replayed: <q>{example.text}</q>
          </p>
        </header>
        <ol className="how-steps">
          <li className="how-step">
            <span className="how-num">1</span>
            <h3>Say it your way</h3>
            <p>Name an Artist, a sound, a place or dates. Shorthand works.</p>
            <div className="how-demo demo-words" data-how-panel>
              <div className="demo-input" data-demo-part>
                <span data-typed>{example.text}</span>
                <span className="caret" aria-hidden />
              </div>
              <div className="demo-chips" data-demo-part>
                <SearchChips interpreted={example.interpreted!} compact />
              </div>
            </div>
          </li>
          <li className="how-step">
            <span className="how-num">2</span>
            <h3>It checks real listings</h3>
            <p>Concerts in the shortlist, from real Ticketmaster listings.</p>
            <div className="how-demo demo-pool" data-how-panel>
              <div className="demo-count" data-demo-part>
                <b data-count>{candidates.total}</b>Concerts considered near{" "}
                {example.interpreted?.region ?? example.interpreted?.place}
              </div>
              <div className="demo-names" data-demo-part>
                {sample.map((name) => (
                  <span className="name" key={name}>
                    {name}
                  </span>
                ))}
                {candidates.names.length > sample.length && (
                  <span className="name more">
                    +{candidates.names.length - sample.length} more
                  </span>
                )}
              </div>
            </div>
          </li>
          <li className="how-step">
            <span className="how-num">3</span>
            <h3>You get the ones that fit</h3>
            <p>Each pick says why. Save it or go get tickets.</p>
            <div className="how-demo" data-how-panel>
              <div className="demo-picks" data-demo-part>
                {picks.map((r) => (
                  <div className="demo-pick" key={r.concert.id}>
                    {r.concert.image && (
                      <Image
                        src={r.concert.image}
                        alt=""
                        width={64}
                        height={48}
                        unoptimized
                        loading="lazy"
                      />
                    )}
                    <div>
                      <b>{nameOf(r)}</b>
                      <span>
                        {[
                          r.concert.date &&
                            `${formatDayShort(r.concert.date)}, ${formatMonthDay(r.concert.date)}`,
                          r.concert.venue,
                        ]
                          .filter(Boolean)
                          .join(" · ")}
                      </span>
                    </div>
                  </div>
                ))}
                <p className="demo-why">
                  <b>Why {nameOf(picks[0])}:</b> {picks[0].reason}
                </p>
              </div>
            </div>
          </li>
        </ol>
      </div>
    </section>
  );
}
