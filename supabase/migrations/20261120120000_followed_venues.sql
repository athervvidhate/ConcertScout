-- Followed Venues for Alerts (ADR 0006). The API writes every row with the secret key after
-- checking the request, so the browser can read and remove its own rows but never write them.

-- A venue a person follows. `venue_key` is the normalized venue and city, so two spellings are one
-- row.
create table public.followed_venues (
  user_id uuid not null references auth.users (id) on delete cascade,
  venue_key text not null check (char_length(venue_key) between 1 and 320),
  name text not null check (char_length(name) between 1 and 200),
  city text check (city is null or char_length(city) between 1 and 120),
  lat double precision check (lat is null or (lat >= -90 and lat <= 90)),
  lon double precision check (lon is null or (lon >= -180 and lon <= 180)),
  followed_at timestamptz not null default now(),
  primary key (user_id, venue_key),
  check ((lat is null) = (lon is null))
);

alter table public.followed_venues enable row level security;

revoke all on public.followed_venues from anon, authenticated;
grant select, delete on public.followed_venues to authenticated;

create policy "People read their own Followed Venues"
  on public.followed_venues for select to authenticated
  using ((select auth.uid()) = user_id);

create policy "People unfollow their own Venues"
  on public.followed_venues for delete to authenticated
  using ((select auth.uid()) = user_id);
