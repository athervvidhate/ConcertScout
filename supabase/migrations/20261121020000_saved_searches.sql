-- Saved Searches that rerun weekly and fold unseen Recommendations into the daily Alert email
-- (Issue #89, ADR 0004, ADR 0006). The API writes every row with the secret key after validating
-- the Reading, so the browser can read and remove its own Saved Searches but never write them,
-- and has no access to sent Recommendation records.

alter table public.alert_settings
  add column saved_searches_paused boolean not null default false;

-- A Search a person chose to keep. `reading` holds only the Reading shown to the person, never
-- visitor coordinates, imported Taste or Spotify data (ADR 0003).
create table public.saved_searches (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users (id) on delete cascade,
  query_text text not null check (char_length(query_text) between 1 and 500),
  reading jsonb not null,
  last_run_at timestamptz,
  created_at timestamptz not null default now()
);

create index saved_searches_user_created_idx
  on public.saved_searches (user_id, created_at);

create or replace function public.enforce_saved_search_limit()
returns trigger
language plpgsql
as $$
begin
  if (select count(*) from public.saved_searches where user_id = new.user_id) >= 5 then
    raise exception 'saved_search_limit' using errcode = 'P0001';
  end if;
  return new;
end;
$$;

create trigger saved_searches_limit_trigger
  before insert on public.saved_searches
  for each row execute function public.enforce_saved_search_limit();

-- Recommendations already sent for a Saved Search, so none repeats on a later weekly rerun.
create table public.saved_search_sent (
  user_id uuid not null references auth.users (id) on delete cascade,
  saved_search_id uuid not null references public.saved_searches (id) on delete cascade,
  concert_id text not null check (char_length(concert_id) between 1 and 100),
  sent_at timestamptz not null default now(),
  primary key (saved_search_id, concert_id)
);

create index saved_search_sent_user_idx
  on public.saved_search_sent (user_id, saved_search_id);

alter table public.saved_searches enable row level security;
alter table public.saved_search_sent enable row level security;

revoke all on public.saved_searches, public.saved_search_sent from anon, authenticated;
grant select, delete on public.saved_searches to authenticated;

create policy "People read their own Saved Searches"
  on public.saved_searches for select to authenticated
  using ((select auth.uid()) = user_id);

create policy "People remove their own Saved Searches"
  on public.saved_searches for delete to authenticated
  using ((select auth.uid()) = user_id);
