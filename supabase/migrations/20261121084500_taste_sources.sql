-- A Taste can combine several sources, such as picks and a YouTube playlist, so a Taste Profile
-- names every source in it, newest first. ADR 0003 still holds: none of them is Spotify OAuth data.

alter table public.taste_profiles add column sources text[];

update public.taste_profiles set sources = array[source];

alter table public.taste_profiles
  alter column sources set not null,
  add constraint taste_profiles_sources_check check (
    cardinality(sources) between 1 and 9
    and sources <@ array[
      'seed', 'csv', 'exportify', 'tunemymusic', 'youtube',
      'lastfm', 'listenbrainz', 'history', 'list'
    ]::text[]
  ),
  drop column source;
