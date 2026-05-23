---
name: aegis-compliance
description: Audits code against the Aegis Corporate OS rules before any commit or review.
disable-model-invocation: true
---

# Aegis Compliance Auditor

Review the proposed code against the following rules. Emit a **WARNING** and block the action if any rule is violated.

## Rules

### Rule 1 — No Commission-First Logic
The code MUST NOT sort, filter, rank, or score results by broker commission fields (`comision`, `porcentaje_comision`, `monto_comision`, or any derived field). The only valid optimization criterion is the Precio/Cobertura ratio for the client.

**Violation pattern:** `ORDER BY comision DESC`, `filter(comision > x)` as primary sort, UI columns that expose commission to the client facing view.

### Rule 2 — No Rogue Schemas
The code MUST NOT create tables, models, or SQLAlchemy schemas outside the 9 base schemas:
`datos`, `operaciones`, `gestion`, `contabilidad`, `grupos`, `comunicacion`, `agenda`, `cruce_tablas`, `configuracion`.

**Violation pattern:** `__table_args__ = {"schema": "nuevo_schema"}` where `nuevo_schema` is not in the list above.

### Rule 3 — Data Sovereignty
No personally identifiable or insurance data may be sent to external services without explicit configuration in `configuracion.parametro`. No hardcoded external URLs handling client data.

## Output format

If compliant: output `✓ AEGIS COMPLIANCE PASS` and a one-line summary.

If violation found: output `✗ AEGIS COMPLIANCE VIOLATION — Rule <N>: <description>` and the exact line(s) that violate the rule. Do NOT proceed until the violation is resolved.
