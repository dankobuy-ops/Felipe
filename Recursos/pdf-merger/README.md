# PDF Merger

Une archivos de distintos tipos (imágenes, texto, Word) en un solo PDF.

## Formatos soportados

| Tipo | Extensiones |
|------|------------|
| Imágenes | JPG, PNG, BMP, GIF, WebP, TIFF |
| Texto | TXT |
| Word | DOCX |

## Calidad de imágenes

Al generar el PDF puedes elegir:

- **Máxima** — JPEG 95%, hasta 1920px (alta fidelidad)
- **Media** — JPEG 72%, hasta 1200px (balance tamaño/calidad)
- **Baja** — JPEG 45%, hasta 800px (mínimo peso)

## Instalación

```bash
pip install -r requirements.txt
```

## Uso

```bash
python app.py
```

1. Haz clic en **＋ Agregar archivos** y selecciona los que quieras unir.
2. Usa **↑ ↓** para reordenarlos.
3. Elige la calidad de imagen.
4. Haz clic en **🖨 Generar PDF** y elige dónde guardar.
