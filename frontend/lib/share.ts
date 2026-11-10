import { API_URL, refusal, UNREACHABLE, type Reading, type Recommendation } from "@/lib/search";

// What the API keeps for a Shared Poster: the Recommendations and the Search's reading.
export type SharedPoster = {
  made: string;
  reading?: Reading;
  recommendations: Recommendation[];
};

// The Poster for a link, or null when the link is unknown or past its 90 days.
export async function fetchSharedPoster(id: string): Promise<SharedPoster | null> {
  const response = await fetch(`${API_URL}/share/${encodeURIComponent(id)}`, {
    cache: "no-store",
  });
  if (response.status === 404 || response.status === 422) return null;
  if (!response.ok) throw new Error(UNREACHABLE);
  return response.json();
}

// Asks the API to keep the Poster it produced for this Search. The browser sends only the ID.
export async function createSharedPoster(searchId: string): Promise<string> {
  let response: Response;
  try {
    response = await fetch(`${API_URL}/share`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ search_id: searchId }),
    });
  } catch {
    throw new Error(UNREACHABLE);
  }
  if (!response.ok) throw await refusal(response);
  return (await response.json()).id;
}

// A Ticket link opens the Poster with that Ticket open.
export function sharedUrl(id: string, concertId?: string): string {
  const url = new URL(`/p/${id}`, window.location.origin);
  if (concertId) url.searchParams.set("ticket", concertId);
  return url.toString();
}

export type Shared = "shared" | "copied";

// The Web Share API where the browser has it, and a copied link otherwise. A person who closes
// the share sheet has not failed, so that reads as null.
export async function shareLink(url: string, title: string): Promise<Shared | null> {
  if (typeof navigator.share === "function") {
    try {
      await navigator.share({ title, url });
      return "shared";
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") return null;
    }
  }
  await navigator.clipboard.writeText(url);
  return "copied";
}
