# SGA Aegis — Sistema de Gestión Aegis

Backend del sistema de gestión a medida para **Seguros Aegis**, corredora independiente en Chile.

## Stack Tecnológico

| Capa | Tecnología |
|------|-----------|
| Backend | Python 3.11+ · FastAPI |
| Base de Datos | PostgreSQL 15+ |
| ORM | SQLAlchemy 2.0 |
| Migraciones | Alembic |
| Frontend | React + Tailwind CSS *(próxima fase)* |
| Scraping | Playwright *(próxima fase)* |

---

## Arquitectura de la Base de Datos

9 esquemas PostgreSQL con ~78 tablas totales:

```
sga_aegis (base de datos)
├── agenda          → Tareas, recordatorios y obligaciones de cumplimiento
├── comunicacion    → Trazabilidad de envíos de email, WhatsApp, documentos
├── configuracion   → Usuarios, roles, parámetros, valores UF/USD
├── contabilidad    → Cuentas corrientes, pagos, liquidaciones, F29
├── cruce_tablas    → Tablas puente N:M (póliza↔vehículo, póliza↔inmueble)
├── datos           → Entidades maestras: clientes, vehículos, inmuebles
├── gestion         → Core del negocio: registros, cotizaciones, pólizas, siniestros
├── grupos          → Agrupaciones lógicas de clientes y pólizas
└── operaciones     → Ramos, compañías, productos, comisiones, red ANS
```

### Esquemas prioritarios T0

#### `datos` — Entidades Maestras

| Tabla | Descripción |
|-------|-------------|
| `cliente` | Personas naturales y jurídicas con RUT único |
| `vehiculo` | Vehículos motorizados vinculados a clientes |
| `inmueble` | Propiedades con datos constructivos |

#### `gestion` — Core del Negocio

| Tabla | Descripción |
|-------|-------------|
| `registro` | Punto de entrada de cualquier trámite |
| `cotizacion` | Propuesta de seguro (→ puede convertirse en póliza) |
| `poliza` | Contrato de seguro vigente (con cadena de renovaciones) |
| `cuota` | Cuotas individuales de cobranza |
| `siniestro` | Denuncias y gestión de siniestros |

#### `operaciones` — Catálogo

| Tabla | Descripción |
|-------|-------------|
| `ramo` | Ramos CMF (Incendio, Vehículos, Vida, etc.) |
| `compania` | Las 9 compañías con las que trabaja Aegis |
| `producto` | Combinaciones compañía+ramo+condiciones |

---

## Estructura del Proyecto

```
sga/
├── app/
│   ├── main.py              # Entrada FastAPI + lifespan
│   ├── config.py            # Settings desde .env
│   ├── database.py          # Engine, Session, Base, crear esquemas
│   ├── models/              # SQLAlchemy ORM
│   │   ├── datos.py         # Cliente, Vehículo, Inmueble
│   │   ├── gestion.py       # Registro, Cotización, Póliza, Cuota, Siniestro
│   │   ├── operaciones.py   # Ramo, Compañía, Producto
│   │   └── configuracion.py # Usuario, ValorUF, Parámetro
│   ├── schemas/             # Pydantic (validación I/O)
│   │   ├── cliente.py
│   │   └── poliza.py
│   └── routers/             # Endpoints REST
│       ├── clientes.py      # CRUD + búsqueda por RUT
│       └── polizas.py       # CRUD + pólizas por vencer
├── alembic/                 # Migraciones de DB
├── scripts/
│   └── create_schemas.sql   # SQL inicial de esquemas
├── requirements.txt
├── alembic.ini
└── .env.example
```

---

## Levantamiento Local

### 1. Pre-requisitos

- Python 3.11+
- PostgreSQL 15+

### 2. Clonar y configurar entorno

```bash
cd sga

# Crear entorno virtual
python -m venv venv

# Activar (Windows)
venv\Scripts\activate

# Activar (Mac/Linux)
source venv/bin/activate

# Instalar dependencias
pip install -r requirements.txt
```

### 3. Configurar variables de entorno

```bash
cp .env.example .env
# Editar .env con tus credenciales de PostgreSQL
```

### 4. Crear la base de datos en PostgreSQL

```sql
-- En psql como superusuario:
CREATE DATABASE sga_aegis ENCODING 'UTF8';
```

### 5. Crear esquemas y tablas

```bash
# Opción A: arrancar el servidor (crea todo automáticamente al iniciar)
uvicorn app.main:app --reload

# Opción B: con Alembic (para proyectos con migraciones versionadas)
alembic revision --autogenerate -m "T0: esquemas iniciales datos y gestion"
alembic upgrade head
```

### 6. Acceder a la API

| URL | Descripción |
|-----|-------------|
| http://localhost:8000 | Root / estado |
| http://localhost:8000/docs | Swagger UI interactivo |
| http://localhost:8000/redoc | ReDoc |

---

## Endpoints Disponibles (T0)

### Clientes `/api/v1/clientes`

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/` | Listar con filtros (buscar, activo) |
| POST | `/` | Crear cliente |
| GET | `/{id}` | Obtener por ID |
| GET | `/rut/{rut}` | Obtener por RUT |
| PATCH | `/{id}` | Actualizar parcialmente |
| DELETE | `/{id}` | Desactivar (soft delete) |

### Pólizas `/api/v1/polizas`

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/` | Listar con filtros (cliente, estado, compañía) |
| POST | `/` | Crear póliza |
| GET | `/por-vencer?dias=30` | Pólizas que vencen pronto |
| GET | `/{id}` | Obtener por ID |
| PATCH | `/{id}` | Actualizar estado/datos |

---

## Fases del Proyecto

| Fase | Descripción | Estado |
|------|-------------|--------|
| **T0** | Diseño DB · Modelos SQLAlchemy · API base | ✅ En curso |
| T1 | Autenticación JWT · CRUD completo · Frontend React | ⏳ |
| T2 | Cotizaciones · Cobranza · Vencimientos | ⏳ |
| T3 | Siniestros · Contabilidad · F29 | ⏳ |
| T4 | Scraping compañías con Playwright | ⏳ |
| T5 | Reportería · Dashboard · ANS | ⏳ |

---

*Principio guía: **Primero Funcional, Luego Perfecto***
