-- Run once in the Supabase SQL editor (Dashboard → SQL Editor → New query → Run).
-- Creates the table the web app writes to and the local watcher drains.

create table if not exists patente_requests (
  id         uuid primary key default gen_random_uuid(),
  job_id     text not null,
  kind       text not null default 'enrich',   -- enrich | export
  status     text not null default 'pending',  -- pending | running | done | error
  message    text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
-- If the table already exists from before, add the column:
alter table patente_requests add column if not exists kind text not null default 'enrich';

alter table patente_requests enable row level security;

-- The web app uses the anon key: it may create a request and read its status.
create policy "anon insert patente_requests"
  on patente_requests for insert to anon with check (true);
create policy "anon read patente_requests"
  on patente_requests for select to anon using (true);

-- The watcher uses the service_role key, which bypasses RLS (full access).
