"use client";

import { Paged } from "@/components/paged";
import {
  type SetlistSummary,
  formatLastShow,
  formatSetlistOverview,
  formatStapleCount,
  hasSetlistData,
  setlistHref,
  useArtistSetlist,
} from "@/lib/setlist";

function SetlistBody({ summary }: { summary: SetlistSummary }) {
  const href = setlistHref(summary.source_url);
  return (
    <>
      <p className="setlist-overview">{formatSetlistOverview(summary)}</p>
      {summary.last_show && (
        <p className="setlist-last">Last show: {formatLastShow(summary.last_show)}</p>
      )}
      <ol className="setlist-staples" aria-label="Most played songs">
        {summary.staples.map((staple) => (
          <li key={staple.name}>
            <span className="setlist-song">{staple.name}</span>
            <span className="setlist-count">
              {formatStapleCount(staple, summary.show_count)}
            </span>
          </li>
        ))}
      </ol>
      {href && (
        <p className="setlist-credit">
          Setlists from{" "}
          <a href={href} target="_blank" rel="noopener noreferrer">
            Setlist.fm
          </a>
        </p>
      )}
    </>
  );
}

/**
 * Ticket detail swap pane for Recent Setlist DNA. Renders inside Paged so the Ticket keeps its
 * fixed height and never scrolls on desktop or mobile viewports.
 */
export function SetlistDnaPane({ name, mbid }: { name: string; mbid?: string }) {
  const summary = useArtistSetlist(name, mbid, true);
  const available = hasSetlistData(summary);
  const state = summary === null ? "loading" : available ? "ready" : "empty";

  return (
    <Paged
      key={state}
      columns={1}
      heading={<p className="dates-heading">Recent setlist</p>}
    >
      {summary === null && (
        <p className="setlist-status" role="status">
          Looking up recent setlists for {name}
        </p>
      )}
      {summary !== null && !available && (
        <p className="setlist-empty">No recent setlists recorded for {name}.</p>
      )}
      {available && <SetlistBody summary={summary} />}
    </Paged>
  );
}

/**
 * Artist panel section for Recent Setlist DNA. Lazily loaded when the panel opens and omitted
 * completely when Setlist.fm has no recorded data for the Artist.
 */
export function SetlistDnaSection({
  name,
  mbid,
  open,
}: {
  name: string;
  mbid?: string;
  open: boolean;
}) {
  const summary = useArtistSetlist(name, mbid, open);
  if (!hasSetlistData(summary)) return null;

  return (
    <section className="setlist-section" aria-label="Recent setlist">
      <h3>Recent setlist</h3>
      <SetlistBody summary={summary} />
    </section>
  );
}
