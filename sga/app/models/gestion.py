"""
Esquema: gestion
Core del negocio: Registro → Cotizacion → Poliza → Documento → Materia + PlanPago + Cuota
+ Cobranza, Solicitud, Siniestro, Comision
Relaciones exactas según Programación Guía - Relaciones entre Registros.csv
"""
from datetime import date, datetime, timedelta
from typing import Optional, TYPE_CHECKING
from sqlalchemy import String, Integer, Date, DateTime, Boolean, Numeric, ForeignKey, Text, Enum, case
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from sqlalchemy.ext.hybrid import hybrid_property
import enum

from app.database import Base
from app.models.mixins import AppSheetMixin

if TYPE_CHECKING:
    from app.models.datos import Rut
    from app.models.grupos import GrupoCliente, GrupoMateria, CruceMateriasXRegistro
    from app.models.operaciones import (
        Seguro, Producto, Ejecutivo, Compania, Ramo, Partner, Plan,
        CruceValoresXCotizacion
    )
    from app.models.contabilidad import Liquidacion, Contable
    from app.models.comunicacion import (
        ComRegistro, ComPoliza, ComDocumento, ComPlanPago, ComCobranza, ComComision
    )


# ─── Enums ────────────────────────────────────────────────────────────────────

class TipoRegistro(str, enum.Enum):
    prospecto  = "prospecto"
    negocio    = "negocio"
    renovacion = "renovacion"
    traspaso   = "traspaso"
    inclusion  = "inclusion"

class EstadoProspecto(str, enum.Enum):
    pendiente      = "pendiente"
    aceptado       = "aceptado"
    rechazado      = "rechazado"
    espera_cliente = "espera_cliente"
    cerrado        = "cerrado"    # legacy

class EstadoNegocio(str, enum.Enum):
    pendiente = "pendiente"
    aceptado  = "aceptado"
    nulo      = "nulo"
    ok        = "ok"      # legacy
    cerrado   = "cerrado" # legacy

class TipoMateria(str, enum.Enum):
    vehiculo   = "vehiculo"
    inmueble   = "inmueble"
    vida_salud = "vida_salud"
    otra       = "otra"

class Moneda(str, enum.Enum):
    clp = "clp"
    uf  = "uf"
    usd = "usd"

class EstadoSeguro(str, enum.Enum):
    pendiente  = "pendiente"
    inspeccion = "inspeccion"
    ok         = "ok"
    cancelada  = "cancelada"
    anulada    = "anulada"
    consumido  = "consumido"
    nulo       = "nulo"       # cayó antes de vigencia; sin movimiento de prima

class TipoDocumento(str, enum.Enum):
    poliza     = "poliza"
    endoso     = "endoso"
    renovacion = "renovacion"
    anulacion  = "anulacion"
    cancelacion = "cancelacion"
    exclusion  = "exclusion"
    inclusion  = "inclusion"
    modificacion = "modificacion"
    prorroga   = "prorroga"
    rehabilitacion = "rehabilitacion"
    otro       = "otro"

class EstadoCuota(str, enum.Enum):
    pendiente    = "pendiente"
    pagada       = "pagada"
    vencida      = "vencida"
    anulada      = "anulada"

class FormaPago(str, enum.Enum):
    directa    = "directa"
    pac        = "pac"
    pat        = "pat"
    anual      = "anual"
    semestral  = "semestral"
    trimestral = "trimestral"
    mensual    = "mensual"
    unico      = "unico"

# Legacy (backward compat)
class TipoTramite(str, enum.Enum):
    cotizacion = "cotizacion"
    renovacion = "renovacion"
    endoso     = "endoso"
    siniestro  = "siniestro"
    anulacion  = "anulacion"
    consulta   = "consulta"

class EstadoRegistro(str, enum.Enum):
    activo  = "activo"
    cerrado = "cerrado"
    anulado = "anulado"

class EstadoPoliza(str, enum.Enum):
    vigente    = "vigente"
    vencida    = "vencida"
    anulada    = "anulada"
    renovada   = "renovada"
    suspendida = "suspendida"

class EstadoSiniestro(str, enum.Enum):
    abierto        = "abierto"
    en_tramite     = "en_tramite"
    en_liquidacion = "en_liquidacion"
    cerrado        = "cerrado"
    rechazado      = "rechazado"


# ─── Registro ─────────────────────────────────────────────────────────────────

class Registro(AppSheetMixin, Base):
    """Punto de entrada del flujo. Puede ser Prospecto, Negocio, Renovación, Traspaso, Inclusión."""
    __tablename__ = "registro"
    __table_args__ = {"schema": "gestion"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    fecha_registro: Mapped[date] = mapped_column(Date, nullable=False, default=date.today)

    tipo_registro: Mapped[TipoRegistro] = mapped_column(
        Enum(TipoRegistro, schema="gestion"), nullable=False, default=TipoRegistro.prospecto
    )
    estado_prospecto:  Mapped[Optional[EstadoProspecto]] = mapped_column(Enum(EstadoProspecto, schema="gestion"), default=EstadoProspecto.pendiente)
    estado_negocio:    Mapped[Optional[EstadoNegocio]]   = mapped_column(Enum(EstadoNegocio, schema="gestion"))
    estado_renovacion: Mapped[Optional[str]] = mapped_column(String(50))
    estado_traspaso:   Mapped[Optional[str]] = mapped_column(String(50))
    estado_inclusion:  Mapped[Optional[str]] = mapped_column(String(50))

    # FKs según guía
    grupo_cliente_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("grupos.grupo_cliente.id"), index=True)   # "Cliente"
    asegurado_id:     Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("datos.rut.id"), index=True)              # "Asegurado"
    contratante_id:   Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("datos.rut.id"), index=True)
    pagador_id:       Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("datos.rut.id"), index=True)
    ejecutivo_id:     Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("operaciones.ejecutivo.id"), index=True)
    compania_id:      Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("operaciones.compania.id"), index=True)
    seguro_id:        Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("operaciones.seguro.id"), index=True)
    producto_id:      Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("operaciones.producto.id"), index=True)
    plan_id:          Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("operaciones.plan.id"), index=True)
    cot_aceptada_id:  Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("gestion.cotizacion.id"), index=True)
    poliza_id:        Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("gestion.poliza.id"), index=True)

    # Datos económicos
    moneda:           Mapped[Optional[Moneda]]      = mapped_column(Enum(Moneda, schema="gestion"))
    forma_pago:       Mapped[Optional[FormaPago]]   = mapped_column(Enum(FormaPago, schema="gestion"))
    n_cuotas:         Mapped[Optional[int]]         = mapped_column(Integer)
    valor_cuota:      Mapped[Optional[float]]       = mapped_column(Numeric(14, 2))
    uf_prima_afecta:  Mapped[Optional[float]]       = mapped_column(Numeric(10, 4))
    uf_prima_exenta:  Mapped[Optional[float]]       = mapped_column(Numeric(10, 4))
    clp_prima_afecta: Mapped[Optional[float]]       = mapped_column(Numeric(14, 2))
    clp_prima_exenta: Mapped[Optional[float]]       = mapped_column(Numeric(14, 2))
    usd_prima_afecta: Mapped[Optional[float]]       = mapped_column(Numeric(10, 2))
    usd_prima_exenta: Mapped[Optional[float]]       = mapped_column(Numeric(10, 2))
    pct_comision_afecta: Mapped[Optional[float]]    = mapped_column(Numeric(5, 2))
    pct_comision_exenta: Mapped[Optional[float]]    = mapped_column(Numeric(5, 2))

    tipo_inspeccion:  Mapped[Optional[str]] = mapped_column(String(50))
    n_inspeccion:     Mapped[Optional[str]] = mapped_column(String(50))
    fecha_inicio_vigencia: Mapped[Optional[date]] = mapped_column(Date)
    condiciones:      Mapped[Optional[str]] = mapped_column(Text)
    archivos:         Mapped[Optional[str]] = mapped_column(String(500))
    comentarios:      Mapped[Optional[str]] = mapped_column(Text)
    fin_gestion:      Mapped[Optional[date]] = mapped_column(Date)
    traspaso_info_1:  Mapped[Optional[str]] = mapped_column(String(300))
    traspaso_info_2:  Mapped[Optional[str]] = mapped_column(String(300))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relaciones
    grupo_cliente: Mapped[Optional["GrupoCliente"]] = relationship("GrupoCliente", back_populates="registros", foreign_keys=[grupo_cliente_id])
    asegurado:     Mapped[Optional["Rut"]]          = relationship("Rut", foreign_keys=[asegurado_id])
    contratante:   Mapped[Optional["Rut"]]          = relationship("Rut", foreign_keys=[contratante_id])
    pagador:       Mapped[Optional["Rut"]]          = relationship("Rut", foreign_keys=[pagador_id])
    ejecutivo:     Mapped[Optional["Ejecutivo"]]    = relationship("Ejecutivo", foreign_keys=[ejecutivo_id])
    compania:      Mapped[Optional["Compania"]]     = relationship("Compania", foreign_keys=[compania_id])
    seguro:        Mapped[Optional["Seguro"]]       = relationship("Seguro", foreign_keys=[seguro_id])
    producto:      Mapped[Optional["Producto"]]     = relationship("Producto", foreign_keys=[producto_id])
    plan:          Mapped[Optional["Plan"]]         = relationship("Plan", foreign_keys=[plan_id])
    cot_aceptada:  Mapped[Optional["Cotizacion"]]   = relationship("Cotizacion", foreign_keys=[cot_aceptada_id], post_update=True)
    poliza_directa: Mapped[Optional["Poliza"]]      = relationship("Poliza", foreign_keys=[poliza_id], post_update=True)

    cotizaciones:  Mapped[list["Cotizacion"]]       = relationship("Cotizacion", back_populates="registro", foreign_keys="[Cotizacion.registro_id]")
    materias_link: Mapped[list["CruceMateriasXRegistro"]] = relationship("CruceMateriasXRegistro", back_populates="registro")
    polizas_link:  Mapped[list["CruceRegistrosXPolizas"]] = relationship("CruceRegistrosXPolizas", back_populates="registro")
    com_registros: Mapped[list["ComRegistro"]] = relationship("ComRegistro", back_populates="registro")

    # ── Propiedades calculadas ────────────────────────────────────────────────

    @property
    def estado_gestion(self) -> str:
        """Estado de gestión del registro según su tipo y estado operativo."""
        t = self.tipo_registro
        if t == TipoRegistro.negocio:
            return "Ok" if self.estado_negocio != EstadoNegocio.pendiente else "Pendiente"
        if t == TipoRegistro.renovacion:
            return "Ok" if self.estado_renovacion != "Pendiente" else "Pendiente"
        if t == TipoRegistro.traspaso:
            return "Ok" if self.estado_traspaso != "Pendiente" else "Pendiente"
        if t == TipoRegistro.prospecto:
            # "ganado"→aceptado, "perdido"→rechazado (AppSheet rename, ver CLAUDE.md)
            if self.estado_prospecto in {EstadoProspecto.aceptado, EstadoProspecto.rechazado}:
                return "Ok"
            return "Ok" if self.estado_prospecto != EstadoProspecto.pendiente else "Pendiente"
        return "Ok"  # inclusion y tipos futuros


# ─── Cotizacion ───────────────────────────────────────────────────────────────

class Cotizacion(AppSheetMixin, Base):
    __tablename__ = "cotizacion"
    __table_args__ = {"schema": "gestion"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    registro_id: Mapped[int] = mapped_column(Integer, ForeignKey("gestion.registro.id"), nullable=False, index=True)
    producto_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("operaciones.producto.id"), index=True)

    fecha_cot:          Mapped[date]           = mapped_column(Date, nullable=False, default=date.today)
    vigencia_dias:      Mapped[Optional[int]]  = mapped_column(Integer)
    numero_cot:         Mapped[Optional[str]]  = mapped_column(String(50), index=True)
    monto_asegurado:    Mapped[Optional[float]] = mapped_column(Numeric(14, 2))
    forma_pago:         Mapped[Optional[FormaPago]] = mapped_column(Enum(FormaPago, schema="gestion"))
    n_cuotas:           Mapped[Optional[int]]  = mapped_column(Integer, default=1)
    descuento_adicional: Mapped[Optional[float]] = mapped_column(Numeric(5, 2))
    promocion:          Mapped[Optional[str]]  = mapped_column(String(200))
    prima:              Mapped[Optional[float]] = mapped_column(Numeric(14, 2))
    deducible:          Mapped[Optional[str]]  = mapped_column(String(200))
    pdf_url:            Mapped[Optional[str]]  = mapped_column(String(500))
    aceptada:           Mapped[bool]           = mapped_column(Boolean, default=False, nullable=False)
    recomendada:        Mapped[bool]           = mapped_column(Boolean, default=False, nullable=False)
    plan_aceptado:      Mapped[Optional[str]]  = mapped_column(String(200))
    deducible_recomendado: Mapped[Optional[str]] = mapped_column(String(200))
    comentarios:        Mapped[Optional[str]]  = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    registro:  Mapped["Registro"]            = relationship("Registro",  back_populates="cotizaciones", foreign_keys=[registro_id])
    producto:  Mapped[Optional["Producto"]]  = relationship("Producto",  foreign_keys=[producto_id])
    valores:   Mapped[list["CruceValoresXCotizacion"]] = relationship("CruceValoresXCotizacion", foreign_keys="[CruceValoresXCotizacion.cotizacion_id]")
    polizas_link: Mapped[list["CruceRegistrosXPolizas"]] = relationship("CruceRegistrosXPolizas", back_populates="cotizacion")
    recotizaciones: Mapped[list["CruceRecotizacionesXPoliza"]] = relationship("CruceRecotizacionesXPoliza", back_populates="cotizacion")
    solicitudes: Mapped[list["Solicitud"]] = relationship("Solicitud", back_populates="cotizacion", foreign_keys="[Solicitud.cotizacion_id]")

    # ── Propiedades calculadas ────────────────────────────────────────────────

    @hybrid_property
    def estado_vigencia(self) -> str:
        """CSV row 15 — cotización vigente mientras no supere su plazo."""
        if not self.vigencia_dias:
            return "Vigente"  # sin plazo → no expira
        vencimiento = self.fecha_cot + timedelta(days=self.vigencia_dias)
        return "Vencida" if vencimiento <= date.today() else "Vigente"

    @estado_vigencia.expression
    @classmethod
    def estado_vigencia(cls):
        from sqlalchemy import or_
        hoy = func.current_date()
        # PostgreSQL: Date + Integer → Date (aritmética nativa)
        vencimiento = cls.fecha_cot + cls.vigencia_dias
        return case(
            (or_(cls.vigencia_dias.is_(None), vencimiento > hoy), "Vigente"),
            else_="Vencida",
        )


# ─── Poliza ───────────────────────────────────────────────────────────────────

class Poliza(AppSheetMixin, Base):
    __tablename__ = "poliza"
    __table_args__ = {"schema": "gestion"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    # FKs según guía
    producto_id:      Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("operaciones.producto.id"), index=True)
    ejecutivo_id:     Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("operaciones.ejecutivo.id"), index=True)
    grupo_cliente_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("grupos.grupo_cliente.id"), index=True)  # "Cliente"
    contratante_id:   Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("datos.rut.id"), index=True)
    pagador_id:       Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("datos.rut.id"), index=True)
    ramo_id:          Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("operaciones.ramo.id"), index=True)
    compania_id:      Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("operaciones.compania.id"), index=True)
    seguro_id:        Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("operaciones.seguro.id"), index=True)
    verificador_traspaso_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("gestion.registro.id"), index=True)

    # Datos de póliza
    numero_poliza:  Mapped[Optional[str]]  = mapped_column(String(50), unique=True, index=True)
    estado_seguro:  Mapped[EstadoSeguro]   = mapped_column(Enum(EstadoSeguro, schema="gestion"), nullable=False, default=EstadoSeguro.pendiente)
    estado:         Mapped[EstadoPoliza]   = mapped_column(Enum(EstadoPoliza, schema="gestion"), nullable=False, default=EstadoPoliza.vigente)
    fecha_emision:  Mapped[Optional[date]] = mapped_column(Date)
    fecha_inicio:   Mapped[Optional[date]] = mapped_column(Date)
    fecha_termino:  Mapped[Optional[date]] = mapped_column(Date)
    moneda:         Mapped[Optional[Moneda]] = mapped_column(Enum(Moneda, schema="gestion"))
    forma_pago:     Mapped[Optional[FormaPago]] = mapped_column(Enum(FormaPago, schema="gestion"))
    n_cuotas:       Mapped[Optional[int]]  = mapped_column(Integer)
    pct_comision_afecta: Mapped[Optional[float]] = mapped_column(Numeric(5, 2))
    pct_comision_exenta: Mapped[Optional[float]] = mapped_column(Numeric(5, 2))

    # Flags
    mandato:     Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    comision_flag: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    renovar:     Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    pago_activo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    recotizar:   Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    activa:      Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    otros_archivos:     Mapped[Optional[str]]  = mapped_column(String(500))
    fecha_cancelacion: Mapped[Optional[date]] = mapped_column(Date)
    comentarios:       Mapped[Optional[str]]  = mapped_column(Text)

    # Legacy (backward compat)
    prima_neta:        Mapped[Optional[float]] = mapped_column(Numeric(14, 2))
    prima_total:       Mapped[Optional[float]] = mapped_column(Numeric(14, 2))
    suma_asegurada:    Mapped[Optional[float]] = mapped_column(Numeric(14, 2))
    numero_cuotas:     Mapped[Optional[int]]   = mapped_column(Integer)
    porcentaje_comision: Mapped[Optional[float]] = mapped_column(Numeric(5, 2))
    monto_comision:    Mapped[Optional[float]] = mapped_column(Numeric(14, 2))
    cotizacion_id:     Mapped[Optional[int]]   = mapped_column(Integer, ForeignKey("gestion.cotizacion.id"), index=True)
    poliza_anterior_id: Mapped[Optional[int]]  = mapped_column(Integer, ForeignKey("gestion.poliza.id"), index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    # Relaciones
    producto:      Mapped[Optional["Producto"]]    = relationship("Producto",    foreign_keys=[producto_id])
    ejecutivo:     Mapped[Optional["Ejecutivo"]]   = relationship("Ejecutivo",   foreign_keys=[ejecutivo_id])
    grupo_cliente: Mapped[Optional["GrupoCliente"]] = relationship("GrupoCliente", back_populates="polizas", foreign_keys=[grupo_cliente_id])
    contratante:   Mapped[Optional["Rut"]]         = relationship("Rut", foreign_keys=[contratante_id])
    pagador:       Mapped[Optional["Rut"]]         = relationship("Rut", foreign_keys=[pagador_id])
    ramo:          Mapped[Optional["Ramo"]]        = relationship("Ramo", foreign_keys=[ramo_id])
    compania:      Mapped[Optional["Compania"]]    = relationship("Compania", foreign_keys=[compania_id])
    seguro:        Mapped[Optional["Seguro"]]      = relationship("Seguro", foreign_keys=[seguro_id])
    verificador_traspaso: Mapped[Optional["Registro"]] = relationship("Registro", foreign_keys=[verificador_traspaso_id])

    documentos:    Mapped[list["Documento"]]       = relationship("Documento",   back_populates="poliza")
    materias:      Mapped[list["Materia"]]         = relationship("Materia",     back_populates="poliza", foreign_keys="[Materia.poliza_id]")
    planes_pago:   Mapped[list["PlanPago"]]        = relationship("PlanPago",    back_populates="poliza")
    cuotas:        Mapped[list["Cuota"]]           = relationship("Cuota",       back_populates="poliza")
    siniestros:    Mapped[list["Siniestro"]]       = relationship("Siniestro",   back_populates="poliza")
    solicitudes:   Mapped[list["Solicitud"]]       = relationship("Solicitud",   back_populates="poliza", foreign_keys="[Solicitud.poliza_id]")
    registros_link: Mapped[list["CruceRegistrosXPolizas"]] = relationship("CruceRegistrosXPolizas", back_populates="poliza")
    recotizaciones: Mapped[list["CruceRecotizacionesXPoliza"]] = relationship("CruceRecotizacionesXPoliza", back_populates="poliza")
    com_polizas:   Mapped[list["ComPoliza"]]       = relationship("ComPoliza",   back_populates="poliza")

    # ── Propiedades calculadas ────────────────────────────────────────────────

    @hybrid_property
    def estado_vigencia(self) -> str:
        """CSV row 36 — vigencia temporal pura, sin estados de seguro."""
        if not self.fecha_inicio or not self.fecha_termino:
            return "Pendiente"
        hoy = date.today()
        if self.fecha_inicio > hoy:
            return "Pendiente"
        if self.fecha_termino > hoy:
            return "Ok"
        return "Finalizada"

    @estado_vigencia.expression
    @classmethod
    def estado_vigencia(cls):
        from sqlalchemy import or_
        hoy = func.current_date()
        return case(
            (or_(cls.fecha_inicio.is_(None), cls.fecha_inicio > hoy), "Pendiente"),
            (cls.fecha_termino > hoy,                                  "Ok"),
            else_="Finalizada",
        )

    @property
    def dias_usados(self) -> int:
        """Días de prima consumida según tipo de terminación.

        - Anulada  → 0  (void desde inicio; sin consumo de prima)
        - Nula     → 0  (cayó antes de vigencia; sin consumo de prima)
        - Cancelada → fecha_cancelacion − fecha_inicio  (cancelación anticipada)
        - Resto    → fecha_termino − fecha_inicio
        """
        if self.estado_seguro in (EstadoSeguro.anulada, EstadoSeguro.nulo):
            return 0
        if self.estado_seguro == EstadoSeguro.cancelada:
            if self.fecha_cancelacion and self.fecha_inicio:
                return abs((self.fecha_cancelacion - self.fecha_inicio).days)
            return 0
        if self.fecha_inicio and self.fecha_termino:
            return abs((self.fecha_termino - self.fecha_inicio).days)
        return 0

    @hybrid_property
    def estado_poliza(self) -> str:
        """Estado operativo calculado de la póliza. Delega vigencia a estado_vigencia."""
        mapa_terminal = {
            EstadoSeguro.consumido: "Consumida",
            EstadoSeguro.cancelada: "Cancelada",
            EstadoSeguro.anulada:   "Anulada",
            EstadoSeguro.nulo:      "Nula",
        }
        if self.estado_seguro in mapa_terminal:
            return mapa_terminal[self.estado_seguro]
        if self.numero_poliza == "Pendiente":
            return "Pendiente"
        if self.recotizar:
            return "Recotizar"
        ev = self.estado_vigencia
        return "Espera" if ev == "Pendiente" else ev

    @estado_poliza.expression
    @classmethod
    def estado_poliza(cls):
        from sqlalchemy import or_
        hoy = func.current_date()
        return case(
            (cls.estado_seguro == EstadoSeguro.consumido, "Consumida"),
            (cls.estado_seguro == EstadoSeguro.cancelada, "Cancelada"),
            (cls.estado_seguro == EstadoSeguro.anulada,   "Anulada"),
            (cls.estado_seguro == EstadoSeguro.nulo,      "Nula"),
            (cls.numero_poliza == "Pendiente",            "Pendiente"),
            (cls.recotizar.is_(True),                     "Recotizar"),
            # estado_vigencia inlined — evita doble evaluación CASE en SQL
            (or_(cls.fecha_inicio.is_(None), cls.fecha_inicio > hoy), "Espera"),
            (cls.fecha_termino > hoy,                                   "Ok"),
            else_="Finalizada",
        )

    @hybrid_property
    def estado_renovacion(self) -> str:
        """CSV row 41 — radar de renovación con umbral de 45 días.

        Requiere: selectinload(Poliza.registros_link)
                  .joinedload(CruceRegistrosXPolizas.registro).
        No expone expresión SQL — búsqueda del registro de renovación
        requiere subquery + JOIN que duplicaría la lógica de estado_poliza.
        """
        if not self.renovar or self.estado_seguro != EstadoSeguro.ok:
            return "No Renovar"

        dias_restantes = (
            (self.fecha_termino - date.today()).days
            if self.fecha_termino
            else 0
        )

        regs_renovacion = [
            link.registro
            for link in self.registros_link
            if link.registro and link.registro.tipo_registro == TipoRegistro.renovacion
        ]

        if not regs_renovacion:
            return "Ok" if dias_restantes > 45 else "Falta"

        # CSV: ANY([Registro Renovación][Estado Renovación])="Pendiente"
        if any(r.estado_renovacion == "Pendiente" for r in regs_renovacion):
            return "Pendiente"
        return "Ok"


# ─── Documento ────────────────────────────────────────────────────────────────

class Documento(AppSheetMixin, Base):
    __tablename__ = "documento"
    __table_args__ = {"schema": "gestion"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    # FKs según guía
    poliza_id:        Mapped[int]           = mapped_column(Integer, ForeignKey("gestion.poliza.id"), nullable=False, index=True)
    cotizacion_id:    Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("gestion.cotizacion.id"), index=True)
    grupo_cliente_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("grupos.grupo_cliente.id"), index=True)
    contratante_id:   Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("datos.rut.id"), index=True)
    producto_id:      Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("operaciones.producto.id"), index=True)
    partner_id:       Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("operaciones.partner.id"), index=True)

    tipo_documento:  Mapped[TipoDocumento] = mapped_column(Enum(TipoDocumento, schema="gestion"), nullable=False, default=TipoDocumento.poliza)
    fecha_emision:   Mapped[date]          = mapped_column(Date, nullable=False)
    fecha_inicio:    Mapped[date]          = mapped_column(Date, nullable=False)
    fecha_termino:   Mapped[date]          = mapped_column(Date, nullable=False)
    numero_documento: Mapped[Optional[str]] = mapped_column(String(50))
    n_cuotas:        Mapped[int]           = mapped_column(Integer, nullable=False, default=1)
    pct_comision_afecta: Mapped[Optional[float]] = mapped_column(Numeric(5, 2))
    pct_comision_exenta: Mapped[Optional[float]] = mapped_column(Numeric(5, 2))
    tipo_inspeccion: Mapped[Optional[str]] = mapped_column(String(50))
    n_inspeccion:    Mapped[Optional[str]] = mapped_column(String(50))
    pdf_url:         Mapped[Optional[str]] = mapped_column(String(500))
    otros_archivos:  Mapped[Optional[str]] = mapped_column(String(500))
    comision_flag:   Mapped[bool]          = mapped_column(Boolean, default=False, nullable=False)
    requiere_doc:    Mapped[bool]          = mapped_column(Boolean, default=False, nullable=False)
    invalidar_diferencia: Mapped[bool]     = mapped_column(Boolean, default=False, nullable=False)
    enviado:         Mapped[bool]          = mapped_column(Boolean, default=False, nullable=False)
    traspaso_info_1: Mapped[Optional[str]] = mapped_column(String(300))
    traspaso_info_2: Mapped[Optional[str]] = mapped_column(String(300))
    comentarios:     Mapped[Optional[str]] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    poliza:        Mapped["Poliza"]            = relationship("Poliza",       back_populates="documentos")
    grupo_cliente: Mapped[Optional["GrupoCliente"]] = relationship("GrupoCliente", back_populates="documentos", foreign_keys=[grupo_cliente_id])
    contratante:   Mapped[Optional["Rut"]]     = relationship("Rut",         foreign_keys=[contratante_id])
    producto:      Mapped[Optional["Producto"]] = relationship("Producto",   foreign_keys=[producto_id])
    partner:       Mapped[Optional["Partner"]] = relationship("Partner",     foreign_keys=[partner_id])

    materias:      Mapped[list["Materia"]]     = relationship("Materia",     back_populates="documento")
    plan_pago:     Mapped[Optional["PlanPago"]] = relationship("PlanPago",   back_populates="documento", uselist=False)
    cuotas:        Mapped[list["Cuota"]]       = relationship("Cuota",       back_populates="documento", foreign_keys="[Cuota.documento_id]")
    solicitudes:   Mapped[list["Solicitud"]]   = relationship("Solicitud",   back_populates="documento", foreign_keys="[Solicitud.documento_id]")
    comisiones_link: Mapped[list["CruceDocumentosXComision"]] = relationship("CruceDocumentosXComision", back_populates="documento")
    liquidaciones_link: Mapped[list["CruceDocumentosXLiquidacion"]] = relationship("CruceDocumentosXLiquidacion", back_populates="documento")
    com_documentos: Mapped[list["ComDocumento"]] = relationship("ComDocumento", back_populates="documento")

    # ── Propiedades calculadas ────────────────────────────────────────────────

    @hybrid_property
    def estado_documento(self) -> str:
        """Estado del documento: 'Pendiente' solo cuando requiere PDF y no está cargado.

        Requiere: joinedload(Documento.poliza).
        Para filtrado masivo de documentos pendientes usar DocumentoService.
        """
        if self.poliza is None:
            return "Ok"
        if self.poliza.estado_seguro == EstadoSeguro.nulo:
            return "Ok"
        if self.poliza.estado_poliza == "Pendiente":
            return "Ok"
        if self.requiere_doc and not self.pdf_url:
            return "Pendiente"
        return "Ok"


# ─── Materia ──────────────────────────────────────────────────────────────────

class Materia(AppSheetMixin, Base):
    """Ítem asegurado dentro de un documento de póliza."""
    __tablename__ = "materia"
    __table_args__ = {"schema": "gestion"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    # FKs según guía
    documento_id:     Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("gestion.documento.id"), index=True)
    base_materia_id:  Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("grupos.grupo_materia.id"), index=True)  # "Base Materia"
    seguro_id:        Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("operaciones.seguro.id"), index=True)
    asegurado_id:     Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("datos.rut.id"), index=True)
    contratante_id:   Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("datos.rut.id"), index=True)
    poliza_id:        Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("gestion.poliza.id"), index=True)
    grupo_cliente_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("grupos.grupo_cliente.id"), index=True)

    uso:          Mapped[Optional[str]]   = mapped_column(String(60))
    deducible:    Mapped[Optional[str]]   = mapped_column(String(200))
    item:         Mapped[Optional[int]]   = mapped_column(Integer)
    afecta_uf:    Mapped[Optional[float]] = mapped_column(Numeric(10, 4))
    exenta_uf:    Mapped[Optional[float]] = mapped_column(Numeric(10, 4))
    afecta_clp:   Mapped[Optional[float]] = mapped_column(Numeric(14, 2))
    exenta_clp:   Mapped[Optional[float]] = mapped_column(Numeric(14, 2))
    afecta_usd:   Mapped[Optional[float]] = mapped_column(Numeric(10, 2))
    exenta_usd:   Mapped[Optional[float]] = mapped_column(Numeric(10, 2))
    monto_asegurado: Mapped[Optional[float]] = mapped_column(Numeric(14, 2))
    tasa_afecta:  Mapped[Optional[float]] = mapped_column(Numeric(6, 4))
    tasa_exenta:  Mapped[Optional[float]] = mapped_column(Numeric(6, 4))
    fecha_exclusion: Mapped[Optional[date]] = mapped_column(Date)
    comentarios:  Mapped[Optional[str]]   = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    documento:     Mapped[Optional["Documento"]]  = relationship("Documento",   back_populates="materias")
    base_materia:  Mapped[Optional["GrupoMateria"]] = relationship("GrupoMateria", back_populates="materias_gestion")
    seguro:        Mapped[Optional["Seguro"]]     = relationship("Seguro",      foreign_keys=[seguro_id])
    asegurado:     Mapped[Optional["Rut"]]        = relationship("Rut",         foreign_keys=[asegurado_id])
    contratante:   Mapped[Optional["Rut"]]        = relationship("Rut",         foreign_keys=[contratante_id])
    poliza:        Mapped[Optional["Poliza"]]     = relationship("Poliza",      back_populates="materias", foreign_keys=[poliza_id])
    grupo_cliente: Mapped[Optional["GrupoCliente"]] = relationship("GrupoCliente", back_populates="materias", foreign_keys=[grupo_cliente_id])

    siniestros:    Mapped[list["Siniestro"]]      = relationship("Siniestro",   back_populates="materia")
    envios_link:   Mapped[list["CruceMateriasXEnvio"]] = relationship("CruceMateriasXEnvio", back_populates="materia")
    items_envio_link: Mapped[list["CruceItemsXEnvioCliente"]] = relationship("CruceItemsXEnvioCliente", back_populates="materia")


# ─── PlanPago ─────────────────────────────────────────────────────────────────

class PlanPago(AppSheetMixin, Base):
    __tablename__ = "plan_pago"
    __table_args__ = {"schema": "gestion"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    documento_id: Mapped[int]           = mapped_column(Integer, ForeignKey("gestion.documento.id"), nullable=False, unique=True, index=True)
    poliza_id:    Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("gestion.poliza.id"), index=True)

    n_plan_pago:    Mapped[Optional[str]]   = mapped_column(String(50))
    fecha_documento: Mapped[Optional[date]] = mapped_column(Date)
    n_cuotas:       Mapped[int]             = mapped_column(Integer, nullable=False, default=1)
    afecta_uf:      Mapped[Optional[float]] = mapped_column(Numeric(10, 4))
    exenta_uf:      Mapped[Optional[float]] = mapped_column(Numeric(10, 4))
    afecta_clp:     Mapped[Optional[float]] = mapped_column(Numeric(14, 2))
    exenta_clp:     Mapped[Optional[float]] = mapped_column(Numeric(14, 2))
    afecta_usd:     Mapped[Optional[float]] = mapped_column(Numeric(10, 2))
    exenta_usd:     Mapped[Optional[float]] = mapped_column(Numeric(10, 2))
    valor_cuota:    Mapped[Optional[float]] = mapped_column(Numeric(14, 2))
    n_cuota_distinta: Mapped[Optional[int]] = mapped_column(Integer)
    valor_cuota_distinta: Mapped[Optional[float]] = mapped_column(Numeric(14, 2))
    vcto_cuota_0:   Mapped[Optional[date]]  = mapped_column(Date)
    vcto_cuota_1:   Mapped[Optional[date]]  = mapped_column(Date)
    pdf_url:        Mapped[Optional[str]]   = mapped_column(String(500))
    activo:         Mapped[bool]            = mapped_column(Boolean, default=True, nullable=False)
    firmado:        Mapped[bool]            = mapped_column(Boolean, default=False, nullable=False)
    enviado:        Mapped[bool]            = mapped_column(Boolean, default=False, nullable=False)
    recibo_envio:   Mapped[Optional[str]]   = mapped_column(String(200))
    cargado_cuota:  Mapped[bool]            = mapped_column(Boolean, default=False, nullable=False)
    comentarios:    Mapped[Optional[str]]   = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    documento: Mapped["Documento"]     = relationship("Documento",  back_populates="plan_pago")
    poliza:    Mapped[Optional["Poliza"]] = relationship("Poliza",  back_populates="planes_pago")
    cuotas:    Mapped[list["Cuota"]]   = relationship("Cuota",      back_populates="plan_pago", foreign_keys="[Cuota.plan_pago_id]")
    com_planes_pago: Mapped[list["ComPlanPago"]] = relationship("ComPlanPago", back_populates="plan_pago")

    # ── Propiedades calculadas ────────────────────────────────────────────────

    @hybrid_property
    def estado_plan_de_pago(self) -> str:
        """Estado del plan de pago derivado de su póliza y conteo de cuotas.

        Requiere: joinedload(PlanPago.poliza) + selectinload(PlanPago.cuotas).
        No expone expresión SQL — usar PolizaService para filtrado masivo.
        """
        if self.poliza is None:
            return "Pendiente"
        estado_pol = self.poliza.estado_poliza
        if estado_pol == "Pendiente":
            return "Pendiente"
        if not self.activo:
            return "Inactivo"
        if len(self.cuotas) != self.n_cuotas:
            return "Verificar Cuotas"
        if estado_pol in {"Ok", "Recotizar"}:
            return "Ok"
        return estado_pol


# ─── Cuota ────────────────────────────────────────────────────────────────────

class Cuota(AppSheetMixin, Base):
    __tablename__ = "cuota"
    __table_args__ = {"schema": "gestion"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    # FKs según guía
    plan_pago_id:     Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("gestion.plan_pago.id"), index=True)
    documento_id:     Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("gestion.documento.id"), index=True)
    poliza_id:        Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("gestion.poliza.id"), index=True)
    compania_id:      Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("operaciones.compania.id"), index=True)
    seguro_id:        Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("operaciones.seguro.id"), index=True)
    grupo_cliente_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("grupos.grupo_cliente.id"), index=True)
    contratante_id:   Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("datos.rut.id"), index=True)

    control_pago:   Mapped[Optional[str]]   = mapped_column(String(30))
    numero_cuota:   Mapped[int]             = mapped_column(Integer, nullable=False)
    estado:         Mapped[EstadoCuota]     = mapped_column(Enum(EstadoCuota, schema="gestion"), nullable=False, default=EstadoCuota.pendiente)
    vencimiento:    Mapped[date]            = mapped_column(Date, nullable=False)
    valor_uf:       Mapped[Optional[float]] = mapped_column(Numeric(10, 4))
    valor_clp:      Mapped[Optional[float]] = mapped_column(Numeric(14, 2))
    valor_usd:      Mapped[Optional[float]] = mapped_column(Numeric(10, 2))
    fecha_pago:     Mapped[Optional[date]]  = mapped_column(Date)
    monto_pago:     Mapped[Optional[float]] = mapped_column(Numeric(14, 2))
    n_ingreso:      Mapped[Optional[str]]   = mapped_column(String(50))
    pago:           Mapped[Optional[str]]   = mapped_column(String(500))
    recibo:         Mapped[Optional[str]]   = mapped_column(String(200))
    factura:        Mapped[Optional[str]]   = mapped_column(String(200))
    cursado:        Mapped[bool]            = mapped_column(Boolean, default=False, nullable=False)
    fa_enviada:     Mapped[bool]            = mapped_column(Boolean, default=False, nullable=False)
    cobrada:        Mapped[bool]            = mapped_column(Boolean, default=False, nullable=False)
    cobro_automatico: Mapped[bool]          = mapped_column(Boolean, default=False, nullable=False)
    cobrar:         Mapped[bool]            = mapped_column(Boolean, default=False, nullable=False)
    comentarios:    Mapped[Optional[str]]   = mapped_column(Text)

    # Aliases (backward compat)
    monto_clp: Mapped[Optional[float]] = mapped_column(Numeric(14, 2))
    monto_uf:  Mapped[Optional[float]] = mapped_column(Numeric(10, 4))
    monto_usd: Mapped[Optional[float]] = mapped_column(Numeric(10, 2))
    fecha_vencimiento: Mapped[Optional[date]] = mapped_column(Date)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    plan_pago:     Mapped[Optional["PlanPago"]]    = relationship("PlanPago",    back_populates="cuotas", foreign_keys=[plan_pago_id])
    documento:     Mapped[Optional["Documento"]]   = relationship("Documento",   back_populates="cuotas", foreign_keys=[documento_id])
    poliza:        Mapped[Optional["Poliza"]]      = relationship("Poliza",      back_populates="cuotas")
    compania:      Mapped[Optional["Compania"]]    = relationship("Compania",    foreign_keys=[compania_id])
    seguro:        Mapped[Optional["Seguro"]]      = relationship("Seguro",      foreign_keys=[seguro_id])
    grupo_cliente: Mapped[Optional["GrupoCliente"]] = relationship("GrupoCliente", back_populates="cuotas", foreign_keys=[grupo_cliente_id])
    contratante:   Mapped[Optional["Rut"]]         = relationship("Rut",         foreign_keys=[contratante_id])
    cobranzas_link: Mapped[list["CruceCuotasXCobranza"]] = relationship("CruceCuotasXCobranza", back_populates="cuota")

    # ── Propiedades calculadas ────────────────────────────────────────────────

    @hybrid_property
    def estado_cuota(self) -> str:
        """Estado operativo de la cuota (Option A: vencimiento siempre presente).

        Requiere: joinedload(Cuota.plan_pago).joinedload(PlanPago.poliza)
                  + selectinload(PlanPago.cuotas).
        No expone expresión SQL — la cadena plan→poliza hace inviable el CASE.
        """
        if self.plan_pago is None:
            return "Cargar"
        estado_plan = self.plan_pago.estado_plan_de_pago
        if estado_plan == "Inactivo":
            return "Ok"
        if self.control_pago:
            return "Pagada"
        poliza = self.plan_pago.poliza
        estado_pol = poliza.estado_poliza if poliza else "Pendiente"
        if estado_pol == "Ok":
            hoy = date.today()
            if (self.vencimiento.year < hoy.year or
                    (self.vencimiento.year == hoy.year and
                     self.vencimiento.month <= hoy.month)):
                return "Pendiente"
            return "Vigente"
        return estado_pol

    @hybrid_property
    def estado_gestion_cuota(self) -> str:
        """Gestión operativa de la cuota — derivada de estado_cuota."""
        ec = self.estado_cuota
        if ec == "Pagada":
            return "Ok" if (self.control_pago != "Transferencia" or self.cursado) else "Pendiente"
        if ec == "Vigente":
            return "Ok"
        poliza = self.plan_pago.poliza if self.plan_pago else None
        estado_pol = poliza.estado_poliza if poliza else "Pendiente"
        return "Pendiente" if estado_pol == "Ok" else "Ok"


# ─── Cobranza ─────────────────────────────────────────────────────────────────

class Cobranza(AppSheetMixin, Base):
    __tablename__ = "cobranza"
    __table_args__ = {"schema": "gestion"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    destinatario_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("grupos.grupo_cliente.id"), index=True)

    fecha_registro: Mapped[Optional[date]]   = mapped_column(Date)
    monto_nominal:  Mapped[Optional[float]]  = mapped_column(Numeric(14, 2))
    cobrado:        Mapped[Optional[float]]  = mapped_column(Numeric(14, 2))
    pagado:         Mapped[Optional[float]]  = mapped_column(Numeric(14, 2))
    diferencia:     Mapped[Optional[float]]  = mapped_column(Numeric(14, 2))
    c_uf_cobro:     Mapped[Optional[float]]  = mapped_column(Numeric(10, 4))
    c_uf_pago:      Mapped[Optional[float]]  = mapped_column(Numeric(10, 4))
    c_usd_cobro:    Mapped[Optional[float]]  = mapped_column(Numeric(10, 2))
    c_usd_pago:     Mapped[Optional[float]]  = mapped_column(Numeric(10, 2))
    comentarios:    Mapped[Optional[str]]    = mapped_column(Text)
    verificador_accion: Mapped[Optional[str]] = mapped_column(String(200))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    destinatario: Mapped[Optional["GrupoCliente"]] = relationship("GrupoCliente", back_populates="cobranzas", foreign_keys=[destinatario_id])
    cuotas_link:  Mapped[list["CruceCuotasXCobranza"]] = relationship("CruceCuotasXCobranza", back_populates="cobranza")
    com_cobranzas: Mapped[list["ComCobranza"]] = relationship("ComCobranza", back_populates="cobranza")


# ─── Solicitud ────────────────────────────────────────────────────────────────

class Solicitud(AppSheetMixin, Base):
    __tablename__ = "solicitud"
    __table_args__ = {"schema": "gestion"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    documento_id:     Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("gestion.documento.id"), index=True)
    poliza_id:        Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("gestion.poliza.id"), index=True)
    ramo_id:          Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("operaciones.ramo.id"), index=True)
    compania_id:      Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("operaciones.compania.id"), index=True)
    ejecutivo_id:     Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("operaciones.ejecutivo.id"), index=True)
    producto_id:      Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("operaciones.producto.id"), index=True)
    cotizacion_id:    Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("gestion.cotizacion.id"), index=True)
    grupo_cliente_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("grupos.grupo_cliente.id"), index=True)
    contratante_id:   Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("datos.rut.id"), index=True)

    tipo:         Mapped[Optional[str]]  = mapped_column(String(60))
    movimiento:   Mapped[Optional[str]]  = mapped_column(String(60))
    fecha_emision: Mapped[Optional[date]] = mapped_column(Date)
    glosa:        Mapped[Optional[str]]  = mapped_column(String(300))
    item:         Mapped[Optional[int]]  = mapped_column(Integer)
    recibo:       Mapped[Optional[str]]  = mapped_column(String(200))
    n_endoso:     Mapped[Optional[str]]  = mapped_column(String(50))
    pdf_folio:    Mapped[Optional[str]]  = mapped_column(String(500))
    pdf_endoso:   Mapped[Optional[str]]  = mapped_column(String(500))
    pdf_recibo:   Mapped[Optional[str]]  = mapped_column(String(500))
    impresion_pdf: Mapped[Optional[str]] = mapped_column(String(500))
    condiciones:  Mapped[Optional[str]]  = mapped_column(Text)
    finalizada:   Mapped[bool]           = mapped_column(Boolean, default=False, nullable=False)
    comentarios:  Mapped[Optional[str]]  = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    documento:     Mapped[Optional["Documento"]]  = relationship("Documento",   back_populates="solicitudes", foreign_keys=[documento_id])
    poliza:        Mapped[Optional["Poliza"]]     = relationship("Poliza",      back_populates="solicitudes", foreign_keys=[poliza_id])
    ramo:          Mapped[Optional["Ramo"]]       = relationship("Ramo",        foreign_keys=[ramo_id])
    compania:      Mapped[Optional["Compania"]]   = relationship("Compania",    foreign_keys=[compania_id])
    ejecutivo:     Mapped[Optional["Ejecutivo"]]  = relationship("Ejecutivo",   foreign_keys=[ejecutivo_id])
    producto:      Mapped[Optional["Producto"]]   = relationship("Producto",    foreign_keys=[producto_id])
    cotizacion:    Mapped[Optional["Cotizacion"]] = relationship("Cotizacion",  back_populates="solicitudes", foreign_keys=[cotizacion_id])
    grupo_cliente: Mapped[Optional["GrupoCliente"]] = relationship("GrupoCliente", back_populates="solicitudes", foreign_keys=[grupo_cliente_id])
    contratante:   Mapped[Optional["Rut"]]        = relationship("Rut",         foreign_keys=[contratante_id])

    # ── Propiedades calculadas ────────────────────────────────────────────────

    @property
    def estado_solicitud(self) -> str:
        """Estado operativo de la solicitud según documentos y finalización."""
        if not self.pdf_folio:  return "Falta Folio"
        if not self.recibo:     return "Falta Recibo"
        if not self.finalizada: return "Pendiente"
        return "Ok"

    @property
    def estado_gestion(self) -> str:
        """Simplifica estado_solicitud a Ok/Pendiente para uso en tablas."""
        return "Ok" if self.estado_solicitud == "Ok" else "Pendiente"


# ─── Siniestro ────────────────────────────────────────────────────────────────

class Siniestro(AppSheetMixin, Base):
    __tablename__ = "siniestro"
    __table_args__ = {"schema": "gestion"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    materia_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("gestion.materia.id"), index=True)
    poliza_id:  Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("gestion.poliza.id"), index=True)

    estado_siniestro: Mapped[Optional[EstadoSiniestro]] = mapped_column(Enum(EstadoSiniestro, schema="gestion"))
    fecha_denuncia:   Mapped[Optional[date]]            = mapped_column(Date)
    fecha_siniestro:  Mapped[Optional[date]] = mapped_column(Date)
    n_siniestro:      Mapped[Optional[str]] = mapped_column(String(50))
    n_ref_liquidadora: Mapped[Optional[str]] = mapped_column(String(50))
    resolucion:       Mapped[Optional[str]] = mapped_column(String(300))
    monto:            Mapped[Optional[float]] = mapped_column(Numeric(14, 2))
    pago:             Mapped[Optional[str]] = mapped_column(String(50))
    respaldo:         Mapped[Optional[str]] = mapped_column(String(500))
    denuncia:         Mapped[Optional[str]] = mapped_column(String(500))
    carpeta:          Mapped[Optional[str]] = mapped_column(String(500))
    comentarios:      Mapped[Optional[str]] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    materia: Mapped[Optional["Materia"]] = relationship("Materia", back_populates="siniestros")
    poliza:  Mapped[Optional["Poliza"]]  = relationship("Poliza",  back_populates="siniestros")


# ─── Comision ─────────────────────────────────────────────────────────────────

class Comision(AppSheetMixin, Base):
    """Liquidación de comisiones emitidas por compañías."""
    __tablename__ = "comision"
    __table_args__ = {"schema": "gestion"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    compania_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("operaciones.compania.id"), index=True)

    tipo:               Mapped[Optional[str]]   = mapped_column(String(50))
    movimiento:         Mapped[Optional[str]]   = mapped_column(String(50))
    cantidad_documentos: Mapped[Optional[int]]  = mapped_column(Integer)
    fecha_liquidacion:  Mapped[Optional[date]]  = mapped_column(Date)
    n_liquidacion:      Mapped[Optional[str]]   = mapped_column(String(50))
    facturacion:        Mapped[Optional[str]]   = mapped_column(String(200))
    monto_afecto:       Mapped[Optional[float]] = mapped_column(Numeric(14, 2))
    monto_exento:       Mapped[Optional[float]] = mapped_column(Numeric(14, 2))
    liquidacion_pdf:    Mapped[Optional[str]]   = mapped_column(String(500))
    detalle:            Mapped[Optional[str]]   = mapped_column(Text)
    comentarios:        Mapped[Optional[str]]   = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    compania: Mapped[Optional["Compania"]] = relationship("Compania", foreign_keys=[compania_id])
    documentos_link: Mapped[list["CruceDocumentosXComision"]] = relationship("CruceDocumentosXComision", back_populates="comision")
    facturas_link:   Mapped[list["CruceFacturasXComision"]]   = relationship("CruceFacturasXComision",   back_populates="comision")
    com_comisiones:  Mapped[list["ComComision"]]              = relationship("ComComision",              back_populates="comision")

    # ── Propiedades calculadas ────────────────────────────────────────────────

    @property
    def n_facturas(self) -> int:
        """CSV Grupo A — 2 si facturación es Separada, 1 en cualquier otro caso."""
        return 2 if self.facturacion == "Separada" else 1

    @hybrid_property
    def estado_comision(self) -> str:
        """CSV row 14 — estado operativo de la liquidación de comisión.

        Requiere: selectinload(Comision.documentos_link)
                  + selectinload(Comision.facturas_link).
        """
        if self.movimiento == "Saldo":
            return "Ok"
        n_docs_cargados = len(self.documentos_link)
        if self.cantidad_documentos is not None and self.cantidad_documentos != n_docs_cargados:
            return "Diferencia Docs"
        if len(self.facturas_link) < self.n_facturas:
            return "Facturar"
        return "Ok"


# ─── Tablas puente de gestión ─────────────────────────────────────────────────

class CruceRegistrosXPolizas(AppSheetMixin, Base):
    __tablename__ = "registros_x_polizas"
    __table_args__ = {"schema": "cruce_tablas"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    registro_id:  Mapped[int] = mapped_column(Integer, ForeignKey("gestion.registro.id"), nullable=False, index=True)
    poliza_id:    Mapped[int] = mapped_column(Integer, ForeignKey("gestion.poliza.id"), nullable=False, index=True)
    cotizacion_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("gestion.cotizacion.id"), index=True)

    registro:    Mapped["Registro"]    = relationship("Registro",    back_populates="polizas_link")
    poliza:      Mapped["Poliza"]      = relationship("Poliza",      back_populates="registros_link")
    cotizacion:  Mapped[Optional["Cotizacion"]] = relationship("Cotizacion", back_populates="polizas_link")


class CruceRecotizacionesXPoliza(AppSheetMixin, Base):
    __tablename__ = "recotizaciones_x_poliza"
    __table_args__ = {"schema": "cruce_tablas"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    poliza_id:    Mapped[int] = mapped_column(Integer, ForeignKey("gestion.poliza.id"), nullable=False, index=True)
    cotizacion_id: Mapped[int] = mapped_column(Integer, ForeignKey("gestion.cotizacion.id"), nullable=False, index=True)
    comentarios:  Mapped[Optional[str]] = mapped_column(Text)

    poliza:    Mapped["Poliza"]    = relationship("Poliza",    back_populates="recotizaciones")
    cotizacion: Mapped["Cotizacion"] = relationship("Cotizacion", back_populates="recotizaciones")


class CruceDocumentosXComision(AppSheetMixin, Base):
    __tablename__ = "documentos_x_comision"
    __table_args__ = {"schema": "cruce_tablas"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    comision_id:  Mapped[int] = mapped_column(Integer, ForeignKey("gestion.comision.id"), nullable=False, index=True)
    documento_id: Mapped[int] = mapped_column(Integer, ForeignKey("gestion.documento.id"), nullable=False, index=True)
    tipo:         Mapped[Optional[str]] = mapped_column(String(50))
    afecto_uf:    Mapped[Optional[float]] = mapped_column(Numeric(10, 4))
    exento_uf:    Mapped[Optional[float]] = mapped_column(Numeric(10, 4))
    cambio_uf:    Mapped[Optional[float]] = mapped_column(Numeric(10, 4))
    afecto_clp:   Mapped[Optional[float]] = mapped_column(Numeric(14, 2))
    exento_clp:   Mapped[Optional[float]] = mapped_column(Numeric(14, 2))
    afecto_usd:   Mapped[Optional[float]] = mapped_column(Numeric(10, 2))
    exento_usd:   Mapped[Optional[float]] = mapped_column(Numeric(10, 2))
    cambio_usd:   Mapped[Optional[float]] = mapped_column(Numeric(10, 2))

    comision:  Mapped["Comision"]  = relationship("Comision",  back_populates="documentos_link")
    documento: Mapped["Documento"] = relationship("Documento", back_populates="comisiones_link")


class CruceDocumentosXLiquidacion(AppSheetMixin, Base):
    __tablename__ = "documentos_x_liquidacion"
    __table_args__ = {"schema": "cruce_tablas"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    liquidacion_id: Mapped[int] = mapped_column(Integer, ForeignKey("contabilidad.liquidacion.id"), nullable=False, index=True)
    documento_id:   Mapped[int] = mapped_column(Integer, ForeignKey("gestion.documento.id"), nullable=False, index=True)

    liquidacion: Mapped["Liquidacion"] = relationship("Liquidacion", back_populates="documentos_link")
    documento:   Mapped["Documento"]  = relationship("Documento",   back_populates="liquidaciones_link")


class CruceCuotasXCobranza(AppSheetMixin, Base):
    __tablename__ = "cuotas_x_cobranza"
    __table_args__ = {"schema": "cruce_tablas"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    cobranza_id:      Mapped[int] = mapped_column(Integer, ForeignKey("gestion.cobranza.id"), nullable=False, index=True)
    cuota_id:         Mapped[int] = mapped_column(Integer, ForeignKey("gestion.cuota.id"), nullable=False, index=True)
    grupo_cliente_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("grupos.grupo_cliente.id"), index=True)

    cobranza: Mapped["Cobranza"] = relationship("Cobranza", back_populates="cuotas_link")
    cuota:    Mapped["Cuota"]    = relationship("Cuota",    back_populates="cobranzas_link")


class CruceFacturasXComision(AppSheetMixin, Base):
    __tablename__ = "facturas_x_comision"
    __table_args__ = {"schema": "cruce_tablas"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    comision_id: Mapped[int] = mapped_column(Integer, ForeignKey("gestion.comision.id"), nullable=False, index=True)
    contable_id: Mapped[int] = mapped_column(Integer, ForeignKey("contabilidad.contable.id"), nullable=False, index=True)

    comision: Mapped["Comision"]  = relationship("Comision",  back_populates="facturas_link")
    contable: Mapped["Contable"]  = relationship("Contable",  back_populates="comisiones_link")


class CruceMateriasXEnvio(AppSheetMixin, Base):
    __tablename__ = "materias_x_envio"
    __table_args__ = {"schema": "cruce_tablas"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    com_materias_id: Mapped[int] = mapped_column(Integer, ForeignKey("comunicacion.com_materia.id"), nullable=False, index=True)
    materia_id:      Mapped[int] = mapped_column(Integer, ForeignKey("gestion.materia.id"), nullable=False, index=True)

    com_materia: Mapped["ComMateria"] = relationship("ComMateria", back_populates="materias_link")
    materia:     Mapped["Materia"]    = relationship("Materia",    back_populates="envios_link")


class CruceItemsXEnvioCliente(AppSheetMixin, Base):
    __tablename__ = "items_x_envio_cliente"
    __table_args__ = {"schema": "cruce_tablas"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    com_cliente_id: Mapped[int]          = mapped_column(Integer, ForeignKey("comunicacion.com_cliente.id"), nullable=False, index=True)
    registro_id:    Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("gestion.registro.id"), index=True)
    poliza_id:      Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("gestion.poliza.id"), index=True)
    materia_id:     Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("gestion.materia.id"), index=True)

    com_cliente: Mapped["ComCliente"]      = relationship("ComCliente", back_populates="items_link")
    registro:    Mapped[Optional["Registro"]] = relationship("Registro", foreign_keys=[registro_id])
    poliza:      Mapped[Optional["Poliza"]]   = relationship("Poliza",   foreign_keys=[poliza_id])
    materia:     Mapped[Optional["Materia"]]  = relationship("Materia",  back_populates="items_envio_link", foreign_keys=[materia_id])
