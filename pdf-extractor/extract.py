"""OCR JPL demanda PDFs and pull the new-format (2008+) vehicle plates.

Scope (decided with the user): read ONLY the patente from the scanned PDF; Rol,
Tribunal and RUT-demandado come from the JPL scraper's data, joined by the Rol
encoded in each filename (`{juzgado}__{rol}__doc{n}.pdf`).
"""
import io
import os
import re
import sys
import glob

import fitz  # PyMuPDF
import numpy as np
from PIL import Image
from rapidocr_onnxruntime import RapidOCR

import patente

_OCR = None
def _ocr():
    global _OCR
    if _OCR is None:
        _OCR = RapidOCR()
    return _OCR

# `lobarnechea__1096__doc0.pdf` -> ('lobarnechea', '1096', 0)
_NAME = re.compile(r"^(?P<juz>[a-z0-9]+)__(?P<rol>[^_]+)__doc(?P<n>\d+)", re.I)

def parse_name(path):
    m = _NAME.match(os.path.basename(path))
    if not m:
        return None, None, None
    return m.group("juz"), m.group("rol"), int(m.group("n"))

def ocr_page_text(page, zoom=2.6):
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
    img = np.array(Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB"))
    res, _ = _ocr()(img)
    return "\n".join(l[1] for l in res) if res else ""

def extract_pdf(path, max_pages=None, verbose=False):
    """Return (plates, n_pages_ocred). OCRs page by page, collecting every
    new-format plate found near a 'patente' anchor across all pages."""
    doc = fitz.open(path)
    n = doc.page_count if max_pages is None else min(max_pages, doc.page_count)
    plates = []
    for i in range(n):
        txt = ocr_page_text(doc[i])
        for p in patente.plates_after_anchor(txt):
            if p not in plates:
                plates.append(p)
        if verbose and patente.plates_after_anchor(txt):
            print(f"    p{i}: {patente.plates_after_anchor(txt)}")
    return plates, n

def main():
    args = sys.argv[1:]
    cap = None
    if "--max" in args:
        cap = int(args[args.index("--max") + 1])
    folder = next((a for a in args if not a.startswith("--") and a.isascii() and os.path.isdir(a)),
                  r"C:\Claude\pdf-extractor\samples")
    for path in sorted(glob.glob(os.path.join(folder, "*.pdf"))):
        juz, rol, docn = parse_name(path)
        plates, npg = extract_pdf(path, max_pages=cap, verbose=True)
        print(f"{os.path.basename(path)}  [juz={juz} rol={rol}]  ({npg} pg OCR'd) -> {plates}")

if __name__ == "__main__":
    main()
