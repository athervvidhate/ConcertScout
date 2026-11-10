import { ChevronLeft, ChevronRight, Pointer } from "lucide-react";
import { Fragment, useRef, useState, type ReactNode } from "react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";

import { ArtistPanel } from "@/components/artist-panel";
import { ConcertPhoto, SourceLink } from "@/components/concert-source";
import { ListenButton, ListenStage } from "@/components/listen";
import { Paged } from "@/components/paged";
import {
  byVenue,
  formatDate,
  formatDayShort,
  formatMonthDay,
  formatConcertTime,
  formatPrice,
  presaleLine,
} from "@/lib/format";
import { headlinerOf, listenTo, nameOf } from "@/lib/lineup";
import type { Concert, Recommendation } from "@/lib/search";

// The festival Artists named on the details pane, so it keeps its size. The Lineup holds the rest.
const NAMED_MATCHES = 3;

type View = "details" | "dates" | "lineup";

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

function suitCount(count: number): string {
  return count === 1 ? "An Artist you might like" : `${count} Artists you might like`;
}

/** A festival's whole Lineup, the Artists who suit the Search first. Each name opens its panel. */
function LineupPane({ concert, matched }: { concert: Concert; matched: string[] }) {
  const rest = concert.artists.map((artist) => artist.name).filter((name) => !matched.includes(name));
  return (
    <ul className="lineup-all">
      {[...matched, ...rest].map((name) => (
        <li key={name} data-match={matched.includes(name) || undefined}>
          <ArtistPanel name={name} className="lineup-row" />
          {matched.includes(name) && <span className="sr-only">, you might like them</span>}
        </li>
      ))}
    </ul>
  );
}

/** The festival's best-suited Artists in one line of names, so the details keep their size. */
function MatchLine({ matched, onOpen, onMore }: { matched: string[]; onOpen?: () => void; onMore: () => void }) {
  const shown = matched.slice(0, NAMED_MATCHES);
  const more = matched.length - shown.length;
  return (
    <p className="lineup-match">
      <span className="lineup-match-label">{suitCount(matched.length)}: </span>
      {shown.map((name, index) => (
        <Fragment key={name}>
          {index > 0 && (index === shown.length - 1 && !more ? " and " : ", ")}
          <ArtistPanel name={name} className="lineup-inline" onOpen={onOpen} />
        </Fragment>
      ))}
      {more > 0 && (
        <>
          {" and "}
          <button type="button" className="lineup-inline" onClick={onMore}>
            {more} more
          </button>
        </>
      )}
    </p>
  );
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
  // More actions beside Tickets, for a Ticket whose host offers none of its own.
  actions?: ReactNode;
};

export function Ticket({
  recommendation,
  rank,
  artistHint,
  onArtistOpen,
  hidePhoto,
  listening: shared,
  onListen,
  actions,
}: TicketProps) {
  const { concert, reason, also = [] } = recommendation;
  const [own, setOwn] = useState(false);
  const listening = onListen ? !!shared : own;
  const listen = onListen ?? setOwn;
  const [view, setView] = useState<View>("details");
  const reduced = useReducedMotion();
  // A swapped pane takes the exact size the details had, and pages anything that does not fit.
  const main = useRef<HTMLDivElement>(null);
  const [paneHeight, setPaneHeight] = useState<number>();
  // After a swap, focus lands on the control that swaps back, once the new pane mounts.
  const moved = useRef<View | null>(null);
  const focusAfterSwap = (to: View) => (node: HTMLButtonElement | null) => {
    if (node && moved.current === to) {
      moved.current = null;
      node.focus();
    }
  };
  const swap = (next: View) => {
    moved.current = next === "details" ? view : "details";
    if (next !== "details") setPaneHeight(main.current?.clientHeight);
    setView(next);
  };
  // Only an Artist has a panel or a Preview. A Concert with no Lineup, or a festival, is its title.
  const headliner = headlinerOf(concert);
  const heard = listenTo(recommendation);
  const matched = concert.festival ? (recommendation.lineup_match ?? []) : [];
  const lineup = concert.festival ? concert.artists.length : 0;
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
          {heard && <ListenStage name={heard} listening={listening} />}
        </div>
      )}
      <div className="ticket-main" ref={main}>
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
              {matched.length > 0 && (
                <MatchLine matched={matched} onOpen={onArtistOpen} onMore={() => swap("lineup")} />
              )}
              {reason && (
                <p>
                  {/* A festival's reason describes its best-suited Artist, so it says who. */}
                  {matched[0] && <strong>{matched[0]}: </strong>}
                  {reason}
                </p>
              )}
              <p className="venue">{details.join(", ")}</p>
              {presale && <p className="presale">{presale}</p>}
              {(heard || lineup > 0 || also.length > 0) && (
                <div className="ticket-pills">
                  {heard && <ListenButton name={heard} listening={listening} onListen={listen} />}
                  {lineup > 0 && (
                    <button
                      ref={focusAfterSwap("lineup")}
                      type="button"
                      className="ticket-pill"
                      onClick={() => swap("lineup")}
                    >
                      Lineup · {lineup}
                      <ChevronRight aria-hidden size={16} />
                    </button>
                  )}
                  {also.length > 0 && (
                    <button
                      ref={focusAfterSwap("dates")}
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
              key={view}
              className="ticket-pane ticket-pane-paged"
              style={{ height: paneHeight }}
              initial={{ opacity: 0, x: reduced ? 0 : 16 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: reduced ? 0 : 16 }}
              transition={{ duration: reduced ? 0 : 0.18 }}
            >
              <button
                ref={focusAfterSwap("details")}
                type="button"
                className="ticket-back"
                onClick={() => swap("details")}
              >
                <ChevronLeft aria-hidden size={16} />
                <span className="sr-only">Back to </span>
                {nameOf(recommendation)}
              </button>
              {view === "lineup" ? (
                <Paged columns={2} heading={<p className="dates-heading">Lineup · {lineup}</p>}>
                  <LineupPane concert={concert} matched={matched} />
                </Paged>
              ) : (
                <Paged columns={1} heading={<p className="dates-heading">{moreDates(also.length)}</p>}>
                  <DatesPane concerts={also} />
                </Paged>
              )}
            </motion.div>
          )}
        </AnimatePresence>
      </div>
      <div className="ticket-stub">
        {concert.price && <Price text={formatPrice(concert.price, true)} />}
        <SourceLink href={concert.url} aria-label={`Tickets for ${concert.name}`}>
          Tickets
        </SourceLink>
        {actions}
      </div>
    </article>
  );
}
