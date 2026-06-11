"""
Esquema: datos
Entidades base: RUTs (persona/empresa), vehículos, inmuebles, vida y salud, otras.
"""
from datetime import date, datetime
from typing import Optional, TYPE_CHECKING
from sqlalchemy import (
    String, Integer, Date, DateTime, Boolean, Numeric,
    ForeignKey, Text, Enum,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
import enum

from app.database import Base
from app.models.mixins import AppSheetMixin

if TYPE_CHECKING:
    from app.models.grupos import GrupoCliente, GrupoMateria
    from app.models.operaciones import Partner
    from app.models.cruce_tablas import RelacionRut
    from app.models.audiencia import Lead, HitoFidelizacion


class Personeria(str, enum.Enum):
    natural  = "natural"
    juridica = "juridica"

TipoPersona = Personeria  # alias backward-compat


class SexoBiologico(str, enum.Enum):
    masculino = "masculino"
    femenino  = "femenino"


class TipoCliente(str, enum.Enum):
    principal  = "principal"
    secundario = "secundario"


class CategoriaVehiculo(str, enum.Enum):
    liviano      = "liviano"
    pesado       = "pesado"
    equipo_movil = "equipo_movil"
    otro         = "otro"


class TipoVehiculo(str, enum.Enum):
    automovil               = "automovil"
    camioneta               = "camioneta"
    camion                  = "camion"
    furgon                  = "furgon"
    jeep                    = "jeep"
    minibus                 = "minibus"
    motocicleta             = "motocicleta"
    station_wagon           = "station_wagon"
    tracto_camion           = "tracto_camion"
    manipulador_telescopico = "manipulador_telescopico"
    semiremolque            = "semiremolque"
    carro_arrastre          = "carro_arrastre"
    tijera_electrica        = "tijera_electrica"
    otro                    = "otro"


class Combustible(str, enum.Enum):
    bencina           = "bencina"
    diesel            = "diesel"
    hibrido_bencina   = "hibrido_bencina"
    electrico         = "electrico"
    hibrido_electrico = "hibrido_electrico"
    otro              = "otro"


class TipoInmueble(str, enum.Enum):
    casa         = "casa"
    departamento = "departamento"
    oficina      = "oficina"
    bodega       = "bodega"
    comunidad    = "comunidad"
    otro         = "otro"


class UsoInmueble(str, enum.Enum):
    habitacional = "habitacional"
    comercial    = "comercial"
    mixto        = "mixto"
    industrial   = "industrial"
    otro         = "otro"


class OcupacionInmueble(str, enum.Enum):
    habitual   = "habitual"
    temporal   = "temporal"
    vacacional = "vacacional"
    desocupado = "desocupado"
    otro       = "otro"


# ─── Rut ─────────────────────────────────────────────────────────────────────

class Rut(AppSheetMixin, Base):
    """Persona natural o jurídica. Padre absoluto del sistema."""
    __tablename__ = "rut"
    __table_args__ = {"schema": "datos"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    rut:              Mapped[str]           = mapped_column(String(15), unique=True, nullable=False, index=True)
    personeria:       Mapped[Personeria]    = mapped_column(Enum(Personeria, schema="datos"), nullable=False, default=Personeria.natural)
    razon_social:     Mapped[Optional[str]] = mapped_column(String(200))
    nombre:           Mapped[Optional[str]] = mapped_column(String(100))
    nombre2:          Mapped[Optional[str]] = mapped_column(String(100))       # 2do nombre
    apellido_paterno: Mapped[Optional[str]] = mapped_column(String(100))
    apellido_materno: Mapped[Optional[str]] = mapped_column(String(100))
    corto:            Mapped[Optional[str]] = mapped_column(String(80))        # alias/nombre corto
    email:            Mapped[Optional[str]] = mapped_column(String(150), index=True)
    email2:           Mapped[Optional[str]] = mapped_column(String(150))       # correo 2
    telefono:         Mapped[Optional[str]] = mapped_column(String(25))        # celular
    telefono_secundario: Mapped[Optional[str]] = mapped_column(String(25))     # fijo
    direccion:        Mapped[Optional[str]] = mapped_column(String(500))
    numero:           Mapped[Optional[str]] = mapped_column(String(50))
    depto:            Mapped[Optional[str]]             = mapped_column(String(200))
    comuna_id:        Mapped[Optional[int]]             = mapped_column(Integer, ForeignKey("operaciones.comuna.id"), index=True)
    sexo:             Mapped[Optional[SexoBiologico]]   = mapped_column(Enum(SexoBiologico, schema="datos"))
    fecha_nacimiento: Mapped[Optional[date]]            = mapped_column(Date)
    giro:             Mapped[Optional[str]]             = mapped_column(String(200))
    tarjeta_credito:  Mapped[Optional[str]]             = mapped_column(String(50))
    cuenta_corriente: Mapped[Optional[str]]             = mapped_column(String(100))
    tipo_cliente:     Mapped[Optional[TipoCliente]]     = mapped_column(Enum(TipoCliente, schema="datos"))
    relacion_cliente: Mapped[Optional[str]]             = mapped_column(String(100))
    contacto:         Mapped[Optional[str]] = mapped_column(String(200))
    activo:           Mapped[bool]          = mapped_column(Boolean, default=True, nullable=False)
    observaciones:    Mapped[Optional[str]] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relaciones
    comuna:      Mapped[Optional["Comuna"]]       = relationship("Comuna", back_populates="ruts", foreign_keys=[comuna_id])
    vida_salud:  Mapped[Optional["VidaSalud"]]    = relationship("VidaSalud", back_populates="titular", uselist=False)
    cargas:      Mapped[list["VidaSaludCarga"]]   = relationship("VidaSaludCarga", back_populates="titular")

    # Grupos que me referencian como cliente
    grupos_cliente: Mapped[list["GrupoCliente"]] = relationship("GrupoCliente", back_populates="rut", foreign_keys="[GrupoCliente.rut_id]")
    # Como asegurado en materias
    grupos_materia_asegurado: Mapped[list["GrupoMateria"]] = relationship("GrupoMateria", back_populates="asegurado", foreign_keys="[GrupoMateria.asegurado_id]")

    # Grafo ontológico de relaciones (familia, holding, sociedad, etc.)
    relaciones_salientes:  Mapped[list["RelacionRut"]] = relationship(
        "RelacionRut",
        foreign_keys="[RelacionRut.rut_origen_id]",
        back_populates="rut_origen",
    )
    relaciones_entrantes: Mapped[list["RelacionRut"]] = relationship(
        "RelacionRut",
        foreign_keys="[RelacionRut.rut_destino_id]",
        back_populates="rut_destino",
    )

    # Audiencia (CRM): leads convertidos + hitos de fidelización
    leads:              Mapped[list["Lead"]]             = relationship("Lead", back_populates="rut", foreign_keys="[Lead.rut_id]")
    hitos_fidelizacion: Mapped[list["HitoFidelizacion"]] = relationship("HitoFidelizacion", back_populates="rut", foreign_keys="[HitoFidelizacion.rut_id]")

    @property
    def nombre_completo(self) -> str:
        if self.personeria == Personeria.juridica:
            return self.razon_social or self.corto or ""
        partes = [self.nombre, self.nombre2, self.apellido_paterno, self.apellido_materno]
        return " ".join(p for p in partes if p).strip()

    # Alias tipo_persona para backward-compat con schema existente
    @property
    def tipo_persona(self):
        return self.personeria


# ─── Vehiculo ─────────────────────────────────────────────────────────────────

class Vehiculo(AppSheetMixin, Base):
    """
    Registro maestro de vehículos (patentes).
    Template: Datos Materias — sin propietario_id.
    La vinculación asegurado↔vehículo vive exclusivamente en grupos.grupo_materia.
    """
    __tablename__ = "vehiculo"
    __table_args__ = {"schema": "datos"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    patente:       Mapped[Optional[str]]              = mapped_column(String(15), index=True)
    categoria:     Mapped[Optional[CategoriaVehiculo]] = mapped_column(Enum(CategoriaVehiculo, schema="datos"))
    tipo_vehiculo: Mapped[Optional[TipoVehiculo]]      = mapped_column(Enum(TipoVehiculo, schema="datos"))
    marca:         Mapped[Optional[str]]              = mapped_column(String(80))
    modelo:        Mapped[Optional[str]]              = mapped_column(String(100))
    version:       Mapped[Optional[str]]              = mapped_column(String(100))
    anio:          Mapped[Optional[int]]              = mapped_column(Integer)
    color:         Mapped[Optional[str]]              = mapped_column(String(50))
    motor:         Mapped[Optional[str]]              = mapped_column(String(60))
    chasis:        Mapped[Optional[str]]              = mapped_column(String(60))
    combustible:   Mapped[Optional[Combustible]]      = mapped_column(Enum(Combustible, schema="datos"))
    n_serie:     Mapped[Optional[str]] = mapped_column(String(60))
    factura:     Mapped[Optional[str]] = mapped_column(String(200))
    guia_despacho: Mapped[Optional[str]] = mapped_column(String(200))
    papeles:     Mapped[Optional[str]] = mapped_column(String(500))
    monto_asegurado: Mapped[Optional[float]] = mapped_column(Numeric(14, 2))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    grupos_materia: Mapped[list["GrupoMateria"]] = relationship("GrupoMateria", back_populates="vehiculo", foreign_keys="[GrupoMateria.vehiculo_id]")
    otras: Mapped[list["Otra"]] = relationship("Otra", back_populates="vehiculo")
    flotas_link: Mapped[list["FlotaXVehiculos"]] = relationship("FlotaXVehiculos", back_populates="vehiculo")


# ─── Inmueble ─────────────────────────────────────────────────────────────────

class Inmueble(AppSheetMixin, Base):
    """
    Registro maestro de inmuebles.
    Template: Datos Materias — sin propietario_id.
    La vinculación asegurado↔inmueble vive exclusivamente en grupos.grupo_materia.
    """
    __tablename__ = "inmueble"
    __table_args__ = {"schema": "datos"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    comuna_id:     Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("operaciones.comuna.id"), index=True)

    tipo_inmueble: Mapped[Optional[TipoInmueble]]      = mapped_column(Enum(TipoInmueble, schema="datos"))
    calle:         Mapped[Optional[str]]               = mapped_column(String(200))
    numero:        Mapped[Optional[str]]               = mapped_column(String(20))
    detalles_dir:  Mapped[Optional[str]]               = mapped_column(String(200))
    uso:           Mapped[Optional[UsoInmueble]]        = mapped_column(Enum(UsoInmueble, schema="datos"))
    ocupacion:     Mapped[Optional[OcupacionInmueble]]  = mapped_column(Enum(OcupacionInmueble, schema="datos"))
    zona:          Mapped[Optional[str]] = mapped_column(String(60))
    distancia_agua: Mapped[Optional[str]] = mapped_column(String(60))
    tipo_construccion: Mapped[Optional[str]] = mapped_column(String(60))
    n_torres:      Mapped[Optional[int]] = mapped_column(Integer)
    n_pisos:       Mapped[Optional[int]] = mapped_column(Integer)
    n_subterraneos: Mapped[Optional[int]] = mapped_column(Integer)
    n_unidades:    Mapped[Optional[int]] = mapped_column(Integer)
    anio_construccion: Mapped[Optional[int]] = mapped_column(Integer)
    mt2_construido: Mapped[Optional[float]] = mapped_column(Numeric(10, 2))
    adicional:     Mapped[Optional[str]] = mapped_column(String(300))
    espacios_comunes: Mapped[Optional[str]] = mapped_column(String(300))
    seguridad_incendio: Mapped[Optional[str]] = mapped_column(String(200))
    seguridad_robo: Mapped[Optional[str]] = mapped_column(String(200))
    n_trabajadores: Mapped[Optional[int]] = mapped_column(Integer)
    monto_edificio: Mapped[Optional[float]] = mapped_column(Numeric(14, 2))
    monto_contenidos: Mapped[Optional[float]] = mapped_column(Numeric(14, 2))
    monto_unidades: Mapped[Optional[float]] = mapped_column(Numeric(14, 2))
    monto_mercaderia: Mapped[Optional[float]] = mapped_column(Numeric(14, 2))
    ficha:         Mapped[Optional[str]] = mapped_column(String(500))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    comuna_rel:  Mapped[Optional["Comuna"]] = relationship("Comuna", back_populates="inmuebles")
    grupos_materia: Mapped[list["GrupoMateria"]] = relationship("GrupoMateria", back_populates="inmueble", foreign_keys="[GrupoMateria.inmueble_id]")
    otras: Mapped[list["Otra"]] = relationship("Otra", back_populates="inmueble")


# ─── VidaSalud ────────────────────────────────────────────────────────────────

class VidaSalud(AppSheetMixin, Base):
    __tablename__ = "vida_salud"
    __table_args__ = {"schema": "datos"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    titular_id: Mapped[int] = mapped_column(Integer, ForeignKey("datos.rut.id"), nullable=False, unique=True, index=True)

    altura:          Mapped[Optional[float]] = mapped_column(Numeric(5, 2))
    peso:            Mapped[Optional[float]] = mapped_column(Numeric(5, 2))
    dps:             Mapped[Optional[str]]   = mapped_column(String(500))
    otros_documentos: Mapped[Optional[str]]  = mapped_column(String(500))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    titular: Mapped["Rut"]              = relationship("Rut", back_populates="vida_salud")
    cargas:  Mapped[list["VidaSaludCarga"]] = relationship("VidaSaludCarga", back_populates="vida_salud_titular")
    grupos_materia: Mapped[list["GrupoMateria"]] = relationship("GrupoMateria", back_populates="vida_salud", foreign_keys="[GrupoMateria.vida_salud_id]")


# ─── VidaSaludCarga ───────────────────────────────────────────────────────────

class VidaSaludCarga(AppSheetMixin, Base):
    __tablename__ = "vida_salud_carga"
    __table_args__ = {"schema": "datos"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    vida_salud_id: Mapped[int] = mapped_column(Integer, ForeignKey("datos.vida_salud.id"), nullable=False, index=True)
    rut_carga_id:  Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("datos.rut.id"), index=True)

    rut:     Mapped[Optional[str]] = mapped_column(String(15))
    nombre:  Mapped[Optional[str]] = mapped_column(String(100))
    nombre2: Mapped[Optional[str]] = mapped_column(String(100))
    paterno: Mapped[Optional[str]] = mapped_column(String(100))
    materno: Mapped[Optional[str]] = mapped_column(String(100))
    fecha_nacimiento: Mapped[Optional[date]] = mapped_column(Date)
    altura:  Mapped[Optional[float]] = mapped_column(Numeric(5, 2))
    peso:    Mapped[Optional[float]] = mapped_column(Numeric(5, 2))
    dps:     Mapped[Optional[str]]   = mapped_column(String(500))
    otros_documentos: Mapped[Optional[str]] = mapped_column(String(500))
    comentarios: Mapped[Optional[str]] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    vida_salud_titular: Mapped["VidaSalud"] = relationship("VidaSalud", back_populates="cargas")
    titular: Mapped[Optional["Rut"]] = relationship("Rut", back_populates="cargas", foreign_keys=[rut_carga_id])


# ─── Otra ─────────────────────────────────────────────────────────────────────

class Otra(AppSheetMixin, Base):
    """
    Materia asegurada que no es vehículo ni inmueble (maquinaria, joya, GPS, etc.).
    Template: Datos Materias — sin propietario_id ni FK a datos.rut.
    vehiculo_id e inmueble_id son referencias cruzadas entre tipos de materia
    (ej. accesorio instalado en un vehículo), no vínculos de propiedad.
    La vinculación asegurado↔otra vive exclusivamente en grupos.grupo_materia.
    """
    __tablename__ = "otra"
    __table_args__ = {"schema": "datos"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    vehiculo_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("datos.vehiculo.id"), index=True)
    inmueble_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("datos.inmueble.id"), index=True)

    tipo_otra:   Mapped[Optional[str]] = mapped_column(String(100))
    materia_asegurada: Mapped[Optional[str]] = mapped_column(String(300))
    informacion_adicional: Mapped[Optional[str]] = mapped_column(Text)
    monto_asegurado: Mapped[Optional[float]] = mapped_column(Numeric(14, 2))
    ficha:       Mapped[Optional[str]] = mapped_column(String(500))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    vehiculo: Mapped[Optional["Vehiculo"]] = relationship("Vehiculo", back_populates="otras")
    inmueble: Mapped[Optional["Inmueble"]] = relationship("Inmueble", back_populates="otras")
    grupos_materia: Mapped[list["GrupoMateria"]] = relationship("GrupoMateria", back_populates="otra", foreign_keys="[GrupoMateria.otra_id]")


# ─── FlotaTransporte ──────────────────────────────────────────────────────────

class FlotaTransporte(AppSheetMixin, Base):
    """
    Flota de transporte: grupo nombrado de vehículos + ficha técnica operacional.
    Registro maestro reutilizable entre pólizas (sin FK a datos.rut).
    La vinculación asegurado↔vehículos de la flota vive en grupos.grupo_materia
    y cruce_tablas.flota_x_vehiculos.
    """
    __tablename__ = "flota_transporte"
    __table_args__ = {"schema": "datos"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    # Identidad
    nombre:      Mapped[str]           = mapped_column(String(200), nullable=False)
    tipo_carga:  Mapped[Optional[str]] = mapped_column(String(100))
    descripcion: Mapped[Optional[str]] = mapped_column(Text)

    # Ficha técnica operacional
    zona_operacion:      Mapped[Optional[str]]   = mapped_column(String(300))
    ruta_habitual:       Mapped[Optional[str]]   = mapped_column(String(500))
    tipo_mercaderia:     Mapped[Optional[str]]   = mapped_column(String(200))
    embalaje:            Mapped[Optional[str]]   = mapped_column(String(200))
    almacenamiento:      Mapped[Optional[str]]   = mapped_column(String(200))
    medidas_seguridad:   Mapped[Optional[str]]   = mapped_column(Text)
    frecuencia_viajes:   Mapped[Optional[str]]   = mapped_column(String(100))
    valor_max_por_viaje: Mapped[Optional[float]] = mapped_column(Numeric(14, 2))
    historial_siniestros: Mapped[Optional[str]]  = mapped_column(Text)
    notas_operacion:     Mapped[Optional[str]]   = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relaciones
    vehiculos_link: Mapped[list["FlotaXVehiculos"]] = relationship("FlotaXVehiculos", back_populates="flota")
    grupos_materia: Mapped[list["GrupoMateria"]] = relationship(
        "GrupoMateria", back_populates="flota_transporte",
        foreign_keys="[GrupoMateria.flota_transporte_id]",
    )


# ─── FlotaXVehiculos (cruce_tablas.flota_x_vehiculos) ─────────────────────────

class FlotaXVehiculos(AppSheetMixin, Base):
    """Puente M:N entre una flota y sus vehículos permanentes."""
    __tablename__ = "flota_x_vehiculos"
    __table_args__ = {"schema": "cruce_tablas"}

    id:           Mapped[int]           = mapped_column(Integer, primary_key=True, index=True)
    flota_id:     Mapped[int]           = mapped_column(Integer, ForeignKey("datos.flota_transporte.id"), nullable=False, index=True)
    vehiculo_id:  Mapped[int]           = mapped_column(Integer, ForeignKey("datos.vehiculo.id"),        nullable=False, index=True)
    asegurado_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("datos.rut.id"),            index=True)
    rol:          Mapped[Optional[str]] = mapped_column(String(50))
    activo:       Mapped[bool]          = mapped_column(Boolean, default=True, nullable=False)
    created_at:   Mapped[datetime]      = mapped_column(DateTime(timezone=True), server_default=func.now())

    flota:     Mapped["FlotaTransporte"] = relationship("FlotaTransporte", back_populates="vehiculos_link")
    vehiculo:  Mapped["Vehiculo"]        = relationship("Vehiculo",        back_populates="flotas_link")
    asegurado: Mapped[Optional["Rut"]]   = relationship("Rut",            foreign_keys=[asegurado_id])


# Alias backward-compat
Cliente = Rut
