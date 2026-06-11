"""
Esquema: operaciones
Catálogos del negocio: Compañías, Ramos, Seguros, Productos, Planes,
Coberturas, Ejecutivos, Bancos, Partners, Gestores, Proveedores, etc.
"""
from datetime import date, datetime
from typing import Optional, TYPE_CHECKING
from sqlalchemy import String, Integer, Date, DateTime, Boolean, Numeric, ForeignKey, Text, Enum
import enum as _enum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.database import Base
from app.models.mixins import AppSheetMixin
from app.models.datos import SexoBiologico


class TipoEjecutivo(str, _enum.Enum):
    compania  = "compania"
    banco     = "banco"
    proveedor = "proveedor"

if TYPE_CHECKING:
    from app.models.datos import Rut
    from app.models.grupos import GrupoEntidad, GrupoMateria


# ─── Banco ────────────────────────────────────────────────────────────────────

class Banco(AppSheetMixin, Base):
    """Banco. Opción B: identidad jurídica en datos.rut via rut_id."""
    __tablename__ = "banco"
    __table_args__ = {"schema": "operaciones"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    rut_id:        Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("datos.rut.id"), index=True)
    corto:         Mapped[Optional[str]] = mapped_column(String(50))
    casa_matriz:   Mapped[Optional[str]] = mapped_column(String(200))
    sucursal:      Mapped[Optional[str]] = mapped_column(String(200))
    fono_matriz:   Mapped[Optional[str]] = mapped_column(String(25))
    fono_sucursal: Mapped[Optional[str]] = mapped_column(String(25))
    web:           Mapped[Optional[str]] = mapped_column(String(200))
    portal:        Mapped[Optional[str]] = mapped_column(String(200))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    rut_ref:        Mapped[Optional["Rut"]]       = relationship("Rut", foreign_keys=[rut_id])
    ejecutivos:     Mapped[list["Ejecutivo"]]      = relationship("Ejecutivo", back_populates="banco", foreign_keys="[Ejecutivo.banco_id]")
    grupos_entidad: Mapped[list["GrupoEntidad"]]   = relationship("GrupoEntidad", back_populates="banco", foreign_keys="[GrupoEntidad.banco_id]")


# ─── Proveedor ────────────────────────────────────────────────────────────────

class Proveedor(AppSheetMixin, Base):
    """Proveedor de servicios. Opción B: identidad en datos.rut via rut_id."""
    __tablename__ = "proveedor"
    __table_args__ = {"schema": "operaciones"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    rut_id:        Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("datos.rut.id"), index=True)
    corto:         Mapped[Optional[str]] = mapped_column(String(50))
    servicio:      Mapped[Optional[str]] = mapped_column(String(200))
    casa_matriz:   Mapped[Optional[str]] = mapped_column(String(200))
    sucursal:      Mapped[Optional[str]] = mapped_column(String(200))
    fono_matriz:   Mapped[Optional[str]] = mapped_column(String(25))
    fono_sucursal: Mapped[Optional[str]] = mapped_column(String(25))
    correo:        Mapped[Optional[str]] = mapped_column(String(150))
    web:           Mapped[Optional[str]] = mapped_column(String(200))
    portal:        Mapped[Optional[str]] = mapped_column(String(200))
    activo:        Mapped[bool]          = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    rut_ref:        Mapped[Optional["Rut"]]      = relationship("Rut", foreign_keys=[rut_id])
    ejecutivos:     Mapped[list["Ejecutivo"]]     = relationship("Ejecutivo",    back_populates="proveedor", foreign_keys="[Ejecutivo.proveedor_id]")
    grupos_entidad: Mapped[list["GrupoEntidad"]]  = relationship("GrupoEntidad", back_populates="proveedor", foreign_keys="[GrupoEntidad.proveedor_id]")


# ─── Partner ──────────────────────────────────────────────────────────────────

class Partner(AppSheetMixin, Base):
    """
    Partner comercial. Opción B: identidad personal en datos.rut via rut_id.
    Solo conserva datos operativos: comisiones pactadas y contrato.
    """
    __tablename__ = "partner"
    __table_args__ = {"schema": "operaciones"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    rut_id:                Mapped[Optional[int]]   = mapped_column(Integer, ForeignKey("datos.rut.id"), index=True)
    comision_nuevos:       Mapped[Optional[float]] = mapped_column(Numeric(5, 2))
    comision_renovaciones: Mapped[Optional[float]] = mapped_column(Numeric(5, 2))
    contrato:              Mapped[Optional[str]]   = mapped_column(String(500))
    activo:                Mapped[bool]            = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    rut_ref:        Mapped[Optional["Rut"]]      = relationship("Rut", foreign_keys=[rut_id])
    grupos_entidad: Mapped[list["GrupoEntidad"]] = relationship("GrupoEntidad", back_populates="partner", foreign_keys="[GrupoEntidad.partner_id]")


# ─── Gestor ───────────────────────────────────────────────────────────────────

class Gestor(AppSheetMixin, Base):
    """
    Gestor interno (corredor/usuario del sistema). Opción B: identidad en datos.rut via rut_id.
    Solo conserva campos operativos únicos: acceso al sistema y cuenta bancaria.
    """
    __tablename__ = "gestor"
    __table_args__ = {"schema": "operaciones"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    rut_id:           Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("datos.rut.id"), index=True)
    usermail:         Mapped[Optional[str]] = mapped_column(String(150))
    cuenta_corriente: Mapped[Optional[str]] = mapped_column(String(100))
    activo:           Mapped[bool]          = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    rut_ref:        Mapped[Optional["Rut"]]          = relationship("Rut", foreign_keys=[rut_id])
    grupos_entidad: Mapped[list["GrupoEntidad"]]     = relationship("GrupoEntidad", back_populates="gestor", foreign_keys="[GrupoEntidad.gestor_id]")


# ─── Compania ─────────────────────────────────────────────────────────────────

class Compania(AppSheetMixin, Base):
    """
    Compañía de seguros. Opción B: identidad en datos.rut via rut_id.
    Los campos rut/razon_social/corto viven exclusivamente en datos.rut.
    """
    __tablename__ = "compania"
    __table_args__ = {"schema": "operaciones"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    # FK a datos.rut (identidad jurídica — sin UNIQUE: múltiples marcas pueden compartir RUT)
    rut_id:                 Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("datos.rut.id"), index=True)
    # Ejecutivo principal asignado a esta compañía
    ejecutivo_principal_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("operaciones.ejecutivo.id"), index=True)
    # Sucesión corporativa: apunta a la compañía que absorbió a esta (NULL si activa)
    sucesora_id:            Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("operaciones.compania.id"), index=True)

    # Nombre comercial/de marca — permite distinguir entidades que comparten RUT
    # (ej. Liberty vs HDI-Liberty comparten 99061000-2 pero son marcas distintas)
    nombre_comercial: Mapped[Optional[str]] = mapped_column(String(150))
    color:            Mapped[Optional[str]] = mapped_column(String(20))

    # Datos operativos específicos de la compañía
    codigo_corredor:  Mapped[Optional[str]] = mapped_column(String(30))
    cuenta_corriente: Mapped[Optional[str]] = mapped_column(String(100))
    fono_asistencia:  Mapped[Optional[str]] = mapped_column(String(25))
    casa_matriz:      Mapped[Optional[str]] = mapped_column(String(200))
    sucursal:         Mapped[Optional[str]] = mapped_column(String(200))
    fono_matriz:      Mapped[Optional[str]] = mapped_column(String(25))
    fono_sucursal:    Mapped[Optional[str]] = mapped_column(String(25))
    web:              Mapped[Optional[str]] = mapped_column(String(200))
    portal:           Mapped[Optional[str]] = mapped_column(String(200))
    activa:           Mapped[bool]          = mapped_column(Boolean, default=True, nullable=False)

    # Plazos de gracia para pólizas caídas por no pago (Radar de Rehabilitación)
    dias_gracia_carta:      Mapped[Optional[int]] = mapped_column(Integer)
    dias_gracia_inspeccion: Mapped[Optional[int]] = mapped_column(Integer)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Relaciones
    rut_ref:             Mapped[Optional["Rut"]]        = relationship("Rut",       foreign_keys=[rut_id])
    ejecutivo_principal: Mapped[Optional["Ejecutivo"]]  = relationship("Ejecutivo", foreign_keys=[ejecutivo_principal_id])
    sucesora:            Mapped[Optional["Compania"]]   = relationship("Compania",  foreign_keys=[sucesora_id], remote_side="Compania.id")
    ejecutivos:          Mapped[list["Ejecutivo"]]     = relationship("Ejecutivo", back_populates="compania", foreign_keys="[Ejecutivo.compania_id]")
    lineas_negocio:      Mapped[list["LineaNegocio"]]  = relationship("LineaNegocio",  back_populates="compania")
    productos:           Mapped[list["Producto"]]      = relationship("Producto",      back_populates="compania")
    grupos_entidad:      Mapped[list["GrupoEntidad"]]  = relationship("GrupoEntidad",  back_populates="compania", foreign_keys="[GrupoEntidad.compania_id]")
    seguros_link:        Mapped[list["CruceSegurosCia"]] = relationship("CruceSegurosCia", back_populates="compania")


# ─── Ejecutivo ────────────────────────────────────────────────────────────────

class Ejecutivo(AppSheetMixin, Base):
    __tablename__ = "ejecutivo"
    __table_args__ = {"schema": "operaciones"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    tipo:        Mapped[Optional[TipoEjecutivo]] = mapped_column(Enum(TipoEjecutivo, schema="operaciones"))
    banco_id:    Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("operaciones.banco.id"), index=True)
    compania_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("operaciones.compania.id"), index=True)
    proveedor_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("operaciones.proveedor.id"), index=True)

    nombre:  Mapped[Optional[str]] = mapped_column(String(100))
    nombre2: Mapped[Optional[str]] = mapped_column(String(100))
    paterno: Mapped[Optional[str]] = mapped_column(String(100))
    materno: Mapped[Optional[str]] = mapped_column(String(100))
    corto:   Mapped[Optional[str]] = mapped_column(String(50))
    correo:  Mapped[Optional[str]] = mapped_column(String(150))
    correo2: Mapped[Optional[str]] = mapped_column(String(150))
    celular: Mapped[Optional[str]] = mapped_column(String(25))
    fijo:    Mapped[Optional[str]] = mapped_column(String(25))
    sexo:    Mapped[Optional[SexoBiologico]] = mapped_column(Enum(SexoBiologico, schema="operaciones"))
    cargo:   Mapped[Optional[str]]           = mapped_column(String(100))
    activo:  Mapped[bool]          = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    banco:     Mapped[Optional["Banco"]]     = relationship("Banco",     back_populates="ejecutivos", foreign_keys=[banco_id])
    compania:  Mapped[Optional["Compania"]]  = relationship("Compania",  back_populates="ejecutivos", foreign_keys=[compania_id])
    proveedor: Mapped[Optional["Proveedor"]] = relationship("Proveedor", back_populates="ejecutivos", foreign_keys=[proveedor_id])
    protocolos: Mapped[list["Protocolo"]]   = relationship("Protocolo",  back_populates="responsable")


# ─── Seguro ───────────────────────────────────────────────────────────────────

class Seguro(AppSheetMixin, Base):
    __tablename__ = "seguro"
    __table_args__ = {"schema": "operaciones"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    nombre:          Mapped[str]           = mapped_column(String(100), nullable=False)
    perfil:          Mapped[Optional[str]] = mapped_column(String(100))
    info_tecnica:    Mapped[Optional[str]] = mapped_column(Text)
    guia_corredor:   Mapped[Optional[str]] = mapped_column(Text)
    info_venta:      Mapped[Optional[str]] = mapped_column(Text)
    activo:          Mapped[bool]          = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    productos:    Mapped[list["Producto"]]     = relationship("Producto",     back_populates="seguro")
    companias_link: Mapped[list["CruceSegurosCia"]] = relationship("CruceSegurosCia", back_populates="seguro")


# ─── Ramo ─────────────────────────────────────────────────────────────────────

class Ramo(AppSheetMixin, Base):
    __tablename__ = "ramo"
    __table_args__ = {"schema": "operaciones"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    ramo:   Mapped[str]           = mapped_column(String(100), nullable=False)
    codigo: Mapped[Optional[str]] = mapped_column(String(20))
    activo: Mapped[bool]          = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    lineas_negocio: Mapped[list["LineaNegocio"]] = relationship("LineaNegocio", back_populates="ramo")
    productos:      Mapped[list["Producto"]]     = relationship("Producto",     back_populates="ramo")


# ─── LineaNegocio ─────────────────────────────────────────────────────────────

class LineaNegocio(AppSheetMixin, Base):
    __tablename__ = "linea_negocio"
    __table_args__ = {"schema": "operaciones"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    ramo_id:    Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("operaciones.ramo.id"), index=True)
    compania_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("operaciones.compania.id"), index=True)

    linea:      Mapped[str]           = mapped_column(String(150), nullable=False)
    carpeta:    Mapped[Optional[str]] = mapped_column(String(500))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    ramo:    Mapped[Optional["Ramo"]]    = relationship("Ramo",    back_populates="lineas_negocio")
    compania: Mapped[Optional["Compania"]] = relationship("Compania", back_populates="lineas_negocio")


# ─── Cobertura ────────────────────────────────────────────────────────────────

class Cobertura(AppSheetMixin, Base):
    __tablename__ = "cobertura"
    __table_args__ = {"schema": "operaciones"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    cobertura: Mapped[str]           = mapped_column(String(200), nullable=False)
    detalles:  Mapped[Optional[str]] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    productos_link: Mapped[list["CruceCoberturasProductos"]] = relationship("CruceCoberturasProductos", back_populates="cobertura")


# ─── Producto ─────────────────────────────────────────────────────────────────

class Producto(AppSheetMixin, Base):
    __tablename__ = "producto"
    __table_args__ = {"schema": "operaciones"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    seguro_id:   Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("operaciones.seguro.id"), index=True)
    compania_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("operaciones.compania.id"), index=True)
    ramo_id:     Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("operaciones.ramo.id"), index=True)

    nombre:          Mapped[str]           = mapped_column(String(200), nullable=False)
    tipo_comision:   Mapped[Optional[str]] = mapped_column(String(50))
    canal:           Mapped[Optional[str]] = mapped_column(String(50))
    convenio:        Mapped[Optional[str]] = mapped_column(String(100))
    tipo_renovacion: Mapped[Optional[str]] = mapped_column(String(50))
    uso:             Mapped[Optional[str]] = mapped_column(String(50))
    comision_afecta: Mapped[Optional[float]] = mapped_column(Numeric(5, 2))
    comision_exenta: Mapped[Optional[float]] = mapped_column(Numeric(5, 2))
    pdf_cobertura:   Mapped[Optional[str]] = mapped_column(String(500))
    activo:          Mapped[bool]          = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    seguro:    Mapped[Optional["Seguro"]]   = relationship("Seguro",   back_populates="productos")
    compania:  Mapped[Optional["Compania"]] = relationship("Compania", back_populates="productos")
    ramo:      Mapped[Optional["Ramo"]]     = relationship("Ramo",     back_populates="productos")
    planes:    Mapped[list["Plan"]]         = relationship("Plan",     back_populates="producto")
    coberturas_link: Mapped[list["CruceCoberturasProductos"]] = relationship("CruceCoberturasProductos", back_populates="producto")


# ─── Plan ─────────────────────────────────────────────────────────────────────

class Plan(AppSheetMixin, Base):
    __tablename__ = "plan"
    __table_args__ = {"schema": "operaciones"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    producto_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("operaciones.producto.id"), index=True)
    plan:        Mapped[str]           = mapped_column(String(200), nullable=False)
    descripcion: Mapped[Optional[str]] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    producto: Mapped[Optional["Producto"]] = relationship("Producto", back_populates="planes")
    valores_cotizacion: Mapped[list["CruceValoresXCotizacion"]] = relationship("CruceValoresXCotizacion", back_populates="plan")


# ─── Protocolo ────────────────────────────────────────────────────────────────

class Protocolo(AppSheetMixin, Base):
    __tablename__ = "protocolo"
    __table_args__ = {"schema": "operaciones"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    grupo_entidad_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("grupos.grupo_entidad.id"), index=True)
    responsable_id:   Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("operaciones.ejecutivo.id"), index=True)

    nombre:      Mapped[Optional[str]] = mapped_column(String(200))
    descripcion: Mapped[Optional[str]] = mapped_column(Text)
    activo:      Mapped[bool]          = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    grupo_entidad: Mapped[Optional["GrupoEntidad"]] = relationship("GrupoEntidad", back_populates="protocolos")
    responsable:   Mapped[Optional["Ejecutivo"]]    = relationship("Ejecutivo",    back_populates="protocolos")


# ─── Comuna ───────────────────────────────────────────────────────────────────

class Comuna(AppSheetMixin, Base):
    __tablename__ = "comuna"
    __table_args__ = {"schema": "operaciones"}

    id:               Mapped[int]           = mapped_column(Integer, primary_key=True, index=True)
    nombre:           Mapped[str]           = mapped_column(String(100), nullable=False, index=True)
    ciudad:           Mapped[Optional[str]] = mapped_column(String(100))
    region:           Mapped[Optional[str]] = mapped_column(String(100))
    codigo_comuna:    Mapped[Optional[str]] = mapped_column(String(10))
    codigo_provincia: Mapped[Optional[str]] = mapped_column(String(10))
    codigo_region:    Mapped[Optional[str]] = mapped_column(String(10))

    ruts:      Mapped[list["Rut"]]     = relationship("Rut",     back_populates="comuna",     foreign_keys="[Rut.comuna_id]")
    inmuebles: Mapped[list["Inmueble"]] = relationship("Inmueble", back_populates="comuna_rel", foreign_keys="[Inmueble.comuna_id]")


# ─── Pols (Depósito de Pólizas/Cláusulas) ────────────────────────────────────

class Pols(AppSheetMixin, Base):
    """Repositorio de cláusulas y textos de pólizas."""
    __tablename__ = "pols"
    __table_args__ = {"schema": "operaciones"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    codigo:          Mapped[Optional[str]] = mapped_column(String(50))
    fecha_deposito:  Mapped[Optional[date]] = mapped_column(Date)
    entidad:         Mapped[Optional[str]] = mapped_column(String(200))
    texto_depositado: Mapped[Optional[str]] = mapped_column(Text)
    polizas_clausulas: Mapped[Optional[str]] = mapped_column(Text)
    temas:           Mapped[Optional[str]] = mapped_column(String(300))
    pdf:             Mapped[Optional[str]] = mapped_column(String(500))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


# ─── Tablas cruce propias de operaciones ─────────────────────────────────────

class CruceSegurosCia(AppSheetMixin, Base):
    """N:M entre Seguros y Compañías."""
    __tablename__ = "seguros_x_cia"
    __table_args__ = {"schema": "cruce_tablas"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    seguro_id:   Mapped[int] = mapped_column(Integer, ForeignKey("operaciones.seguro.id"), nullable=False, index=True)
    compania_id: Mapped[int] = mapped_column(Integer, ForeignKey("operaciones.compania.id"), nullable=False, index=True)

    seguro:   Mapped["Seguro"]   = relationship("Seguro",   back_populates="companias_link")
    compania: Mapped["Compania"] = relationship("Compania", back_populates="seguros_link")


class CruceCoberturasProductos(AppSheetMixin, Base):
    """N:M entre Coberturas y Productos."""
    __tablename__ = "coberturas_x_productos"
    __table_args__ = {"schema": "cruce_tablas"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    producto_id:  Mapped[int] = mapped_column(Integer, ForeignKey("operaciones.producto.id"), nullable=False, index=True)
    cobertura_id: Mapped[int] = mapped_column(Integer, ForeignKey("operaciones.cobertura.id"), nullable=False, index=True)

    producto:  Mapped["Producto"]  = relationship("Producto",  back_populates="coberturas_link")
    cobertura: Mapped["Cobertura"] = relationship("Cobertura", back_populates="productos_link")


class CruceValoresXCotizacion(AppSheetMixin, Base):
    """N:M entre Cotizaciones y Planes (con valores económicos)."""
    __tablename__ = "valores_x_cotizacion"
    __table_args__ = {"schema": "cruce_tablas"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    cotizacion_id: Mapped[int] = mapped_column(Integer, ForeignKey("gestion.cotizacion.id"), nullable=False, index=True)
    plan_id:       Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("operaciones.plan.id"), index=True)

    uf_prima_afecta:  Mapped[Optional[float]] = mapped_column(Numeric(10, 4))
    uf_prima_exenta:  Mapped[Optional[float]] = mapped_column(Numeric(10, 4))
    uf_cuota:         Mapped[Optional[float]] = mapped_column(Numeric(10, 4))
    clp_prima_afecta: Mapped[Optional[float]] = mapped_column(Numeric(14, 2))
    clp_prima_exenta: Mapped[Optional[float]] = mapped_column(Numeric(14, 2))
    clp_cuota:        Mapped[Optional[float]] = mapped_column(Numeric(14, 2))
    usd_prima_afecta: Mapped[Optional[float]] = mapped_column(Numeric(10, 2))
    usd_prima_exenta: Mapped[Optional[float]] = mapped_column(Numeric(10, 2))
    usd_cuota:        Mapped[Optional[float]] = mapped_column(Numeric(10, 2))
    tasa_afecta:      Mapped[Optional[float]] = mapped_column(Numeric(6, 4))
    tasa_exenta:      Mapped[Optional[float]] = mapped_column(Numeric(6, 4))
    cambio_moneda:    Mapped[Optional[float]] = mapped_column(Numeric(14, 6))

    plan: Mapped[Optional["Plan"]] = relationship("Plan", back_populates="valores_cotizacion")
