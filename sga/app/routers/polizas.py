from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session, joinedload
from typing import Optional
from datetime import date, timedelta
from pydantic import BaseModel

from app.database import get_db
from app.models.gestion import (
    Poliza, Documento, PlanPago, Cuota,
    EstadoPoliza, EstadoSeguro, TipoDocumento, EstadoCuota,
)
from app.models.comunicacion import ComDocumento as ComunicacionDocumento
from app.schemas.poliza import PolizaCreate, PolizaUpdate, PolizaOut

router = APIRouter(prefix="/polizas", tags=["Pólizas"])


# ── Schemas de entrada para acciones ────────────────────────────────────────

class EmitirInput(BaseModel):
    numero_poliza: Optional[str] = None
    numero_documento: Optional[str] = None
    fecha_emision: date
    fecha_inicio: date
    fecha_termino: date
    n_cuotas: int = 1
    valor_cuota_clp: Optional[float] = None
    valor_cuota_uf: Optional[float] = None
    fecha_primera_cuota: Optional[date] = None
    pct_comision_afecta: Optional[float] = None
    pct_comision_exenta: Optional[float] = None
    prima_neta: Optional[float] = None
    prima_total: Optional[float] = None
    pdf_url: Optional[str] = None


class EnviarInput(BaseModel):
    correo_destinatario: Optional[str] = None
    cc_envio: Optional[str] = None
    asunto: Optional[str] = None
    cuerpo: Optional[str] = None


# ── Endpoints base ─────────────────────────────────────────────────────────

def _load_poliza(db: Session, poliza_id: int) -> Poliza:
    poliza = (
        db.query(Poliza)
        .options(joinedload(Poliza.documentos), joinedload(Poliza.cuotas))
        .filter(Poliza.id == poliza_id)
        .first()
    )
    if not poliza:
        raise HTTPException(status_code=404, detail="Póliza no encontrada.")
    return poliza


@router.get("/", response_model=list[PolizaOut])
def listar_polizas(
    skip: int = 0,
    limit: int = Query(default=50, le=200),
    cliente_id: Optional[int] = None,
    estado: Optional[EstadoPoliza] = None,
    estado_seguro: Optional[EstadoSeguro] = None,
    compania_id: Optional[int] = None,
    vence_antes_de: Optional[date] = None,
    db: Session = Depends(get_db),
):
    q = db.query(Poliza).options(joinedload(Poliza.documentos), joinedload(Poliza.cuotas))
    if cliente_id:
        q = q.filter(Poliza.cliente_id == cliente_id)
    if estado:
        q = q.filter(Poliza.estado == estado)
    if estado_seguro:
        q = q.filter(Poliza.estado_seguro == estado_seguro)
    if compania_id:
        q = q.filter(Poliza.compania_id == compania_id)
    if vence_antes_de:
        q = q.filter(Poliza.fecha_termino <= vence_antes_de)
    return q.order_by(Poliza.id.desc()).offset(skip).limit(limit).all()


@router.get("/por-vencer", response_model=list[PolizaOut])
def polizas_por_vencer(
    dias: int = Query(default=30),
    db: Session = Depends(get_db),
):
    hoy = date.today()
    limite = hoy + timedelta(days=dias)
    return (
        db.query(Poliza)
        .options(joinedload(Poliza.documentos), joinedload(Poliza.cuotas))
        .filter(Poliza.estado == EstadoPoliza.vigente)
        .filter(Poliza.fecha_termino >= hoy)
        .filter(Poliza.fecha_termino <= limite)
        .order_by(Poliza.fecha_termino)
        .all()
    )


@router.post("/", response_model=PolizaOut, status_code=status.HTTP_201_CREATED)
def crear_poliza(data: PolizaCreate, db: Session = Depends(get_db)):
    if data.numero_poliza and db.query(Poliza).filter(
        Poliza.numero_poliza == data.numero_poliza
    ).first():
        raise HTTPException(status_code=400, detail=f"N° póliza {data.numero_poliza} ya existe.")
    poliza = Poliza(**data.model_dump())
    if data.porcentaje_comision and data.prima_neta:
        poliza.monto_comision = round(data.prima_neta * data.porcentaje_comision / 100, 2)
    db.add(poliza)
    db.commit()
    return _load_poliza(db, poliza.id)


@router.get("/{poliza_id}", response_model=PolizaOut)
def obtener_poliza(poliza_id: int, db: Session = Depends(get_db)):
    return _load_poliza(db, poliza_id)


@router.patch("/{poliza_id}", response_model=PolizaOut)
def actualizar_poliza(poliza_id: int, data: PolizaUpdate, db: Session = Depends(get_db)):
    poliza = db.query(Poliza).filter(Poliza.id == poliza_id).first()
    if not poliza:
        raise HTTPException(status_code=404, detail="Póliza no encontrada.")
    for campo, valor in data.model_dump(exclude_unset=True).items():
        setattr(poliza, campo, valor)
    db.commit()
    return _load_poliza(db, poliza_id)


# ── PASO 4: Emitir póliza ─────────────────────────────────────────────────

@router.post("/{poliza_id}/emitir")
def emitir_poliza(poliza_id: int, data: EmitirInput, db: Session = Depends(get_db)):
    """
    PASO 4: Emite la póliza.
    - Actualiza Póliza con número, fechas y estado ok.
    - Crea Documento de emisión.
    - Crea PlanPago.
    - Genera N registros de Cuota con vencimientos mensuales desde fecha_primera_cuota.
    """
    poliza = db.query(Poliza).filter(Poliza.id == poliza_id).first()
    if not poliza:
        raise HTTPException(status_code=404, detail="Póliza no encontrada.")

    # 1. Actualizar Póliza
    if data.numero_poliza:
        existe = db.query(Poliza).filter(
            Poliza.numero_poliza == data.numero_poliza, Poliza.id != poliza_id
        ).first()
        if existe:
            raise HTTPException(status_code=400, detail=f"N° póliza {data.numero_poliza} ya existe.")
        poliza.numero_poliza = data.numero_poliza
    poliza.fecha_emision = data.fecha_emision
    poliza.fecha_inicio = data.fecha_inicio
    poliza.fecha_termino = data.fecha_termino
    poliza.estado_seguro = EstadoSeguro.ok
    poliza.estado = EstadoPoliza.vigente
    poliza.n_cuotas = data.n_cuotas
    if data.pct_comision_afecta:
        poliza.pct_comision_afecta = data.pct_comision_afecta
    if data.pct_comision_exenta:
        poliza.pct_comision_exenta = data.pct_comision_exenta
    if data.prima_neta:
        poliza.prima_neta = data.prima_neta
    if data.prima_total:
        poliza.prima_total = data.prima_total

    # 2. Crear Documento
    doc = Documento(
        poliza_id=poliza.id,
        tipo_documento=TipoDocumento.poliza,
        fecha_emision=data.fecha_emision,
        fecha_inicio=data.fecha_inicio,
        fecha_termino=data.fecha_termino,
        numero_documento=data.numero_documento,
        n_cuotas=data.n_cuotas,
        pct_comision_afecta=data.pct_comision_afecta,
        pct_comision_exenta=data.pct_comision_exenta,
        pdf_url=data.pdf_url,
    )
    db.add(doc)
    db.flush()

    # 3. Crear PlanPago
    plan = PlanPago(
        documento_id=doc.id,
        n_cuotas=data.n_cuotas,
        valor_cuota_clp=data.valor_cuota_clp,
        valor_cuota_uf=data.valor_cuota_uf,
        fecha_primera_cuota=data.fecha_primera_cuota,
    )
    db.add(plan)
    db.flush()

    # 4. Generar Cuotas
    vcto_base = data.fecha_primera_cuota or data.fecha_inicio
    for i in range(data.n_cuotas):
        # Vencimiento mensual desde la fecha base
        mes = vcto_base.month + i
        anio = vcto_base.year + (mes - 1) // 12
        mes = ((mes - 1) % 12) + 1
        try:
            vcto = vcto_base.replace(year=anio, month=mes)
        except ValueError:
            # Día inválido para ese mes (ej: 31 de febrero) → último día del mes
            import calendar
            ultimo = calendar.monthrange(anio, mes)[1]
            vcto = vcto_base.replace(year=anio, month=mes, day=ultimo)

        cuota = Cuota(
            poliza_id=poliza.id,
            plan_pago_id=plan.id,
            numero_cuota=i + 1,
            estado=EstadoCuota.pendiente,
            monto_clp=data.valor_cuota_clp,
            monto_uf=data.valor_cuota_uf,
            fecha_vencimiento=vcto,
        )
        db.add(cuota)

    db.commit()

    return {
        "mensaje": f"Póliza emitida correctamente con {data.n_cuotas} cuota(s).",
        "poliza_id": poliza.id,
        "documento_id": doc.id,
        "plan_pago_id": plan.id,
        "cuotas_generadas": data.n_cuotas,
    }


# ── PASO 5: Enviar póliza al cliente ─────────────────────────────────────

@router.post("/{poliza_id}/enviar")
def enviar_poliza(poliza_id: int, data: EnviarInput, db: Session = Depends(get_db)):
    """
    PASO 5: Registra el envío del documento al cliente.
    Crea una fila en ComunicacionDocumento y marca el Documento como enviado.
    """
    poliza = db.query(Poliza).filter(Poliza.id == poliza_id).first()
    if not poliza:
        raise HTTPException(status_code=404, detail="Póliza no encontrada.")

    # Obtener el último documento de esta póliza
    doc = (
        db.query(Documento)
        .filter(Documento.poliza_id == poliza_id)
        .order_by(Documento.id.desc())
        .first()
    )
    if not doc:
        raise HTTPException(
            status_code=400,
            detail="La póliza no tiene documentos emitidos. Primero ejecuta 'Emitir'."
        )

    # Crear registro de comunicación
    comunicacion = ComunicacionDocumento(
        documento_id=doc.id,
        fecha=date.today(),
        correo_destinatario=data.correo_destinatario,
        cc_envio=data.cc_envio,
        asunto=data.asunto or f"Envío de Póliza N° {poliza.numero_poliza or poliza_id}",
        cuerpo=data.cuerpo,
        enviado=True,
    )
    db.add(comunicacion)

    # Marcar documento como enviado
    doc.enviado = True

    db.commit()

    return {
        "mensaje": "Póliza enviada al cliente.",
        "poliza_id": poliza_id,
        "documento_id": doc.id,
        "correo_destinatario": data.correo_destinatario,
        "comunicacion_id": comunicacion.id,
    }
