-- ============================================================================
-- Felipe relational schema (run once in the Supabase SQL editor).
-- Supersedes export_tables.sql. The `checkpoints` JSON store stays the scrape
-- source of truth; these tables are the derived, queryable layer that
-- export_sheets.py regenerates (and mirrors to the Google Sheet) on each run.
--
-- Model: 6 entity tables (juzgados, ruts, causas, tramites, documentos,
-- patentes) + 2 junctions (causa_rut, causa_patente).
-- ============================================================================

-- ── Entity: Juzgados ────────────────────────────────────────────────────────
create table if not exists juzgados (
  juzgado_id text primary key,
  nombre     text not null default '',
  url        text not null default ''
);

-- ── Entity: Ruts (every RUT-identified party: demandantes, demandados, owners)─
create table if not exists ruts (
  rut            text primary key,
  tipo           text not null default '',   -- persona | empresa
  nombre         text not null default '',
  segundo_nombre text not null default '',
  ap_paterno     text not null default '',
  ap_materno     text not null default '',
  razon_social   text not null default '',
  email          text not null default '',
  telefono       text not null default '',
  domicilio      text not null default '',
  updated_at     timestamptz not null default now()
);

-- ── Entity: Causas ──────────────────────────────────────────────────────────
create table if not exists causas (
  caso_id         text primary key,
  rol             text not null default '',
  juzgado_id      text references juzgados(juzgado_id),
  materia         text not null default '',
  fecha_causa     text not null default '',
  fecha_citacion  text not null default '',
  fecha_estado    text not null default '',
  estado          text not null default '',
  boleta_numero   text not null default '',
  boleta_fecha    text not null default '',
  monto_demandado text not null default '',
  updated_at      timestamptz not null default now()
);
create index if not exists causas_juzgado_idx on causas (juzgado_id);

-- ── Entity: Trámites ────────────────────────────────────────────────────────
create table if not exists tramites (
  tramite_id  text primary key,
  caso_id     text not null references causas(caso_id),
  fecha       text not null default '',
  descripcion text not null default '',
  pdf_url     text not null default ''
);
create index if not exists tramites_caso_idx on tramites (caso_id);

-- ── Entity: Documentos ──────────────────────────────────────────────────────
create table if not exists documentos (
  documento_id text primary key,
  caso_id      text not null references causas(caso_id),
  descripcion  text not null default '',
  pdf_url      text not null default ''
);
create index if not exists documentos_caso_idx on documentos (caso_id);

-- ── Entity: Patentes (master plate list; enrichment fills the rest) ──────────
-- Preserve existing enriched rows: rename rut->rut_propietario, drop enriched_at.
alter table patentes rename column rut to rut_propietario;
alter table patentes drop column if exists enriched_at;
alter table patentes add column if not exists nombre_propietario text not null default '';
-- Link the plate to its owner as a ruts entity. NOT VALID so the migration does
-- not fail on existing owner RUTs that aren't in `ruts` yet — the next export
-- upserts owners into `ruts`, and new writes are checked from here on.
alter table patentes
  add constraint patentes_rut_propietario_fkey
  foreign key (rut_propietario) references ruts(rut) not valid;

-- ── Junction: Causa ↔ Rut (the demandante/demandado relationship) ────────────
-- One row per party in a causa. vinculo_id = "<caso_id>::<rut>".
-- Name is quoted to preserve the capital X (matches the Sheet tab CausaXRut).
create table if not exists "causaXrut" (
  vinculo_id text primary key,
  caso_id    text not null references causas(caso_id),
  rut        text not null references ruts(rut),
  rol_parte  text not null default '',   -- demandante | demandado
  updated_at timestamptz not null default now()
);
create index if not exists causaxrut_caso_idx on "causaXrut" (caso_id);
create index if not exists causaxrut_rut_idx  on "causaXrut" (rut);

-- ── Junction: Causa ↔ Patente (plate in a causa, tied to the party) ──────────
-- vinculo_id = "<caso_id>::<rut>::<patente>". rut NULL when no party identified.
create table if not exists "causaXpatente" (
  vinculo_id text primary key,
  caso_id    text not null references causas(caso_id),
  rut        text references ruts(rut),
  patente    text not null references patentes(patente),
  updated_at timestamptz not null default now()
);
create index if not exists causaxpatente_caso_idx    on "causaXpatente" (caso_id);
create index if not exists causaxpatente_rut_idx     on "causaXpatente" (rut);
create index if not exists causaxpatente_patente_idx on "causaXpatente" (patente);

-- ── Drop the old derived tables (replaced by ruts / causa_rut / causa_patente)─
drop table if exists patente_demandado;
drop table if exists causa_demandado;
drop table if exists demandados;

-- ── RLS: writes use the service_role key (bypasses RLS); the SPA reads via anon.
do $$
declare t text;
begin
  foreach t in array array['juzgados','ruts','causas','tramites','documentos',
                           'causaXrut','causaXpatente'] loop
    execute format('alter table %I enable row level security;', t);
    execute format('drop policy if exists "anon read %1$s" on %1$s;', t);
    execute format('create policy "anon read %1$s" on %1$s for select to anon using (true);', t);
  end loop;
end $$;
