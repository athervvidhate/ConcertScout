-- Account-synced Taste Profile (docs/specs/08-universal-taste-hub.md). One row per Account holds
-- the confirmed Artist names of a Taste, favourites first. The API writes it with the secret key,
-- so the browser can read and clear its own row but never write one (ADR 0004).
--
-- ADR 0003: data from a Spotify account never lands here. `source` lists only Taste that is not
-- Spotify OAuth data, so a row for the Spotify connection cannot exist.

create table public.taste_profiles (
  user_id uuid primary key references auth.users (id) on delete cascade,
  source text not null check (
    source in (
      'seed', 'csv', 'exportify', 'tunemymusic', 'youtube',
      'lastfm', 'listenbrainz', 'history', 'list'
    )
  ),
  artists jsonb not null check (
    jsonb_typeof(artists) = 'array' and jsonb_array_length(artists) between 1 and 100
  ),
  updated_at timestamptz not null default now()
);

alter table public.taste_profiles enable row level security;

revoke all on public.taste_profiles from anon, authenticated;
grant select, delete on public.taste_profiles to authenticated;

create policy "People read their own Taste Profile"
  on public.taste_profiles for select to authenticated
  using ((select auth.uid()) = user_id);

create policy "People clear their own Taste Profile"
  on public.taste_profiles for delete to authenticated
  using ((select auth.uid()) = user_id);
