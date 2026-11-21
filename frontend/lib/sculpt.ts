import {
  API_URL,
  type Candidates,
  type Recommendation,
  refusal,
} from "@/lib/search";

export type DiscoveryMode = "balanced" | "familiar" | "deep_cuts";

export type SculptState = {
  discovery: DiscoveryMode;
  max_price: number | null;
  weekends_only: boolean;
  intimate_only: boolean;
  hide_festivals: boolean;
  boost_artists: string[];
  exclude_artists: string[];
};

export type SculptMeta = {
  pool_total: number;
  filtered_total: number;
  unpriced_count: number;
  unknown_room_count: number;
  eliminated_by?: string | null;
};

export type SculptResponse = {
  search_id: string;
  poster: { recommendations: Recommendation[] };
  candidates: Candidates;
  meta: SculptMeta;
};

export const MAX_BOOST_ARTISTS = 5;
export const MAX_EXCLUDE_ARTISTS = 10;

export const DEFAULT_SCULPT: SculptState = {
  discovery: "balanced",
  max_price: null,
  weekends_only: false,
  intimate_only: false,
  hide_festivals: false,
  boost_artists: [],
  exclude_artists: [],
};

function keyOf(name: string): string {
  return name.trim().toLocaleLowerCase();
}

export function isDefaultSculpt(state: SculptState): boolean {
  return (
    state.discovery === "balanced" &&
    state.max_price === null &&
    !state.weekends_only &&
    !state.intimate_only &&
    !state.hide_festivals &&
    state.boost_artists.length === 0 &&
    state.exclude_artists.length === 0
  );
}

export function isBoosted(state: SculptState, artist: string): boolean {
  const target = keyOf(artist);
  return state.boost_artists.some((name) => keyOf(name) === target);
}

export function toggleBoostArtist(
  state: SculptState,
  artist: string,
): SculptState {
  const trimmed = artist.trim();
  const target = keyOf(trimmed);
  if (!target) return state;
  const exists = state.boost_artists.some((name) => keyOf(name) === target);
  const boost_artists = exists
    ? state.boost_artists.filter((name) => keyOf(name) !== target)
    : [...state.boost_artists, trimmed].slice(0, MAX_BOOST_ARTISTS);
  const exclude_artists = state.exclude_artists.filter(
    (name) => keyOf(name) !== target,
  );
  return { ...state, boost_artists, exclude_artists };
}

export function toggleExcludeArtist(
  state: SculptState,
  artist: string,
): SculptState {
  const trimmed = artist.trim();
  const target = keyOf(trimmed);
  if (!target) return state;
  const exists = state.exclude_artists.some((name) => keyOf(name) === target);
  const exclude_artists = exists
    ? state.exclude_artists.filter((name) => keyOf(name) !== target)
    : [...state.exclude_artists, trimmed].slice(0, MAX_EXCLUDE_ARTISTS);
  const boost_artists = state.boost_artists.filter(
    (name) => keyOf(name) !== target,
  );
  return { ...state, boost_artists, exclude_artists };
}

export function removeSteeringArtist(
  state: SculptState,
  kind: "boost" | "exclude",
  artist: string,
): SculptState {
  const target = keyOf(artist);
  if (kind === "boost") {
    return {
      ...state,
      boost_artists: state.boost_artists.filter((n) => keyOf(n) !== target),
    };
  }
  return {
    ...state,
    exclude_artists: state.exclude_artists.filter((n) => keyOf(n) !== target),
  };
}

export function relaxFilter(
  state: SculptState,
  eliminatedBy: string | null | undefined,
): { next: SculptState; reason: string; label: string } {
  if (eliminatedBy === "max_price" && state.max_price !== null) {
    return {
      next: { ...state, max_price: null },
      reason: `No Concerts in this pool have a reported price under $${state.max_price}.`,
      label: "Remove price cap",
    };
  }
  if (eliminatedBy === "weekends_only" && state.weekends_only) {
    return {
      next: { ...state, weekends_only: false },
      reason: "No Concerts in this pool fall on Friday through Sunday.",
      label: "Show any day",
    };
  }
  if (eliminatedBy === "intimate_only" && state.intimate_only) {
    return {
      next: { ...state, intimate_only: false },
      reason: "No Concerts in this pool have a verified intimate room size.",
      label: "Show any room size",
    };
  }
  if (eliminatedBy === "hide_festivals" && state.hide_festivals) {
    return {
      next: { ...state, hide_festivals: false },
      reason: "Only festivals matched in this pool.",
      label: "Include festivals",
    };
  }
  if (eliminatedBy === "exclude_artists" && state.exclude_artists.length > 0) {
    return {
      next: { ...state, exclude_artists: [] },
      reason: "Your hidden Artists removed the remaining Concerts in this pool.",
      label: "Clear hidden Artists",
    };
  }
  return {
    next: DEFAULT_SCULPT,
    reason: "Your current filters removed every Concert in this pool.",
    label: "Reset filters",
  };
}

export async function sculptPoster(
  searchId: string,
  state: SculptState,
  signal?: AbortSignal,
): Promise<SculptResponse> {
  const response = await fetch(
    `${API_URL}/search/${encodeURIComponent(searchId)}/sculpt`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(state),
      signal,
    },
  );
  if (!response.ok) {
    throw await refusal(response);
  }
  return (await response.json()) as SculptResponse;
}
