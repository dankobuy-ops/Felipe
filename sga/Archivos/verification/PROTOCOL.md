# SGA Database Verification Protocol

## Purpose
Interactive table-by-table audit. For each table: I run the checks, report results in chat,
user validates. Focus: structure correctness, CSV→DB mapping, business logic, and column taxonomy.

Data quality / integrity cleanup is deferred — a separate cleanup script will handle it
before final migration from AppSheet.

## How to resume
1. `git pull origin main` to get latest progress
2. Check `progress.md` in this folder — find the first table without ✅ APPROVED
3. Tell Claude: "verify {schema}.{table}" — it reads this file and runs the 4-step protocol

---

## 4-Step Protocol

### STEP 1 — STRUCTURE + MAPPING
Show a single side-by-side table:

| CSV Column | DB Column | DB Type | Nullable | Notes |
|---|---|---|---|---|

- List every CSV column and its DB mapping
- List DB columns with no CSV source (mark as `— (no CSV source)`)
- Flag: CSV columns with no DB target (data loss risk?)
- Flag: type mismatches, length concerns
- Flag: missing FK constraints or indexes on FK columns

### STEP 2 — LOGIC
Review the business logic behind the table:
- Enum columns: do DB enum values cover all CSV values seen in practice?
- Computed / derived columns: is anything stored that should be computed at query time instead?
- FK relationships: do they make architectural sense?
- AppSheet virtual columns: were they accidentally mapped to DB? (should stay computed)
- Any column whose behavior is unclear or whose role overlaps with another

### STEP 3 — COLUMN TAXONOMY
Classify every **DB column** as one of:

| Category | Meaning | App behavior |
|---|---|---|
| `CANONICAL` | User-entered source of truth, seeded from AppSheet | Editable in forms, shown in tables |
| `FK` | Integer foreign key to another table | Rendered as lookup/select in UI |
| `METADATA` | System-managed: id, created_at, updated_at, appsheet_id | Read-only, detail view only |
| `DERIVED` | Currently stored but could/should be computed from other columns | Flag for potential removal |
| `COMPUTED` | Calculated at query time (SQL expression or @property), not in DB | Shown in UI, never editable |
| `DEPRECATED` | Zero data, redundant, candidate for DROP | Hidden in UI, drop in cleanup |

### STEP 4 — VERDICT
- ✅ **APPROVED** — structure and mapping correct, taxonomy recorded
- ⚠️ **WARN** — issues noted but not blocking (document them, continue)
- ❌ **BLOCKED** — critical structural issue, fix before marking approved

---

## Table Order

### Schema: datos (start here)
| # | Table | Rows | CSV Source |
|---|-------|------|-----------|
| 1 | datos.rut | 257 | Datos - Datos Ruts.csv |
| 2 | datos.vehiculo | 272 | Datos - Datos Vehículos.csv |
| 3 | datos.inmueble | 38 | Datos - Datos Inmuebles.csv |
| 4 | datos.otra | 28 | Datos - Datos Otras.csv |
| 5 | datos.vida_salud | 0 | (structure only) |
| 6 | datos.vida_salud_carga | 0 | (structure only) |
| 7 | datos.flota_transporte | 0 | (structure only) |

### Schema: grupos
| # | Table | Rows | CSV Source |
|---|-------|------|-----------|
| 8 | grupos.grupo_cliente | 153 | Grupos - Grupos Clientes.csv |
| 9 | grupos.grupo_entidad | 267 | Grupos - Grupos Entidades.csv |
| 10 | grupos.grupo_materia | 335 | Grupos - Grupos Materias.csv |

### Schema: operaciones
| # | Table | Rows | CSV Source |
|---|-------|------|-----------|
| 11 | operaciones.compania | 15 | Operaciones - Operaciones Compañías.csv |
| 12 | operaciones.seguro | 78 | Operaciones - Operaciones Seguros.csv |
| 13 | operaciones.producto | 328 | Operaciones - Operaciones Productos.csv |
| 14 | operaciones.ejecutivo | 52 | Operaciones - Operaciones Ejecutivos.csv |
| 15 | operaciones.pols | 1099 | Operaciones - Operaciones POLS.csv |
| 16 | operaciones.ramo | 74 | Operaciones - Operaciones Ramos.csv |
| 17 | operaciones.comuna | 692 | Operaciones - Operaciones Comunas.csv |
| 18 | operaciones.proveedor | 24 | Operaciones - Operaciones Proveedores.csv |
| 19 | operaciones.plan | 24 | Operaciones - Operaciones Planes.csv |
| 20 | operaciones.banco | 4 | Operaciones - Operaciones Bancos.csv |
| 21 | operaciones.gestor | 4 | Operaciones - Operaciones Gestores.csv |
| 22 | operaciones.partner | 4 | Operaciones - Operaciones Partners.csv |
| 23 | operaciones.protocolo | 3 | Operaciones - Operaciones Protocolos.csv |
| 24 | operaciones.cobertura | 0 | (structure only) |
| 25 | operaciones.linea_negocio | 0 | (structure only) |
| 26 | operaciones.correo_link_usuario | 0 | NEW TABLE — Operaciones - Operaciones Correos_Links_Usuarios.csv |

### Schema: cruce_tablas
| # | Table | Rows | CSV Source |
|---|-------|------|-----------|
| 26 | cruce_tablas.registros_x_polizas | 535 | Cruce - Cruce RegistrosXPólizas.csv |
| 27 | cruce_tablas.materias_x_registro | 351 | Cruce - Cruce MateriasXRegistro.csv |
| 28 | cruce_tablas.documentos_x_comision | 636 | Cruce - Cruce DocumentosXComisión.csv |
| 29 | cruce_tablas.facturas_x_comision | 248 | Cruce - Cruce FacturasXComisión.csv |
| 30 | cruce_tablas.seguros_x_cia | 81 | Cruce - Cruce SegurosXCía.csv |
| 31 | cruce_tablas.valores_x_cotizacion | 46 | Cruce - Cruce ValoresXCotización.csv |
| 32 | cruce_tablas.cuotas_x_cobranza | 21 | Cruce - Cruce CuotasXCobranza.csv |
| 33 | cruce_tablas.documentos_x_liquidacion | 19 | Cruce - Cruce DocumentosXLiquidación.csv |
| 34 | cruce_tablas.flota_x_vehiculos | 0 | (structure only) |
| 35 | cruce_tablas.coberturas_x_productos | 0 | (structure only) |
| 36 | cruce_tablas.relaciones_ruts | 0 | (structure only) |
| 37 | cruce_tablas.recotizaciones_x_poliza | 0 | (structure only) |
| 38 | cruce_tablas.notas_x_entidades | 0 | (structure only) |
| 39 | cruce_tablas.items_x_envio_cliente | 0 | (structure only) |
| 40 | cruce_tablas.materias_x_envio | 0 | (structure only) |

### Schema: gestion
| # | Table | Rows | CSV Source |
|---|-------|------|-----------|
| 41 | gestion.registro | 672 | Gestión - Gestión Registros.csv |
| 42 | gestion.poliza | 547 | Gestión - Gestión Pólizas.csv |
| 43 | gestion.plan_pago | 717 | Gestión - Gestión Planes de Pago.csv |
| 44 | gestion.cuota | 5003 | Gestión - Gestión Cuotas.csv |
| 45 | gestion.documento | 717 | Gestión - Gestión Documentos.csv |
| 46 | gestion.materia | 914 | Gestión - Gestión Materias.csv |
| 47 | gestion.cotizacion | 468 | Gestión - Gestión Cotizaciones.csv |
| 48 | gestion.comision | 273 | Gestión - Gestión Comisiones.csv |
| 49 | gestion.solicitud | 302 | Gestión - Gestión Solicitudes.csv |
| 50 | gestion.cobranza | 17 | Gestión - Gestión Cobranza.csv |
| 51 | gestion.siniestro | 16 | Gestión - Gestión Siniestros.csv |
| 52 | gestion.nota | 0 | (structure only) |
| 53 | gestion.permanencia | 0 | (structure only) |

### Schema: contabilidad
| # | Table | Rows | CSV Source |
|---|-------|------|-----------|
| 54 | contabilidad.cta_cte | 771 | Contabilidad - Contabilidad Cta Cte.csv |
| 55 | contabilidad.contable | 315 | Contabilidad - Contabilidad Contables.csv |
| 56 | contabilidad.cartola | 32 | Contabilidad - Contabilidad Cartolas.csv |
| 57 | contabilidad.ppm | 39 | Contabilidad - Contabilidad PPM.csv |
| 58 | contabilidad.fecu | 11 | Contabilidad - Contabilidad FECU.csv |
| 59 | contabilidad.liquidacion | 5 | Contabilidad - Contabilidad Liquidaciones.csv |
| 60 | contabilidad.cierre_mensual | 0 | (structure only) |
| 61 | contabilidad.fondo | 0 | (structure only) |
| 62 | contabilidad.pago_cliente | 0 | (structure only) |
| 63 | contabilidad.presupuesto | 0 | (structure only) |

### Schema: comunicacion
| # | Table | Rows | CSV Source |
|---|-------|------|-----------|
| 64 | comunicacion.com_cobranza | 12 | Comunicación - Comunicación Cobranza.csv |
| 65 | comunicacion.com_documento | 2 | Comunicación - Comunicación Documentos.csv |
| 66 | comunicacion.com_cliente | 0 | (structure only) |
| 67 | comunicacion.com_comision | 0 | (structure only) |
| 68 | comunicacion.com_liquidacion | 0 | (structure only) |
| 69 | comunicacion.com_materia | 0 | (structure only) |
| 70 | comunicacion.com_otros | 0 | (structure only) |
| 71 | comunicacion.com_plan_pago | 0 | (structure only) |
| 72 | comunicacion.com_poliza | 0 | (structure only) |
| 73 | comunicacion.com_registro | 0 | (structure only) |

### Schema: agenda
| # | Table | Rows | CSV Source |
|---|-------|------|-----------|
| 74 | agenda.categoria | 10 | Agenda - Agenda Categorías.csv |
| 75 | agenda.obligacion | 9 | Agenda - Agenda Obligaciones.csv |
| 76 | agenda.tarea | 99 | Agenda - Agenda Tareas.csv |

### Schema: configuracion
| # | Table | Rows | CSV Source |
|---|-------|------|-----------|
| 77 | configuracion.parametro | 1 | (manual) |
| 78 | configuracion.vista_dinamica | 1 | (manual) |
| 79 | configuracion.usuario | 0 | (structure only) |
| 80 | configuracion.valor_uf | 0 | (structure only) |

---

## Column Taxonomy Reference

| Category | Meaning | App behavior |
|---|---|---|
| `CANONICAL` | User-entered source of truth, seeded from AppSheet | Editable in forms, shown in tables |
| `FK` | Integer foreign key to another table's id | Rendered as lookup/select in UI |
| `METADATA` | System-managed: id, created_at, updated_at, appsheet_id | Read-only, detail view only |
| `DERIVED` | Currently stored but could/should be computed from other columns | Flag for potential removal |
| `COMPUTED` | Calculated at query time (SQL expression or @property), not in DB | Shown in UI, never editable |
| `DEPRECATED` | Zero data, redundant, candidate for DROP | Hidden in UI, drop in cleanup |

The taxonomy is built incrementally as each table is verified.
Final output: `Archivos/verification/column_taxonomy.json`
