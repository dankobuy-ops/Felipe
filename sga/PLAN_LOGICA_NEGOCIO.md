# Plan: Lógica de Negocio — Fórmulas y Columnas Virtuales

> **Directriz Corporate OS:** "Datos Puros Primero, Lógica Después."
> Este archivo es la hoja de ruta técnica para la Fase de Desarrollo de la API.
> No implementar hasta iniciar esa fase.

Fuente: `Archivos/OI61/CSV/Programación Guía - Columnas virtuales y formulas.csv`
Total: 60 fórmulas · Fecha de captura: 2026-05-20

---

## Arquitectura General

El `Estado Póliza` es la raíz del árbol de dependencias. Todos los demás estados
derivan de él en cascada:

```
Estado Póliza  ←  estado_seguro + fecha_termino + recotizar + TODAY()
    │
    ├─► Estado Plan de Pago  ←  activo + n_cuotas + Estado Póliza
    │       │
    │       └─► Estado Cuota  ←  vencimiento + control_pago + Estado Plan + TODAY()
    │               │
    │               └─► Estado Cobranza  ←  IN("Pendiente", cuotas)
    │
    ├─► Estado Documento  ←  requiere_doc + pdf + Estado Póliza
    │       │
    │       ├─► Estado Comisión (Documento)
    │       ├─► Estado Liquidación
    │       └─► Estado Envío (Documento)
    │
    └─► Estado Materia / Estado Cobertura
```

---

## Grupo A — Matemáticas Simples
> **Implementación:** `@property` en modelo SQLAlchemy o cálculo en frontend.
> Sin queries adicionales.

| Campo | Tabla | Fórmula |
|-------|-------|---------|
| Días de Vigencia | Documentos | `(F Vigencia - I Vigencia).days` |
| Días de Vigencia | Pólizas | Si cancelada: `abs(fecha_cancelacion - I Vigencia).days`; else `abs(F Vigencia - I Vigencia).days` |
| Días Pol | Pólizas | `floor(abs((F Vigencia - I Vigencia).total_seconds() / 86400))` |
| Días Gestión | Registros | Si pendiente: `(today - fecha_registro).days`; else `(fin_gestion - fecha_registro).days` |
| N° Facturas | Comisiones | `2 if facturacion == "Separada" else 1` |
| Diferencia Comisión | Documentos | `0 if invalidar_diferencia else (comision_total_a_pagar - total_comisionado)` |
| Comisión Partner | Documentos | `total_pagado_comision * pct_comision_partner` |
| Contador de Meses Vigentes | Documentos | `(year_today - year_inicio) * 12 + (month_today - month_inicio) - (1 if day_today < day_inicio else 0)` |
| Total Documentado | Comisiones | `SUM(facturas where estado_factura == "Ok", monto_factura)` |
| EsSaldo? | CruceDocXComisión | `monto_afecto + monto_exento <= 0` |
| Total a Pagar | Liquidaciones | `SUM(documentos, comision_a_pagar)` |

---

## Grupo B — Lógica Propia (misma fila)
> **Implementación:** `@property` o `@hybrid_property` en modelo SQLAlchemy.
> Sin joins ni queries adicionales.

### Gestión Solicitudes

```python
@property
def estado_solicitud(self) -> str:
    if not self.pdf_folio:     return "Falta Folio"
    if not self.recibo:        return "Falta Recibo"
    if not self.finalizada:    return "Pendiente"
    return "Ok"

@property
def estado_gestion(self) -> str:
    return "Ok" if self.estado_solicitud == "Ok" else "Pendiente"
```

### Contabilidad Liquidaciones

```python
@property
def estado(self) -> str:
    return "Pendiente" if not self.fecha_pago else "Ok"

@property
def gestion(self) -> str:
    return self.estado  # mismo valor
```

### Contabilidad Contables

```python
@property
def estado_ingreso(self) -> str:
    if self.estado_documento != "Ok": return "Ok"
    return "Ok" if self.doc_ingresado else "Pendiente"

@property
def estado_pago(self) -> str:
    if self.tipo_documento != "FA":   return "Ok"
    if self.estado_documento != "Ok": return "Ok"
    return "Ok" if self.cta_cte else "Pendiente"
```

### Gestión Cotizaciones

```python
@property
def estado_vigencia(self) -> str:
    delta_hours = (self.vencimiento - date.today()).days * 24
    return "Vencida" if delta_hours <= 0 else "Vigente"
```

### Gestión Materias (Gestion)

```python
@property
def estado_cobertura(self) -> str:
    estados_ok = {"Ok", "Espera", "Pendiente"}
    tipos_activos = {"Póliza", "Inclusión", "Prórroga", "Modificación", "Rehabilitación"}
    if self.estado_poliza not in estados_ok:  return "Inactiva"
    return "Activa" if self.tipo_documento in tipos_activos else "Inactiva"

@property
def estado_materia(self) -> str:
    if self.estado_poliza not in {"Ok", "Espera"}:  return "No Cubierta"
    return "Cubierta" if self.estado_cobertura == "Activa" else "No Cubierta"
```

### Gestión Planes de Pago

```python
@property
def estado_gestion(self) -> str:
    if not self.activo:   return "Ok"
    if not self.firmado:  return "Firmar"
    if not self.enviado:  return "Enviar"
    if not self.recibo_envio: return "Pendiente"
    return "Ok"
```

---

## Grupo C — Dependen de TODAY()
> **Implementación:** `@hybrid_property` en SQLAlchemy con expresión SQL para
> soporte en queries. Calcular top-down en este orden.

### 1. Estado Póliza (RAÍZ — calcular primero)

```python
@hybrid_property
def estado_poliza(self) -> str:
    # Mapeo directo desde estado_seguro
    mapa = {
        "consumido": "Consumida",
        "cancelada": "Cancelada",
        "anulada":   "Anulada",
        "nulo":      "Nula",
    }
    if self.estado_seguro in mapa:
        return mapa[self.estado_seguro]
    if self.numero_poliza == "Pendiente":
        return "Pendiente"
    if self.recotizar:
        return "Recotizar"
    # Vigencia
    today = date.today()
    if self.fecha_inicio > today:
        return "Espera"      # "Pendiente" en fórmula original = aún no inicia
    if self.fecha_termino > today:
        return "Ok"          # vigente
    return "Finalizada"
```

### 2. Estado Vigencia (Póliza)

```python
@hybrid_property
def estado_vigencia(self) -> str:
    today = date.today()
    if self.fecha_inicio > today:  return "Pendiente"
    if self.fecha_termino > today: return "Ok"
    return "Finalizada"
```

### 3. Estado Plan de Pago

```python
@hybrid_property
def estado_plan_de_pago(self) -> str:
    estado_pol = self.poliza.estado_poliza  # requiere join
    if estado_pol == "Pendiente":           return "Pendiente"
    if not self.activo:                     return "Inactivo"
    if len(self.cuotas) != self.n_cuotas:  return "Verificar Cuotas"
    if estado_pol in {"Ok", "Recotizar"}:  return "Ok"
    return estado_pol
```

### 4. Estado Cuota

```python
@hybrid_property
def estado_cuota(self) -> str:
    estado_plan = self.plan_pago.estado_plan_de_pago
    if estado_plan == "Inactivo":     return "Ok"
    if not self.vencimiento:          return "Cargar"
    if self.control_pago:             return "Pagada"

    estado_pol = self.plan_pago.poliza.estado_poliza
    if estado_pol == "Ok":
        today = date.today()
        if (self.vencimiento.year < today.year or
            (self.vencimiento.year == today.year and
             self.vencimiento.month <= today.month)):
            return "Pendiente"
        return "Vigente"
    return estado_pol  # hereda estado de la póliza

@hybrid_property
def estado_gestion_cuota(self) -> str:
    ec = self.estado_cuota
    if ec == "Pagada":
        if self.control_pago == "Transferencia":
            return "Ok" if self.cursado else "Pendiente"
        return "Ok"
    if ec == "Vigente":
        return "Ok"
    estado_pol = self.plan_pago.poliza.estado_poliza
    return "Pendiente" if estado_pol == "Ok" else "Ok"
```

### 5. Estado Renovación (Póliza)

```python
@hybrid_property
def estado_renovacion(self) -> str:
    if not (self.renovar and self.estado_seguro == "ok"):
        return "No Renovar"
    today = date.today()
    dias_restantes = (self.fecha_termino - today).days
    if not self.registro_renovacion_id:
        return "Ok" if dias_restantes > 45 else "Falta"
    # Delega a estado del registro de renovación (requiere join)
    if self.registro_renovacion.estado_renovacion == "Pendiente":
        return "Pendiente"
    return "Ok"
```

---

## Grupo D — Agregaciones sobre Hijos
> **Implementación:** Métodos en `PolizaService` / `DocumentoService`.
> Requieren queries SQL con joins. No usar como `@property` (N+1 queries).

### PolizaService

```python
class PolizaService:

    def estado_envio(poliza_id) -> str:
        # IN(FALSE, documentos.enviado) → si algún doc no enviado → Pendiente
        ...

    def estado_pago_cuotas(poliza_id) -> str:
        cuota_estados = query cuotas where poliza_id
        if not cuota_estados:          return "Cargar Cuotas"
        if "Pendiente" in estados:     return "Pendiente"
        if "Vigente" in estados:       return "Ok"
        return "Finalizada"

    def estado_comision(poliza_id) -> str:
        # Verifica documentos con comision pendiente
        ...

    def estado_plan_de_pago_agg(poliza_id) -> str:
        # IN("Verificar Cuotas", planes) → "Verificar Cuotas"
        # IN("Pendiente", planes) → "Pendiente"
        ...

    def estado_solicitud_agg(poliza_id) -> str:
        solicitud_estados = query solicitudes where poliza_id
        if "Pendiente" in estados:     return "Pendiente"
        if "Falta Recibo" in estados:  return "Falta Recibo"
        if "Falta Folio" in estados:   return "Falta Folio"
        return "Ok"

    def estado_carga_materias(poliza_id) -> str:
        if poliza.estado_poliza == "Pendiente": return "Ok"
        return "Ok" if materias else "Pendiente"

    def estado_carga_cuotas(poliza_id) -> str:
        # Agrega estados de planes de pago
        ...

    def estado_carga_docs(poliza_id) -> str:
        docs_pendientes = query documentos where estado_documento = "Pendiente"
        return "Pendiente" if docs_pendientes else "Ok"

    def n_items_activos(poliza_id) -> int:
        return COUNT materias where estado_materia = "Cubierta"

    def grupo_materia(poliza_id) -> Optional[int]:
        materias = query materias where poliza_id
        return materias[0].base_materia_id if len(materias) == 1 else None
```

### DocumentoService

```python
class DocumentoService:

    def estado_comision(documento_id) -> str:
        # Verifica comisiones cargadas vs esperadas, diferencias
        # Fórmula compleja con meses vigentes y montos
        ...

    def diferencia_comision_valida(documento_id) -> bool:
        # Moneda != CLP: tolerancia 0.01
        # CLP: tolerancia 500 (afecta) / 1000 (exenta)
        ...

    def estado_liquidacion(documento_id) -> str:
        if not self.partner_id:         return "No Aplica"
        if not liquidaciones:           return "Falta Liquidar"
        if "Pendiente" in liq_estados: return "Pendiente"
        return "Ok"

    def estado_envio(documento_id) -> str:
        if self.enviado: return "Ok"
        coms = query comunicacion_documentos where documento_id
        if not coms: return "Cargar Envío"
        estado = coms[0].estado_envio
        return {"Enviado": "Enviado", "": "Enviar", "Enviar": "Enviar",
                "Enviando": "Pendiente"}.get(estado, estado)

    def pct_comision_partner(documento_id) -> float:
        if tipo_registro == "Renovación":
            return partner.comision_renovaciones
        return partner.comision_nuevos

    def estado_plan_de_pago_doc(documento_id) -> str:
        # Agrega estados de planes asociados al documento
        ...

    def estado_documento(documento_id) -> str:
        if poliza.estado_seguro == "nulo":           return "Ok"
        if poliza.estado_poliza == "Pendiente":      return "Ok"
        if self.requiere_doc and not self.pdf_url:   return "Pendiente"
        return "Ok"
```

### GrupoMateriaService

```python
class GrupoMateriaService:

    def materia_asegurada(grupo_materia_id) -> bool:
        return any(m.estado_materia == "Cubierta"
                   for m in gestión_materias where verificador == grupo_materia_id)

    def estado_materia(grupo_materia_id) -> str:
        if not self.activa:
            estados_activos = {"Activa", "Espera", "Pendiente"}
            if any(m.estado_materia in estados_activos for m in gestion_materias):
                return "Activar"
            return "Inactiva"
        return "Activa"

    def verificador_registro(grupo_materia_id) -> bool:
        return any(m.estado_gestion == "Pendiente"
                   for m in materias_x_registros where registro.tipo == "Prospecto")
```

### CobranzaService

```python
class CobranzaService:

    def hay_cuota_pendiente(cobranza_id) -> bool:
        return any(c.estado_cuota == "Pendiente" for c in cuotas)

    def estado_cobranza(cobranza_id) -> str:
        return "Pendiente" if self.hay_cuota_pendiente else "Ok"

    def estado_gestion(cobranza_id) -> str:
        if not cuotas:  return "Cargar"
        coms = query comunicacion_cobranzas where cobranza_id
        if not coms:    return any(coms).envio
        if any(c.envio == "Enviado" for c in coms): return "Ok"
        return coms[0].envio
```

### ComisionGestionService

```python
class ComisionGestionService:

    def estado_comision(comision_id) -> str:
        if self.movimiento == "Saldo":          return "Ok"
        if self.cantidad_documentos != n_docs_cargados:
            return "Diferencia Docs"
        if COUNT(facturas) < self.n_facturas:   return "Facturar"
        return "Ok"
```

### RegistroService

```python
class RegistroService:

    def estado_gestion(registro_id) -> str:
        t = self.tipo_registro
        if t == "Negocio":
            return "Ok" if self.estado_negocio != "pendiente" else "Pendiente"
        if t == "Renovación":
            return "Ok" if self.estado_renovacion != "Pendiente" else "Pendiente"
        if t == "Traspaso":
            return "Ok" if self.estado_traspaso != "Pendiente" else "Pendiente"
        if t == "Prospecto":
            if self.estado_prospecto in {"ganado", "perdido"}:
                return "Ok"
            return "Ok" if self.estado_prospecto != "pendiente" else "Pendiente"
        return "Ok"
```

---

## Contabilidad Contables — Estado Comisión Base

```python
@property
def estado_comision_base(self) -> str:
    if self.tipo_documento != "FA":       return "No Aplica"
    if self.tipo_movimiento != "Venta":   return "No Aplica"
    if self.estado_documento != "Ok":     return "Ok"
    return self.comision_base.estado_comision
```

---

## Notas de Implementación

1. **Orden de cálculo obligatorio:** Estado Póliza → Estado Plan → Estado Cuota → resto
2. **Flujo de cobranza:** `CobranzaService.hay_cuota_pendiente()` es el trigger para el proceso automático. Implementar como query indexada sobre `cuota.vencimiento` y `cuota.control_pago`.
3. **N+1 warnings:** Los métodos del Grupo D NUNCA como `@property` en modelos — siempre como métodos de servicio con joins explícitos.
4. **Cache candidatos:** `estado_poliza` y `estado_plan_de_pago` son costosos de recomputar. Candidatos para Redis o columna materializada con refresh diario.
5. **Campos renombrados vs AppSheet:** `"Ganado"→aceptado`, `"Perdido"→perdido`, `"Espera Cliente"→en_espera` (ver migraciones Alembic del schema gestion).
