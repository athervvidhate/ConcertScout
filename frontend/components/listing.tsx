import { formatConcertTime, formatMonthDay, presaleLine } from "@/lib/format";
import type { Concert } from "@/lib/search";
import { showTitle } from "@/lib/show-title";

type Props = {
  concert: Concert;
  /** The name the row leads with. It defaults to the Concert's first Artist. */
  artist?: string;
  /** Where the name links. It defaults to the Concert's tickets. */
  href?: string;
  /** Why this Concert is here, when the board's heading does not already say. */
  note?: string;
  /** Shows the state or province, for a board that spans more than one region. */
  anywhere?: boolean;
};

export function Listing({ concert, artist, href, note, anywhere = false }: Props) {
  const name = artist ?? concert.artists[0]?.name ?? concert.name;
  const title = showTitle(concert, name);
  const presale = presaleLine(concert);
  const city = [concert.city, anywhere ? concert.region : undefined].filter(Boolean).join(", ");
  return (
    <li className="listing">
      {concert.date ? (
        <time className="listing-date" dateTime={concert.date}>
          {formatMonthDay(concert.date)}
        </time>
      ) : (
        <span />
      )}
      <div className="listing-what">
        <a className="listing-artist" href={href ?? concert.url} target="_blank" rel="nofollow noopener noreferrer">
          {name}
        </a>
        {title && <p>{title}</p>}
        {note && <p className="listing-note">{note}</p>}
      </div>
      <div className="listing-where">
        {concert.venue && <p>{concert.venue}</p>}
        <p>{[city, formatConcertTime(concert)].filter(Boolean).join(" at ")}</p>
        {presale && <p className="listing-note">{presale}</p>}
      </div>
      <a
        className="listing-tickets"
        href={concert.url}
        target="_blank"
        rel="nofollow noopener noreferrer"
        aria-label={`Tickets for ${concert.name}`}
      >
        Tickets
      </a>
    </li>
  );
}
