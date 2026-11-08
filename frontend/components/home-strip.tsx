import { SEARCH_EXAMPLES } from "@/lib/search-examples";
import Image from "next/image";
import { nameOf } from "@/components/ticket";
import type { HomeExample } from "@/lib/home-examples";

export function HomeStrip({
  examples,
  onExample,
  active,
}: {
  examples: HomeExample[];
  active: number;
  onExample: (text: string) => void;
}) {
  const picks = examples
    .flatMap((example) =>
      example.poster.recommendations.slice(0, 2).map((r) => ({ example, r })),
    )
    .filter(({ r }) => r.concert.image)
    .slice(0, 6);
  if (!picks.length) return null;
  return (
    <section className="home-strip" aria-label="Found by real Searches">
      <header>
        <h2>Found by real Searches</h2>
        <p>Open an example. See what made the cut.</p>
      </header>
      <div className="strip">
        {picks.map(({ r, example }) => (
          <button
            className="strip-tile"
            data-active={example.text === SEARCH_EXAMPLES[active]}
            key={`${example.text}-${r.concert.id}`}
            onClick={() => onExample(example.text)}
            aria-label={`See ${example.text}`}
          >
            <Image
              src={r.concert.image!}
              alt=""
              fill
              unoptimized
              sizes="(max-width:640px) 50vw, 20vw"
            />
            <span>
              <b>{nameOf(r)}</b>
              <small>{r.concert.city}</small>
            </span>
          </button>
        ))}
      </div>
    </section>
  );
}
