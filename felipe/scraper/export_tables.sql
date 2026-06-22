-- Normalized export tables (derived layer).
--
-- The scrape source of truth stays the `checkpoints` JSON store; these tables
-- mirror what export_sheets.py pushes to Google Sheets so the same data is also
-- queryable relationally in Supabase. Run once in the SQL editor
-- (Dashboard -> SQL Editor -> New query -> Run).
--
-- export_sheets.py upserts into them on every run (unless --no-db), using the
-- service_role key, which bypasses RLS.

-- Clean party entity — one row per unique person, keyed by RUT.
create table if not exists demandados (
  rut            text primary key,
  nombre         text not null default '',
  segundo_nombre text not null default '',
  ap_paterno     text not null default '',
  ap_materno     text not null default '',
  email          text not null default '',
  email_source   text not null default '',
  telefono       text not null default '',
  domicilio      text not null default '',
  updated_at     timestamptz not null default now()
);

-- Junction — which party is a defendant in which causa.
-- vinculo_id = "<caso_id>::<rut>".
create table if not exists causa_demandado (
  vinculo_id text primary key,
  caso_id    text not null,
  rol        text not null default '',
  rut        text not null,
  updated_at timestamptz not null default now()
);
create index if not exists causa_demandado_caso_idx on causa_demandado (caso_id);
create index if not exists causa_demandado_rut_idx  on causa_demandado (rut);

-- Junction — which plate is linked to which party within a causa.
-- A ROL may carry several plates, so multiple rows per caso_id are expected.
-- rut may be '' when a causa has plates but no identified party.
-- vinculo_id = "<caso_id>::<rut>::<patente>".
create table if not exists patente_demandado (
  vinculo_id text primary key,
  caso_id    text not null,
  rol        text not null default '',
  rut        text not null default '',
  patente    text not null,
  updated_at timestamptz not null default now()
);
create index if not exists patente_demandado_caso_idx    on patente_demandado (caso_id);
create index if not exists patente_demandado_rut_idx     on patente_demandado (rut);
create index if not exists patente_demandado_patente_idx on patente_demandado (patente);

-- RLS: writes happen with the service_role key (bypasses RLS). Mirror the
-- app's existing posture — the SPA reads via the anon key — by allowing anon
-- SELECT only. No anon insert/update/delete.
alter table demandados        enable row level security;
alter table causa_demandado   enable row level security;
alter table patente_demandado enable row level security;

create policy "anon read demandados"        on demandados        for select to anon using (true);
create policy "anon read causa_demandado"   on causa_demandado   for select to anon using (true);
create policy "anon read patente_demandado" on patente_demandado for select to anon using (true);
