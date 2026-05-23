import os
from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context
from dotenv import load_dotenv

load_dotenv()

config = context.config
config.set_main_option("sqlalchemy.url", os.environ["DATABASE_URL"])

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Importar TODOS los modelos para que Alembic los detecte en Base.metadata
from app.database import Base
from app.models.datos import Rut, Vehiculo, Inmueble, VidaSalud, VidaSaludCarga, Otra
from app.models.cruce_tablas import RelacionRut
from app.models.operaciones import (
    Banco, Proveedor, Partner, Gestor, Compania, Ejecutivo,
    Seguro, Ramo, LineaNegocio, Cobertura, Producto, Plan, Protocolo, Pols, Comuna,
    CruceSegurosCia, CruceCoberturasProductos, CruceValoresXCotizacion,
)
from app.models.grupos import GrupoCliente, GrupoMateria, GrupoEntidad, CruceMateriasXRegistro
from app.models.comunicacion import (
    ComCliente, ComCobranza, ComComision, ComDocumento,
    ComLiquidacion, ComPlanPago, ComPoliza, ComRegistro, ComMateria, ComOtros,
)
from app.models.gestion import (
    Registro, Cotizacion, Poliza, Documento, Materia, PlanPago, Cuota,
    Cobranza, Solicitud, Siniestro, Comision,
    CruceRegistrosXPolizas, CruceRecotizacionesXPoliza,
    CruceDocumentosXComision, CruceDocumentosXLiquidacion,
    CruceCuotasXCobranza, CruceFacturasXComision,
    CruceMateriasXEnvio, CruceItemsXEnvioCliente,
)
from app.models.contabilidad import (
    CtaCte, Contable, Cartola, Liquidacion, Fecu,
    CierreMensual, Fondo, Ppm, PagoCliente, Presupuesto,
)
from app.models.agenda import AgendaCategoria, AgendaObligacion, AgendaTarea
from app.models.configuracion import Usuario, ValorUF, Parametro
from app.models.comision import Comision as Permanencia

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_schemas=True,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_schemas=True,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
