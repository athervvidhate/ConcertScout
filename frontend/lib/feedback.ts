import { formatDate } from "@/lib/format";
import { API_URL, type Reading, type Recommendation, refusal } from "@/lib/search";

export type Report = {
  search: string;
  note: string;
  reading: Reading | null;
  recommendations: Recommendation[];
  error: string | null;
};

function describe({ concert }: Recommendation): string {
  const when = concert.date && formatDate(concert.date);
  return [concert.name, when, concert.venue, concert.city, concert.region].filter(Boolean).join(", ");
}

export async function sendReport({ search, note, reading, recommendations, error }: Report) {
  const response = await fetch(`${API_URL}/feedback`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      search,
      note,
      reading: reading ? JSON.stringify(reading) : "",
      results: recommendations.slice(0, 30).map(describe),
      error: error ?? "",
    }),
  });
  if (!response.ok) throw await refusal(response);
}
