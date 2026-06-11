# CLAUDE_HANDOFF.md — SGA Aegis
> **Instrucción para Claude:** Lee este archivo completo antes de hacer cualquier cosa.
> Luego ejecuta la sección "First-run checklist" si es una máquina nueva.
> Este archivo se actualiza al final de cada sesión de trabajo significativa.

---

## 0. Identidad del proyecto

**SGA Aegis** — Sistema de gestión para corredora de seguros.
- Stack: FastAPI 0.115 + PostgreSQL (Supabase) + React 18 / Vite 5 + Tailwind CSS 3
- Repo GitHub: `https://github.com/dankobuy-ops/SGA.git`
- **Base de datos: Supabase (cloud)** — host `aws-1-sa-east-1.pooler.supabase.com`, project ref `kmccuscbgcxenpyrlznk`. Una sola DB compartida entre máquinas; no se reconstruye localmente.
- Rama principal: `main`
- Working directory esperado: `C:\claude\sga` (Windows)
- Usuario git: `dankobuy-ops` · email dev: `bcldeals@gmail.com`

### ✅ Lo que YA viene con el repo (no instalar por separado)
Al clonar el repo ya tendrás:
- **Todos los skills de Claude / gstack** — vendored en `.claude/skills/` (versión 1.48.0.0)
- **Configuración de permisos Claude Code** — `.claude/settings.local.json` (permite git, alembic, npm, uvicorn, etc. sin prompts manuales)
- **CLAUDE.md** con reglas de arquitectura del proyecto
- **PLAN_LOGICA_NEGOCIO.md** con la hoja de ruta de fórmulas

### ❌ Lo que NO viene con el repo (copiar manualmente en cada PC)
- **`.env`** — contiene la `DATABASE_URL` con password de Supabase + `SECRET_KEY` JWT. Guardarlo en password manager (1Password, etc.) y copiar al root del repo en cada PC nueva. Sin él, el backend no arranca.

---

## 1. First-run checklist (máquina nueva)

### 1.0 Prerrequisitos del sistema (instalar si no están)
```
Python 3.12.x  →  https://www.python.org/downloads/
Node.js 24.x   →  https://nodejs.org/
Git            →  ya instalado (GitHub conectado)
Claude Code    →  ya instalado
PostgreSQL 15+ →  OPCIONAL (solo para fallback offline; ver 1.7)
```

Verificar versiones:
```powershell
python --version    # debe ser 3.12.x
node --version      # debe ser v24.x
```

### 1.1 Clonar el repo
```powershell
# Si GitHub ya está configurado en esta máquina:
git clone https://github.com/dankobuy-ops/SGA.git C:\claude\sga
cd C:\claude\sga

# O si ya existe pero puede estar desactualizado:
cd C:\claude\sga
git pull origin main
git log --oneline -5    # verificar que el HEAD coincide con la sección 3
```

### 1.2 Copiar el archivo `.env` (desde tu password manager)
El `.env` **NO** está en el repo (contiene secrets). Pegarlo en `C:\claude\sga\.env`. Estructura esperada:
```env
# DB local (rápida, para dev día a día)
LOCAL_DATABASE_URL=postgresql://postgres:<password-local>@localhost:5432/sga_aegis

# DB cloud (Supabase, fuente de verdad multi-PC)
# Password "<TU-PASSWORD>" URL-encoded (% → %25, # → %23)
CLOUD_DATABASE_URL=postgresql://postgres.kmccuscbgcxenpyrlznk:<PASSWORD-URLENCODED>@aws-1-sa-east-1.pooler.supabase.com:5432/postgres

# Activa — la que usa el backend. Por defecto: LOCAL.
DATABASE_URL=postgresql://postgres:<password-local>@localhost:5432/sga_aegis

SECRET_KEY=<clave-jwt-fuerte-min-32-chars>
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=480
ENVIRONMENT=development
DEBUG=true
APP_NAME=SGA Aegis
APP_VERSION=0.1.0
```
> Los passwords reales están en password manager. **Sí necesitas Postgres local** para este workflow (la app apunta a `LOCAL_DATABASE_URL` por defecto).

### 1.3 Backend — Python + Postgres local
```powershell
cd C:\claude\sga

# Crear y activar virtualenv
python -m venv venv
venv\Scripts\activate

# Instalar dependencias
venv\Scripts\pip install -r requirements.txt

# Crear DB local (si no existe)
# En psql: CREATE DATABASE sga_aegis;

# Bajar el último estado desde cloud → local
venv\Scripts\python scripts\sync_db.py from-cloud

# Verificar alembic — debe mostrar: e0b3cee4b03e (head)
venv\Scripts\alembic current
```

> Workflow: trabajamos contra LOCAL durante el día (rápido, sin latencia). En cada commit
> corremos `python scripts/sync_db.py to-cloud` para subir el estado a Supabase. Al cambiar
> de PC: `from-cloud` baja el último estado. Ver regla en `CLAUDE.md` sección "DATABASE WORKFLOW".

### 1.4 Frontend — Node
```powershell
cd C:\claude\sga\frontend
npm install
cd ..
```

### 1.5 Smoke test — verificar que todo funciona
```powershell
# Terminal 1: Backend
cd C:\claude\sga
venv\Scripts\uvicorn app.main:app --reload --port 8000

# Terminal 2: Frontend
cd C:\claude\sga\frontend
npm run dev    # puerto 5173
```
- `http://localhost:5173` → UI carga correctamente, muestra pólizas/registros con datos reales
- `http://localhost:8000/docs` → Swagger muestra todos los endpoints
- `http://localhost:8000/api/v1/menu/me` → devuelve `{"rol":"admin",...}`

### 1.6 (Opcional) Fallback local PostgreSQL
Solo si quieres trabajar offline o Supabase está caído:
1. Instalar PostgreSQL 15+
2. `CREATE DATABASE sga_aegis;` en psql/pgAdmin
3. En `.env`, comentar la línea de Supabase y descomentar la línea localhost
4. Construir schema localmente:
   ```powershell
   venv\Scripts\python -c "from app.database import engine, Base, create_schemas; from app.models import *; create_schemas(); Base.metadata.create_all(bind=engine)"
   venv\Scripts\alembic stamp head
   venv\Scripts\python scripts\seed_from_csv.py
   ```
5. Al volver online, comentar localhost y descomentar Supabase.

> Nota: La migración base `83fde1b4e675` está vacía. Schema se construye via `create_all` (los modelos son la fuente de verdad), no via `alembic upgrade head` desde cero. Las migraciones existen para tracking incremental, no para build inicial.

---

## 2. Arquitectura rápida

```
app/
  main.py              — FastAPI app, CORS, registro de routers
  config.py            — Settings via pydantic-settings (.env)
  database.py          — Engine, SessionLocal, Base
  models/
    gestion.py         — CORE: Registro→Cotizacion→Poliza→Documento→PlanPago→Cuota
                         + Cobranza, Solicitud, Siniestro, Comision, Nota
                         + tablas puente (CruceRegistrosXPolizas, CruceDocumentosXComision, etc.)
    datos.py           — Rut, Vehiculo, Inmueble, VidaSalud, Otra
    operaciones.py     — Compania, Producto, Seguro, Ejecutivo, Ramo, Partner
    grupos.py          — GrupoCliente, GrupoMateria, GrupoEntidad
    contabilidad.py    — Liquidacion, Contable, Cartola, CierreMensual, Fondo, etc.
    comunicacion.py    — ComRegistro, ComPoliza, ComDocumento, ComCobranza, etc.
    configuracion.py   — Usuario, Parametro, ValorUF, VistaDinamica
    comision.py        — Permanencia (alias Comision) — ciclo interno Aegis
    cruce_tablas.py    — CruceNotasXEntidades (bridge 29 FKs + CheckConstraint)
  routers/
    system.py          — CRUD genérico + schema explorer + vistas dinámicas (GET/PUT /vistas)
    menu.py            — Módulos del menú + mock /me (⚠️ auth pendiente)
    registros.py, polizas.py, clientes.py, comisiones.py, cotizaciones.py, operaciones.py
  services/
    permanencia.py       — Ciclo RETENIDA→LIBERADA→PAGADA (comisiones internas Aegis)
    comision_service.py  — Triggers facturabilidad (BR3): cuota N°1 pagada ó plan firmado+enviado
    cobranza_service.py  — CobranzaService: EXISTS/bool_or SQL, N+1 safe
    documento_service.py — DocumentoService: liquidacion, envio, comision, tolerancias
    poliza_service.py    — PolizaService: SUM CASE, EXISTS, COUNT SQL

frontend/src/
  catalog/entities.js   — FUENTE DE VERDAD UI — toda entidad nueva va aquí primero
  components/
    DashboardTemplate.jsx — 3 paneles + view switcher tabla/lista + sort server-side
    DataTable.jsx          — Tabla con headers sort, copy-to-clipboard, sin truncación
    GenericList.jsx        — Vista cards alternativa (comparte CellValue con DataTable)
    DetailPanel.jsx        — Panel detalle + botón "Ver completo"
  pages/
    WorkspacePage.jsx    — Página genérica (usa DashboardTemplate + entities.js)
    RegistroDetalle.jsx, PolizaDetalle.jsx — Páginas 360° dedicadas
```

### 9 Schemas PostgreSQL
`datos` · `operaciones` · `gestion` · `contabilidad` · `grupos` · `comunicacion` · `agenda` · `cruce_tablas` · `configuracion`

> `configuracion` está en `EXCLUDED_SCHEMAS` — el router genérico no lo sirve. Usar endpoints dedicados.

### Flujo de negocio principal
```
Registro → Cotizacion → Poliza → Documento → PlanPago → Cuota
                                            → Materia → Siniestro
                                            → Solicitud
gestion.permanencia  →  RETENIDA (4 meses) → LIBERADA → PAGADA
gestion.comision     →  Liquidaciones de compañías (externo)
```

---

## 3. Estado actual del repo

**Alembic head:** `e0b3cee4b03e`
**Git HEAD:** ver `git log --oneline -1` (cambia frecuentemente)
**Branch:** `main`
**Base de datos:** Supabase cloud (`aws-1-sa-east-1.pooler.supabase.com`, project `kmccuscbgcxenpyrlznk`) — seedeada con dataset completo desde `Archivos/OI61/CSV`.

### Datos en la DB (post-seed inicial 2026-05-29)
- 257 ruts · 15 compañías · 26 ejecutivos · 12 proveedores · 2 bancos · 2 partners · 2 gestores
- 672 registros · 468 cotizaciones · 547 pólizas · 717 documentos · 717 planes de pago · **5003 cuotas**
- 272 vehículos · 38 inmuebles · 335 grupos materias · 267 grupos entidades · 153 grupos clientes
- 0 notas (la centralización Phase 3 quedó con la tabla creada; backfill histórico no se replicó al rebuild — re-correr la migración 9a50374 si se quieren los comentarios históricos)

### Lo que está funcionando
- UI genérica 3-paneles: filtros, paginación server-side, sort por columna, vista tabla/lista
- Persistencia de vista por entidad via `configuracion.vista_dinamica` (GET/PUT /system/vistas)
- Copy-to-clipboard en celdas de tabla, botón "Ver completo" en panel detalle
- Notas centralizadas: `gestion.nota` + bridge `cruce_tablas.notas_x_entidades` (29 FKs, schema listo, sin datos backfilleados)
- Árbol de lógica financiera completo:
  - `@property` / `@hybrid_property` en modelos: `estado_poliza`, `estado_cuota`, `estado_plan_de_pago`, `estado_documento`, `estado_materia`, `estado_solicitud`, `estado_gestion` (todos los modelos), `n_facturas`, `total_documentado`, `dias_vigencia`, `contador_meses_vigentes`, `es_saldo`, `PlanPago.estado_gestion`
  - Servicios N+1 safe: `CobranzaService`, `DocumentoService`, `PolizaService`, `ComisionService`
  - Partial indexes: `idx_cuota_pendiente_vencimiento`, `idx_documento_pendiente_pdf`, `idx_permanencia_liberacion` (creados por migraciones — verificar en cloud DB con `\di` en psql)
- ⚠️ Auth: **MOCK** — `/api/v1/menu/me` siempre devuelve `rol="admin"`. NO deployar.
- ⚠️ Multi-PC: cloud DB compartida vía Supabase. Cambios hechos en PC #1 son visibles inmediatamente en PC #2. Sin sincronización manual.

---

## 4. Próximos pasos (prioridad descendente)

### 🔴 CRÍTICO — JWT Authentication
La única prioridad que bloquea todo lo demás antes de producción.
- **Archivo:** `app/routers/menu.py` → reemplazar `get_current_user()` (mock actual)
- Agregar `Depends(get_current_user)` a todos los routers
- Wiring de `ROLE_SCHEMA_PERMISSIONS` en `system.py` para filtrar schemas por rol
- `configuracion.usuario` ya tiene la tabla y campos (`hashed_password`, `rol`, `activo`)
- Librerías ya instaladas: `python-jose`, `passlib`

### 🟠 ALTO

**Inline NotasPanel** — Componente frontend
- Lee `GET /system/table/cruce_tablas/notas_x_entidades?filter_{entity}_id={id}` y muestra las notas
- Botón "Nueva Nota" → `POST /system/table/gestion/nota` + `POST /system/table/cruce_tablas/notas_x_entidades`
- Debe aparecer en cada `DetailPanel`

**Commission lifecycle UI**
- Superficie para `permanencia.py` + `ComisionService`
- Cola RETENIDA → botón liberar → botón pagar
- Endpoints faltantes: `PUT /comisiones/{id}/liberar` y `PUT /comisiones/{id}/pagar`

### 🟡 MEDIO
- **Siniestros workflow** — Página dedicada con transitions de estado
- **Cliente 360°** — Detalle `datos.rut` con todas sus pólizas, cuotas, siniestros
- **Server-side pagination** — `solicitud`, `cuota`, `registro` superarán 200 filas en producción
- **Test suite** — Ver blueprint en `CLAUDE.md` (pytest + httpx)

### ⚪ BAJO / DEUDA TÉCNICA
- `Siniestro.estado_siniestro` es `String(50)` → migrar a enum `EstadoSiniestro` (ya definido)
- `main.py`: `from app.models import *` → imports explícitos
- CORS `allow_methods=["*"]` → restringir en producción
- `GlobalConfig` POST sin auth → riesgo en producción

---

## 5. Reglas de arquitectura (NO violar)

1. **AEGIS CORPORATE OS:** NUNCA ordenar/filtrar/rankear por monto de comisión del corredor. Solo precio/cobertura del cliente.
2. **9 schemas únicos.** NUNCA crear tablas fuera de: `datos`, `operaciones`, `gestion`, `contabilidad`, `grupos`, `comunicacion`, `agenda`, `cruce_tablas`, `configuracion`.
3. **Paginación obligatoria** en todo endpoint de lista: `limit` + `offset`. Fetches ilimitados prohibidos.
4. **Servicios Grupo D** — N+1 unsafe: NUNCA como `@property`. Siempre en `app/services/` con SQL explícito.
5. **Datos Materias** — `datos.vehiculo`, `datos.inmueble`, `datos.otra` NO tienen `propietario_id`. El vínculo asegurado↔ítem vive exclusivamente en `grupos.grupo_materia`.
6. **Enums SQLAlchemy** — declarar con `schema=` igual al schema de la tabla.
7. **`get_db()`** — único punto de inyección de sesión. NUNCA `SessionLocal()` directo en routers.
8. **`configuracion` excluido del router genérico** — usar endpoints dedicados (`/system/vistas`, `/system/config`).

---

## 6. Comandos frecuentes

```powershell
# Backend
venv\Scripts\uvicorn app.main:app --reload --port 8000

# Frontend
cd frontend && npm run dev    # puerto 5173

# Migraciones
venv\Scripts\alembic revision --autogenerate -m "descripcion"
# ⚠️ SIEMPRE revisar el archivo generado antes de aplicar:
# Alembic detecta espuriamente: uq_rut_corto, idx_poliza_caido, idx_poliza_estado_vigencia
# → Eliminar esas operaciones del upgrade()/downgrade() antes de aplicar
venv\Scripts\alembic upgrade head
venv\Scripts\alembic current    # verificar head

# Verificar compilación Python
venv\Scripts\python -c "from app.main import app; print('OK')"

# Build React (verificar sin errores)
cd frontend && npm run build
```

---

## 7. Notas de implementación importantes

**Dos sistemas de comisiones distintos (NO confundir):**
- `gestion.comision` = liquidaciones que las compañías pagan al corredor (externo, Grupo D)
- `gestion.permanencia` (modelo en `app/models/comision.py`) = fee interno de Aegis con ciclo de retención 4 meses

**CheckConstraint en `cruce_tablas.notas_x_entidades`:** Alembic autogenerate NO detecta cambios en CheckConstraints. Si se modifica la tabla, hay que escribir manualmente `op.drop_constraint` + `op.create_check_constraint` en la migración.

**`post_update=True`:** Las relaciones `Registro.cot_aceptada` y `Registro.poliza_directa` lo usan para romper ciclos circulares en INSERTs.

**FK label resolution en `system.py`:** `_resolve_fk_values` hace N queries (1 por columna FK). Candidato a optimización con JOIN antes de escalar. Ver `COMPOSITE_LABEL_SQL` para etiquetas compuestas ya definidas.

**`DashboardTemplate` fetch modes:**
- `config.endpoint` empieza con `/system/table/` → paginación server-side + sort via API
- Cualquier otro endpoint → filter client-side sobre máx 200 filas (legacy)

**Alembic spurious detections:** En cada autogenerate aparecen 3 cambios fantasmas de objetos de DB que no están en el modelo (`uq_rut_corto`, `idx_poliza_caido`, `idx_poliza_estado_vigencia`). Siempre eliminarlos del migration generado.

---

## 8. Skills disponibles en este proyecto

Los skills están vendored en `.claude/skills/` (ya en el repo, versión gstack **1.48.0.0**).
No requieren instalación separada — se activan automáticamente con Claude Code.

Skills clave para este proyecto:
- `/plan` o `/plan-eng-review` — diseño y revisión arquitectónica
- `/review` — code review de diffs
- `/qa` — testing de UI en browser
- `/ship` — preparar commit/PR
- `/context-save` — guardar checkpoint de sesión
- `/context-restore` — restaurar checkpoint anterior
- `/investigate` — debugging de bugs
- `/aegis-compliance` — verificar AEGIS CORPORATE OS (precio/cobertura first)
- `/aegis-extend` — guía para extender el sistema con nuevas entidades
- `/safe-endpoint` — verificar seguridad de nuevos endpoints

---

*Última actualización: 2026-05-29 — migración a Supabase cloud + seed_from_csv reparado para refactors actuales.*
*Actualizar secciones 3 y 4 al final de cada sesión de trabajo.*
