from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import Optional
from datetime import date

from app.database import get_db
from app.models.gestion import Poliza, EstadoPoliza
from app.schemas.poliza import PolizaCreate, PolizaUpdate, PolizaOut

router = APIRouter(prefix="/polizas", tags=["Pólizas"])


@router.get("/", response_model=list[PolizaOut])
def listar_polizas(
    skip: int = 0,
    limit: int = Query(default=50, le=200),
    cliente_id: Optional[int] = None,
    estado: Optional[EstadoPoliza] = None,
    compania_id: Optional[int] = None,
    vence_antes_de: Optional[date] = None,
    db: Session = Depends(get_db),
):
    q = db.query(Poliza)
    if cliente_id:
        q = q.filter(Poliza.cliente_id == cliente_id)
    if estado:
        q = q.filter(Poliza.estado == estado)
    if compania_id:
        q = q.filter(Poliza.compania_id == compania_id)
    if vence_antes_de:
        q = q.filter(Poliza.fecha_termino <= vence_antes_de)
    return q.order_by(Poliza.fecha_termino.desc()).offset(skip).limit(limit).all()


@router.post("/", response_model=PolizaOut, status_code=status.HTTP_201_CREATED)
def crear_poliza(data: PolizaCreate, db: Session = Depends(get_db)):
    if db.query(Poliza).filter(Poliza.numero_poliza == data.numero_poliza).first():
        raise HTTPException(status_code=400, detail=f"N° póliza {data.numero_poliza} ya existe.")
    if data.porcentaje_comision and data.prima_neta:
        monto_comision = data.prima_neta * data.porcentaje_comision / 100
    else:
        monto_comision = None
    poliza = Poliza(**data.model_dump(), monto_comision=monto_comision)
    db.add(poliza)
    db.commit()
    db.refresh(poliza)
    return poliza


@router.get("/por-vencer", response_model=list[PolizaOut])
def polizas_por_vencer(
    dias: int = Query(default=30, description="Pólizas que vencen en los próximos N días"),
    db: Session = Depends(get_db),
):
    from datetime import timedelta
    hoy = date.today()
    limite = hoy + timedelta(days=dias)
    return (
        db.query(Poliza)
        .filter(Poliza.estado == EstadoPoliza.vigente)
        .filter(Poliza.fecha_termino >= hoy)
        .filter(Poliza.fecha_termino <= limite)
        .order_by(Poliza.fecha_termino)
        .all()
    )


@router.get("/{poliza_id}", response_model=PolizaOut)
def obtener_poliza(poliza_id: int, db: Session = Depends(get_db)):
    poliza = db.query(Poliza).filter(Poliza.id == poliza_id).first()
    if not poliza:
        raise HTTPException(status_code=404, detail="Póliza no encontrada.")
    return poliza


@router.patch("/{poliza_id}", response_model=PolizaOut)
def actualizar_poliza(poliza_id: int, data: PolizaUpdate, db: Session = Depends(get_db)):
    poliza = db.query(Poliza).filter(Poliza.id == poliza_id).first()
    if not poliza:
        raise HTTPException(status_code=404, detail="Póliza no encontrada.")
    for campo, valor in data.model_dump(exclude_unset=True).items():
        setattr(poliza, campo, valor)
    db.commit()
    db.refresh(poliza)
    return poliza
