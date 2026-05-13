from datetime import date, datetime
from typing import Optional
from pydantic import BaseModel
from app.models.gestion import EstadoPoliza, FormaPago


class PolizaBase(BaseModel):
    numero_poliza: str
    cliente_id: int
    compania_id: Optional[int] = None
    ramo_id: Optional[int] = None
    fecha_emision: date
    fecha_inicio: date
    fecha_termino: date
    prima_neta: float
    prima_total: float
    suma_asegurada: Optional[float] = None
    forma_pago: FormaPago = FormaPago.anual
    numero_cuotas: int = 1
    porcentaje_comision: Optional[float] = None
    observaciones: Optional[str] = None


class PolizaCreate(PolizaBase):
    cotizacion_id: Optional[int] = None
    poliza_anterior_id: Optional[int] = None


class PolizaUpdate(BaseModel):
    estado: Optional[EstadoPoliza] = None
    fecha_termino: Optional[date] = None
    prima_total: Optional[float] = None
    observaciones: Optional[str] = None
    activa: Optional[bool] = None


class PolizaOut(PolizaBase):
    id: int
    estado: EstadoPoliza
    cotizacion_id: Optional[int]
    poliza_anterior_id: Optional[int]
    monto_comision: Optional[float]
    activa: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
