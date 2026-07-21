# pdf-extractor — patentes desde demandas escaneadas (JPL)

Lee las demandas **escaneadas** (PDF de solo-imagen) de los Juzgados de Policía
Local y extrae la **patente** del vehículo con OCR local (offline). El resto de
las columnas (Rol, Tribunal, RUT del demandado) **no** se leen del PDF: ya las
tiene el scraper JPL y se **cruzan** por el Rol que viene en el nombre del archivo.

## Por qué así
- Los PDF son 100% imágenes → se necesita OCR (no tienen texto seleccionable).
- El scraper (`felipe/scraper`) ya guarda Rol, Tribunal (juzgado) y el RUT del
  demandado (tab `CausaXRut`, rol_parte = demandado) en su Google Sheet.
- Lo único que suele faltar es la **patente**, que va escrita dentro de la imagen
  de la demanda. Eso es lo que este tool recupera.

## Formato de patente
Solo se extraen patentes **nuevas (2008+)**: 4 letras (sin vocales) + 2 dígitos,
p.ej. `KGDD66`. Las antiguas (2 letras + 4 dígitos) se descartan.

## Flujo
1. `{juzgado}__{rol}__doc{n}.pdf`  → juzgado + rol (clave de cruce).
2. OCR de las páginas (RapidOCR, local) → texto.
3. `patente.py` ancla en la palabra “patente” y lee la corrida de caracteres en
   mayúscula/dígitos que sigue, la parte en bloques de 6 y conserva las nuevas.
4. Cruce con el Sheet del scraper: Rol, Tribunal, RUT demandado.
5. Salida `out/patentes_extraidas.csv` (una fila por patente).

## Buskin — modo Google Drive (recomendado)
`buskin.py` lee los PDF directamente desde la carpeta "Documentos" del scraper en
Drive (misma cuenta danko.buy), sin descargar a mano. Procesa SOLO las causas que
aún no tienen patente (las que faltan en `CausaXPatente`).

**Patrón de dónde está la patente (investigado):**
- Siempre en **doc0** (nunca en los adjuntos doc1..docN) → se OCR solo doc0.
- En la **página 0** (Procobro antiguo), **4** (Costanera/ACOFK "…es (son): PATENTE")
  o **15** (bundle largo). Buskin prueba [0,4,15] primero y se detiene al primer hallazgo.
- La pestaña `Documentos` no sirve para esto (descripción = "ProcesoNNNN", incompleta).
- OCR a veces no lee la palabra "patente"; `plates_in_text` agrega un respaldo que
  escanea la página completa (formato nuevo) cuando hay contexto de vehículo/peaje.

```
python buskin.py --pilot 50         # 50 causas (muestra repartida) para medir
python buskin.py --rols 1096,1097   # causas específicas (pruebas)
python buskin.py --dry-run --pilot 20   # sin escribir la planilla
python buskin.py                    # TODAS las causas faltantes (reanudable)
```
Reanudable: `buskin_checkpoint.json` guarda cada rol procesado; re-ejecutar continúa.

## Archivos
- `patente.py`     — parser de patentes (con tests: `python patente.py`).
- `buskin.py`      — app principal: lee de Drive, OCR de doc0, cruza y escribe la planilla.
- `extract.py`     — OCR de PDFs locales (una carpeta).
- `run_extract.py` — pipeline local (carpeta local + cruce + CSV).
- `sheet.py`       — escribe la planilla de salida (cuenta danko.buy).
- `samples/`       — PDFs de prueba (locales).

## Uso local (carpeta en disco)
```
python run_extract.py                 # procesa samples/
python run_extract.py "C:\ruta\pdfs"  # otra carpeta local
```

## Notas
- El scraper y Buskin autentican como **danko.buy@gmail.com** (token de felipe/scraper).
  La integración de Google en Claude (MCP) es OTRA cuenta (danko.brzovic) — no confundir.
- Solo patentes **nuevas (2008+)**. Cap de páginas por causa: env `BUSKIN_PAGE_CAP` (20).
