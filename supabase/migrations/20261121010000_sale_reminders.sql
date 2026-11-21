-- Sale reminders for Saved Concerts (Issue #88, ADR 0006). The API writes every row with the
-- secret key after checking the request, so the browser can read its own settings but never write
-- them, and has no access to sent reminder records.

alter table public.alert_settings
  add column sale_reminders_enabled boolean not null default false,
  add column timezone text check (timezone is null or char_length(timezone) between 1 and 100),
  add constraint alert_settings_sale_reminders_timezone
    check (not sale_reminders_enabled or timezone is not null);

-- Upcoming sales an Alert already reminded an Account about, so each presale and general sale is
-- reminded about once.
create table public.sale_reminders_sent (
  user_id uuid not null references auth.users (id) on delete cascade,
  concert_id text not null check (char_length(concert_id) between 1 and 100),
  sale_key text not null check (char_length(sale_key) between 1 and 200),
  sent_at timestamptz not null default now(),
  primary key (user_id, concert_id, sale_key)
);

alter table public.sale_reminders_sent enable row level security;

revoke all on public.sale_reminders_sent from anon, authenticated;
