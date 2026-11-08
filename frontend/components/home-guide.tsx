"use client";

import { Button } from "@base-ui/react/button";
import { useInView, useReducedMotion } from "motion/react";
import Image from "next/image";
import { useEffect, useRef, useState } from "react";
import type { HomeExample } from "@/lib/home-examples";
import { nameOf } from "@/components/ticket";

type Props = {
  personal: boolean;
  locationLabel: string;
  onLocation: () => void;
  onTaste: () => void;
  example?: HomeExample;
};

export function HomeGuide({
  personal,
  locationLabel,
  onLocation,
  onTaste,
  example,
}: Props) {
  const ref = useRef<HTMLElement>(null);
  const inView = useInView(ref, { amount: 0.2 });
  const reduced = useReducedMotion();
  const [step, setStep] = useState(0);
  useEffect(() => {
    if (!inView || reduced) return;
    const timer = setInterval(() => setStep((s) => (s + 1) % 4), 2200);
    return () => clearInterval(timer);
  }, [inView, reduced]);
  const stage = reduced ? 3 : step;
  const picks = example?.poster.recommendations.slice(0, 3) ?? [];
  return (
    <div className="home-guide">
      <section className="how" aria-labelledby="home-how" ref={ref}>
        <header className="how-head">
          <h2 id="home-how">How a Search works</h2>
          <p>
            {example ? (
              <>
                A real Search: <q>{example.text}</q>
              </>
            ) : (
              "Your words become a Poster of real Concerts."
            )}
          </p>
        </header>
        <ol className="how-steps">
          <li className="how-step">
            <span className="how-num">1</span>
            <h3>Say it your way</h3>
            <p>Name an Artist, a sound or a city. Dates are optional.</p>
            {example && (
              <div
                className="how-demo"
                style={{ opacity: stage >= 1 ? 1 : 0 }}
                aria-hidden={stage < 1}
              >
                <p>{example.text}</p>
                <div className="cloud">
                  {[
                    ...(example.interpreted?.artists ?? []),
                    ...(example.interpreted?.genres ?? []),
                    example.interpreted?.region ?? example.interpreted?.place,
                  ]
                    .filter(Boolean)
                    .map((n) => (
                      <span className="name" key={n}>
                        {n}
                      </span>
                    ))}
                </div>
              </div>
            )}
          </li>
          <li className="how-step">
            <span className="how-num">2</span>
            <h3>Check the listings</h3>
            <p>Real Concerts meet Artists who sound like your Taste.</p>
            {example && (
              <div
                className="how-demo"
                style={{ opacity: stage >= 2 ? 1 : 0 }}
                aria-hidden={stage < 2}
              >
                <p>{example.candidates?.total} Concerts considered</p>
                <div className="cloud">
                  {example.candidates?.names.slice(0, 8).map((n) => (
                    <span className="name" key={n}>
                      {n}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </li>
          <li className="how-step">
            <span className="how-num">3</span>
            <h3>Find your next night out</h3>
            <p>Open a Ticket for the details. Save what you like.</p>
            {example && (
              <div
                className="how-demo demo-picks"
                style={{ opacity: stage >= 3 ? 1 : 0 }}
                aria-hidden={stage < 3}
              >
                {picks.map((r) => (
                  <div className="demo-pick" key={r.concert.id}>
                    {r.concert.image && (
                      <Image
                        src={r.concert.image}
                        width={64}
                        height={48}
                        unoptimized
                        alt=""
                        loading="lazy"
                      />
                    )}
                    <span>
                      <b>{nameOf(r)}</b>
                      {r.concert.venue}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </li>
        </ol>
      </section>
      {personal && (
        <section className="home-personal" aria-labelledby="home-yours">
          <div>
            <h2 id="home-yours">Make it yours</h2>
            <p>
              Bring the Artists you already play. Connect Spotify or import your
              Taste, and share your location to find Concerts near you.
            </p>
          </div>
          <div className="yours-actions">
            <Button onClick={onTaste}>Add your Taste</Button>
            <Button onClick={onLocation}>{locationLabel}</Button>
          </div>
        </section>
      )}
    </div>
  );
}
