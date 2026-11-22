-- Permanent anonymized numeric Search telemetry for Engineering Lab (/lab).
--
-- Privacy invariant: rows hold strictly numeric timings, costs, cache counts, funnel sizes, and
-- hour-bucketed UTC timestamps. Never Search text, Artist names, coordinates, IPs, or Spotify data.
-- All reads and writes go through FastAPI using the server secret key.

create table public.search_telemetry (
  id bigint generated always as identity primary key,
  recorded_at timestamptz not null,
  total_ms double precision not null check (total_ms >= 0),
  steps_ms jsonb not null default '{}'::jsonb,
  cost_usd double precision not null default 0 check (cost_usd >= 0),
  cost_complete boolean not null default true,
  cache_hits integer not null default 0 check (cache_hits >= 0),
  cache_misses integer not null default 0 check (cache_misses >= 0),
  pool_total integer not null default 0 check (pool_total >= 0),
  shortlist_total integer not null default 0 check (shortlist_total >= 0),
  picks_total integer not null default 0 check (picks_total >= 0),
  source text not null default 'live' check (source in ('live', 'backfill'))
);

create index search_telemetry_recorded_idx
  on public.search_telemetry (recorded_at desc, id desc);

alter table public.search_telemetry enable row level security;

revoke all on public.search_telemetry from anon, authenticated;
