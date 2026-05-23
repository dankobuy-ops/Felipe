from datetime import date, datetime
from typing import Optional
from pydantic import BaseModel
from app.models.gestion import EstadoPoliza, EstadoSeguro, FormaPago, Moneda


class PolizaCreate(BaseModel):
    cliente_id: int
    producto_id: Optional[int] = None
    contratante_id: Optional[int] = None
    pagador_id: Optional[int] = None
    numero_poliza: Optional[str] = None
    fecha_emision: Optional[date] = None
    fecha_inicio: Optional[date] = None
    fecha_termino: Optional[date] = None
    moneda: Optional[Moneda] = None
    forma_pago: Optional[FormaPago] = None
    n_cuotas: Optional[int] = 1
    pct_comision_afecta: Optional[float] = None
    pct_comision_exenta: Optional[float] = None
    # Legacy
    compania_id: Optional[int] = None
    ramo_id: Optional[int] = None
    prima_neta: Optional[float] = None
    prima_total: Optional[float] = None
    suma_asegurada: Optional[float] = None
    numero_cuotas: Optional[int] = None
    porcentaje_comision: Optional[float] = None
    cotizacion_id: Optional[int] = None
    poliza_anterior_id: Optional[int] = None
    comentarios: Optional[str] = None


class PolizaUpdate(BaseModel):
    estado: Optional[EstadoPoliza] = None
    estado_seguro: Optional[EstadoSeguro] = None
    numero_poliza: Optional[str] = None
    fecha_emision: Optional[date] = None
    fecha_inicio: Optional[date] = None
    fecha_termino: Optional[date] = None
    forma_pago: Optional[FormaPago] = None
    n_cuotas: Optional[int] = None
    prima_neta: Optional[float] = None
    prima_total: Optional[float] = None
    pct_comision_afecta: Optional[float] = None
    pct_comision_exenta: Optional[float] = None
    mandato: Optional[bool] = None
    renovar: Optional[bool] = None
    pago_activo: Optional[bool] = None
    recotizar: Optional[bool] = None
    activa: Optional[bool] = None
    fecha_cancelacion: Optional[date] = None
    comentarios: Optional[str] = None


class DocumentoResumen(BaseModel):
    id: int
    tipo_documento: str
    fecha_emision: date
    fecha_inicio: date
    fecha_termino: date
    numero_documento: Optional[str] = None
    n_cuotas: int
    enviado: bool

    model_config = {"from_attributes": True}


class CuotaResumen(BaseModel):
    id: int
    numero_cuota: int
    estado: str
    monto_clp: Optional[float] = None
    monto_uf: Optional[float] = None
    fecha_vencimiento: date
    fecha_pago: Optional[date] = None

    model_config = {"from_attributes": True}


class PolizaOut(BaseModel):
    id: int
    cliente_id: int
    producto_id: Optional[int] = None
    contratante_id: Optional[int] = None
    pagador_id: Optional[int] = None
    estado_seguro: EstadoSeguro
    estado: EstadoPoliza
    numero_poliza: Optional[str] = None
    fecha_emision: Optional[date] = None
    fecha_inicio: Optional[date] = None
    fecha_termino: Optional[date] = None
    moneda: Optional[Moneda] = None
    forma_pago: Optional[FormaPago] = None
    n_cuotas: Optional[int] = None
    pct_comision_afecta: Optional[float] = None
    pct_comision_exenta: Optional[float] = None
    mandato: bool
    comision_flag: bool
    renovar: bool
    pago_activo: bool
    recotizar: bool
    activa: bool
    fecha_cancelacion: Optional[date] = None
    comentarios: Optional[str] = None
    # Legacy
    compania_id: Optional[int] = None
    ramo_id: Optional[int] = None
    prima_neta: Optional[float] = None
    prima_total: Optional[float] = None
    suma_asegurada: Optional[float] = None
    numero_cuotas: Optional[int] = None
    porcentaje_comision: Optional[float] = None
    monto_comision: Optional[float] = None
    cotizacion_id: Optional[int] = None
    poliza_anterior_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    documentos: list[DocumentoResumen] = []
    cuotas: list[CuotaResumen] = []

    model_config = {"from_attributes": True}
