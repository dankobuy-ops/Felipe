---
name: aegis-extend
description: Maps new commercial features into the 9 semantic schemas. Never creates independent tables outside the taxonomy.
disable-model-invocation: true
---

# Aegis Schema Extension Mapper

When asked to build a new feature, map every data element exclusively across the existing 9 schemas before writing any code.

## The 9 Schemas and Their Responsibility

| Schema | Owns |
|--------|------|
| `datos` | Master records: Rut, Vehiculo, Inmueble, VidaSalud, and new insurable items |
| `operaciones` | Compania, Producto, Seguro, Ramo, Ejecutivo — catalog/reference data |
| `gestion` | Core transactional flow: Registro → Cotizacion → Poliza → Cuota → Siniestro |
| `contabilidad` | Liquidacion, Cartola, Contable — financial records |
| `grupos` | GrupoCliente, GrupoMateria, GrupoEntidad — relationship groupings |
| `comunicacion` | All outbound/inbound communications tied to records or policies |
| `agenda` | ObligacionAgenda, TareaAgenda — time-bound tasks and SLAs |
| `cruce_tablas` | Pure M:N bridge tables only — no business columns |
| `configuracion` | Parametro key-value — all configurable thresholds and rules |

## Mapping Protocol

1. **List every data entity** in the requested feature.
2. **Assign each entity to a schema** using the table above. If it fits nowhere, propose extending the closest schema with new columns or a new table inside that schema.
3. **Identify relationships**: FK to `datos.rut` only through `grupos.grupo_materia` or `grupos.grupo_cliente` — never direct FK from a business table to `datos.rut` except the documented exceptions in `CLAUDE.md`.
4. **Flag configuracion candidates**: any threshold, limit, or rule that could change → goes to `configuracion.parametro`.
5. Output a mapping table before writing any model code.

## Output format

```
Feature: <name>

| Entity | Schema | Table (new/existing) | Notes |
|--------|--------|----------------------|-------|
| ...    | ...    | ...                  | ...   |

Configuracion candidates:
- parametro key: <key>, default: <value>, purpose: <why>

FK design:
- <table_a>.<col> → <table_b>.<col> — rationale
```

Only after the mapping is confirmed, proceed to generate the SQLAlchemy models and Alembic migration.
