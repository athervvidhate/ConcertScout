import { formatDate, formatPrice, formatTime } from "@/lib/format";
import type { Concert, Recommendation } from "@/lib/search";

function ConcertItem({ concert }: { concert: Concert }) {
  const when = [
    concert.date && formatDate(concert.date),
    concert.time && formatTime(concert.time),
  ].filter(Boolean);
  const where = [concert.venue, concert.city, concert.region].filter(Boolean);

  return (
    <li className="border-b border-stone-200 py-4">
      <a href={concert.url} className="font-medium underline-offset-2 hover:underline">
        {concert.name}
      </a>
      {concert.artists.length > 0 && (
        <p className="text-sm text-stone-600">
          {concert.artists.map((artist) => artist.name).join(", ")}
        </p>
      )}
      {when.length > 0 && <p className="text-sm">{when.join(" at ")}</p>}
      {where.length > 0 && <p className="text-sm">{where.join(", ")}</p>}
      {concert.price && <p className="text-sm">{formatPrice(concert.price)}</p>}
    </li>
  );
}

export function ConcertList({ recommendations }: { recommendations: Recommendation[] }) {
  return (
    <ul>
      {recommendations.map(({ concert }) => (
        <ConcertItem key={concert.id} concert={concert} />
      ))}
    </ul>
  );
}
