-- Preserve the effective ranking grade on Saved Concerts when the saved Recommendation had one.
alter table public.saved_concerts
  add column if not exists grade text check (grade in ('seed', 'strong', 'fair'));
