import { EventSourceParserStream } from "eventsource-parser/stream";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

export type Price = { min: number; max: number; currency: string };

export type Artist = { name: string };

// A Concert's facts. Anything the source does not report is left out.
export type Concert = {
  id: string;
  name: string;
  url: string;
  artists: Artist[];
  date?: string;
  time?: string;
  venue?: string;
  city?: string;
  region?: string;
  price?: Price;
};

export type Recommendation = { concert: Concert; reason: string };

// What the interpreter read from a Search. Anything it did not find is left out.
export type Interpreted = { place?: string; start?: string; end?: string; artists: string[] };

// Who made the shortlist. `total` counts Concerts, and an Artist's names appear once.
export type Candidates = { names: string[]; total: number };

export type SearchError = { code: string; message: string; retry_after?: number };

// The visitor has to change these Searches, so running one again cannot help.
export const NEEDS_A_NEW_SEARCH = ["needs_taste_or_place", "needs_place", "place_not_found"];

export type SearchEvent =
  | { event: "status"; data: { step: string; message: string } }
  | { event: "interpreted"; data: Interpreted }
  | { event: "pool"; data: { total: number } }
  | { event: "candidates"; data: Candidates }
  | { event: "poster"; data: { recommendations: Recommendation[] } }
  | { event: "error"; data: SearchError }
  | { event: "done"; data: Record<string, never> };

export async function* streamSearch(
  text: string,
  signal: AbortSignal,
): AsyncGenerator<SearchEvent> {
  const response = await fetch(`${API_URL}/search`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
    signal,
  });
  if (!response.ok || !response.body) {
    const error: SearchError = await response.json();
    throw new Error(error.message);
  }

  const reader = response.body
    .pipeThrough(new TextDecoderStream())
    .pipeThrough(new EventSourceParserStream())
    .getReader();
  while (true) {
    const { done, value } = await reader.read();
    if (done) return;
    yield { event: value.event, data: JSON.parse(value.data) } as SearchEvent;
  }
}
