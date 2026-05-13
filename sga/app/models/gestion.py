"""
Esquema: gestion
Core del negocio: Registro, Cotización, Póliza, Cobranza, Siniestro.
"""
from datetime import date, datetime
from typing import Optional, TYPE_CHECKING
from sqlalchemy import String, Integer, Date, DateTime, Boolean, Numeric, ForeignKey, Text, Enum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
import enum

from app.database import Base

if TYPE_CHECKING:
    from app.models.datos import Cliente, Vehiculo, Inmueble
    from app.models.operaciones import Ramo, Compania
    from app.models.configuracion import Usuario


# ── Enums ────────────────────────────────────────────────────────────────────

class TipoTramite(str, enum.Enum):
    cotizacion   = "cotizacion"
    renovacion   = "renovacion"
    endoso       = "endoso"
    siniestro    = "siniestro"
    anulacion    = "anulacion"
    consulta     = "consulta"

class EstadoRegistro(str, enum.Enum):
    activo       = "activo"
    cerrado      = "cerrado"
    anulado      = "anulado"

class EstadoCotizacion(str, enum.Enum):
    pendiente    = "pendiente"
    enviada      = "enviada"
    aceptada     = "aceptada"
    rechazada    = "rechazada"
    vencida      = "vencida"
    anulada      = "anulada"

class EstadoPoliza(str, enum.Enum):
    vigente      = "vigente"
    vencida      = "vencida"
    anulada      = "anulada"
    renovada     = "renovada"
    suspendida   = "suspendida"

class FormaPago(str, enum.Enum):
    anual        = "anual"
    semestral    = "semestral"
    trimestral   = "trimestral"
    mensual      = "mensual"

class EstadoSiniestro(str, enum.Enum):
    denunciado   = "denunciado"
    en_tramite   = "en_tramite"
    en_liquidacion = "en_liquidacion"
    cerrado      = "cerrado"
    rechazado    = "rechazado"

class EstadoCuota(str, enum.Enum):
    pendiente    = "pendiente"
    pagada       = "pagada"
    vencida      = "vencida"
    anulada      = "anulada"


# ── Registro ─────────────────────────────────────────────────────────────────

class Registro(Base):
    """Punto de entrada de cualquier gestión. Todo comienza con un Registro."""
    __tablename__ = "registro"
    __table_args__ = {"schema": "gestion"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    numero: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)
    tipo_tramite: Mapped[TipoTramite] = mapped_column(
        Enum(TipoTramite, schema="gestion"), nullable=False
    )
    estado: Mapped[EstadoRegistro] = mapped_column(
        Enum(EstadoRegistro, schema="gestion"), nullable=False, default=EstadoRegistro.activo
    )

    cliente_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("datos.cliente.id"), nullable=False, index=True
    )
    ejecutivo_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("configuracion.usuario.id"), index=True
    )

    fecha_registro: Mapped[date] = mapped_column(Date, nullable=False, default=date.today)
    observaciones: Mapped[Optional[str]] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relaciones
    cliente: Mapped["Cliente"] = relationship("Cliente", back_populates="registros")
    cotizaciones: Mapped[list["Cotizacion"]] = relationship("Cotizacion", back_populates="registro")

    def __repr__(self) -> str:
        return f"<Registro {self.numero} {self.tipo_tramite} cliente_id={self.cliente_id}>"


# ── Cotización ───────────────────────────────────────────────────────────────

class Cotizacion(Base):
    __tablename__ = "cotizacion"
    __table_args__ = {"schema": "gestion"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    numero: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)
    estado: Mapped[EstadoCotizacion] = mapped_column(
        Enum(EstadoCotizacion, schema="gestion"), nullable=False, default=EstadoCotizacion.pendiente
    )

    registro_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("gestion.registro.id"), nullable=False, index=True
    )
    cliente_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("datos.cliente.id"), nullable=False, index=True
    )
    ramo_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("operaciones.ramo.id"), index=True
    )
    compania_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("operaciones.compania.id"), index=True
    )

    fecha_cotizacion: Mapped[date] = mapped_column(Date, nullable=False, default=date.today)
    fecha_vencimiento: Mapped[Optional[date]] = mapped_column(Date)
    fecha_inicio_cobertura: Mapped[Optional[date]] = mapped_column(Date)
    fecha_termino_cobertura: Mapped[Optional[date]] = mapped_column(Date)

    # Montos (en pesos CLP)
    prima_neta: Mapped[Optional[float]] = mapped_column(Numeric(14, 2))
    recargo: Mapped[Optional[float]] = mapped_column(Numeric(14, 2), default=0)
    descuento: Mapped[Optional[float]] = mapped_column(Numeric(14, 2), default=0)
    prima_total: Mapped[Optional[float]] = mapped_column(Numeric(14, 2))

    forma_pago: Mapped[Optional[FormaPago]] = mapped_column(
        Enum(FormaPago, schema="gestion")
    )
    numero_cuotas: Mapped[Optional[int]] = mapped_column(Integer, default=1)
    observaciones: Mapped[Optional[str]] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relaciones
    registro: Mapped["Registro"] = relationship("Registro", back_populates="cotizaciones")
    poliza: Mapped[Optional["Poliza"]] = relationship("Poliza", back_populates="cotizacion", uselist=False)

    def __repr__(self) -> str:
        return f"<Cotizacion {self.numero} estado={self.estado}>"


# ── Póliza ───────────────────────────────────────────────────────────────────

class Poliza(Base):
    __tablename__ = "poliza"
    __table_args__ = {"schema": "gestion"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    numero_poliza: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    estado: Mapped[EstadoPoliza] = mapped_column(
        Enum(EstadoPoliza, schema="gestion"), nullable=False, default=EstadoPoliza.vigente
    )

    cotizacion_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("gestion.cotizacion.id"), index=True
    )
    cliente_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("datos.cliente.id"), nullable=False, index=True
    )
    compania_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("operaciones.compania.id"), index=True
    )
    ramo_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("operaciones.ramo.id"), index=True
    )
    # Auto-referencia para cadena de renovaciones
    poliza_anterior_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("gestion.poliza.id"), index=True
    )

    fecha_emision: Mapped[date] = mapped_column(Date, nullable=False)
    fecha_inicio: Mapped[date] = mapped_column(Date, nullable=False)
    fecha_termino: Mapped[date] = mapped_column(Date, nullable=False)

    # Montos
    prima_neta: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    prima_total: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    suma_asegurada: Mapped[Optional[float]] = mapped_column(Numeric(14, 2))

    forma_pago: Mapped[FormaPago] = mapped_column(
        Enum(FormaPago, schema="gestion"), nullable=False, default=FormaPago.anual
    )
    numero_cuotas: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    # Comisión Aegis
    porcentaje_comision: Mapped[Optional[float]] = mapped_column(Numeric(5, 2))
    monto_comision: Mapped[Optional[float]] = mapped_column(Numeric(14, 2))

    observaciones: Mapped[Optional[str]] = mapped_column(Text)
    activa: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relaciones
    cotizacion: Mapped[Optional["Cotizacion"]] = relationship("Cotizacion", back_populates="poliza")
    siniestros: Mapped[list["Siniestro"]] = relationship("Siniestro", back_populates="poliza")
    cuotas: Mapped[list["Cuota"]] = relationship("Cuota", back_populates="poliza")
    poliza_anterior: Mapped[Optional["Poliza"]] = relationship(
        "Poliza", remote_side="Poliza.id", foreign_keys=[poliza_anterior_id]
    )

    def __repr__(self) -> str:
        return f"<Poliza {self.numero_poliza} estado={self.estado} vigencia={self.fecha_inicio}/{self.fecha_termino}>"


# ── Cuota (Cobranza) ─────────────────────────────────────────────────────────

class Cuota(Base):
    __tablename__ = "cuota"
    __table_args__ = {"schema": "gestion"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    poliza_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("gestion.poliza.id"), nullable=False, index=True
    )
    numero_cuota: Mapped[int] = mapped_column(Integer, nullable=False)
    estado: Mapped[EstadoCuota] = mapped_column(
        Enum(EstadoCuota, schema="gestion"), nullable=False, default=EstadoCuota.pendiente
    )

    monto: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    fecha_vencimiento: Mapped[date] = mapped_column(Date, nullable=False)
    fecha_pago: Mapped[Optional[date]] = mapped_column(Date)
    medio_pago: Mapped[Optional[str]] = mapped_column(String(50))
    referencia_pago: Mapped[Optional[str]] = mapped_column(String(100))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    poliza: Mapped["Poliza"] = relationship("Poliza", back_populates="cuotas")

    def __repr__(self) -> str:
        return f"<Cuota poliza_id={self.poliza_id} #{self.numero_cuota} {self.estado}>"


# ── Siniestro ────────────────────────────────────────────────────────────────

class Siniestro(Base):
    __tablename__ = "siniestro"
    __table_args__ = {"schema": "gestion"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    numero: Mapped[str] = mapped_column(String(30), unique=True, nullable=False, index=True)
    estado: Mapped[EstadoSiniestro] = mapped_column(
        Enum(EstadoSiniestro, schema="gestion"), nullable=False, default=EstadoSiniestro.denunciado
    )

    poliza_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("gestion.poliza.id"), nullable=False, index=True
    )
    cliente_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("datos.cliente.id"), nullable=False, index=True
    )

    fecha_siniestro: Mapped[date] = mapped_column(Date, nullable=False)
    fecha_denuncia: Mapped[date] = mapped_column(Date, nullable=False, default=date.today)
    fecha_cierre: Mapped[Optional[date]] = mapped_column(Date)

    descripcion: Mapped[str] = mapped_column(Text, nullable=False)
    tipo_siniestro: Mapped[Optional[str]] = mapped_column(String(100))
    lugar: Mapped[Optional[str]] = mapped_column(String(300))

    # Montos
    monto_reclamado: Mapped[Optional[float]] = mapped_column(Numeric(14, 2))
    monto_liquidado: Mapped[Optional[float]] = mapped_column(Numeric(14, 2))
    deducible: Mapped[Optional[float]] = mapped_column(Numeric(14, 2))

    numero_compania: Mapped[Optional[str]] = mapped_column(String(50))
    liquidador: Mapped[Optional[str]] = mapped_column(String(150))
    observaciones: Mapped[Optional[str]] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relaciones
    poliza: Mapped["Poliza"] = relationship("Poliza", back_populates="siniestros")

    def __repr__(self) -> str:
        return f"<Siniestro {self.numero} estado={self.estado}>"
