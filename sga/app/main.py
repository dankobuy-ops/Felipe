from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import create_schemas, Base, engine
from app.models import *  # registrar todos los modelos
from app.routers import clientes, polizas, comisiones, registros, cotizaciones, operaciones, menu, system


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: crear esquemas y tablas
    create_schemas()
    Base.metadata.create_all(bind=engine)
    print(f"✅ SGA Aegis v{settings.app_version} iniciado — {settings.environment}")
    yield
    # Shutdown
    print("👋 SGA Aegis detenido.")


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Sistema de Gestión Aegis — API Backend",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(registros.router, prefix="/api/v1")
app.include_router(cotizaciones.router, prefix="/api/v1")
app.include_router(clientes.router, prefix="/api/v1")
app.include_router(polizas.router, prefix="/api/v1")
app.include_router(comisiones.router, prefix="/api/v1")
app.include_router(operaciones.router, prefix="/api/v1")
app.include_router(menu.router, prefix="/api/v1")
app.include_router(system.router, prefix="/api/v1")


@app.get("/", tags=["Root"])
def root():
    return {
        "sistema": settings.app_name,
        "version": settings.app_version,
        "estado": "operativo",
        "docs": "/docs",
    }


@app.get("/health", tags=["Root"])
def health():
    return {"status": "ok"}
