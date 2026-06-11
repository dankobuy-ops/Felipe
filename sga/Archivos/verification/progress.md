# DB Verification Progress

**Last updated:** 2026-06-10  
**Branch:** main  
**Protocol:** See PROTOCOL.md

## How to resume on another PC
1. `python scripts/sync_db.py from-cloud` — refresh local DB
2. `git pull origin main` — get latest progress
3. Open this file, find first table not marked ✅ APPROVED
4. Tell Claude: "verify {schema}.{table}"

---

## Status by Table

### Group 1 — Core Business Flow
| # | Table | Rows | Status | Notes |
|---|-------|------|--------|-------|
| 1 | gestion.registro | 672 | ✅ APPROVED | DERIVED-heavy: most fields auto-fill via cot_aceptada/poliza; estado_*→enum; +genera_comision +modifica_materia bools; tipo_materia→COMPUTED; asegurado_id KEEP(derived via asset); DROP traspaso_info_1/2; Comentarios→nota |
| 2 | gestion.poliza | 547 | ✅ APPROVED | umbrella of invariant conditions + computed totals; prices live in materia; estado_seguro(4 masc)+estado_vigencia(dates)+estado_poliza(computed fem); DROP estado/activa/verificador_traspaso; estado_seguro→Ok/Cancelado/Anulado/Consumido; comision_flag→genera_comision; mandato kept(bool+file) |
| 3 | gestion.plan_pago | 717 | ✅ APPROVED | financed installment plan per document; Design Y 1:N (drop unique→partial-unique-on-active); holds FINANCED totals (Pactado); n_plan_pago kept(label); fecha_documento→fecha_plan_pago; cargado_cuota→computed; add updated_at; cuota generation via service |
| 4 | gestion.cuota | 5003 | ✅ APPROVED | installment; Pactado(valor_*)+Pagado(monto_pago→monto_pagado, always CLP, ≠valor_clp); control_pago→enum; estado_cuota=void-override (poliza+documento void→cuota void, else self-state); pago/recibo/factura=files; cobrada=reminder flag; DROP cobro_automatico+cobrar; plan_pago_id NOT NULL; add updated_at |
| 5 | gestion.documento | 717 | ✅ APPROVED | aggregator; estado_documento(computed PDF-completeness) KEEP + NEW boolean `activo`(void state→drives cuota/materia override); genera_movimiento(from tipo+Modif flag); comisión/n_cuotas/inspección auto-COPIED(derived); comision_flag→genera_comision; numero_documento NOT NULL; DROP traspaso_info; plan_pago rel→list |
| 6 | gestion.materia | 914 | ✅ APPROVED | price source-of-truth; priced line per (documento, asset); uso→uso_id; DROP deducible(keep plan_id); 5 derived FKs kept; estado_cobertura/estado_materia computed via views (option 3); NOT NULL documento/base_materia/uso/plan/item/monto_asegurado |

### Group 2 — Master Data
| # | Table | Rows | Status | Notes |
|---|-------|------|--------|-------|
| 7 | datos.rut | 257 | ✅ APPROVED | See migration notes below |
| 8 | datos.vehiculo | 272 | ✅ APPROVED | marca/modelo/color→FK to operaciones lookup tables; combustible stays enum; monto_asegurado CANONICAL(manual); Comentarios→seed to gestion.nota; factura/guia/papeles paths replace in final migration |
| 9 | datos.inmueble | 38 | ✅ APPROVED | zona/tipo_construccion/distancia_agua→enum(Alembic); espacios_comunes/seguridad_incendio/seguridad_robo→enum[]; enum values confirmed |
| 10 | datos.otra | 28 | ✅ APPROVED | add updated_at; tipo_otra→enum(cobertura_vehiculo/inmueble/materia_nueva); seed vehiculo_id+inmueble_id from CSV maps |
| 11 | operaciones.compania | 15 | ✅ APPROVED | rut_id→NOT NULL; remove nombre_comercial (→datos.rut.corto); dias_gracia_* stay per-company; add updated_at; seed appsheet_id |
| 12 | operaciones.seguro | 78 | ✅ APPROVED | TRUNCATE+RESEED (doubled); perfil→perfil_id FK→NEW TABLE operaciones.perfil; add updated_at; seed appsheet_id |
| 13 | operaciones.producto | 328 | ✅ APPROVED | TRUNCATE+RESEED (doubled); uso→uso_id FK; comision_afecta/exenta→Numeric(8,6); tipo_comision/canal/tipo_renovacion→enum; add pols_id FK→pols; add updated_at; seed appsheet_id |
| 14 | operaciones.ejecutivo | 52 | ✅ APPROVED | TRUNCATE+RESEED (doubled); personal data stays (not via datos.rut—by design); add updated_at; seed appsheet_id |
| 15 | operaciones.pols | 1099 | ✅ APPROVED | add compania_id FK→compania (nullable); connect to producto via producto.pols_id |

### Group 3 — Business Logic
| # | Table | Rows | Status | Notes |
|---|-------|------|--------|-------|
| 16 | gestion.cotizacion | 468 | ⏳ PENDING | |
| 17 | gestion.comision | 273 | ⏳ PENDING | |
| 18 | gestion.solicitud | 302 | ⏳ PENDING | |
| 19 | gestion.cobranza | 17 | ⏳ PENDING | |
| 20 | gestion.siniestro | 16 | ⏳ PENDING | |

### Group 4 — Accounting
| # | Table | Rows | Status | Notes |
|---|-------|------|--------|-------|
| 21 | contabilidad.cta_cte | 771 | ⏳ PENDING | |
| 22 | contabilidad.contable | 315 | ⏳ PENDING | |
| 23 | contabilidad.cartola | 32 | ⏳ PENDING | |
| 24 | contabilidad.ppm | 39 | ⏳ PENDING | |
| 25 | contabilidad.fecu | 11 | ⏳ PENDING | |
| 26 | contabilidad.liquidacion | 5 | ⏳ PENDING | |

### Group 5 — Groups & Cross-Tables
| # | Table | Rows | Status | Notes |
|---|-------|------|--------|-------|
| 27 | grupos.grupo_cliente | 153 | ✅ APPROVED | rut_id→NOT NULL; add updated_at; seed partner_id+appsheet_id |
| 28 | grupos.grupo_entidad | 267 | ✅ APPROVED | add updated_at; seed appsheet_id; CSV found (Grupos - Grupos Entidades.csv) |
| 29 | grupos.grupo_materia | 335 | ✅ APPROVED | uso→uso_id FK→operaciones.uso catalog; comentarios→gestion.nota; add updated_at |
| 30 | cruce_tablas.registros_x_polizas | 535 | ✅ APPROVED | DROP cotizacion_id (redundant — cotizacion already has registro_id FK); seed appsheet_id |
| 31 | cruce_tablas.materias_x_registro | 351 | ✅ APPROVED | DROP asegurado_id (lives in grupo_materia); seed appsheet_id |
| 32 | cruce_tablas.documentos_x_comision | 636 | ✅ APPROVED | tipo→enum(Comision/Saldo/Ajuste); DROP cambio_uf+cambio_usd (COMPUTED: uf_amount × valor_uf from document) |
| 33 | cruce_tablas.facturas_x_comision | 248 | ✅ APPROVED | 296 CSV vs 248 DB is by design — only facturas link here, not boletas/notas de crédito |
| 34 | cruce_tablas.seguros_x_cia | 81 | ✅ APPROVED | independent capability catalog (52/81 have no producto yet — valid) |
| 35 | cruce_tablas.valores_x_cotizacion | 46 | ✅ APPROVED | plan_id→NOT NULL; only currency-matching columns filled (NULL not 0); SEED FIX: 0→NULL for non-primary currency cols |
| 36 | cruce_tablas.cuotas_x_cobranza | 21 | ✅ APPROVED | DEPRECATE grupo_cliente_id (0/21 filled, reachable via cobranza chain) |
| 37 | cruce_tablas.documentos_x_liquidacion | 19 | ✅ APPROVED | clean junction |

### Group 6 — Catalog & Config
| # | Table | Rows | Status | Notes |
|---|-------|------|--------|-------|
| 38 | operaciones.ramo | 74 | ✅ APPROVED | TRUNCATE+RESEED (doubled); add updated_at; seed appsheet_id |
| 39 | operaciones.comuna | 692 | ✅ APPROVED | TRUNCATE+RESEED (doubled); no timestamps needed; seed appsheet_id |
| 40 | operaciones.proveedor | 24 | ✅ APPROVED | TRUNCATE+RESEED (doubled); rut_id→NOT NULL; remove corto+correo (→datos.rut); add updated_at; seed appsheet_id |
| 41 | operaciones.plan | 24 | ✅ APPROVED | REMOVE producto_id; concept name=Plan everywhere; junction cruce_tablas.planes_x_producto (M:N); gestion.materia+cotizacion use plan_id FK |
| 42 | operaciones.banco | 4 | ✅ APPROVED | rut_id→NOT NULL; remove corto (→datos.rut.corto); add updated_at; seed appsheet_id |
| 43 | operaciones.gestor | 4 | ✅ APPROVED | rut_id→NOT NULL; remove cuenta_corriente (→datos.rut); add updated_at; seed appsheet_id |
| 44 | operaciones.partner | 4 | ✅ APPROVED | rut_id→NOT NULL; keep comision_nuevos/renovaciones/contrato; seed appsheet_id |
| 45 | operaciones.protocolo | 3 | ✅ APPROVED | grupo_entidad_id→NOT NULL; responsable_id→NOT NULL; add archivos varchar; add updated_at |
| 46 | operaciones.correo_link_usuario | 0 | ✅ APPROVED | NEW TABLE (16th CSV); flexible catalog for credentials/links/emails per entity; multi-entity FK (all nullable); seed from Correos_Links_Usuarios.csv |
| 47 | agenda.categoria | 10 | ⏳ PENDING | |
| 47 | agenda.obligacion | 9 | ⏳ PENDING | |
| 48 | agenda.tarea | 99 | ⏳ PENDING | |
| 49 | comunicacion.com_cobranza | 12 | ⏳ PENDING | |
| 50 | comunicacion.com_documento | 2 | ⏳ PENDING | |
| 51 | configuracion.parametro | 1 | ⏳ PENDING | |
| 52 | configuracion.vista_dinamica | 1 | ⏳ PENDING | |

### Group 7 — Zero-Row Tables (structure only)
| # | Table | Status | Notes |
|---|-------|--------|-------|
| 53 | comunicacion.com_cliente | ⏳ PENDING | |
| 54 | comunicacion.com_comision | ⏳ PENDING | |
| 55 | comunicacion.com_liquidacion | ⏳ PENDING | |
| 56 | comunicacion.com_materia | ⏳ PENDING | |
| 57 | comunicacion.com_otros | ⏳ PENDING | |
| 58 | comunicacion.com_plan_pago | ⏳ PENDING | |
| 59 | comunicacion.com_poliza | ⏳ PENDING | |
| 60 | comunicacion.com_registro | ⏳ PENDING | |
| 61 | configuracion.usuario | ⏳ PENDING | |
| 62 | configuracion.valor_uf | ⏳ PENDING | |
| 63 | contabilidad.cierre_mensual | ⏳ PENDING | |
| 64 | contabilidad.fondo | ⏳ PENDING | |
| 65 | contabilidad.pago_cliente | ⏳ PENDING | |
| 66 | contabilidad.presupuesto | ⏳ PENDING | |
| 67 | cruce_tablas.coberturas_x_productos | ✅ APPROVED | M:N producto↔cobertura; seed after final migration |
| 68 | cruce_tablas.flota_x_vehiculos | ✅ APPROVED | rol→enum RolFlota (values TBD); asegurado_id nullable |
| 69 | cruce_tablas.items_x_envio_cliente | ✅ APPROVED | structure correct |
| 70 | cruce_tablas.materias_x_envio | ✅ APPROVED | structure correct |
| 71 | cruce_tablas.notas_x_entidades | ✅ APPROVED | 29-FK centralized notes junction (previously decided) |
| 72 | cruce_tablas.recotizaciones_x_poliza | ✅ APPROVED | re-quoting active policies — DROP comentarios→gestion.nota; structure valid |
| 73 | cruce_tablas.relaciones_ruts | ✅ APPROVED | tipo_relacion→enum TipoRelacionRut (values TBD) |
| 74 | datos.flota_transporte | ✅ APPROVED | tipo_carga+medidas_seguridad→enum[]; historial_siniestros→DEPRECATED; frecuencia_viajes free text |
| 75 | datos.vida_salud | ✅ APPROVED | add updated_at |
| 76 | datos.vida_salud_carga | ✅ APPROVED | drop nombre/paterno/materno/rut/fecha_nacimiento/comentarios; rut_carga_id→NOT NULL; add updated_at |
| 77 | gestion.nota | ⏳ PENDING | |
| 78 | gestion.permanencia | ⏳ PENDING | |
| 79 | operaciones.cobertura | ✅ APPROVED | connects to productos via EXISTING cruce_tablas.coberturas_x_productos (M:N); seed after final migration |
| 80 | operaciones.linea_negocio | ✅ APPROVED | add perfil_id FK→operaciones.perfil; junction cruce_tablas.productos_x_linea (M:N); remove Comentarios→gestion.nota; ramo_id+compania_id already in DB |

---

---

## Migration Notes (decisions made during verification)

### datos.rut
**ADD columns:**
- `grupo_cliente_id` INT FK → grupos.grupo_cliente (nullable; post_update=True on relationship due to circular FK with grupo_cliente.rut_id)
- `contacto_id` INT FK → datos.rut self-ref (rename+retype from `contacto` varchar; old text values need resolving to rut IDs in cleanup)

**NEW TABLE: cruce_tablas.rut_rol**
- `rut_id` FK → datos.rut NOT NULL
- `rol` enum NOT NULL — values: cliente, gestor, compania, banco, partner, proveedor, otro
- Indexes: btree on (rol), btree on (rut_id)
- Replaces `tipo_cliente` boolean pattern

**DEPRECATE (drop in cleanup migration):**
- `numero` — always empty, address numbers embedded in `direccion`
- `tipo_cliente` — replaced by cruce_tablas.rut_rol junction table

**Contact resolution logic (app layer):**
1. datos.rut.contacto_id is set → use that RUT
2. datos.rut.grupo_cliente_id is set → use grupo_cliente.rut_id as default contact
3. Neither → RUT is incomplete (creation flow was interrupted)

**New client creation flow (3-step transaction):**
1. INSERT datos.rut (grupo_cliente_id = NULL)
2. INSERT grupos.grupo_cliente (rut_id = new rut id, partner_id, carpeta)
3. UPDATE datos.rut SET grupo_cliente_id = new grupo_cliente id
Uses post_update=True on SQLAlchemy relationship.

**grupo_cliente.rut_id → KEEP** (default contact RUT for the group)

### datos.vehiculo
**CONVERT columns (varchar → FK):**
- `marca` → `marca_id` FK → operaciones.marca_vehiculo(id, nombre)
- `modelo` → `modelo_id` FK → operaciones.modelo_vehiculo(id, marca_id, nombre) — hierarchical
- `color` → `color_id` FK → operaciones.color_vehiculo(id, nombre) — normalizes Plata/Plateado

**NEW TABLES (operaciones schema):**
- `operaciones.marca_vehiculo(id, nombre)`
- `operaciones.modelo_vehiculo(id, marca_id FK, nombre)`
- `operaciones.color_vehiculo(id, nombre)`

**SEED FIXES:**
- Populate new lookup tables from existing varchar data before replacing columns
- Write CSV `Comentarios` (18 rows) → gestion.nota + cruce_tablas.notas_x_entidades
- Populate factura, guia_despacho, papeles from CSV (AppSheet paths, replace in final migration)
- Populate appsheet_id from CSV

**KEEP as-is:** combustible (enum), anio (integer), monto_asegurado (CANONICAL, manual entry)

### datos.inmueble
**CONVERT to enum (Alembic extensible):**
- `zona` → ZonaInmueble: Urbana, Rural, Periurbana, Industrial
- `tipo_construccion` → TipoConstruccion: Sólida, Liviana, Mixta, Prefabricada
- `distancia_agua` → DistanciaAgua: menos_50m, entre_50m_200m, mas_200m

**CONVERT to enum[] (multi-select, Alembic extensible):**
- `espacios_comunes` → EspacioComun[]: Piscina, Gimnasio, Estacionamiento, Salón, Jardín, Quincho, Conserjería
- `seguridad_incendio` → SeguridadIncendio[]: Alarma, Extintor, Rociadores, Salida_emergencia, Detector_humo, Red_seca
- `seguridad_robo` → SeguridadRobo[]: Alarma, CCTV, Guardia, Reja, Cerradura_reforzada, Portero, Guardias_24hrs

**Note:** Enum values to be confirmed with user before writing migration. Current CSV text values need remapping to new enum keys.

### datos.otra
- ADD `updated_at` TIMESTAMPTZ (missing vs all other datos tables)
- CONVERT `tipo_otra` varchar → enum: cobertura_vehiculo, cobertura_inmueble, materia_nueva
- SEED FIX: populate vehiculo_id and inmueble_id from CSV AppSheet IDs using existing maps["vehiculo"] / maps["inmueble"]

### datos.vida_salud
- ADD `updated_at` TIMESTAMPTZ

### datos.vida_salud_carga
- ADD `updated_at` TIMESTAMPTZ
- CHANGE `rut_carga_id` nullable → NOT NULL
- DROP: rut (varchar), nombre, nombre2, paterno, materno, fecha_nacimiento, comentarios
- KEEP: vida_salud_id, rut_carga_id, altura, peso, dps, otros_documentos

### datos.flota_transporte
- CONVERT `tipo_carga` varchar → enum[] TipoCarga: general, perecedero, refrigerado, peligroso, liquido, a_granel, maquinaria, electronico, farmaceutico, otro
- CONVERT `medidas_seguridad` text → enum[] MedidaSeguridad: GPS, escolta, seguro_antirrobo, camara_bordo, candados_reforzados, contenedor_sellado, conductor_certificado, otro
- DEPRECATE `historial_siniestros` — computed from gestion.siniestro via flota_x_vehiculos
- KEEP `frecuencia_viajes` as free text

### CROSS-CUTTING: operaciones.uso catalog (affects 4 tables)
NEW TABLE `operaciones.uso(id, nombre, descripcion, activo)`:
  Seed values: particular, comercial, habitacional, vacacional, mixto, industrial, otro

Tables to update (replace uso varchar/enum → uso_id FK → operaciones.uso):
- datos.inmueble.uso (UsoInmueble enum → FK, drop enum)
- grupos.grupo_materia.uso (varchar → FK)
- gestion.materia.uso (varchar → FK) ← apply when verifying gestion.materia
- operaciones.producto.uso (varchar → FK) ← DECIDED: producto values: Particular/Comercial/NULL

### CROSS-CUTTING: rut_id NOT NULL rule
All tables that have `rut_id FK → datos.rut` must have it NOT NULL:
- operaciones.compania.rut_id → NOT NULL
- operaciones.banco.rut_id → NOT NULL
- operaciones.gestor.rut_id → NOT NULL
- operaciones.partner.rut_id → NOT NULL
- operaciones.proveedor.rut_id → NOT NULL
Rationale: datos.rut centralizes ALL ruts in the system. No entity record
can exist without a rut. If the rut is missing, create it first.

### CROSS-CUTTING: ramo / seguro / producto hierarchy
Three distinct concepts — use them precisely:

**ramo** = CMF regulatory classification (e.g., "310 Vehículos", "100 Incendio")
  - Immutable regulatory catalog. Used for: regulatory reporting, commission tax classification.
  - Never company-specific.

**seguro** = internal product family (e.g., "Seguro de Auto", "Seguro de Hogar")
  - Groups related productos across all companies.
  - seguro.perfil_id → operaciones.perfil (which market segment this family targets)
  - Used for: catalog browsing, cross-selling recommendations, profile matching.
  - A seguro can span multiple ramos (e.g., "Seguro Multiriesgo" covers Incendio + RCI).

**producto** = the specific sellable unit (e.g., "Plan Auto Básico — Rimac")
  - Always belongs to one compania, one seguro, one ramo.
  - producto.pols_id FK → operaciones.pols (policy template for this product)
  - Available plans → cruce_tablas.planes_x_producto (M:N)
  - Available coberturas → cruce_tablas.coberturas_x_productos (M:N, already exists)
  - Commission rates: comision_afecta / comision_exenta as Numeric(8,6), display 2 decimals

### CROSS-CUTTING: Plan concept (name cleanup)
Concept name is "Plan" everywhere — remove all references to "deducible" in column names.
- `operaciones.plan` = the catalog of plan/coverage tier options
- At cotizacion and materia level: plan_id FK → operaciones.plan
- A producto can have multiple plans: junction cruce_tablas.planes_x_producto (producto_id, plan_id)
- Cleanup task: when verifying gestion.cotizacion and gestion.materia, rename any "deducible" column to plan_id

### operaciones.compania
- `rut_id` → NOT NULL
- REMOVE `nombre_comercial` (DERIVED: datos.rut.corto is the short name; datos.rut.razon_social is the legal name — UI fetches both from rut_id join, no separate storage)
- `dias_gracia_carta`, `dias_gracia_inspeccion` → STAY per-company (each insurer has different grace periods)
- ADD `updated_at` TIMESTAMPTZ
- SEED: populate appsheet_id from CSV ID column

### operaciones.seguro
- TRUNCATE + RE-SEED (78 rows = 2× 39 CSV, seed ran twice)
- CONVERT `perfil` varchar → `perfil_id` FK → NEW TABLE `operaciones.perfil`
- ADD `updated_at` TIMESTAMPTZ
- SEED: populate appsheet_id

**NEW TABLE operaciones.perfil:**
- `id, nombre, descripcion, activo, created_at`
- Seed values: Masivo, Corporativo, Pyme, Personal, Familia, Premium, Otro
- Purpose: market segmentation — groups seguros by target client profile.
  Future: grupo_cliente.perfil_id FK to match clients with suitable products.

### operaciones.producto
- TRUNCATE + RE-SEED (328 rows = 2× 164 CSV, seed ran twice)
- REPLACE `uso` varchar → `uso_id` FK → operaciones.uso (values: Particular/Comercial/NULL→NULL)
- CONVERT `tipo_comision` varchar → TipoComision enum: Anual, Mensual
- CONVERT `canal` varchar → Canal enum: Web, ANS, Directo
- CONVERT `tipo_renovacion` varchar → TipoRenovacion enum: Automatica, Manual
- KEEP `convenio` as varchar (sparse, few values, no enum needed)
- CHANGE `comision_afecta` and `comision_exenta`: Numeric(5,2) → Numeric(8,6)
  (store 6 decimal places, UI rounds to 2 for display)
- ADD `pols_id` FK → operaciones.pols (nullable — not all products have a POLS template)
- ADD `updated_at` TIMESTAMPTZ
- SEED: populate appsheet_id

### operaciones.pols
- ADD `compania_id` FK → operaciones.compania (nullable — company may not be in system yet)

### operaciones.ramo
- TRUNCATE + RE-SEED (74 rows = 2× 37 CSV)
- ADD `updated_at` TIMESTAMPTZ
- SEED: populate appsheet_id

### operaciones.plan
- REMOVE `producto_id` FK (was never populated: 0/24 filled)
- Plan is a generic catalog of coverage tiers/deductible options, not product-specific
- A producto can have multiple plans: NEW junction cruce_tablas.planes_x_producto
  (producto_id FK → operaciones.producto, plan_id FK → operaciones.plan)
- gestion.materia and gestion.cotizacion both reference plan_id FK → operaciones.plan
  (cleanup task: rename any "deducible" column to plan_id when those tables are verified)

### operaciones.banco
- `rut_id` → NOT NULL
- REMOVE `corto` (DERIVED from datos.rut.corto via rut_id join)
- `casa_matriz`, `sucursal`, `fono_matriz`, `fono_sucursal`, `web`, `portal` → STAY (banco-specific operational fields not in datos.rut)
- ADD `updated_at` TIMESTAMPTZ
- SEED: populate appsheet_id for the 2 rows that came from CSV

### operaciones.gestor
- `rut_id` → NOT NULL
- REMOVE `cuenta_corriente` (DERIVED from datos.rut.cuenta_corriente)
- KEEP `usermail` (gestor-specific: their app/system login email, different from personal email in datos.rut)
- ADD `updated_at` TIMESTAMPTZ
- SEED: populate appsheet_id

### operaciones.partner
- `rut_id` → NOT NULL
- No fields to remove (only operational fields remain: comision_nuevos, comision_renovaciones, contrato)
- `contrato` → file path, replace in final migration
- SEED: populate appsheet_id

### operaciones.proveedor
- TRUNCATE + RE-SEED (24 rows = 2× 12 CSV)
- `rut_id` → NOT NULL
- REMOVE `corto` (DERIVED from datos.rut.corto)
- REMOVE `correo` (DERIVED from datos.rut.email) — no CSV source, was added manually
- `servicio`, `casa_matriz`, `sucursal`, `fono_matriz`, `fono_sucursal`, `web`, `portal` → STAY (proveedor-specific)
- ADD `updated_at` TIMESTAMPTZ
- SEED: populate appsheet_id

### operaciones.protocolo
- `grupo_entidad_id` → NOT NULL (FK to grupos.grupo_entidad)
- `responsable_id` → NOT NULL (FK to operaciones.ejecutivo)
  Values may be missing — backfill in final migration
- ADD `archivos` varchar (file path from CSV "Archivos" column)
- ADD `updated_at` TIMESTAMPTZ

### operaciones.comuna
- TRUNCATE + RE-SEED (692 rows = 2× 346 CSV)
- No timestamp columns needed (geographic catalog, immutable)
- SEED: populate appsheet_id

### operaciones.cobertura
- Connects to productos via EXISTING cruce_tablas.coberturas_x_productos (M:N)
- Seed when ready; 1 CSV row available
- After final migration: script to auto-link coberturas to corresponding productos

### operaciones.linea_negocio
- ADD `perfil_id` FK → operaciones.perfil (which market segment this business line targets)
- NEW junction cruce_tablas.productos_x_linea (linea_negocio_id, producto_id) — M:N
- Remove Comentarios → gestion.nota (centralized)
- `ramo_id`, `compania_id` already in DB — KEEP
- `carpeta` → file path, keep

### NEW TABLE: operaciones.correo_link_usuario (16th operaciones CSV)
This is a flexible catalog for storing contacts, credentials, portal links, and emails
that don't fit as hardcoded fields on any specific entity table.
One row = one credential/link/email entry for one entity.

**Columns:**
- `id` — PK
- `compania_id` FK → operaciones.compania (nullable)
- `banco_id` FK → operaciones.banco (nullable)
- `proveedor_id` FK → operaciones.proveedor (nullable)
- `gestor_id` FK → operaciones.gestor (nullable)
- `partner_id` FK → operaciones.partner (nullable)
- `grupo_entidad_id` FK → grupos.grupo_entidad (nullable)
- `tipo` varchar — what kind of entity (Cía / Entidad / etc.)
- `tipo_usuario` varchar — type of account (Admin, Consulta, API, etc.)
- `tipo_link` enum — Pago, Portal_Corredor, Pagina_Web, Suscripcion_Mandato, Inspecciones
- `tipo_correo` enum — Asistencia, Cobranzas, Comisiones, Inspecciones, Mesa_Central, Siniestros, Solicitudes
- `usuario` varchar — username / login
- `link` varchar — URL
- `correo` varchar — email address
- `contrasena` varchar — password (plaintext, internal use only; flag for future encryption)
- `fono` varchar
- `created_at` TIMESTAMPTZ
- `updated_at` TIMESTAMPTZ
- `appsheet_id` varchar
Note: CSV "Comentarios" column → gestion.nota (centralized)
Note: At most one FK should be non-NULL per row (enforced by app layer, not DB constraint)

### grupos.grupo_cliente
- `rut_id` → NOT NULL
- ADD `updated_at`
- SEED: partner_id from datos.rut CSV Partner column (21 rows, 2 unique partners)
- SEED: appsheet_id

### grupos.grupo_entidad
- ADD `updated_at`
- SEED: appsheet_id

### grupos.grupo_materia
- REPLACE `uso` varchar → `uso_id` FK → operaciones.uso
- DROP `comentarios` → move to gestion.nota + notas_x_entidades
- ADD `updated_at`

### cruce_tablas.documentos_x_comision
- CONVERT `tipo` varchar → TipoDocComision enum: Comision, Saldo, Ajuste
- DEPRECATE `cambio_uf` and `cambio_usd` — COMPUTED at query time:
  `cambio_uf = (afecto_uf + exento_uf) × valor_uf` where valor_uf comes from the linked document
  `cambio_usd` = same pattern with USD rate
  Neither should be stored; the inputs (uf amounts + exchange rate on document) are sufficient.

### cruce_tablas.facturas_x_comision
- 296 CSV vs 248 DB is by design: CSV includes all contable↔comision links, but only contable
  entries of type Factura should appear here. Boletas, notas de crédito, etc. are excluded.
- Structure correct as-is. Gap resolved in cleanup migration.

### cruce_tablas.registros_x_polizas
- DROP `cotizacion_id` — redundant. cotizacion already points to registro via FK.
  The traceability chain is: poliza → (via registros_x_polizas) → registro → cotizacion(es).
- SEED FIX: populate appsheet_id

### cruce_tablas.materias_x_registro
- DROP `asegurado_id` — lives in grupos.grupo_materia.asegurado_id already.
- SEED FIX: populate appsheet_id

### cruce_tablas.cuotas_x_cobranza
- DEPRECATE `grupo_cliente_id` (0/21 filled; reachable via cobranza→registro→grupo_cliente)

### cruce_tablas.valores_x_cotizacion
- `plan_id` → NOT NULL
- Only the currency-matching column set should be filled; others stay NULL.
  AppSheet defaulted empty numeric fields to 0 — SEED FIX: convert 0→NULL for all
  uf_*/clp_*/usd_*/tasa_*/cambio_moneda columns where the policy currency doesn't match.
- SEED FIX: populate appsheet_id

### cruce_tablas.recotizaciones_x_poliza
- Purpose: re-quoting an active policy — client wants to explore better options mid-term.
  poliza_id = the active policy being re-evaluated
  cotizacion_id = the new comparison quote
- DROP `comentarios` → gestion.nota (centralized pattern)

### NEW TABLES to create in cruce_tablas (decisions from prior schemas)

**cruce_tablas.rut_rol** (from datos.rut):
- rut_id FK → datos.rut NOT NULL
- rol enum NOT NULL — values: cliente, gestor, compania, banco, partner, proveedor, otro
- Indexes: btree on (rol), btree on (rut_id)

**cruce_tablas.planes_x_producto** (from operaciones.plan):
- producto_id FK → operaciones.producto NOT NULL
- plan_id FK → operaciones.plan NOT NULL
- No extra payload columns

**cruce_tablas.productos_x_linea** (from operaciones.linea_negocio):
- linea_negocio_id FK → operaciones.linea_negocio NOT NULL
- producto_id FK → operaciones.producto NOT NULL
- No extra payload columns

---

## gestion schema — verification notes

### gestion.registro  ✅ APPROVED (2026-06-10)
**Core insight:** registro is a DERIVED-heavy table. Only a few fields are user-entered; most are
auto-populated by the app layer from the linked **Cot Aceptada** (cotizacion) or from **Póliza**,
with the exact source depending on `tipo_registro`.

**Auto-fill source by type:** (renovacion and inclusion are similar — both driven by poliza_id + cot_aceptada)
- `prospecto` / `negocio` → fields fill from **cot_aceptada**.
- `renovacion` → **inherits all fields from the renewed policy** (poliza_id): prime values, dates,
  product, commissions, etc. are surfaced in the app from the original policy. Override rules:
    - If the **product changes**, the conditions must be entered/updated manually for the renewal.
    - If the inherited conditions are unsatisfactory, OR a **cotizacion offers better conditions than
      the original policy**, then ALL conditions are updated from that cotizacion (cot_aceptada).
  So: default = inherit from renewed póliza; override = manual edit or pull from cot_aceptada.
- `inclusion` → **general/structural policy conditions** fill from **poliza_id**, BUT **prices and
  `fecha_inicio_vigencia` do NOT fill at first**. This type should generally include a **cotizacion**,
  so price values are taken from there (cot_aceptada). Prices + fecha_inicio_vigencia are **backfilled
  once the inclusion policy document is emitted**.
- `traspaso` → **MANUAL**. No cot_aceptada / source policy to derive from; user enters the minimum
  necessary data by hand. The otherwise-DERIVED fields are entered manually for this type.

**CANONICAL (user-entered):**
- fecha_registro, tipo_registro
- estado_prospecto, estado_negocio, estado_renovacion, estado_traspaso, estado_inclusion
- contratante_id (set at creation), pagador_id (defaults to contratante)
- cot_aceptada_id (the accepted quote — drives auto-fill for prospecto/negocio/renovacion)
- poliza_id (renovacion = policy being renewed; inclusion = policy being included into; NOT the produced policy)
- condiciones, archivos (file path), fin_gestion (date gestion closed — business won or fell through)
- (for `traspaso`) the otherwise-DERIVED economic/FK fields, entered manually

**ADD two control booleans (CANONICAL):**
- `genera_comision` (← CSV "Comisión?") — whether the business yields commission.
  e.g. Traspaso yields none until the next renewal.
- `modifica_materia` (← CSV "Modifica Materia?") — renovation flag: client has modifications
  to apply to the asset being renewed.

**Estado columns → all enums** (negocio/prospecto already enum; add the other three):
- estado_renovacion → NEW enum EstadoRenovacion: Renovado, No_Renovado, Cambio_Cia, Prorroga, Pendiente
- estado_traspaso   → NEW enum EstadoTraspaso: Ok, Pendiente
- estado_inclusion  → NEW enum EstadoInclusion: Pendiente (empty data is fine)

**DERIVED (stored, auto-filled by app per the type rules above; manual for traspaso):**
- grupo_cliente_id ← auto via contratante.rut → grupo_cliente ("Cliente" populates from Contratante)
- asegurado_id ← auto via the linked asset/materia → grupo_materia.asegurado
  (KEEP the column — reverses earlier drop proposal; source of truth stays grupos.grupo_materia)
- seguro_id ← auto (cot_aceptada / poliza)
- compania_id, producto_id, plan_id, ejecutivo_id ← auto (cot_aceptada / poliza)
- moneda, forma_pago, n_cuotas, valor_cuota ← auto (cot_aceptada / poliza)
- uf/clp/usd_prima_afecta/exenta, pct_comision_afecta/exenta ← auto (cot_aceptada / poliza)
- tipo_inspeccion, n_inspeccion ← auto (cot_aceptada / poliza)
- **fecha_inicio_vigencia** ← special: NOT set at creation for any type. Backfilled from the
  **produced póliza once that policy record is completed** (timing depends on inspection / approval).

**COMPUTED (do NOT store):**
- tipo_materia (CSV "Tipo Materia" = Individual/Múltiple) — was an AppSheet logic column to route
  PDF templates by single vs multiple assets. Compute from COUNT(materias_x_registro).
- estado_gestion — already a @property in the model.

**DEPRECATE (drop in cleanup):**
- traspaso_info_1, traspaso_info_2 — AppSheet auxiliary columns, no longer needed.

**To gestion.nota:** CSV "Comentarios" (60 non-empty) → gestion.nota + notas_x_entidades.

**poliza_id semantics:** the policy being renewed (renovacion) or included into (inclusion). The
policy a registro eventually *produces* is linked separately via cruce_tablas.registros_x_polizas.
Don't conflate the two.

**Seed completeness (deferred):** the final seed must populate the CANONICAL + DERIVED columns the
current seed skips (forma_pago, usd_prima_*, condiciones, archivos, fin_gestion, cot_aceptada_id,
estado_inclusion) once the cot_aceptada / poliza auto-fill logic lives in the service layer.

**Row count:** CSV 996 → DB 672; 324 skipped (Cliente without grupo_cliente match) — data-quality, deferred.

### gestion.poliza  ✅ APPROVED (2026-06-10)
**Role:** the policy "umbrella" — stores the scalar, **invariant policy conditions** (the header) and
exposes computed totals. Per-asset prices and installment schedules live in child tables.

**Source-of-truth split (by cardinality):**
- Scalar invariants (1 per policy) → stored physically on poliza.
- Prima / prices (per asset) → **`gestion.materia` is the source of truth**. NO prima columns on poliza.
- Installment schedules → **`gestion.plan_pago` / `gestion.cuota`, governed by `gestion.documento`**.
- All policy-level totals → **COMPUTED, never stored**.

**Invariant conditions (do NOT change with assets/modifications) — CANONICAL stored:**
producto_id (NOT NULL) + derived compania_id/ramo_id/seguro_id; fecha_termino (end date);
grupo_cliente_id; contratante_id; pagador_id; ejecutivo_id; forma_pago; pct_comision_afecta/exenta.
Header fields: numero_poliza, fecha_emision, fecha_inicio, moneda, n_cuotas (header default),
estado_seguro, control booleans, mandato, fecha_cancelacion (nullable — only when cancelled), otros_archivos.

**NOT NULL stance:** nullable-until-emitted + completeness gate. Fields known at binding
(producto, contratante, pagador, moneda, ejecutivo, end date) → NOT NULL. Emission-dependent fields
(numero_poliza, fecha_emision, anything price-derived) → nullable until the company emits the policy
PDF; a rule (app-layer or CHECK) blocks estado_seguro reaching an emitted/"Ok" state until filled.

**Status — three distinct concepts:**
- `estado_seguro` — CANONICAL, stored, **masculine**, user-interactive. Enum shrinks to exactly
  **Ok, Cancelado, Anulado, Consumido** (CSV data already matches these 4).
- `estado_vigencia` — COMPUTED, dates only: **Vigente / Vencida** (Pendiente if before fecha_inicio).
- `estado_poliza` — COMPUTED (NEW), **feminine**, comprehensive for viewing:
  **Vigente, Vencida, Cancelada, Anulada, Consumida, Caída, Pendiente, Condicional**
  (inspección folded into Pendiente). Derived from estado_seguro + estado_vigencia + payment state
  (Caída) + admin conditions (Condicional) + emission/inspection state (Pendiente).
- DROP stored `estado` (EstadoPoliza) and `activa` — replaced by the computed concepts above.

**Computed totals (NOT stored — hybrid properties w/ SQL expressions + a `poliza_resumen` view):**
- Asset rollups (SUM over materia): total_prima_afecta/exenta per currency, total_monto_asegurado, total_comision_generada.
- Installment rollups (over active plan_pago/cuota): n_cuotas_total, total_a_pagar, total_pagado, saldo_pendiente.

**mandato:** KEEP — two jobs: bool control ("need to send signed PDF?") + a file reference for the
signed document (path, like other archivos; not a blob).

**DROP:** estado, activa, verificador_traspaso_id (AppSheet auxiliary).
**Rename:** comision_flag → `genera_comision` (consistency with registro).
**→ gestion.nota:** Comentarios (38 non-empty).
**Renewal lineage:** poliza_anterior_id (self-FK) kept; backfilled via backfill_poliza_anterior.py.

**Commission-sort clarification (narrows AEGIS rule in CLAUDE.md):** the no-commission-ranking rule
applies to **client-facing recommendation/comparison logic** (never rank/optimize coverage by broker
commission). It does NOT forbid commission as a **sortable column in internal accounting/reconciliation
grids** (cross-checking against the insurer). Recommendation-ranking prohibition stays intact.
TODO: add one clarifying line to CLAUDE.md (pending user go-ahead).

**Cardinality model → carry into plan_pago / cuota / documento / materia:**
- **Plan de pago is per DOCUMENT** (not per policy). A document can have multiple planes de pago over
  time but **only 1 active**. Cuotas attach to plan_pago.
  **DECIDED — Design Y (1:N, one active):** `documento → plan_pago` is **1:N**. DROP the current
  `PlanPago.documento_id` `unique=True` (it baked a wrong 1:1 assumption — one row per document in
  today's seed data does NOT imply a 1:1 relationship) and replace with a **partial unique index
  `UNIQUE (documento_id) WHERE activo`** so a document keeps its plan history while only 1 is active.
  Keep the `activo` flag (it's meaningful under 1:N). Apply when verifying plan_pago.
- **A policy has multiple documents → multiple active planes de pago coexist** (one active per document),
  each scoped to its own asset(s).
- **Mid-policy inclusion adds a NEW document; the old document is NOT discarded.** Old document governs
  the original asset; new document (endoso) governs the newly included asset. Each carries its own
  active plan de pago (the inclusion's installment count = months remaining to policy end).
- **`documento → plan_pago` is 0-or-1 (OPTIONAL), driven by price movement:**
  - **Price-movement documents** (set/change the prima the client pays — e.g. póliza, renovación,
    inclusión) → generate a **new plan de pago** (+ its cuotas).
  - **Non-price documents** (correct asset data, fix a commission %, other administrative/corrective
    changes) → **no plan de pago** (no change to what the client pays; commission is the broker's cut,
    not the client's price).
  - Documento needs a way to express this — derivable from `tipo_documento`, or an explicit flag
    (e.g. `genera_movimiento`). Decide when verifying `gestion.documento`.
- Prima source stays `gestion.materia` (per asset).

**Data-flow (feeders → aggregators) — verification dependency map:**
```
materia ───┐
           ├──> documento ──> poliza   (documento governs; poliza = umbrella)
plan_pago ─┘
   ▲ │  (two-way with cuota)
   │ ▼
 cuota
```
- materia → documento (assets belong to a document)
- plan_pago → documento (a document's active plan de pago)
- cuota ⇄ plan_pago: plan_pago defines how many installments + theoretical totals; cuotas report back
  the live state of every installment.
- documento → poliza (documents roll up to the policy umbrella; poliza totals computed from here down)

**Row count:** CSV 998 → 547 real rows (451 blank placeholder rows) = DB 547. ✓

### gestion.materia  ✅ APPROVED (2026-06-10)
**Role:** one **priced line per (documento, asset)** — `documento_id` (governing doc) + `base_materia_id`
(→ grupos.grupo_materia = asset↔asegurado). The SAME asset gets a new materia row under each new
document (original + inclusión/modificación). **Source of truth for per-asset prices.**

**NOT NULL:** documento_id, base_materia_id, uso_id, plan_id, item, monto_asegurado.
(Prima columns are NOT blanket NOT NULL — see currency-family rule below. NOT NULL targets need cleanup
backfill, e.g. monto_asegurado only 219/921 populated today.)

**CANONICAL (price source — these are `Pactado` nature):** afecta_uf/exenta_uf, afecta_clp/exenta_clp,
afecta_usd/exenta_usd (per currency-family rule), monto_asegurado, tasa_afecta, tasa_exenta, item,
plan_id (from "Deducible"), uso(→uso_id), fecha_exclusion (nullable — only when excluded).

**DERIVED (auto-filled via lineage — KEPT stored, user-approved):** poliza_id, grupo_cliente_id,
contratante_id (via documento→poliza); seguro_id, asegurado_id (via base_materia→grupo_materia).

**uso → uso_id FK** → operaciones.uso (cross-cutting catalog).
**DROP `deducible` varchar** (legacy raw appsheet id; plan_id FK is canonical).
**ADD `certificado` (varchar)** — certificado de cobertura per asset (rare; certain policy types, e.g.
equipo móvil). Explicit certificado↔materia link; deliberately a column here, NOT a separate table,
NOT mixed into documento. One per asset = one per materia stint.
**→ gestion.nota:** Comentarios (10 non-empty).

**Computed estado fields (Option 3 — layered DB views, mapped read-only into ORM, filterable):**
`v_poliza_estado` (estado_vigencia, estado_poliza) → `v_materia_estado` (estado_cobertura,
estado_materia), surfaced via column_property so `Materia.estado_cobertura` / `.estado_materia` are
filterable / sortable / paginatable. No stored data, no drift; rule change = one ALTER VIEW.
- `estado_cobertura` → **Activa / Excluida / Inactiva**:
  - Excluida if fecha_exclusion set and ≤ today.
  - Activa if not excluded AND documento.tipo_documento ∈ {poliza, inclusion, prorroga, modificacion,
    rehabilitacion} AND policy permits coverage.
  - Inactiva otherwise.
- `estado_materia` → **Cubierta / No Cubierta**:
  - Cubierta if estado_poliza ∈ {Vigente, Pendiente, Condicional} AND estado_cobertura == Activa.
  - No Cubierta otherwise.
- Replaces old "Ok"/"Espera" vocabulary. Sets/rules agreed, may tweak later.

**monto_asegurado vs datos.vehiculo.monto_asegurado:** asset table = nominal asset value;
materia.monto_asegurado = value insured on THIS policy line. Both CANONICAL, different scope.

**Row count:** CSV 921 → DB 914 (7 skipped: documento unresolved — deferred).

### gestion.plan_pago  ✅ APPROVED (2026-06-10)
**Role:** the **financed installment plan** for a document. Holds the **Pactado financiado** side.

**Design Y (1:N, one active):** a document can have multiple plans over time, only 1 active. DROP
`unique=True` on `documento_id` → partial unique `UNIQUE (documento_id) WHERE activo`; KEEP `activo`.
Current data is 1:1 (717 docs ↔ 717 plans) = backfill baseline, NOT real history — do NOT recover the
446 inactive/dup CSV rows (backfill noise). The constraint change is forward-looking (e.g. 12→6 change).

**Financed vs base:** plan_pago totals (afecta/exenta) + valor_cuota = **financiado** (base + interés,
what the client pays in installments). Base lives on `materia`; **interés = financiado − base** (computed;
no rate stored — user rarely has it). See "Per-asset financial model" below.

**CANONICAL:** documento_id, n_plan_pago (the plan LABEL — KEEP; "." values are backfill junk to clean),
n_cuotas, afecta/exenta UF/CLP/USD (financed totals), valor_cuota, valor_cuota_distinta, n_cuota_distinta,
vcto_cuota_0, vcto_cuota_1, **`fecha_plan_pago`** (RENAMED from fecha_documento — it's the PLAN's own start
date, can differ from the document's; e.g. a 12→6 change starts later), activo, firmado, enviado,
recibo_envio (send-tracking id to the company), pdf_url.

**DERIVED:** poliza_id (via documento→poliza; kept).
**COMPUTED (not stored):** `cargado_cuota` (= EXISTS cuotas for this plan); `estado_plan_de_pago`
(update old "Ok"/"Recotizar" vocab → new estado_poliza values; fold into option-3 view); Pagado rollups
(total_pagado, saldo_pendiente, n_cuotas_pagadas — from cuota).
**METADATA:** id, created_at, **ADD `updated_at`** (currently missing), appsheet_id (= document id in
legacy data — backfill artifact, non-issue).
**→ gestion.nota:** Comentarios (0 data).

**Currency:** financed totals follow the cross-cutting family/precision rule; valor_cuota /
valor_cuota_distinta are single-currency cols → Numeric(N,6), display per moneda.

**Cuota generation (replaces the AppSheet bot):** service `PlanPagoService.generar_cuotas(plan_pago)`
reads n_cuotas, valor_cuota, n_cuota_distinta/valor_cuota_distinta, vcto_cuota_0/1, moneda → writes cuota
rows (numero, vencimiento, monto_pactado=financed, monto_pagado=NULL, estado=pendiente). vcto_cuota_0 =
first due (often a pie at signing); vcto_cuota_1 sets the monthly cadence; cuotas 2…n = vcto_cuota_1 +
(k−1) months. Trigger: plan activation or explicit endpoint; idempotent. Supersede (12→6): old plan
activo=False, unpaid cuotas voided, new plan generates the remaining schedule.

**Row count:** CSV 999 → DB 717 (1 plan per document; the rest = backfill dup/inactive, intentionally dropped).

### gestion.cuota  ✅ APPROVED (2026-06-10)
**Role:** the installment. Holds BOTH **Pactado financiado** (valor_*) and **Pagado** (monto_pagado);
one end of the `cruce_tablas.cuotas_x_materia` ledger.

**Pactado vs Pagado (distinct currencies — do NOT conflate):**
- **Pactado financiado:** valor_uf / valor_clp / valor_usd — currency-split, family rule + precision.
- **Pagado:** `monto_pago` → RENAME **`monto_pagado`** + fecha_pago. **Always CLP** (actual pesos paid,
  even for UF policies — UF converted at payment date); Numeric(N,0).
  **`monto_pagado` ≠ `valor_clp`:** valor_clp = Pactado when the policy IS CLP-denominated;
  monto_pagado = actual CLP paid for ANY policy currency.
- Reconciliation: Pactado (valor_uf × UF-rate at vencimiento) vs Pagado (monto_pagado) → captures UF drift.

**estado_cuota — VOID-OVERRIDE hierarchy** (coupled with estado_poliza AND estado_documento, but only as
downward void overrides; otherwise self-determined):
1. If the **policy** is voided/terminal (Anulada / Cancelada / Consumida …) → the cuota reflects that.
2. Else if the cuota's **document is inactive** (`documento.activo = false`) → the cuota is voided too.
3. Else (policy OK **and** document active) → the cuota follows its OWN state: **Pagada** (payment present:
   control_pago / monto_pagado / fecha_pago), **Pendiente** (vencimiento ≤ today, unpaid), **Vigente**
   (vencimiento > today, unpaid).
This is why one policy can hold BOTH anulled and active installments — voiding happens per **document**
via `documento.activo`. COMPUTED; layered option-3 view: `v_poliza_estado` + `documento.activo` → cuota
estado. `estado_gestion_cuota` same.

**CANONICAL:** plan_pago_id (**NOT NULL**), control_pago (→ enum: Directo/Automático/Transferencia/Gratis;
"Anulada" → via estado_cuota void, not a method), numero_cuota (= current; drop CSV "/total" = plan.n_cuotas),
vencimiento, valor_uf/clp/usd (Pactado), monto_pagado + fecha_pago (Pagado), n_ingreso, cursado, fa_enviada,
**cobrada** (= "already reminded the client to pay?" filter flag — NOT "paid"; KEEP).
**FILE columns:** pago, recibo, factura — store FILES (payment proof / receipt / invoice); file paths,
replace in final migration.

**DERIVED (kept):** documento_id, poliza_id, compania_id, seguro_id, grupo_cliente_id, contratante_id (via plan_pago lineage).
**METADATA:** id, created_at, **ADD `updated_at`**, appsheet_id.
**DROP:** `cobro_automatico` (AppSheet aux; its CSV data is leaked virtual estado text — Pagada/Vigente/
Pendiente/… — mis-seeded; status is the computed estado_cuota), `cobrar` (AppSheet aid to auto-populate
cobranza; that workflow moves to the service layer).
**→ gestion.nota:** Comentarios (29).
**Ledger:** `monto_pagado` is what gets allocated per asset in `cruce_tablas.cuotas_x_materia`.

**Row count:** CSV 9999 → 5004 real (Vencimiento filled) → DB 5003 (~4995 blank placeholder rows).

### gestion.documento  ✅ APPROVED (2026-06-10) — **closes Group 1**
**Role:** the aggregator — ties materia + plan_pago + cuota to the policy; one per price movement.

**State model — one stored boolean input + one computed rollup:**
- **NEW `activo` (BOOLEAN, stored, VOID input):** whether the document is active. **The cuota & materia
  void-override read this RAW boolean directly** (activo = false → its cuotas/materias voided). Set by the
  anulación / cancelación / exclusión workflow (service layer).
- **`estado_documento` (COMPUTED — never stored, no CSV source; already a hybrid property):** the
  human-readable rollup, composed from `activo` + `requiere_doc` + `pdf_url`:
    - **Anulado** — `activo = false`
    - **Pendiente** — activo, `requiere_doc` and no `pdf_url`
    - **Ok** — activo and (pdf present or not required)
  Display/filter only; the cascade uses the raw `activo` boolean, not this string.

**`genera_movimiento` (price-movement → plan de pago):** stored boolean, default derived from
`tipo_documento` (Póliza/Renovación/Inclusión/Prórroga/Rehabilitación → true; Anulación/Cancelación →
false), **explicitly set for Modificación** (premium change vs data correction).

**CANONICAL:** poliza_id, cotizacion_id (nullable — filled when a quote was needed for the business),
tipo_documento, fecha_emision, fecha_inicio, fecha_termino, **numero_documento (→ NOT NULL)**,
requiere_doc (control — some docs legitimately have no PDF), **invalidar_diferencia** (control — TRUE when
a commission **theoretical-vs-paid** difference is ACCEPTED, suppresses the flag rule; ties to comisión
Pactado/Pagado reconciliation), enviado, activo (void), genera_movimiento.

**DERIVED (auto-COPIED at creation, stored — NOT computed):** pct_comision_afecta/exenta, n_cuotas,
tipo_inspeccion, n_inspeccion, **genera_comision** (← from the originating cotización / registro).
**DERIVED (lineage, kept):** grupo_cliente_id, contratante_id, producto_id, partner_id (via poliza).
**FILE:** pdf_url, otros_archivos.
**Rename:** comision_flag → `genera_comision` (drop "_flag"; consistent across the app).
**COMPUTED:** estado_documento (PDF completeness), dias_vigencia, contador_meses_vigentes.
**DROP:** traspaso_info_1, traspaso_info_2 (AppSheet aux, as in registro).
**Design Y:** `plan_pago` relationship `uselist=False` → **True** (list + active-plan accessor).
**METADATA:** id, created_at, updated_at, appsheet_id.
**→ gestion.nota:** Comentarios (25 non-empty).

**Row count:** CSV 999 → DB 717 (276 blank-tipo placeholder rows).

---

## Cross-cutting decisions (apply across ALL tables)

### Currency precision + family rule (revises CLAUDE.md monetary convention)
- **CLP family** (`*_clp`): `Numeric(N, 0)` — NO decimals. Suggested `Numeric(15, 0)`.
- **UF family** (`*_uf`): `Numeric(N, 6)` — store 6 decimals, **display rounded to 2**. Suggested `Numeric(14, 6)`.
- **USD family** (`*_usd`): `Numeric(N, 6)` — store 6 decimals, **display rounded to 2**. Suggested `Numeric(14, 6)`.
- **Only the currency family matching the policy's `moneda` is populated; the other families stay NULL**
  (no 0-padding). App-wide: materia, registro primas, plan_pago, cuota, valores_x_cotizacion,
  cotizacion, contabilidad… Enforce via app layer (and/or CHECK keyed on moneda).
- "Round to 2" is **frontend formatting only** (store 6).
- `monto_asegurado`: single column → `Numeric(N, 6)`, displayed per the line's moneda (0 dec CLP, 2 UF/USD).
- Rates/tasas are NOT currency — keep `Numeric(6, 4)`.
- TODO: update CLAUDE.md monetary convention (pending user go-ahead).

### Naturaleza del valor — `Pactado` vs `Pagado` (NEW cross-cutting distinction)
Every financial amount has two natures, **both needed across the app** for verification / reconciliation
(comparing what should be paid vs what was actually paid):
- **`Pactado`** — agreed / planned value (what SHOULD be paid).
- **`Pagado`** — actual value paid.
- Column convention: paired suffixes `..._pactado` / `..._pagado`.
- Where each lives: plan_pago / materia carry the **Pactado** side; the **Pagado** side is tracked on
  the payment rows (cuota) and rolls up. Apply per-table as verified (esp. plan_pago + cuota).

### Per-asset financial model (cross-cutting: materia / plan_pago / cuota + NEW ledger)
**Two-tier Pactado:**
- **base (contado)** → `materia` prima (per asset; the price source).
- **financiado (base + interés)** → `plan_pago` totals + `cuota` (what's actually paid in installments).
- **interés = financiado − base** (COMPUTED; no rate stored — user rarely has the rate).

**Per-asset stints + churn:** every price movement (include/exclude) = a **new documento + new plan_pago**.
The asset's priced line is a `materia` row with start + `fecha_exclusion`. Same asset in/out multiple times
= multiple materia rows. **Certificado de cobertura** (rare; certain policy types) = one per asset, stored
as a **column on `materia`** — NOT a separate table, NOT mixed into documento.

**Allocation ledger `cruce_tablas.cuotas_x_materia` (NEW TABLE):**
`cuota_id · materia_id · monto_pactado (financed share) · monto_pagado · origen (computado | manual)`
- **Default COMPUTED:** companies send ONE lump payment (no per-asset breakdown). Allocate each cuota's
  payment across the assets active that period, proportional to base prima, grossed up by interest.
- **Manual OVERRIDE** (`origen=manual`) when a company does provide per-asset detail — protected from the
  computed rule.
- Lets plan_pago/cuota "talk to" materia → exact paid-per-asset across churn and re-entry.

**⏳ OPEN QUESTION (defer — settle later, does NOT block schema):** the exact interest split in the
pro-rata refund formula below is not yet locked. Method is confirmed pro-rata; only the interest treatment
is pending. It's pure engine/`configuracion.parametro` logic, no table change depends on it.

**Reconciliation (owed/refund) — method is ALWAYS pro-rata, interest-aware** (interest split PENDING):
- `consumido_base = base × (días activos / días del término)`   ← coverage earned by time
- `interés_debido = (financiado − base) × (cuotas vencidas / n_cuotas)`   ← interest earned by installments elapsed
- `saldo_asset = Σ pagado_asset − (consumido_base + interés_debido)`  ( >0 → company refunds · <0 → client owes )
- Roll up per asset → policy. **Pro-rata params / interest treatment live in `configuracion.parametro`**
  (no hardcoded business rules, per CLAUDE.md). Alternative considered: prorate full financed total by days
  (simpler, but refunds interest by time — rejected in favor of the split above).

---

## Column Taxonomy (built incrementally)
See: `column_taxonomy.json` in this folder
