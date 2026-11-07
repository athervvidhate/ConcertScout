import { formatDate } from "@/lib/format";
import { API_URL, type Interpreted, type Recommendation, SearchRefused } from "@/lib/search";

export type Report = {
  search: string;
  note: string;
  interpreted: Interpreted | null;
  recommendations: Recommendation[];
  error: string | null;
};

function describe({ concert }: Recommendation): string {
  const when = concert.date && formatDate(concert.date);
  return [concert.name, when, concert.venue, concert.city, concert.region].filter(Boolean).join(", ");
}

export async function sendReport({ search, note, interpreted, recommendations, error }: Report) {
  const response = await fetch(`${API_URL}/feedback`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      search,
      note,
      reading: interpreted ? JSON.stringify(interpreted) : "",
      results: recommendations.slice(0, 30).map(describe),
      error: error ?? "",
    }),
  });
  if (!response.ok) throw new SearchRefused(await response.json());
}
