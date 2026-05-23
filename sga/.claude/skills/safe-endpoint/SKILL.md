---
name: safe-endpoint
description: Generates secure, paginated FastAPI endpoints aligned with the SGA frontend structure.
disable-model-invocation: true
---

# Safe Endpoint Generator

When generating a FastAPI endpoint, enforce all rules below without exception.

## Mandatory Rules

### 1. Server-side pagination (required on all list endpoints)
Every endpoint returning a collection MUST accept `limit: int = Query(default=50, le=200)` and
`offset: int = Query(default=0, ge=0)`. Never fetch unbounded rows.

```python
@router.get("/schema/table")
def list_items(
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    total = db.query(func.count(Model.id)).scalar()
    items = db.query(Model).offset(offset).limit(limit).all()
    return {"total": total, "items": items, "limit": limit, "offset": offset}
```

### 2. SQL injection mitigation
- NEVER concatenate raw strings into queries.
- NEVER use f-strings inside `text()` with user input.
- All dynamic schema/table names MUST be validated against `ALLOWED_SCHEMAS` and the
  `information_schema` whitelist before use (see `system.py` pattern).
- All filter values MUST be passed as bound parameters.

### 3. Frontend alignment (`entities.js`)
The JSON response shape MUST match what `DashboardTemplate` expects:
- List endpoint: `{ total: int, items: [...], limit: int, offset: int }`
- Detail endpoint: flat object with field names matching the `fields` array in the entity config.
- FK fields: include both the raw id (`compania_id`) and the resolved display value
  (`compania_nombre`) when the frontend entity declares a `fk` field type.

### 4. Session injection
Always use `db: Session = Depends(get_db)`. Never instantiate `SessionLocal()` inside a router.

### 5. Schema validation
Use Pydantic v2 `model_config = ConfigDict(from_attributes=True)` on all response schemas.
Use `model_config = ConfigDict(strict=True)` on all input/write schemas.

## Output format

1. Router function with full type annotations and docstring (one line, Spanish).
2. Pydantic request/response schemas.
3. Note any index that should be added to support the query efficiently.
