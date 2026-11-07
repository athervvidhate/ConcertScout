import { EventSourceParserStream } from "eventsource-parser/stream";

// Locally the API sits on the same machine as the page, so a phone on the network finds it too.
function localApi(): string {
  if (typeof window === "undefined") return "http://127.0.0.1:8000";
  const { protocol, hostname } = window.location;
  return protocol === "https:" ? `https://${hostname}:8443` : `http://${hostname}:8000`;
}

export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? localApi();

export type Price = { min: number; max: number; currency: string };

export type Artist = { name: string };

export type Coordinates = { lat: number; lon: number };

export type Presale = { name: string; start: string; end: string };

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
  image?: string;
  general_sale?: string;
  presales?: Presale[];
};

// `also` holds the same Artist's other dates.
export type Recommendation = { concert: Concert; score?: number; reason?: string; also?: Concert[] };

// What the interpreter read from a Search. Anything it did not find is left out.
export type Interpreted = {
  place?: string;
  // A named area wider than a city. `place` is then its center, and `radius_miles` its reach.
  region?: string;
  radius_miles?: number;
  start?: string;
  end?: string;
  artists: string[];
  genres: string[];
};

// Who made the shortlist. `total` counts Concerts, and an Artist's names appear once.
export type Candidates = { names: string[]; total: number };

export type SearchError = { code: string; message: string; retry_after?: number };

// The visitor has to change these Searches, so running one again cannot help.
export const NEEDS_A_NEW_SEARCH = ["needs_taste_or_place", "needs_place", "place_not_found"];

// The API refused this Search before it started. Waiting or changing nothing will not help
// when it says when to come back, or when Search is off.
export class SearchRefused extends Error {
  readonly retryable: boolean;

  constructor({ code, message, retry_after }: SearchError) {
    super(message);
    this.retryable = retry_after === undefined && code !== "search_off";
  }
}

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
  token: string,
  taste: string[],
  near: Coordinates | null,
  signal: AbortSignal,
): AsyncGenerator<SearchEvent> {
  const response = await fetch(`${API_URL}/search`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text, token, taste, near }),
    signal,
  });
  if (!response.ok || !response.body) {
    throw new SearchRefused(await response.json());
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
