import type { SupabaseClient } from "@supabase/supabase-js";

import { formatMonthDay, viewerZone } from "@/lib/format";
import { API_URL, refusal, type Concert } from "@/lib/search";

const SUPABASE_URL = process.env.NEXT_PUBLIC_SUPABASE_URL;
const SUPABASE_KEY = process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY;
const MEMBERS_STORAGE_KEY = "concert-scout-group-members";

export const MAX_GROUP_MEMBERS = 6;
export const MAX_GROUP_TASTE = 100;

export type VoteChoice = "in" | "maybe" | "pass";
export type MatchBadge = "Named" | "Similar" | "Co-billed" | "Sounds close" | "Style match";
export type GroupSort = "fit" | "votes";

export type GroupPlace = {
  name: string;
  lat: number;
  lon: number;
  state_code?: string;
  country_code?: string;
  radius_miles?: number;
};

export type GroupMember = {
  id: string;
  name: string;
  artists: string[];
  start_date?: string;
  end_date?: string;
  max_price?: number;
  joined_at: string;
};

export type MemberMatch = {
  member_id: string;
  name: string;
  signal: string;
  badge: MatchBadge;
  via?: string;
  matched_artist: string;
};

export type VoteCounts = Record<VoteChoice, number>;

export type GroupPick = {
  concert: Concert;
  everyone_fits: boolean;
  member_matches: MemberMatch[];
  lineup_match: string[];
  member_votes: Record<string, VoteChoice>;
  vote_counts: VoteCounts;
  consensus_in: boolean;
};

export type EffectiveConstraints = {
  start_date?: string;
  end_date?: string;
  max_price?: number;
  dates_conflict: boolean;
};

export type GroupRoomState = {
  id: string;
  title: string;
  place: GroupPlace;
  start_date?: string;
  end_date?: string;
  max_price?: number;
  effective: EffectiveConstraints;
  members: GroupMember[];
  picks: GroupPick[];
  pool_total: number;
  created_at: string;
  expires_at: string;
};

export type GroupMembershipResponse = {
  room: GroupRoomState;
  member_id: string;
};

export type CreateGroupInput = {
  place: string;
  title?: string;
  start_date?: string;
  end_date?: string;
  max_price?: number;
  member_name: string;
  artists: string[];
  member_start_date?: string;
  member_end_date?: string;
  member_max_price?: number;
};

export type JoinGroupInput = {
  name: string;
  artists: string[];
  start_date?: string;
  end_date?: string;
  max_price?: number;
};

export type UpdateGroupInput = {
  place?: string;
  title?: string;
  start_date?: string;
  end_date?: string;
  max_price?: number;
  clear_dates?: boolean;
  clear_max_price?: boolean;
};

export type UpdateMemberInput = {
  artists: string[];
  start_date?: string;
  end_date?: string;
  max_price?: number;
  clear_dates?: boolean;
  clear_max_price?: boolean;
};

export const QUICK_PICK_ARTISTS = [
  "Khruangbin",
  "Tame Impala",
  "Bonobo",
  "Four Tet",
  "Parcels",
  "Kaytranada",
  "Jamie xx",
  "Caribou",
] as const;

export function parseArtistsInput(raw: string): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const part of raw.split(/[\n,;]+/)) {
    const cleaned = part.trim().replace(/\s+/g, " ");
    const key = cleaned.toLowerCase();
    if (!cleaned || seen.has(key)) continue;
    seen.add(key);
    out.push(cleaned);
    if (out.length >= MAX_GROUP_TASTE) break;
  }
  return out;
}

export function mergeArtists(existing: string[], incoming: string[]): string[] {
  return parseArtistsInput([...existing, ...incoming].join("\n"));
}

export function sortGroupPicks(picks: GroupPick[], mode: GroupSort): GroupPick[] {
  if (mode === "fit") return [...picks];
  return picks
    .map((pick, index) => ({ pick, index }))
    .sort((a, b) => {
      if (a.pick.consensus_in !== b.pick.consensus_in) {
        return a.pick.consensus_in ? -1 : 1;
      }
      if (a.pick.vote_counts.in !== b.pick.vote_counts.in) {
        return b.pick.vote_counts.in - a.pick.vote_counts.in;
      }
      if (a.pick.vote_counts.maybe !== b.pick.vote_counts.maybe) {
        return b.pick.vote_counts.maybe - a.pick.vote_counts.maybe;
      }
      if (a.pick.vote_counts.pass !== b.pick.vote_counts.pass) {
        return a.pick.vote_counts.pass - b.pick.vote_counts.pass;
      }
      return a.index - b.index;
    })
    .map(({ pick }) => pick);
}

export function memberInitials(name: string): string {
  const words = name.trim().split(/\s+/).filter(Boolean);
  if (words.length === 0) return "?";
  if (words.length === 1) return words[0].slice(0, 2).toUpperCase();
  return `${words[0][0]}${words[words.length - 1][0]}`.toUpperCase();
}

export function formatDateWindow(start?: string, end?: string): string | null {
  if (start && end) {
    if (start === end) return formatMonthDay(start);
    return `${formatMonthDay(start)} – ${formatMonthDay(end)}`;
  }
  if (start) return `From ${formatMonthDay(start)}`;
  if (end) return `Until ${formatMonthDay(end)}`;
  return null;
}

export function groupShareUrl(roomId: string): string {
  return `${window.location.origin}/g/${roomId}`;
}

function readStoredMap(): Record<string, string> {
  try {
    const raw = localStorage.getItem(MEMBERS_STORAGE_KEY);
    if (!raw) return {};
    const parsed: unknown = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return {};
    const result: Record<string, string> = {};
    for (const [key, value] of Object.entries(parsed)) {
      if (typeof value === "string" && value.length > 0) result[key] = value;
    }
    return result;
  } catch {
    return {};
  }
}

export function readRoomMemberId(roomId: string): string | null {
  return readStoredMap()[roomId] ?? null;
}

export function rememberRoomMemberId(roomId: string, memberId: string): void {
  try {
    const map = readStoredMap();
    map[roomId] = memberId;
    localStorage.setItem(MEMBERS_STORAGE_KEY, JSON.stringify(map));
  } catch {
    /* Storage unavailable; session stays in memory for this tab. */
  }
}

export function forgetRoomMemberId(roomId: string): void {
  try {
    const map = readStoredMap();
    delete map[roomId];
    localStorage.setItem(MEMBERS_STORAGE_KEY, JSON.stringify(map));
  } catch {
    /* Storage unavailable. */
  }
}

export async function createGroupRoom(input: CreateGroupInput): Promise<GroupMembershipResponse> {
  const response = await fetch(`${API_URL}/groups`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...input, time_zone: viewerZone() }),
  });
  if (!response.ok) throw await refusal(response);
  return response.json();
}

export async function fetchGroupRoom(
  roomId: string,
  signal?: AbortSignal,
): Promise<GroupRoomState> {
  const response = await fetch(`${API_URL}/groups/${encodeURIComponent(roomId)}`, { signal });
  if (!response.ok) throw await refusal(response);
  return response.json();
}

export async function joinGroupRoom(
  roomId: string,
  input: JoinGroupInput,
): Promise<GroupMembershipResponse> {
  const response = await fetch(`${API_URL}/groups/${encodeURIComponent(roomId)}/members`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  if (!response.ok) throw await refusal(response);
  return response.json();
}

export async function castGroupVote(
  roomId: string,
  memberId: string,
  concertId: string,
  vote: VoteChoice,
): Promise<GroupRoomState> {
  const response = await fetch(`${API_URL}/groups/${encodeURIComponent(roomId)}/votes`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ member_id: memberId, concert_id: concertId, vote }),
  });
  if (!response.ok) throw await refusal(response);
  return response.json();
}

export async function leaveGroupRoom(
  roomId: string,
  memberId: string,
): Promise<GroupRoomState> {
  const response = await fetch(
    `${API_URL}/groups/${encodeURIComponent(roomId)}/members/${encodeURIComponent(memberId)}`,
    { method: "DELETE" },
  );
  if (!response.ok) throw await refusal(response);
  return response.json();
}

export async function updateGroupRoom(
  roomId: string,
  input: UpdateGroupInput,
): Promise<GroupRoomState> {
  const response = await fetch(`${API_URL}/groups/${encodeURIComponent(roomId)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...input, time_zone: viewerZone() }),
  });
  if (!response.ok) throw await refusal(response);
  return response.json();
}

export async function updateGroupMember(
  roomId: string,
  memberId: string,
  input: UpdateMemberInput,
): Promise<GroupRoomState> {
  const response = await fetch(
    `${API_URL}/groups/${encodeURIComponent(roomId)}/members/${encodeURIComponent(memberId)}`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(input),
    },
  );
  if (!response.ok) throw await refusal(response);
  return response.json();
}

let realtimeClient: SupabaseClient | null = null;
let realtimeLoading: Promise<SupabaseClient | null> | null = null;

async function getRealtimeClient(): Promise<SupabaseClient | null> {
  if (!SUPABASE_URL || !SUPABASE_KEY) return null;
  if (realtimeClient) return realtimeClient;
  realtimeLoading ??= import("@supabase/supabase-js")
    .then(({ createClient }) => {
      realtimeClient = createClient(SUPABASE_URL, SUPABASE_KEY, {
        auth: { persistSession: false, autoRefreshToken: false, detectSessionInUrl: false },
      });
      return realtimeClient;
    })
    .catch(() => {
      realtimeLoading = null;
      return null;
    });
  return realtimeLoading;
}

/**
 * Subscribe to Supabase Realtime updates for a Group Scout room's members and votes.
 * Falls back cleanly to polling whenever Realtime is disabled or unreachable.
 */
export function subscribeGroupRoom(
  roomId: string,
  onChange: () => void,
  onFallback: () => void,
  onLive?: () => void,
): () => void {
  if (!SUPABASE_URL || !SUPABASE_KEY) {
    onFallback();
    return () => {};
  }

  let closed = false;
  let subscribed = false;
  let cleanupChannel: (() => void) | null = null;

  const fallbackTimer = setTimeout(() => {
    if (!closed && !subscribed) onFallback();
  }, 3500);

  void getRealtimeClient().then((client) => {
    if (closed || !client) {
      if (!closed) onFallback();
      return;
    }
    const channel = client
      .channel(`group-room:${roomId}`)
      .on(
        "postgres_changes",
        {
          event: "UPDATE",
          schema: "public",
          table: "group_rooms",
          filter: `id=eq.${roomId}`,
        },
        () => {
          if (!closed) onChange();
        },
      )
      .on(
        "postgres_changes",
        {
          event: "*",
          schema: "public",
          table: "group_members",
          filter: `room_id=eq.${roomId}`,
        },
        () => {
          if (!closed) onChange();
        },
      )
      .on(
        "postgres_changes",
        {
          event: "*",
          schema: "public",
          table: "group_votes",
          filter: `room_id=eq.${roomId}`,
        },
        () => {
          if (!closed) onChange();
        },
      )
      .subscribe((status) => {
        if (closed) return;
        if (status === "SUBSCRIBED") {
          subscribed = true;
          clearTimeout(fallbackTimer);
          onLive?.();
        } else if (status === "CHANNEL_ERROR" || status === "TIMED_OUT" || status === "CLOSED") {
          clearTimeout(fallbackTimer);
          onFallback();
        }
      });

    cleanupChannel = () => {
      void client.removeChannel(channel);
    };
  });

  return () => {
    closed = true;
    clearTimeout(fallbackTimer);
    cleanupChannel?.();
  };
}
