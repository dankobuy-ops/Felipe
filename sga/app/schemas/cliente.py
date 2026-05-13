from datetime import date, datetime
from typing import Optional
from pydantic import BaseModel, EmailStr
from app.models.datos import TipoPersona


class ClienteBase(BaseModel):
    rut: str
    tipo_persona: TipoPersona = TipoPersona.natural
    nombre: Optional[str] = None
    apellido_paterno: Optional[str] = None
    apellido_materno: Optional[str] = None
    razon_social: Optional[str] = None
    fecha_nacimiento: Optional[date] = None
    email: Optional[str] = None
    telefono: Optional[str] = None
    direccion: Optional[str] = None
    numero: Optional[str] = None
    depto: Optional[str] = None
    comuna: Optional[str] = None
    ciudad: Optional[str] = None
    region: Optional[str] = None
    observaciones: Optional[str] = None


class ClienteCreate(ClienteBase):
    pass


class ClienteUpdate(BaseModel):
    nombre: Optional[str] = None
    apellido_paterno: Optional[str] = None
    apellido_materno: Optional[str] = None
    razon_social: Optional[str] = None
    email: Optional[str] = None
    telefono: Optional[str] = None
    direccion: Optional[str] = None
    comuna: Optional[str] = None
    ciudad: Optional[str] = None
    region: Optional[str] = None
    observaciones: Optional[str] = None
    activo: Optional[bool] = None


class ClienteOut(ClienteBase):
    id: int
    activo: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
