---
name: translate-logic
description: Translates AppSheet virtual column formulas into Python backend logic (property, hybrid_property, or Service).
disable-model-invocation: true
---

# AppSheet → Python Logic Translator

Read the formulas from `PLAN_LOGICA_NEGOCIO.md`. When asked to translate a specific formula, apply the decision tree below and emit the correct Python implementation.

## Decision Tree

### Category A — `@property` (single-row, pure Python)
Use when: the formula reads only fields on the same row and requires no database query.

```python
@property
def campo_calculado(self) -> tipo:
    # pure Python — no DB access
    return self.campo_a + self.campo_b
```

### Category B — `@hybrid_property` (time-dependent or SQL-expressible)
Use when: the formula compares against `func.now()`, `TODAY()`, date arithmetic, or can be expressed as a SQL expression for server-side filtering.

```python
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy import func

@hybrid_property
def campo_calculado(self):
    return (func.now() - self.fecha_inicio).days  # example

@campo_calculado.expression
def campo_calculado(cls):
    return (func.now() - cls.fecha_inicio)
```

### Category C — Service class (cross-table aggregation)
Use when: the formula reads from multiple tables, involves JOINs, or aggregates child rows.

Create a method in the appropriate service (`PolizaService`, `ComisionService`, etc.) under `app/services/`. Accept a `db: Session` parameter. Never embed cross-table logic in a model.

```python
class PolizaService:
    @staticmethod
    def campo_agregado(db: Session, poliza_id: int) -> Decimal:
        return db.query(func.sum(Cuota.monto)).filter(
            Cuota.poliza_id == poliza_id,
            Cuota.estado == "PAGADA"
        ).scalar() or Decimal("0")
```

## Output format

1. State the category (A / B / C) and rationale.
2. Provide the full Python implementation ready to paste.
3. Note any migration or index needed if the hybrid expression requires it.
