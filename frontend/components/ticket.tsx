import { ChevronLeft, ChevronRight, Pointer } from "lucide-react";
import { Fragment, useRef, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";

import { ArtistPanel } from "@/components/artist-panel";
import { ConcertPhoto, SourceLink } from "@/components/concert-source";
import { ListenButton, ListenStage } from "@/components/listen";
import {
  byVenue,
  formatDate,
  formatDayShort,
  formatMonthDay,
  formatConcertTime,
  formatPrice,
  presaleLine,
} from "@/lib/format";
import type { Concert, Recommendation } from "@/lib/search";

/** What a Recommendation is called. With no Lineup that is the Concert's own name, never an Artist. */
export function nameOf({ concert }: Recommendation): string {
  return concert.artists[0]?.name ?? concert.name;
}

function Price({ text }: { text: string }) {
  const parts = text.split(" to ");
  const longest = Math.max(...parts.map((part) => part.length));
  return (
    <span
      className="price"
      style={{ fontSize: `min(46px, ${140 / longest}cqw)` }}
    >
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

function moreDates(count: number): string {
  return count === 1 ? "1 more date" : `${count} more dates`;
}

/** The headliner's other dates, by venue. It takes the details' place rather than adding to them. */
function DatesPane({ concerts }: { concerts: Concert[] }) {
  return (
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
                  <SourceLink
                    href={concert.url}
                    aria-label={`Tickets for ${[concert.date && formatDate(concert.date), placeOf(concert)].filter(Boolean).join(", ")}`}
                  >
                    {concert.date
                      ? `${formatDayShort(concert.date)} ${formatMonthDay(concert.date)}`
                      : "Tickets"}
                  </SourceLink>
                </li>
              ))}
            </ul>
          </li>
        );
      })}
    </ul>
  );
}

type TicketProps = {
  recommendation: Recommendation;
  rank: number;
  // Shown once, on a visitor's first Ticket, because the name doesn't look like a button.
  artistHint?: boolean;
  onArtistOpen?: () => void;
  /** Set where the photograph lives outside the Ticket, which then also holds Listen's stage. */
  hidePhoto?: boolean;
  listening?: boolean;
  onListen?: (listening: boolean) => void;
};

export function Ticket({
  recommendation,
  rank,
  artistHint,
  onArtistOpen,
  hidePhoto,
  listening: shared,
  onListen,
}: TicketProps) {
  const { concert, reason, also = [] } = recommendation;
  const [own, setOwn] = useState(false);
  const listening = onListen ? !!shared : own;
  const listen = onListen ?? setOwn;
  const [view, setView] = useState<"details" | "dates">("details");
  const reduced = useReducedMotion();
  // After a swap, focus lands on the control that swaps back, once the new pane mounts.
  const moved = useRef(false);
  const focusAfterSwap = (node: HTMLButtonElement | null) => {
    if (node && moved.current) {
      moved.current = false;
      node.focus();
    }
  };
  const swap = (next: "details" | "dates") => {
    moved.current = true;
    setView(next);
  };
  // Only an Artist has a panel or a Preview. A Concert with no Lineup is just its title.
  const headliner = concert.artists[0]?.name;
  const details = [
    placeOf(concert),
    concert.date && formatDayShort(concert.date),
    formatConcertTime(concert),
  ].filter(Boolean);
  const presale = presaleLine(concert);

  return (
    <article className="ticket" data-color={rank % 5}>
      {!hidePhoto && (
        <div className="ticket-media">
          <ConcertPhoto
            concert={concert}
            className="ticket-photo"
            sizes="(max-width: 600px) 100vw, 800px"
            draggable={false}
          />
          {headliner && <ListenStage name={headliner} listening={listening} />}
        </div>
      )}
      <div className="ticket-main">
        {/* One pane at a time, so the Ticket never grows to fit both. */}
        <AnimatePresence mode="wait" initial={false}>
          {view === "details" ? (
            <motion.div
              key="details"
              className="ticket-pane"
              initial={{ opacity: 0, x: reduced ? 0 : -16 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: reduced ? 0 : -16 }}
              transition={{ duration: reduced ? 0 : 0.18 }}
            >
              {concert.date && (
                <time
                  className="date"
                  dateTime={concert.date}
                  aria-label={formatDate(concert.date)}
                >
                  {formatMonthDay(concert.date)}
                </time>
              )}
              <h2>
                {headliner ? (
                  <ArtistPanel name={headliner} onOpen={onArtistOpen} />
                ) : (
                  concert.name
                )}
              </h2>
              {headliner && artistHint && (
                <p className="artist-hint">
                  <Pointer aria-hidden size={15} />
                  Tap the name for more
                </p>
              )}
              {reason && <p>{reason}</p>}
              <p className="venue">{details.join(", ")}</p>
              {presale && <p className="presale">{presale}</p>}
              {(headliner || also.length > 0) && (
                <div className="ticket-pills">
                  {headliner && (
                    <ListenButton name={headliner} listening={listening} onListen={listen} />
                  )}
                  {also.length > 0 && (
                    <button
                      ref={focusAfterSwap}
                      type="button"
                      className="ticket-pill"
                      onClick={() => swap("dates")}
                    >
                      {moreDates(also.length)}
                      <ChevronRight aria-hidden size={16} />
                    </button>
                  )}
                </div>
              )}
            </motion.div>
          ) : (
            <motion.div
              key="dates"
              className="ticket-pane"
              initial={{ opacity: 0, x: reduced ? 0 : 16 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: reduced ? 0 : 16 }}
              transition={{ duration: reduced ? 0 : 0.18 }}
            >
              <button
                ref={focusAfterSwap}
                type="button"
                className="ticket-back"
                onClick={() => swap("details")}
              >
                <ChevronLeft aria-hidden size={16} />
                <span className="sr-only">Back to </span>
                {nameOf(recommendation)}
              </button>
              <p className="dates-heading">{moreDates(also.length)}</p>
              <DatesPane concerts={also} />
            </motion.div>
          )}
        </AnimatePresence>
      </div>
      <div className="ticket-stub">
        {concert.price && <Price text={formatPrice(concert.price, true)} />}
        <SourceLink href={concert.url} aria-label={`Tickets for ${concert.name}`}>
          Tickets
        </SourceLink>
      </div>
    </article>
  );
}
