"""
Esquema: configuracion
Usuarios, parámetros globales, valores UF/USD.
"""
from datetime import date, datetime
from typing import Optional
from sqlalchemy import String, Integer, Date, DateTime, Boolean, Numeric, Text, Enum
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
import enum

from app.database import Base


class RolUsuario(str, enum.Enum):
    admin      = "admin"
    ejecutivo  = "ejecutivo"
    supervisor = "supervisor"
    readonly   = "readonly"


class Usuario(Base):
    __tablename__ = "usuario"
    __table_args__ = {"schema": "configuracion"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    nombre: Mapped[str] = mapped_column(String(100), nullable=False)
    email: Mapped[str] = mapped_column(String(150), unique=True, nullable=False, index=True)
    hashed_password: Mapped[str] = mapped_column(String(200), nullable=False)
    rol: Mapped[RolUsuario] = mapped_column(
        Enum(RolUsuario, schema="configuracion"), nullable=False, default=RolUsuario.ejecutivo
    )
    activo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    def __repr__(self) -> str:
        return f"<Usuario {self.email} rol={self.rol}>"


class ValorUF(Base):
    """Valor diario de la UF para cálculos históricos."""
    __tablename__ = "valor_uf"
    __table_args__ = {"schema": "configuracion"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    fecha: Mapped[date] = mapped_column(Date, unique=True, nullable=False, index=True)
    valor: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self) -> str:
        return f"<ValorUF {self.fecha} = {self.valor}>"


class Parametro(Base):
    """Parámetros de configuración clave-valor."""
    __tablename__ = "parametro"
    __table_args__ = {"schema": "configuracion"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    clave: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    valor: Mapped[str] = mapped_column(Text, nullable=False)
    descripcion: Mapped[Optional[str]] = mapped_column(String(300))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    def __repr__(self) -> str:
        return f"<Parametro {self.clave}>"
