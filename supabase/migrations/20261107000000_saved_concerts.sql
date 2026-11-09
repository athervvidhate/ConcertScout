-- A person's Saved Concerts. The API writes each row with Concert facts it read from the source,
-- so the browser can read and remove its own rows but never write facts itself.
create table public.saved_concerts (
  user_id uuid not null references auth.users (id) on delete cascade,
  concert_id text not null check (char_length(concert_id) between 1 and 100),
  concert jsonb not null,
  reason text check (char_length(reason) <= 1000),
  saved_at timestamptz not null default now(),
  primary key (user_id, concert_id)
);

alter table public.saved_concerts enable row level security;

revoke all on public.saved_concerts from anon, authenticated;
grant select, delete on public.saved_concerts to authenticated;

create policy "People read their own Saved Concerts"
  on public.saved_concerts for select to authenticated
  using ((select auth.uid()) = user_id);

create policy "People remove their own Saved Concerts"
  on public.saved_concerts for delete to authenticated
  using ((select auth.uid()) = user_id);
