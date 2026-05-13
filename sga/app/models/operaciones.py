"""
Esquema: operaciones
Catálogo de ramos, compañías, productos y parametrización de comisiones.
"""
from datetime import datetime
from typing import Optional
from sqlalchemy import String, Integer, DateTime, Boolean, Numeric, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.database import Base


class Ramo(Base):
    __tablename__ = "ramo"
    __table_args__ = {"schema": "operaciones"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    codigo: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    nombre: Mapped[str] = mapped_column(String(100), nullable=False)
    descripcion: Mapped[Optional[str]] = mapped_column(Text)
    activo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self) -> str:
        return f"<Ramo {self.codigo} {self.nombre}>"


class Compania(Base):
    __tablename__ = "compania"
    __table_args__ = {"schema": "operaciones"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    nombre: Mapped[str] = mapped_column(String(150), nullable=False)
    nombre_corto: Mapped[Optional[str]] = mapped_column(String(50))
    rut: Mapped[Optional[str]] = mapped_column(String(12))
    email_siniestros: Mapped[Optional[str]] = mapped_column(String(150))
    email_emision: Mapped[Optional[str]] = mapped_column(String(150))
    telefono: Mapped[Optional[str]] = mapped_column(String(20))
    web: Mapped[Optional[str]] = mapped_column(String(200))
    codigo_cmc: Mapped[Optional[str]] = mapped_column(String(20))
    activa: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self) -> str:
        return f"<Compania {self.nombre_corto or self.nombre}>"


class Producto(Base):
    """Producto específico: combinación compañía + ramo + condiciones."""
    __tablename__ = "producto"
    __table_args__ = {"schema": "operaciones"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    nombre: Mapped[str] = mapped_column(String(200), nullable=False)
    compania_id: Mapped[int] = mapped_column(Integer, nullable=False)
    ramo_id: Mapped[int] = mapped_column(Integer, nullable=False)
    comision_base: Mapped[Optional[float]] = mapped_column(Numeric(5, 2))
    activo: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self) -> str:
        return f"<Producto {self.nombre}>"
