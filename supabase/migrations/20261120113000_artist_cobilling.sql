-- Live Co-Billing Graph (docs/specs/09-hybrid-retrieval.md).
-- Stores canonical Artist pairs mined from Catalog and Ticketmaster Lineups, with per-Concert
-- deduplication so repeated syncs and pool refreshes never double-count a bill.
-- Only the API writes and reads these tables using the server secret key.

create table public.artist_cobilling (
  artist_a text not null check (char_length(artist_a) between 1 and 200),
  artist_b text not null check (char_length(artist_b) between 1 and 200),
  weight double precision not null check (weight > 0),
  shared_shows integer not null default 1 check (shared_shows >= 1),
  last_seen date not null,
  primary key (artist_a, artist_b),
  check (artist_a < artist_b)
);

create index artist_cobilling_artist_a_weight_idx
  on public.artist_cobilling (artist_a, weight desc);

create index artist_cobilling_artist_b_weight_idx
  on public.artist_cobilling (artist_b, weight desc);

-- Concerts already counted into `artist_cobilling`, so repeated syncs never double-count.
create table public.cobilling_seen_concerts (
  concert_id text primary key check (char_length(concert_id) between 1 and 200),
  seen_at timestamptz not null default now()
);

alter table public.artist_cobilling enable row level security;
alter table public.cobilling_seen_concerts enable row level security;

revoke all on public.artist_cobilling, public.cobilling_seen_concerts
  from anon, authenticated;

-- Atomically mark unseen Concerts and accumulate their canonical Artist pairs.
create or replace function public.record_cobilling_bills(p_bills jsonb)
returns integer
language plpgsql
set search_path = ''
as $$
declare
  v_recorded integer := 0;
begin
  if p_bills is null or jsonb_typeof(p_bills) <> 'array' then
    return 0;
  end if;

  with input_bills as (
    select distinct on (b.concert_id)
      b.concert_id,
      b.concert_date,
      b.weight,
      b.artists
    from jsonb_to_recordset(p_bills) as b(
      concert_id text,
      concert_date date,
      weight double precision,
      artists jsonb
    )
    where b.concert_id is not null
      and char_length(b.concert_id) between 1 and 200
      and b.concert_date is not null
      and b.weight > 0
      and jsonb_typeof(b.artists) = 'array'
      and jsonb_array_length(b.artists) between 2 and 40
    order by b.concert_id, b.concert_date desc
  ),
  inserted_concerts as (
    insert into public.cobilling_seen_concerts (concert_id)
    select concert_id from input_bills
    on conflict (concert_id) do nothing
    returning concert_id
  ),
  new_bills as (
    select ib.concert_id, ib.concert_date, ib.weight, ib.artists
    from input_bills ib
    join inserted_concerts ic on ic.concert_id = ib.concert_id
  ),
  bill_artists as (
    select distinct
      nb.concert_id,
      nb.concert_date,
      nb.weight,
      a.artist
    from new_bills nb
    cross join lateral jsonb_array_elements_text(nb.artists) as a(artist)
    where char_length(a.artist) between 1 and 200
  ),
  pairs as (
    select
      a1.artist as artist_a,
      a2.artist as artist_b,
      sum(a1.weight) as weight,
      count(*)::integer as shared_shows,
      max(a1.concert_date) as last_seen
    from bill_artists a1
    join bill_artists a2
      on a1.concert_id = a2.concert_id
     and a1.artist < a2.artist
    group by a1.artist, a2.artist
  ),
  upserted as (
    insert into public.artist_cobilling (artist_a, artist_b, weight, shared_shows, last_seen)
    select artist_a, artist_b, weight, shared_shows, last_seen
    from pairs
    on conflict (artist_a, artist_b) do update set
      weight = public.artist_cobilling.weight + excluded.weight,
      shared_shows = public.artist_cobilling.shared_shows + excluded.shared_shows,
      last_seen = greatest(public.artist_cobilling.last_seen, excluded.last_seen)
    returning 1
  )
  select (select count(*) from inserted_concerts)
  into v_recorded
  from (select count(*) from upserted) _;

  return v_recorded;
end;
$$;

-- Top co-billed peers for each normalized seed Artist key, using both side indexes.
create or replace function public.cobilling_neighbors(
  p_artists text[],
  p_limit integer default 50
)
returns table (
  seed text,
  peer text,
  weight double precision,
  shared_shows integer,
  last_seen date
)
language sql
stable
set search_path = ''
as $$
  with edges as (
    select artist_a as seed, artist_b as peer, weight, shared_shows, last_seen
    from public.artist_cobilling
    where artist_a = any(p_artists)
    union all
    select artist_b as seed, artist_a as peer, weight, shared_shows, last_seen
    from public.artist_cobilling
    where artist_b = any(p_artists)
  ),
  ranked as (
    select
      seed,
      peer,
      weight,
      shared_shows,
      last_seen,
      row_number() over (
        partition by seed
        order by weight desc, shared_shows desc, peer asc
      ) as rn
    from edges
  )
  select seed, peer, weight, shared_shows, last_seen
  from ranked
  where rn <= greatest(p_limit, 1)
  order by seed asc, weight desc, shared_shows desc, peer asc;
$$;

revoke all on function public.record_cobilling_bills(jsonb)
  from public, anon, authenticated;
grant execute on function public.record_cobilling_bills(jsonb)
  to service_role;

revoke all on function public.cobilling_neighbors(text[], integer)
  from public, anon, authenticated;
grant execute on function public.cobilling_neighbors(text[], integer)
  to service_role;
