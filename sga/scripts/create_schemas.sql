-- ============================================================
-- SGA Aegis — Inicialización de Esquemas PostgreSQL
-- Ejecutar UNA SOLA VEZ contra la base de datos sga_aegis
-- ============================================================

-- Crear base de datos (ejecutar como superusuario)
-- CREATE DATABASE sga_aegis ENCODING 'UTF8';

-- Crear los 9 esquemas
CREATE SCHEMA IF NOT EXISTS agenda;
CREATE SCHEMA IF NOT EXISTS comunicacion;
CREATE SCHEMA IF NOT EXISTS configuracion;
CREATE SCHEMA IF NOT EXISTS contabilidad;
CREATE SCHEMA IF NOT EXISTS cruce_tablas;
CREATE SCHEMA IF NOT EXISTS datos;
CREATE SCHEMA IF NOT EXISTS gestion;
CREATE SCHEMA IF NOT EXISTS grupos;
CREATE SCHEMA IF NOT EXISTS operaciones;

-- Extensiones útiles
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "unaccent";

-- Datos iniciales: Ramos (catálogo CMF)
-- (Ejecutar después de que las tablas hayan sido creadas por Alembic/SQLAlchemy)
/*
INSERT INTO operaciones.ramo (codigo, nombre) VALUES
  ('100', 'Incendio'),
  ('200', 'Terremoto'),
  ('300', 'Vehículos'),
  ('400', 'Transporte'),
  ('500', 'Accidentes Personales'),
  ('600', 'Responsabilidad Civil'),
  ('700', 'Vida'),
  ('800', 'Salud'),
  ('900', 'Técnico'),
  ('1000','Garantía y Crédito')
ON CONFLICT (codigo) DO NOTHING;

INSERT INTO operaciones.compania (nombre, nombre_corto) VALUES
  ('BCI Seguros Generales S.A.',       'BCI'),
  ('Compañía de Seguros Chubb S.A.',   'CHUBB'),
  ('Consorcio Nacional de Seguros',    'CONSORCIO'),
  ('HDI Seguros S.A.',                 'HDI'),
  ('Liberty Seguros S.A.',             'LIBERTY'),
  ('Mapfre Compañía de Seguros',       'MAPFRE'),
  ('Reale Seguros Generales S.A.',     'REALE'),
  ('Southbridge Compañía de Seguros',  'SOUTHBRIDGE'),
  ('Zurich Chile Seguros S.A.',        'ZURICH')
ON CONFLICT DO NOTHING;
*/
