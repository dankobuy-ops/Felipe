from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_
from typing import Optional

from app.database import get_db
from app.models.datos import Cliente
from app.schemas.cliente import ClienteCreate, ClienteUpdate, ClienteOut

router = APIRouter(prefix="/clientes", tags=["Clientes"])


@router.get("/", response_model=list[ClienteOut])
def listar_clientes(
    skip: int = 0,
    limit: int = Query(default=50, le=200),
    buscar: Optional[str] = None,
    activo: Optional[bool] = True,
    db: Session = Depends(get_db),
):
    q = db.query(Cliente)
    if activo is not None:
        q = q.filter(Cliente.activo == activo)
    if buscar:
        term = f"%{buscar}%"
        q = q.filter(or_(
            Cliente.rut.ilike(term),
            Cliente.nombre.ilike(term),
            Cliente.apellido_paterno.ilike(term),
            Cliente.razon_social.ilike(term),
            Cliente.email.ilike(term),
        ))
    return q.offset(skip).limit(limit).all()


@router.post("/", response_model=ClienteOut, status_code=status.HTTP_201_CREATED)
def crear_cliente(data: ClienteCreate, db: Session = Depends(get_db)):
    if db.query(Cliente).filter(Cliente.rut == data.rut).first():
        raise HTTPException(status_code=400, detail=f"RUT {data.rut} ya registrado.")
    cliente = Cliente(**data.model_dump())
    db.add(cliente)
    db.commit()
    db.refresh(cliente)
    return cliente


@router.get("/{cliente_id}", response_model=ClienteOut)
def obtener_cliente(cliente_id: int, db: Session = Depends(get_db)):
    cliente = db.query(Cliente).filter(Cliente.id == cliente_id).first()
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente no encontrado.")
    return cliente


@router.get("/rut/{rut}", response_model=ClienteOut)
def obtener_cliente_por_rut(rut: str, db: Session = Depends(get_db)):
    cliente = db.query(Cliente).filter(Cliente.rut == rut).first()
    if not cliente:
        raise HTTPException(status_code=404, detail=f"RUT {rut} no encontrado.")
    return cliente


@router.patch("/{cliente_id}", response_model=ClienteOut)
def actualizar_cliente(cliente_id: int, data: ClienteUpdate, db: Session = Depends(get_db)):
    cliente = db.query(Cliente).filter(Cliente.id == cliente_id).first()
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente no encontrado.")
    for campo, valor in data.model_dump(exclude_unset=True).items():
        setattr(cliente, campo, valor)
    db.commit()
    db.refresh(cliente)
    return cliente


@router.delete("/{cliente_id}", status_code=status.HTTP_204_NO_CONTENT)
def desactivar_cliente(cliente_id: int, db: Session = Depends(get_db)):
    cliente = db.query(Cliente).filter(Cliente.id == cliente_id).first()
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente no encontrado.")
    cliente.activo = False
    db.commit()
