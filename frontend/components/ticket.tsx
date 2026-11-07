import { Pointer } from "lucide-react";
import Image from "next/image";
import { Fragment } from "react";

import { ArtistPanel } from "@/components/artist-panel";
import { byVenue, formatDate, formatDayShort, formatMonthDay, formatConcertTime, formatPrice, presaleLine } from "@/lib/format";
import type { Concert, Recommendation } from "@/lib/search";

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

function placeOf({ venue, city, region }: Concert): string {
  return [venue, city, region].filter(Boolean).join(", ");
}

function OtherDates({ concerts }: { concerts: Concert[] }) {
  const count = concerts.length === 1 ? "1 more date" : `${concerts.length} more dates`;
  return (
    <details className="other-dates">
      <summary>{count}</summary>
      <ul className="other-venues">
        {byVenue(concerts).map((shows) => {
          const { id, venue, city, region } = shows[0];
          return (
            <li key={id}>
              <p className="other-place">{[city, region].filter(Boolean).join(", ")}</p>
              {venue && <p className="other-venue">{venue}</p>}
              <ul className="other-chips">
                {shows.map((concert) => (
                  <li key={concert.id}>
                    <a
                      href={concert.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      aria-label={`Tickets for ${[concert.date && formatDate(concert.date), placeOf(concert)].filter(Boolean).join(", ")}`}
                    >
                      {concert.date
                        ? `${formatDayShort(concert.date)} ${formatMonthDay(concert.date)}`
                        : "Tickets"}
                    </a>
                  </li>
                ))}
              </ul>
            </li>
          );
        })}
      </ul>
    </details>
  );
}

type TicketProps = {
  recommendation: Recommendation;
  rank: number;
  // Shown once, on a visitor's first Ticket, because the name doesn't look like a button.
  artistHint?: boolean;
  onArtistOpen?: () => void;
};

export function Ticket({ recommendation, rank, artistHint, onArtistOpen }: TicketProps) {
  const { concert, reason, also = [] } = recommendation;
  const details = [
    placeOf(concert),
    concert.date && formatDayShort(concert.date),
    formatConcertTime(concert),
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
          <ArtistPanel name={nameOf(recommendation)} onOpen={onArtistOpen} />
        </h2>
        {artistHint && (
          <p className="artist-hint">
            <Pointer aria-hidden size={15} />
            Tap the name for more
          </p>
        )}
        {reason && <p>{reason}</p>}
        <p className="venue">{details.join(", ")}</p>
        {presale && <p className="presale">{presale}</p>}
        {also.length > 0 && <OtherDates concerts={also} />}
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
