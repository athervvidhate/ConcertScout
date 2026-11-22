-- Group Scout (/g/[id]): shareable rooms for 2 to 6 friends (docs/specs/14-group-scout.md).
--
-- Rooms are capability URLs identified by a 128-bit unguessable random ID. Browsers may read
-- room state for Supabase Realtime subscriptions, while all writes go through FastAPI using the
-- server secret key so Concert facts stay source-backed (ADR 0002), rooms stay capped at 6
-- friends, and Spotify account data never enters a room (ADR 0003).

create table public.group_rooms (
  id text primary key,
  title text not null,
  place jsonb not null,
  start_date date,
  end_date date,
  max_price double precision,
  concerts jsonb not null default '[]'::jsonb,
  created_at timestamptz not null default now(),
  expires_at timestamptz not null default (now() + interval '30 days')
);

create table public.group_members (
  id uuid primary key default gen_random_uuid(),
  room_id text not null references public.group_rooms (id) on delete cascade,
  name text not null,
  artists text[] not null default '{}',
  start_date date,
  end_date date,
  max_price double precision,
  joined_at timestamptz not null default now()
);

create table public.group_votes (
  room_id text not null references public.group_rooms (id) on delete cascade,
  member_id uuid not null references public.group_members (id) on delete cascade,
  concert_id text not null,
  vote text not null check (vote in ('in', 'maybe', 'pass')),
  updated_at timestamptz not null default now(),
  primary key (room_id, member_id, concert_id)
);

create index group_members_room_joined_idx on public.group_members (room_id, joined_at);
create index group_votes_room_idx on public.group_votes (room_id);

-- Filtered Realtime subscriptions need the old room_id on DELETE events.
alter table public.group_members replica identity full;
alter table public.group_votes replica identity full;

alter table public.group_rooms enable row level security;
alter table public.group_members enable row level security;
alter table public.group_votes enable row level security;

revoke all on public.group_rooms from anon, authenticated;
revoke all on public.group_members from anon, authenticated;
revoke all on public.group_votes from anon, authenticated;

grant select on public.group_rooms to anon, authenticated;
grant select on public.group_members to anon, authenticated;
grant select on public.group_votes to anon, authenticated;

create policy "Anyone with a room link can read the room"
  on public.group_rooms for select to anon, authenticated
  using (true);

create policy "Anyone with a room link can read room members"
  on public.group_members for select to anon, authenticated
  using (true);

create policy "Anyone with a room link can read room votes"
  on public.group_votes for select to anon, authenticated
  using (true);

do $$
declare
  tbl text;
begin
  if exists (select 1 from pg_publication where pubname = 'supabase_realtime') then
    foreach tbl in array array['group_rooms', 'group_members', 'group_votes'] loop
      if not exists (
        select 1
        from pg_publication_tables
        where pubname = 'supabase_realtime'
          and schemaname = 'public'
          and tablename = tbl
      ) then
        execute format('alter publication supabase_realtime add table public.%I', tbl);
      end if;
    end loop;
  end if;
end
$$;
