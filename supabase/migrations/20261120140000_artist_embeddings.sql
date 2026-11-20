-- Hybrid semantic retrieval (docs/specs/09-hybrid-retrieval.md).
-- One 512-dimension unit vector per Artist: Tier 1 from a source-grounded Sonic Card, Tier 2 from
-- the weighted centroid of the Artist's Co-Billed peers. A Search scores only the Artists in its
-- Concert pool by key, so there is no ANN index and nothing is filtered after a global search.
-- Only the API writes and reads these using the server secret key.

create extension if not exists vector with schema extensions;

create table public.artist_embeddings (
  artist_key text primary key check (char_length(artist_key) between 1 and 200),
  mbid text,
  tier smallint not null check (tier in (1, 2)),
  card_hash text not null check (char_length(card_hash) = 64),
  embedding extensions.vector(512) not null,
  updated_at timestamptz not null default now()
);

alter table public.artist_embeddings enable row level security;

revoke all on public.artist_embeddings from anon, authenticated;

-- Insert or replace rows. Each element carries artist_key, mbid, tier, card_hash and embedding
-- (an array of 512 numbers). Returns how many rows were written.
create or replace function public.upsert_artist_embeddings(p_rows jsonb)
returns integer
language plpgsql
set search_path = ''
as $$
declare
  v_written integer := 0;
begin
  if p_rows is null or jsonb_typeof(p_rows) <> 'array' then
    return 0;
  end if;

  with input_rows as (
    select distinct on (r.artist_key)
      r.artist_key, r.mbid, r.tier, r.card_hash, r.embedding
    from jsonb_to_recordset(p_rows) as r(
      artist_key text,
      mbid text,
      tier smallint,
      card_hash text,
      embedding jsonb
    )
    where jsonb_typeof(r.embedding) = 'array'
    order by r.artist_key
  ),
  written as (
    insert into public.artist_embeddings (artist_key, mbid, tier, card_hash, embedding)
    select artist_key, mbid, tier, card_hash, (embedding::text)::extensions.vector(512)
    from input_rows
    on conflict (artist_key) do update set
      mbid = excluded.mbid,
      tier = excluded.tier,
      card_hash = excluded.card_hash,
      embedding = excluded.embedding,
      updated_at = now()
    returning 1
  )
  select count(*) into v_written from written;

  return v_written;
end;
$$;

-- What each key already holds, so an unchanged Artist is never embedded again.
create or replace function public.artist_embedding_state(p_artists text[])
returns table (artist_key text, tier smallint, card_hash text)
language sql
stable
set search_path = ''
as $$
  select e.artist_key, e.tier, e.card_hash
  from public.artist_embeddings e
  where e.artist_key = any(p_artists);
$$;

-- The stored vectors for these keys, as `[x,y,...]` text, for the Tier 2 centroid.
create or replace function public.artist_embeddings_for(p_artists text[])
returns table (artist_key text, tier smallint, card_hash text, embedding text)
language sql
stable
set search_path = ''
as $$
  select e.artist_key, e.tier, e.card_hash, e.embedding::text
  from public.artist_embeddings e
  where e.artist_key = any(p_artists);
$$;

-- Exact cosine similarity of the query vector to the pool's Artists, best first. Only Artists at
-- or above p_floor come back, which also keeps the answer under the Data API's row limit.
create or replace function public.semantic_scores(
  p_query text,
  p_artists text[],
  p_floor double precision default 0
)
returns table (artist_key text, cosine double precision)
language sql
stable
set search_path = ''
as $$
  with q as materialized (
    select p_query::extensions.vector(512) as v
  ),
  scored as (
    select
      e.artist_key,
      (1 - (e.embedding operator(extensions.<=>) q.v))::double precision as cosine
    from q
    cross join public.artist_embeddings e
    where e.artist_key = any(p_artists)
  )
  select s.artist_key, s.cosine
  from scored s
  where s.cosine >= p_floor
  order by s.cosine desc, s.artist_key asc
  limit 1000;
$$;

revoke all on function public.upsert_artist_embeddings(jsonb)
  from public, anon, authenticated;
grant execute on function public.upsert_artist_embeddings(jsonb) to service_role;

revoke all on function public.artist_embedding_state(text[])
  from public, anon, authenticated;
grant execute on function public.artist_embedding_state(text[]) to service_role;

revoke all on function public.artist_embeddings_for(text[])
  from public, anon, authenticated;
grant execute on function public.artist_embeddings_for(text[]) to service_role;

revoke all on function public.semantic_scores(text, text[], double precision)
  from public, anon, authenticated;
grant execute on function public.semantic_scores(text, text[], double precision)
  to service_role;
