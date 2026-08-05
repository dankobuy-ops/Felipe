-- ============================================================================
-- ⚠️  SUPERSEDED — HISTORICAL REFERENCE ONLY. DO NOT RUN THIS FILE.  ⚠️
--
-- This is the original Supabase-era DDL. It does NOT describe the live database.
-- The live store is Neon Postgres, and its tables are created at runtime by
-- dbstore._ddl() (pjud/scraper/dbstore.py:113) from the column lists in
-- gstore.TABS (pjud/scraper/gstore.py:26).
--
-- Two differences that will bite you if you read this as current:
--   * Live tables are UNPREFIXED — `causas`, not `pjud_causas`.
--   * Live `causas` has extra DB-managed columns (fill, fill_status, detalles)
--     and its primary key is `causa_id`; there is no `id` column.
-- Also note `documentos.cuaderno_id` FKs to cuadernos.id, not to the causa.
--
-- Kept because it is still the clearest picture of the original relational
-- model. For the schema that actually exists, read dbstore.py + HANDOFF_CDP.md.
-- ============================================================================
--
-- PJUD (Oficina Judicial Virtual) relational schema — run once in the Supabase
-- SQL editor. Same project as JPL (xjlpsgchgfxryvhhrklx); all tables use the
-- `pjud_` prefix to stay clearly separate from the JPL tables.
--
-- Model (8 tables): tribunales, ruts, causas, litigantes, cuadernos, escritos,
-- documentos, anexos. Text primary keys; the scraper upserts; the exporter
-- mirrors these to the Google Sheet.
--
-- Storage: a public `pjud-docs` bucket holds downloaded PDFs (documentos,
-- anexos) and the per-causa ebook; the tables store the public URL.
-- ============================================================================

-- ── Entity: Tribunales (locked scope = just Arica / 1º Juzgado de Letras) ─────
create table if not exists pjud_tribunales (
  id       text primary key,            -- e.g. 'arica-1'
  corte    text not null default '',     -- C.A. de Arica
  tribunal text not null default ''      -- 1º Juzgado de Letras de Arica
);

-- ── Entity: Ruts (every party seen in Litigantes: persona or empresa) ─────────
-- OJV exposes no email/phone/domicilio — kept for parity with JPL's `ruts`.
create table if not exists pjud_ruts (
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

-- ── Entity: Causas ────────────────────────────────────────────────────────────
create table if not exists pjud_causas (
  rol          text primary key,          -- e.g. 'C-996-2026'
  f_ingreso    text not null default '',
  estado_adm   text not null default '',
  procedimiento text not null default '',
  ubicacion    text not null default '',
  estado_proc  text not null default '',
  etapa        text not null default '',
  tribunal     text references pjud_tribunales(id),
  competencia  text not null default '',
  ebook        text not null default '',   -- Storage public URL (per-causa ebook PDF)
  updated_at   timestamptz not null default now()
);
create index if not exists pjud_causas_tribunal_idx on pjud_causas (tribunal);

-- ── Junction: Litigantes (Causa ↔ Rut, with the participant role) ─────────────
-- id = '‹rol›::‹rut›'. participante = DTE. | DDO. | AB.DTE | AP.DTE | …
create table if not exists pjud_litigantes (
  id          text primary key,
  causa       text not null references pjud_causas(rol),
  rut         text not null references pjud_ruts(rut),
  participante text not null default '',
  updated_at  timestamptz not null default now()
);
create index if not exists pjud_litigantes_causa_idx on pjud_litigantes (causa);
create index if not exists pjud_litigantes_rut_idx   on pjud_litigantes (rut);

-- ── Entity: Cuadernos (the Historia rows, per cuaderno) ───────────────────────
-- id = '‹rol›::‹cuaderno›::‹folio›::‹n›' — folio repeats within a cuaderno, so
-- `n` disambiguates duplicate folios in source order.
create table if not exists pjud_cuadernos (
  id                 text primary key,
  causa              text not null references pjud_causas(rol),
  cuaderno           text not null default '',   -- '1 - Principal', '2 - Apremio', …
  folio              text not null default '',
  etapa              text not null default '',
  tramite            text not null default '',
  descripcion_tramite text not null default '',
  fecha_tramite      text not null default '',
  foja               text not null default '',
  georref            text not null default ''
);
create index if not exists pjud_cuadernos_causa_idx on pjud_cuadernos (causa);

-- ── Entity: Escritos (pendientes/ingresados per cuaderno) ─────────────────────
create table if not exists pjud_escritos (
  id           text primary key,
  cuaderno     text not null references pjud_cuadernos(id),
  fecha_ingreso text not null default '',
  tipo_escrito text not null default '',
  solicitante  text not null default ''
);
create index if not exists pjud_escritos_cuaderno_idx on pjud_escritos (cuaderno);

-- ── Entity: Documentos (PDFs attached to a Historia row) ──────────────────────
create table if not exists pjud_documentos (
  id          text primary key,
  cuaderno    text not null references pjud_cuadernos(id),
  origen      text not null default '',   -- which form/source (docu/docuS)
  folio       text not null default '',
  descripcion text not null default '',
  url         text not null default ''    -- Storage public URL
);
create index if not exists pjud_documentos_cuaderno_idx on pjud_documentos (cuaderno);

-- ── Entity: Anexos (causa- or row-level attachments) ──────────────────────────
create table if not exists pjud_anexos (
  id         text primary key,
  cuaderno   text not null references pjud_cuadernos(id),
  origen     text not null default '',
  folio      text not null default '',
  fecha      text not null default '',
  referencia text not null default '',
  url        text not null default ''     -- Storage public URL
);
create index if not exists pjud_anexos_cuaderno_idx on pjud_anexos (cuaderno);

-- ── Storage: public bucket for downloaded PDFs (docs, anexos, ebooks) ─────────
insert into storage.buckets (id, name, public)
values ('pjud-docs', 'pjud-docs', true)
on conflict (id) do update set public = true;

-- ── RLS: writes use the service_role key (bypasses RLS); the SPA reads via anon.
do $$
declare t text;
begin
  foreach t in array array['pjud_tribunales','pjud_ruts','pjud_causas',
                           'pjud_litigantes','pjud_cuadernos','pjud_escritos',
                           'pjud_documentos','pjud_anexos'] loop
    execute format('alter table %I enable row level security;', t);
    execute format('drop policy if exists "anon read %1$s" on %1$s;', t);
    execute format('create policy "anon read %1$s" on %1$s for select to anon using (true);', t);
  end loop;
end $$;
