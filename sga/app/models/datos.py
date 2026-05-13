"""
Esquema: datos
Entidades maestras del sistema: clientes, vehículos, inmuebles, RUTs.
"""
from datetime import date, datetime
from typing import Optional, TYPE_CHECKING
from sqlalchemy import String, Integer, Date, DateTime, Boolean, Numeric, ForeignKey, Text, Enum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
import enum

from app.database import Base

if TYPE_CHECKING:
    from app.models.gestion import Registro, Poliza, Siniestro


# ── Enums ────────────────────────────────────────────────────────────────────

class TipoPersona(str, enum.Enum):
    natural   = "natural"
    juridica  = "juridica"

class TipoVehiculo(str, enum.Enum):
    sedan       = "sedan"
    suv         = "suv"
    camioneta   = "camioneta"
    camion      = "camion"
    moto        = "moto"
    bus         = "bus"
    furgon      = "furgon"
    otro        = "otro"

class UsoVehiculo(str, enum.Enum):
    particular  = "particular"
    comercial   = "comercial"
    taxi        = "taxi"
    uber        = "uber"

class TipoInmueble(str, enum.Enum):
    casa        = "casa"
    departamento= "departamento"
    oficina     = "oficina"
    bodega      = "bodega"
    local       = "local"
    terreno     = "terreno"
    otro        = "otro"

class MaterialConstruccion(str, enum.Enum):
    solido      = "solido"
    mixto       = "mixto"
    madera      = "madera"
    metalico    = "metalico"


# ── Cliente ──────────────────────────────────────────────────────────────────

class Cliente(Base):
    __tablename__ = "cliente"
    __table_args__ = {"schema": "datos"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    rut: Mapped[str] = mapped_column(String(12), unique=True, nullable=False, index=True)
    tipo_persona: Mapped[TipoPersona] = mapped_column(
        Enum(TipoPersona, schema="datos"), nullable=False, default=TipoPersona.natural
    )

    # Persona natural
    nombre: Mapped[Optional[str]] = mapped_column(String(100))
    apellido_paterno: Mapped[Optional[str]] = mapped_column(String(100))
    apellido_materno: Mapped[Optional[str]] = mapped_column(String(100))
    fecha_nacimiento: Mapped[Optional[date]] = mapped_column(Date)

    # Persona jurídica
    razon_social: Mapped[Optional[str]] = mapped_column(String(200))
    giro: Mapped[Optional[str]] = mapped_column(String(200))

    # Contacto
    email: Mapped[Optional[str]] = mapped_column(String(150), index=True)
    telefono: Mapped[Optional[str]] = mapped_column(String(20))
    telefono_secundario: Mapped[Optional[str]] = mapped_column(String(20))

    # Dirección
    direccion: Mapped[Optional[str]] = mapped_column(String(200))
    numero: Mapped[Optional[str]] = mapped_column(String(20))
    depto: Mapped[Optional[str]] = mapped_column(String(20))
    comuna: Mapped[Optional[str]] = mapped_column(String(100))
    ciudad: Mapped[Optional[str]] = mapped_column(String(100))
    region: Mapped[Optional[str]] = mapped_column(String(100))

    activo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    observaciones: Mapped[Optional[str]] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relaciones
    vehiculos: Mapped[list["Vehiculo"]] = relationship("Vehiculo", back_populates="cliente")
    inmuebles: Mapped[list["Inmueble"]] = relationship("Inmueble", back_populates="cliente")
    registros: Mapped[list["Registro"]] = relationship("Registro", back_populates="cliente")

    @property
    def nombre_completo(self) -> str:
        if self.tipo_persona == TipoPersona.juridica:
            return self.razon_social or ""
        partes = [self.nombre, self.apellido_paterno, self.apellido_materno]
        return " ".join(p for p in partes if p)

    def __repr__(self) -> str:
        return f"<Cliente rut={self.rut} nombre={self.nombre_completo}>"


# ── Vehículo ─────────────────────────────────────────────────────────────────

class Vehiculo(Base):
    __tablename__ = "vehiculo"
    __table_args__ = {"schema": "datos"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    patente: Mapped[str] = mapped_column(String(10), unique=True, nullable=False, index=True)
    marca: Mapped[str] = mapped_column(String(80), nullable=False)
    modelo: Mapped[str] = mapped_column(String(100), nullable=False)
    anio: Mapped[int] = mapped_column(Integer, nullable=False)
    tipo: Mapped[TipoVehiculo] = mapped_column(
        Enum(TipoVehiculo, schema="datos"), nullable=False, default=TipoVehiculo.sedan
    )
    uso: Mapped[UsoVehiculo] = mapped_column(
        Enum(UsoVehiculo, schema="datos"), nullable=False, default=UsoVehiculo.particular
    )
    color: Mapped[Optional[str]] = mapped_column(String(50))
    numero_chasis: Mapped[Optional[str]] = mapped_column(String(50))
    numero_motor: Mapped[Optional[str]] = mapped_column(String(50))
    valor_comercial: Mapped[Optional[float]] = mapped_column(Numeric(14, 2))

    cliente_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("datos.cliente.id"), index=True
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relaciones
    cliente: Mapped[Optional["Cliente"]] = relationship("Cliente", back_populates="vehiculos")

    def __repr__(self) -> str:
        return f"<Vehiculo patente={self.patente} {self.marca} {self.modelo} {self.anio}>"


# ── Inmueble ─────────────────────────────────────────────────────────────────

class Inmueble(Base):
    __tablename__ = "inmueble"
    __table_args__ = {"schema": "datos"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    tipo: Mapped[TipoInmueble] = mapped_column(
        Enum(TipoInmueble, schema="datos"), nullable=False
    )
    direccion: Mapped[str] = mapped_column(String(200), nullable=False)
    numero: Mapped[Optional[str]] = mapped_column(String(20))
    depto: Mapped[Optional[str]] = mapped_column(String(20))
    comuna: Mapped[str] = mapped_column(String(100), nullable=False)
    ciudad: Mapped[Optional[str]] = mapped_column(String(100))
    region: Mapped[Optional[str]] = mapped_column(String(100))

    # Características constructivas
    material_construccion: Mapped[Optional[MaterialConstruccion]] = mapped_column(
        Enum(MaterialConstruccion, schema="datos")
    )
    anio_construccion: Mapped[Optional[int]] = mapped_column(Integer)
    superficie_total: Mapped[Optional[float]] = mapped_column(Numeric(10, 2))
    superficie_construida: Mapped[Optional[float]] = mapped_column(Numeric(10, 2))
    numero_pisos: Mapped[Optional[int]] = mapped_column(Integer)
    valor_comercial: Mapped[Optional[float]] = mapped_column(Numeric(14, 2))

    cliente_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("datos.cliente.id"), index=True
    )

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relaciones
    cliente: Mapped[Optional["Cliente"]] = relationship("Cliente", back_populates="inmuebles")

    def __repr__(self) -> str:
        return f"<Inmueble {self.tipo} {self.direccion} {self.comuna}>"
