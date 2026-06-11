# ── Esquema: datos ────────────────────────────────────────────────────────────
from app.models.datos import Rut, Vehiculo, Inmueble, VidaSalud, VidaSaludCarga, Otra

# ── Esquema: cruce_tablas ─────────────────────────────────────────────────────
from app.models.cruce_tablas import RelacionRut
# Alias backward-compat
Cliente = Rut

# ── Esquema: operaciones ──────────────────────────────────────────────────────
from app.models.operaciones import (
    Banco, Proveedor, Partner, Gestor,
    Compania, Ejecutivo,
    Seguro, Ramo, LineaNegocio,
    Cobertura, Producto, Plan, Protocolo,
    Pols, Comuna,
    CruceSegurosCia, CruceCoberturasProductos, CruceValoresXCotizacion,
)

# ── Esquema: grupos ───────────────────────────────────────────────────────────
from app.models.grupos import GrupoCliente, GrupoMateria, GrupoEntidad, CruceMateriasXRegistro

# ── Esquema: comunicacion ─────────────────────────────────────────────────────
from app.models.comunicacion import (
    ComCliente, ComCobranza, ComComision, ComDocumento,
    ComLiquidacion, ComPlanPago, ComPoliza, ComRegistro,
    ComMateria, ComOtros,
)

# ── Esquema: audiencia ────────────────────────────────────────────────────────
from app.models.audiencia import (
    Lead, Campana, HitoFidelizacion,
    OrigenLead, EstadoLead, EstadoCampana, TipoHito,
)

# ── Esquema: gestion ──────────────────────────────────────────────────────────
from app.models.gestion import (
    # Enums (exportados para uso en routers/schemas)
    TipoRegistro, EstadoProspecto, EstadoNegocio, TipoMateria, Moneda,
    EstadoSeguro, TipoDocumento, FormaPago,
    EstadoPoliza,
    # Modelos
    Registro, Cotizacion, Poliza,
    Documento, Materia, PlanPago, Cuota,
    Cobranza, Solicitud, Siniestro, Comision,
    # Puentes gestion
    CruceRegistrosXPolizas, CruceRecotizacionesXPoliza,
    CruceDocumentosXComision, CruceDocumentosXLiquidacion,
    CruceCuotasXCobranza, CruceFacturasXComision,
    CruceMateriasXEnvio, CruceItemsXEnvioCliente,
)

# ── Esquema: contabilidad ─────────────────────────────────────────────────────
from app.models.contabilidad import (
    CtaCte, Contable, Cartola, Liquidacion,
    Fecu, CierreMensual, Fondo, Ppm, PagoCliente, Presupuesto,
)

# ── Esquema: agenda ───────────────────────────────────────────────────────────
from app.models.agenda import AgendaCategoria, AgendaObligacion, AgendaTarea

# ── Configuración (solo usuarios y valores de referencia) ─────────────────────
from app.models.configuracion import Usuario, ValorUF, Parametro

__all__ = [
    # datos
    "Rut", "Cliente", "Vehiculo", "Inmueble", "VidaSalud", "VidaSaludCarga", "Otra",
    # cruce_tablas
    "RelacionRut",
    # operaciones
    "Banco", "Proveedor", "Partner", "Gestor",
    "Compania", "Ejecutivo",
    "Seguro", "Ramo", "LineaNegocio",
    "Cobertura", "Producto", "Plan", "Protocolo",
    "Pols", "Comuna",
    "CruceSegurosCia", "CruceCoberturasProductos", "CruceValoresXCotizacion",
    # grupos
    "GrupoCliente", "GrupoMateria", "GrupoEntidad", "CruceMateriasXRegistro",
    # comunicacion
    "ComCliente", "ComCobranza", "ComComision", "ComDocumento",
    "ComLiquidacion", "ComPlanPago", "ComPoliza", "ComRegistro",
    "ComMateria", "ComOtros",
    # audiencia
    "Lead", "Campana", "HitoFidelizacion",
    "OrigenLead", "EstadoLead", "EstadoCampana", "TipoHito",
    # gestion
    "TipoRegistro", "EstadoProspecto", "EstadoNegocio", "TipoMateria", "Moneda",
    "EstadoSeguro", "TipoDocumento", "FormaPago", "EstadoPoliza",
    "Registro", "Cotizacion", "Poliza",
    "Documento", "Materia", "PlanPago", "Cuota",
    "Cobranza", "Solicitud", "Siniestro", "Comision",
    "CruceRegistrosXPolizas", "CruceRecotizacionesXPoliza",
    "CruceDocumentosXComision", "CruceDocumentosXLiquidacion",
    "CruceCuotasXCobranza", "CruceFacturasXComision",
    "CruceMateriasXEnvio", "CruceItemsXEnvioCliente",
    # contabilidad
    "CtaCte", "Contable", "Cartola", "Liquidacion",
    "Fecu", "CierreMensual", "Fondo", "Ppm", "PagoCliente", "Presupuesto",
    # agenda
    "AgendaCategoria", "AgendaObligacion", "AgendaTarea",
    # configuracion
    "Usuario", "ValorUF", "Parametro",
]
