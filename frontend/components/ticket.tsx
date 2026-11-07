import Image from "next/image";
import { Fragment } from "react";

import { ArtistPanel } from "@/components/artist-panel";
import { formatDate, formatDayShort, formatMonthDay, formatPrice, formatTime, presaleLine } from "@/lib/format";
import type { Recommendation } from "@/lib/search";

export function nameOf({ concert }: Recommendation): string {
  return concert.artists[0]?.name ?? concert.name;
}

function Price({ text }: { text: string }) {
  const parts = text.split(" to ");
  const longest = Math.max(...parts.map((part) => part.length));
  return (
    <span className="price" style={{ fontSize: `min(46px, ${140 / longest}cqw)` }}>
      {parts.map((part, index) => (
        <Fragment key={part + index}>
          {index > 0 && <span className="price-to"> to </span>}
          <span className="price-value">{part}</span>
        </Fragment>
      ))}
    </span>
  );
}

export function Ticket({ recommendation, rank }: { recommendation: Recommendation; rank: number }) {
  const { concert, reason } = recommendation;
  const details = [
    concert.venue,
    concert.city,
    concert.region,
    concert.date && formatDayShort(concert.date),
    concert.time && formatTime(concert.time),
  ].filter(Boolean);
  const presale = presaleLine(concert);

  return (
    <article className="ticket" data-color={rank % 5}>
      {concert.image && (
        <div className="ticket-photo">
          {/* Ticketmaster already sizes these, so nothing is resized here. */}
          <Image src={concert.image} alt="" fill unoptimized draggable={false} />
        </div>
      )}
      <div className="ticket-main">
        {concert.date && (
          <time className="date" dateTime={concert.date} aria-label={formatDate(concert.date)}>
            {formatMonthDay(concert.date)}
          </time>
        )}
        <h2>
          <ArtistPanel name={nameOf(recommendation)} />
        </h2>
        {reason && <p>{reason}</p>}
        <p className="venue">{details.join(", ")}</p>
        {presale && <p className="presale">{presale}</p>}
      </div>
      <div className="ticket-stub">
        <span>Admit one</span>
        {concert.price && <Price text={formatPrice(concert.price, true)} />}
        <a
          href={concert.url}
          target="_blank"
          rel="noopener noreferrer"
          aria-label={`Tickets for ${concert.name}`}
        >
          Tickets
        </a>
      </div>
    </article>
  );
}
