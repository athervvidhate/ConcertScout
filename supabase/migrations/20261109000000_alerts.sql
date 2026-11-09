-- Followed Artists and Alerts (ADR 0006). The API writes every row with the secret key after
-- checking the request, so the browser can read and remove its own rows but never write them.

-- An Artist a person follows. `artist_key` is the normalized name, so two spellings are one row.
create table public.followed_artists (
  user_id uuid not null references auth.users (id) on delete cascade,
  artist_key text not null check (char_length(artist_key) between 1 and 200),
  name text not null check (char_length(name) between 1 and 200),
  followed_at timestamptz not null default now(),
  primary key (user_id, artist_key)
);

-- Where an Account wants to hear about Concerts, as the geocoder reported it, and whether Alerts
-- are on. One row per Account.
create table public.alert_settings (
  user_id uuid primary key references auth.users (id) on delete cascade,
  place jsonb,
  enabled boolean not null default false,
  updated_at timestamptz not null default now(),
  check (not enabled or place is not null)
);

-- Concerts an Alert already told an Account about, so none is sent twice.
create table public.alerts_sent (
  user_id uuid not null references auth.users (id) on delete cascade,
  concert_id text not null check (char_length(concert_id) between 1 and 100),
  sent_at timestamptz not null default now(),
  primary key (user_id, concert_id)
);

alter table public.followed_artists enable row level security;
alter table public.alert_settings enable row level security;
alter table public.alerts_sent enable row level security;

revoke all on public.followed_artists, public.alert_settings, public.alerts_sent
  from anon, authenticated;
grant select, delete on public.followed_artists to authenticated;
grant select on public.alert_settings to authenticated;

create policy "People read their own Followed Artists"
  on public.followed_artists for select to authenticated
  using ((select auth.uid()) = user_id);

create policy "People unfollow their own Artists"
  on public.followed_artists for delete to authenticated
  using ((select auth.uid()) = user_id);

create policy "People read their own Alert settings"
  on public.alert_settings for select to authenticated
  using ((select auth.uid()) = user_id);
