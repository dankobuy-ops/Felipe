"""
PDF Merger — une archivos JPG, PNG, TXT, DOCX en un solo PDF.
Para imágenes: calidad máxima, media o baja.
"""
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
import threading
import io

from PIL import Image
from reportlab.lib.pagesizes import A4, letter
from reportlab.lib.units import cm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image as RLImage, PageBreak
from reportlab.lib import colors
import docx

# ── Calidades de imagen ───────────────────────────────────────────────────────
CALIDADES = {
    "Máxima  (sin pérdida)": {"jpeg_quality": 95, "max_width": 1920, "max_height": 2700},
    "Media   (balanceada)":  {"jpeg_quality": 72, "max_width": 1200, "max_height": 1700},
    "Baja    (tamaño mín.)": {"jpeg_quality": 45, "max_width":  800, "max_height": 1100},
}

PAGE_W, PAGE_H = A4
MARGIN = 2 * cm


def img_to_rl(path: Path, quality_cfg: dict) -> RLImage:
    """Convierte imagen PIL a elemento ReportLab respetando calidad y márgenes."""
    img = Image.open(path)
    if img.mode in ("RGBA", "P"):
        bg = Image.new("RGB", img.size, (255, 255, 255))
        bg.paste(img, mask=img.split()[-1] if img.mode == "RGBA" else None)
        img = bg
    elif img.mode != "RGB":
        img = img.convert("RGB")

    mw, mh = quality_cfg["max_width"], quality_cfg["max_height"]
    img.thumbnail((mw, mh), Image.LANCZOS)

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality_cfg["jpeg_quality"], optimize=True)
    buf.seek(0)

    avail_w = PAGE_W - 2 * MARGIN
    avail_h = PAGE_H - 2 * MARGIN
    iw, ih = img.size
    scale = min(avail_w / iw, avail_h / ih, 1.0)
    return RLImage(buf, width=iw * scale, height=ih * scale)


def txt_to_paragraphs(path: Path, style) -> list:
    """Lee TXT y devuelve lista de Paragraph."""
    text = path.read_text(encoding="utf-8", errors="replace")
    elems = []
    for line in text.splitlines():
        safe = line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        elems.append(Paragraph(safe or "&nbsp;", style))
    return elems


def docx_to_paragraphs(path: Path, h1_style, body_style) -> list:
    """Extrae texto de DOCX preservando estilos básicos."""
    doc = docx.Document(str(path))
    elems = []
    for para in doc.paragraphs:
        text = para.text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        if not text.strip():
            elems.append(Spacer(1, 6))
            continue
        if para.style.name.startswith("Heading"):
            elems.append(Paragraph(f"<b>{text}</b>", h1_style))
        else:
            elems.append(Paragraph(text, body_style))
    return elems


def build_pdf(files: list[Path], output: Path, quality_key: str,
              progress_cb=None, log_cb=None):
    quality_cfg = CALIDADES[quality_key]
    styles = getSampleStyleSheet()

    body_style = ParagraphStyle(
        "body", parent=styles["Normal"],
        fontSize=10, leading=14, textColor=colors.HexColor("#1a1a1a"),
        fontName="Helvetica",
    )
    h1_style = ParagraphStyle(
        "h1", parent=body_style,
        fontSize=13, leading=18, fontName="Helvetica-Bold",
        spaceAfter=6,
    )
    caption_style = ParagraphStyle(
        "caption", parent=body_style,
        fontSize=8, textColor=colors.HexColor("#666666"),
        alignment=1,  # centrado
    )

    doc = SimpleDocTemplate(
        str(output),
        pagesize=A4,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=MARGIN, bottomMargin=MARGIN,
    )

    story = []
    image_exts = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".gif", ".webp"}
    text_exts  = {".txt"}
    docx_exts  = {".docx"}

    total = len(files)
    for i, path in enumerate(files, 1):
        if log_cb:
            log_cb(f"Procesando: {path.name}")
        if progress_cb:
            progress_cb(i / total)

        ext = path.suffix.lower()

        if ext in image_exts:
            if story:
                story.append(PageBreak())
            story.append(img_to_rl(path, quality_cfg))
            story.append(Spacer(1, 4))
            story.append(Paragraph(path.name, caption_style))

        elif ext in text_exts:
            if story:
                story.append(PageBreak())
            story.append(Paragraph(f"<b>{path.name}</b>", h1_style))
            story.append(Spacer(1, 8))
            story.extend(txt_to_paragraphs(path, body_style))

        elif ext in docx_exts:
            if story:
                story.append(PageBreak())
            story.append(Paragraph(f"<b>{path.name}</b>", h1_style))
            story.append(Spacer(1, 8))
            story.extend(docx_to_paragraphs(path, h1_style, body_style))

        else:
            if log_cb:
                log_cb(f"  ⚠ Formato no soportado: {path.suffix} — omitido")

    if not story:
        raise ValueError("No hay contenido válido para generar el PDF.")

    doc.build(story)


# ── UI ────────────────────────────────────────────────────────────────────────

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("PDF Merger")
        self.geometry("680x560")
        self.resizable(True, True)
        self.configure(bg="#F0F4F8")
        self._build_ui()

    def _build_ui(self):
        BG     = "#F0F4F8"
        CARD   = "#FFFFFF"
        ACCENT = "#1B3A6B"
        GOLD   = "#C7A965"
        GRAY   = "#64748B"

        # ── Header ────────────────────────────────────────────────────────
        header = tk.Frame(self, bg=ACCENT, height=56)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(header, text="  PDF Merger", bg=ACCENT, fg="white",
                 font=("Helvetica", 16, "bold")).pack(side="left", padx=16, pady=12)
        tk.Label(header, text="une archivos en un solo PDF", bg=ACCENT, fg="#94B4D4",
                 font=("Helvetica", 10)).pack(side="left", pady=12)

        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True, padx=20, pady=16)

        # ── Lista de archivos ─────────────────────────────────────────────
        list_frame = tk.LabelFrame(body, text="Archivos a unir  (arrastra para reordenar)",
                                   bg=CARD, fg=ACCENT, font=("Helvetica", 10, "bold"),
                                   bd=1, relief="solid")
        list_frame.pack(fill="both", expand=True)

        list_inner = tk.Frame(list_frame, bg=CARD)
        list_inner.pack(fill="both", expand=True, padx=8, pady=8)

        scroll = ttk.Scrollbar(list_inner, orient="vertical")
        self.listbox = tk.Listbox(list_inner, yscrollcommand=scroll.set,
                                  selectmode="extended", font=("Helvetica", 10),
                                  bg="white", fg="#1a1a1a", relief="flat",
                                  highlightthickness=1, highlightcolor="#CBD5E1",
                                  activestyle="dotbox", selectbackground=ACCENT,
                                  selectforeground="white")
        scroll.config(command=self.listbox.yview)
        scroll.pack(side="right", fill="y")
        self.listbox.pack(fill="both", expand=True)

        # Botones lista
        btn_row = tk.Frame(list_frame, bg=CARD)
        btn_row.pack(fill="x", padx=8, pady=(0, 8))

        self._btn(btn_row, "＋ Agregar archivos", ACCENT, "white",
                  self._add_files).pack(side="left", padx=(0, 6))
        self._btn(btn_row, "↑ Subir", "#E2E8F0", GRAY,
                  self._move_up).pack(side="left", padx=3)
        self._btn(btn_row, "↓ Bajar", "#E2E8F0", GRAY,
                  self._move_down).pack(side="left", padx=3)
        self._btn(btn_row, "✕ Quitar", "#FEE2E2", "#DC2626",
                  self._remove).pack(side="left", padx=3)

        # ── Calidad de imagen ─────────────────────────────────────────────
        opts_frame = tk.LabelFrame(body, text="Calidad de imágenes",
                                   bg=CARD, fg=ACCENT, font=("Helvetica", 10, "bold"),
                                   bd=1, relief="solid")
        opts_frame.pack(fill="x", pady=(12, 0))

        self.quality_var = tk.StringVar(value=list(CALIDADES.keys())[0])
        q_row = tk.Frame(opts_frame, bg=CARD)
        q_row.pack(fill="x", padx=12, pady=10)

        for i, key in enumerate(CALIDADES):
            rb = tk.Radiobutton(q_row, text=key, variable=self.quality_var, value=key,
                                bg=CARD, fg="#1a1a1a", font=("Helvetica", 10),
                                activebackground=CARD, selectcolor="#DBEAFE",
                                indicatoron=True, relief="flat")
            rb.grid(row=0, column=i, padx=(0, 24), sticky="w")

        # ── Barra de progreso + log ───────────────────────────────────────
        prog_frame = tk.Frame(body, bg=BG)
        prog_frame.pack(fill="x", pady=(12, 0))

        self.progress = ttk.Progressbar(prog_frame, mode="determinate", length=400)
        self.progress.pack(fill="x")

        self.log_var = tk.StringVar(value="Listo para unir.")
        tk.Label(prog_frame, textvariable=self.log_var, bg=BG, fg=GRAY,
                 font=("Helvetica", 9), anchor="w").pack(fill="x", pady=(4, 0))

        # ── Botón principal ───────────────────────────────────────────────
        self._btn(body, "🖨  Generar PDF", GOLD, ACCENT,
                  self._generate, font_size=12, pad_y=10).pack(fill="x", pady=(14, 0))

        self.files: list[Path] = []

    def _btn(self, parent, text, bg, fg, cmd, font_size=10, pad_y=6):
        return tk.Button(parent, text=text, bg=bg, fg=fg, relief="flat",
                         font=("Helvetica", font_size, "bold"),
                         activebackground=bg, activeforeground=fg,
                         cursor="hand2", padx=12, pady=pad_y, command=cmd)

    # ── Acciones ──────────────────────────────────────────────────────────────
    def _add_files(self):
        paths = filedialog.askopenfilenames(
            title="Seleccionar archivos",
            filetypes=[
                ("Todos los soportados", "*.jpg *.jpeg *.png *.bmp *.tiff *.gif *.webp *.txt *.docx"),
                ("Imágenes",  "*.jpg *.jpeg *.png *.bmp *.tiff *.gif *.webp"),
                ("Texto",     "*.txt"),
                ("Word",      "*.docx"),
                ("Todos",     "*.*"),
            ]
        )
        for p in paths:
            path = Path(p)
            if path not in self.files:
                self.files.append(path)
                self.listbox.insert("end", f"  {path.name}   ← {path.parent}")
        self._refresh_count()

    def _remove(self):
        sel = list(self.listbox.curselection())[::-1]
        for i in sel:
            self.listbox.delete(i)
            self.files.pop(i)
        self._refresh_count()

    def _move_up(self):
        sel = self.listbox.curselection()
        if not sel or sel[0] == 0: return
        for i in sel:
            j = i - 1
            self.files[i], self.files[j] = self.files[j], self.files[i]
            a, b = self.listbox.get(i), self.listbox.get(j)
            self.listbox.delete(j, i)
            self.listbox.insert(j, a)
            self.listbox.insert(i, b)
        self.listbox.selection_clear(0, "end")
        for i in sel: self.listbox.selection_set(i - 1)

    def _move_down(self):
        sel = self.listbox.curselection()
        if not sel or sel[-1] >= len(self.files) - 1: return
        for i in reversed(sel):
            j = i + 1
            self.files[i], self.files[j] = self.files[j], self.files[i]
            a, b = self.listbox.get(i), self.listbox.get(j)
            self.listbox.delete(i, j)
            self.listbox.insert(i, b)
            self.listbox.insert(j, a)
        self.listbox.selection_clear(0, "end")
        for i in sel: self.listbox.selection_set(i + 1)

    def _refresh_count(self):
        n = len(self.files)
        self.log_var.set(f"{n} archivo{'s' if n != 1 else ''} en la lista.")

    def _generate(self):
        if not self.files:
            messagebox.showwarning("Sin archivos", "Agrega al menos un archivo.")
            return

        output = filedialog.asksaveasfilename(
            title="Guardar PDF como",
            defaultextension=".pdf",
            filetypes=[("PDF", "*.pdf")],
            initialfile="documento_unido.pdf",
        )
        if not output: return

        self.progress["value"] = 0
        self.log_var.set("Iniciando...")
        self.update_idletasks()

        quality_key = self.quality_var.get()
        files_copy  = list(self.files)
        output_path = Path(output)

        def worker():
            try:
                build_pdf(
                    files_copy, output_path, quality_key,
                    progress_cb=lambda v: self.after(0, lambda: self._set_progress(v)),
                    log_cb=lambda m: self.after(0, lambda: self.log_var.set(m)),
                )
                self.after(0, lambda: self._done(output_path))
            except Exception as e:
                self.after(0, lambda: self._error(str(e)))

        threading.Thread(target=worker, daemon=True).start()

    def _set_progress(self, v):
        self.progress["value"] = int(v * 100)
        self.update_idletasks()

    def _done(self, path):
        self.progress["value"] = 100
        self.log_var.set(f"PDF generado: {path.name}  ({path.stat().st_size / 1024:.0f} KB)")
        if messagebox.askyesno("Listo", f"PDF creado correctamente.\n\n{path}\n\n¿Abrir el archivo?"):
            import os, subprocess
            try: os.startfile(str(path))
            except: subprocess.Popen(["xdg-open", str(path)])

    def _error(self, msg):
        self.progress["value"] = 0
        self.log_var.set(f"Error: {msg}")
        messagebox.showerror("Error", msg)


if __name__ == "__main__":
    app = App()
    app.mainloop()
