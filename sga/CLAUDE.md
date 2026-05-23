# CLAUDE.md — SGA Aegis

Sistema de gestión para corredora de seguros. Stack: FastAPI + PostgreSQL + React/Vite.

## Core Principles (Phase 2 — FastAPI & Business Logic)

### AEGIS CORPORATE OS
The **Precio/Cobertura** (Price/Coverage) ratio is absolute. NEVER write algorithms that sort,
filter, or rank results by broker commission amounts or commission percentages. The client's
interest (best coverage for best price) is the only valid optimization criterion.

### ARCHITECTURE
Strict adherence to the 9 semantic schemas: `datos`, `operaciones`, `gestion`, `contabilidad`,
`grupos`, `comunicacion`, `agenda`, `cruce_tablas`, `configuracion`. Extend existing schemas.
NEVER create independent data silos or tables outside this taxonomy.

### CODE
- Do NOT hardcode SLAs, business rules, or configurable thresholds — read them from
  `configuracion.parametro` (key-value store).
- All endpoints MUST use server-side pagination (`limit` + `offset`). Fetching unbounded result
  sets is forbidden in new code.
- Use the custom skills (`.claude/skills/`) as enforcement gates before submitting code.

## Template: Datos Materias

Patrón arquitectónico para tablas de registro maestro de ítems asegurados.

**Tablas bajo este template:** `datos.vehiculo`, `datos.inmueble`, `datos.otra`
(y cualquier nuevo tipo de materia que se agregue en el futuro)

| Tabla | Sin FK propietario a rut | Notas |
|---|---|---|
| `datos.vehiculo` | ✓ eliminado (migración a1b2c3d4e5f6) | registro puro de patentes |
| `datos.inmueble` | ✓ eliminado (migración a1b2c3d4e5f6) | registro puro de propiedades |
| `datos.otra` | ✓ nunca lo tuvo | tiene `vehiculo_id`/`inmueble_id` como referencias cruzadas entre materias (no propietario) |
| `datos.vida_salud` | ✓ (caso especial — ver nota) | **extiende** un `datos.rut` en perfil de salud; `titular_id` es FK 1:1 de identidad, NO de propiedad transferible. No puede separarse de la persona. |
| `datos.vida_salud_carga` | ✓ (caso especial — ver nota) | depósito de cargas (dependientes) que NO se quieren registrar como RUTs completos; `vida_salud_id` es FK de composición; `rut_carga_id` es enlace opcional si la carga SÍ tiene RUT |

**Nota `datos.vida_salud`:** El campo `titular_id` (FK a `datos.rut`) se conserva porque es una relación 1:1 de identidad — el perfil de salud ES la extensión del RUT para seguros de vida/salud. No es una relación de propiedad transferible como `propietario_id` en vehículos. El asegurado operativo sigue pasando por `grupos.grupo_materia.vida_salud_id`.

**Nota `datos.vida_salud_carga`:** El campo `rut_carga_id` (FK opcional a `datos.rut`) se conserva como enlace de conveniencia. Las cargas que NO están en `datos.rut` se almacenan con su información básica (rut como String, nombre, etc.) directamente en esta tabla.

**Regla invariante:** estas tablas **NO tienen `propietario_id`** ni ninguna FK directa a `datos.rut`.
Son registros puros del ítem físico (patente, chasis, dirección, etc.) que pueden existir
independientemente de quién los asegure y cambiar de asegurado sin duplicar datos.

**La vinculación asegurado↔ítem vive exclusivamente en `grupos.grupo_materia`**, que tiene:
- `asegurado_id` → FK a `datos.rut` (quién es el asegurado)
- `vehiculo_id` / `inmueble_id` / `otra_id` → FK al ítem específico
- `activa` → si la relación está vigente
- `uso`, `seguro_id` → parámetros específicos de esa cobertura

**Para agregar un nuevo tipo de materia:**
1. Crear tabla en schema `datos` **sin FK a datos.rut**
2. Añadir columna FK opcional en `grupos.grupo_materia` apuntando a la nueva tabla
3. Seguir el mismo patrón de migración CSV del template
4. La función `_audit_column_coverage()` en `migracion_maestra.py` reportará automáticamente la cobertura

**Decisión registrada:** 2026-05-19 — `propietario_id` eliminado de `datos.vehiculo` e `datos.inmueble` via migración Alembic `a1b2c3d4e5f6`.

### Patrón: Materia Derivada (`datos.otra`)

`datos.otra` puede ser de dos tipos según `tipo_otra`:

1. **Materia nueva independiente** — `vehiculo_id = NULL` y `inmueble_id = NULL`. La materia es un ítem completamente nuevo (maquinaria, joya, GPS, etc.). `materia_asegurada` describe el ítem desde cero.

2. **Cobertura adicional sobre materia existente** — `vehiculo_id` o `inmueble_id` apunta al registro base. En lugar de duplicar todos los datos del vehículo/inmueble, `datos.otra` agrega una capa de cobertura específica encima. `materia_asegurada` especifica qué parte o cobertura se asegura (ej. `'SOAP'`, `'RCI'`, `'Garantía'`).

Este patrón permite tener múltiples coberturas sobre el mismo vehículo o inmueble sin duplicar sus datos físicos.

## Stack técnico

| Capa | Tecnología |
|------|-----------|
| Backend | Python 3.12, FastAPI 0.115, SQLAlchemy 2.0, Alembic, Pydantic v2 |
| Base de datos | PostgreSQL — 9 schemas custom, 73+ tablas |
| Frontend | React 18, Vite 5, Tailwind CSS 3, React Router v6, Axios |
| Auth | JWT preparado (python-jose + passlib instalados) — **mock activo** |

## Estructura del proyecto

```
app/
  main.py              — FastAPI app, lifespan, CORS, registro de routers
  config.py            — Settings via pydantic-settings (.env)
  database.py          — Engine, SessionLocal, Base, creación de schemas
  models/              — SQLAlchemy models agrupados por schema PG
    gestion.py         — Core del negocio (Registro→Cotizacion→Poliza→Cuota)
    datos.py           — Maestros: Rut, Vehiculo, Inmueble, VidaSalud
    operaciones.py     — Compania, Producto, Seguro, Ejecutivo, Ramo
    grupos.py          — GrupoCliente, GrupoMateria, GrupoEntidad
    contabilidad.py    — Liquidacion, Cartola, Contable
    agenda.py          — AgendaObligacion, AgendaTarea
    comunicacion.py    — Comunicaciones (ComRegistro, ComPoliza, etc.)
    configuracion.py   — Parametro (key-value store)
  routers/
    system.py          — Router genérico CRUD + schema explorer + bulk insert
    menu.py            — Módulos del menú + mock /me
    registros.py       — CRUD específico de Registro
    polizas.py         — CRUD específico de Poliza
    clientes.py        — CRUD de Rut/clientes
    comisiones.py      — Endpoints de comisiones
    cotizaciones.py    — Endpoints de cotizaciones
    operaciones.py     — Endpoints de operaciones
  services/
    permanencia.py     — Lógica: ciclo de vida comisiones (4 meses retención)
  schemas/             — Pydantic schemas de entrada/salida

frontend/src/
  catalog/entities.js  — Catálogo central: entidades, campos, endpoints
  components/
    DashboardTemplate.jsx — UI universal de 3 paneles (filtros|tabla|detalle)
    DataTable.jsx
    DetailPanel.jsx
    EditRowPanel.jsx
    FilterPanel.jsx
  contexts/AuthContext.jsx
  hooks/               — useLocalStorage, useMenu, useGlobalConfig, etc.
  pages/               — WorkspacePage (genérico), páginas específicas
  api/index.js         — Cliente Axios centralizado
```

## Schemas PostgreSQL

```
agenda / comunicacion / configuracion / contabilidad /
cruce_tablas / datos / gestion / grupos / operaciones
```

El schema `gestion` es el core del negocio. `cruce_tablas` contiene solo tablas puente (M:N).

## Flujo de datos principal

```
Registro → Cotizacion → Poliza → Documento → PlanPago → Cuota
                                            → Materia
                                            → Solicitud
                    → Siniestro
                    → Comision (ciclo: RETENIDA → LIBERADA → PAGADA)
```

## Reglas de arquitectura

### Backend
- Nunca usar `from app.models import *` en código nuevo — importar explícitamente
- Toda tabla nueva requiere su schema declarado en `__table_args__ = {"schema": "nombre"}`
- Validar schema contra `ALLOWED_SCHEMAS` antes de cualquier consulta dinámica en system.py
- `get_db()` es el único punto de inyección de sesión — nunca crear `SessionLocal()` en routers
- Pydantic v2: usar `model_config = ConfigDict(...)`, no `class Config`
- Los enums SQLAlchemy deben declararse con `schema=` igual al schema de la tabla
- `post_update=True` en relaciones circulares (ej. `Registro.cot_aceptada`, `Registro.poliza_directa`)

### Frontend
- Todo endpoint de datos pasa por `/api/v1/system/table/{schema}/{table}` — NO crear endpoints específicos para listar salvo que requieran lógica de negocio
- El catálogo `entities.js` es la fuente de verdad UI — toda entidad nueva requiere entrada aquí
- `DashboardTemplate` recibe un `config` del catálogo y maneja todo lo demás
- Los filtros son client-side sobre un fetch máximo de 200 filas — para tablas con >500 registros, pasar a server-side con `apiParam`
- Estado persistente por entidad: `sga_filtros_{id}` y `sga_columnas_{id}` en localStorage
- Axios base URL: `/api/v1` — nunca hardcodear URLs completas

### Base de datos
- `id` siempre es PK Integer autoincrement
- `created_at` / `updated_at` via `server_default=func.now()` — nunca setear manualmente
- Campos monetarios: `Numeric(14, 2)` para CLP/USD, `Numeric(10, 4)` para UF
- Porcentajes: `Numeric(5, 2)` — ej. `12.50` para 12.5%
- No usar `Float` para dinero — siempre `Numeric`

## Estado actual de auth

**MOCK ACTIVO**: `/api/v1/menu/me` devuelve siempre `rol="admin"`. Las rutas NO están protegidas.

Cuando se implemente JWT:
1. Reemplazar `get_current_user()` en `menu.py` por decodificación de token
2. Agregar `Depends(get_current_user)` a todos los routers
3. Usar `ROLE_SCHEMA_PERMISSIONS` de `system.py` para filtrar schemas por rol

## Testing (gstack /qa)

No hay tests escritos aún. Flujos críticos a cubrir:

### Backend (pytest + httpx)
```
tests/
  test_system_router.py   — browse_table, bulk_insert, update_row, delete_rows
  test_menu_router.py     — /me, /modules filtrado por rol
  test_permanencia.py     — crear_comision, procesar_liberaciones, cancelar_comision
  test_auth.py            — cuando JWT esté implementado
```

Fixtures necesarias:
- `db_session` — SQLAlchemy session en transacción rollback automático
- `test_client` — TestClient de FastAPI con override de `get_db`
- Seed mínimo: 1 Compania, 1 Seguro, 1 Producto, 1 GrupoCliente, 1 Registro, 1 Poliza

### Frontend (Playwright / gstack)
Flujos a verificar antes de cada PR:
1. Carga inicial `/registros` — tabla muestra datos, paneles redimensionables
2. Filtrado client-side — badge filter por `tipo_registro`, texto libre
3. Selección de fila — panel derecho aparece con detalle
4. `+ Nuevo` en entidades con `newPath` configurado
5. `__diccionario` y `__explorador` (solo admin)
6. Bulk insert CSV — subir archivo, revisar resultados
7. Responsive mobile — tabs Filtros / Tabla / Detalle

## Puntos de atención (gstack /review)

### Seguridad
- `system.py` usa f-strings con `schema_name` y `table_name` — validados contra `ALLOWED_SCHEMAS` + existencia en `information_schema` antes de ejecutar
- `bulk_insert`: columnas validadas contra el esquema real de la tabla, valores parametrizados — no hay SQLi por diseño
- `update_row` / `delete_rows`: ídem, valores siempre en params
- CORS: `allow_methods=["*"]` — en producción restringir a `["GET","POST","PUT","PATCH","DELETE"]`
- `debug=True` en config — usar `settings.debug` para condicionar comportamiento

### Escalabilidad
- `DashboardTemplate` fetcha siempre `page_size=200` — bottleneck en tablas grandes (>500 registros)
- `_resolve_fk_values` hace N queries (una por columna FK) — candidato a optimización con JOIN
- `procesar_liberaciones()` es O(n) sin índice parcial en `(estado, fecha_liberacion)` — crear índice

### Deuda técnica
- Columnas duplicadas en `Poliza` y `Cuota` marcadas como "Legacy (backward compat)"
- `Siniestro.estado_siniestro` es `String(50)` — debería ser enum `EstadoSiniestro` que ya existe
- `from app.models import *` en `main.py` — reemplazar por imports explícitos

## Convenciones de commit (gstack /ship)

```
feat(scope): descripción en español
fix(scope): descripción en español
refactor(scope): descripción en español
test(scope): descripción en español
chore(scope): descripción en español
```

Scopes válidos: `auth`, `gestion`, `comisiones`, `polizas`, `frontend`, `db`, `seed`, `config`

Ejemplo:
```
feat(comisiones): agregar endpoint de liberación manual de comisiones retenidas
```

## Variables de entorno requeridas (.env)

```env
DATABASE_URL=postgresql://user:pass@localhost:5432/sga_aegis
SECRET_KEY=<clave-jwt-fuerte>
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=480
ENVIRONMENT=development
DEBUG=true
```

## Comandos frecuentes

```powershell
# Backend
venv/Scripts/uvicorn app.main:app --reload --port 8000

# Frontend
cd frontend && npm run dev   # puerto 5173

# Migraciones
venv/Scripts/alembic revision --autogenerate -m "descripcion"
venv/Scripts/alembic upgrade head

# Seed desde CSVs
venv/Scripts/python scripts/seed_from_csv.py

# Reset DB
venv/Scripts/python scripts/reset_db.py
```
