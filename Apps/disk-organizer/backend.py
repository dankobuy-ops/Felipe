#!/usr/bin/env python3
"""
Disk Organizer — Backend local  v1.1
======================================
Uso (Python):
    pip install flask
    python backend.py

Uso (ejecutable compilado):
    Doble clic en backend.exe  — no requiere Python instalado

Compilar con PyInstaller:
    pip install pyinstaller
    pyinstaller --onefile --name backend backend.py

Escucha en http://localhost:5000
"""

import os
import sys
import shutil
from pathlib import Path
from datetime import datetime
from flask import Flask, request, jsonify

app = Flask(__name__)

# ─── CORS ─────────────────────────────────────────────────────────────────────
# Acepta peticiones desde GitHub Pages y desde localhost (dev)
ALLOWED_ORIGINS = {
    'https://dankobuy-ops.github.io',
    'http://localhost',
    'http://localhost:5000',
    'http://127.0.0.1',
    'null',   # file:// abierto directamente en el browser
}

@app.after_request
def add_cors(response):
    origin = request.headers.get('Origin', '')
    # Permite el origen exacto si está en la lista, o cualquier localhost
    if origin in ALLOWED_ORIGINS or origin.startswith('http://localhost:') or origin.startswith('http://127.0.0.1:'):
        response.headers['Access-Control-Allow-Origin']  = origin
        response.headers['Vary'] = 'Origin'
    else:
        # Fallback permisivo para que funcione sin importar cómo se sirva la web
        response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    return response

@app.route('/', defaults={'path': ''}, methods=['OPTIONS'])
@app.route('/<path:path>', methods=['OPTIONS'])
def options_handler(path):
    return '', 204

# ─── Configuración ────────────────────────────────────────────────────────────
PERSONAL_EXTS = {
    'images':    {'.jpg','.jpeg','.png','.gif','.bmp','.webp','.heic','.tiff','.raw','.cr2','.nef'},
    'documents': {'.pdf','.docx','.doc','.xlsx','.xls','.pptx','.ppt','.txt','.csv','.odt','.rtf','.pages','.numbers'},
    'audio':     {'.mp3','.wav','.flac','.aac','.ogg','.m4a','.wma','.opus','.alac'},
    'video':     {'.mp4','.mkv','.avi','.mov','.wmv','.flv','.m4v','.ts','.vob','.webm','.3gp'},
}

ALL_PERSONAL_EXTS = {ext for exts in PERSONAL_EXTS.values() for ext in exts}

SYSTEM_DIRS = {
    'windows', 'program files', 'program files (x86)', 'programdata',
    'appdata', '$recycle.bin', 'system volume information', 'boot',
    'recovery', 'perflogs', 'intel', 'amd', 'nvidia', 'msocache',
    'winsxs', 'syswow64', 'system32', 'drivers', 'inf', 'assembly',
    '__pycache__', 'node_modules', '.git', 'venv', '.venv', 'env',
    '.vs', 'obj', 'bin', 'packages', 'vendor',
}

def get_category(ext: str) -> str:
    ext = ext.lower()
    for cat, exts in PERSONAL_EXTS.items():
        if ext in exts:
            return cat
    return 'other'

def skip_dir(name: str) -> bool:
    return name.lower() in SYSTEM_DIRS or name.startswith('.')

# ─── GET /ping  (health check ligero) ────────────────────────────────────────
@app.route('/ping', methods=['GET'])
def ping():
    return jsonify({'ok': True, 'version': '1.1'}), 200

# ─── POST /scan ───────────────────────────────────────────────────────────────
@app.route('/scan', methods=['POST'])
def scan():
    body     = request.get_json(silent=True) or {}
    raw_path = body.get('path', '').strip()

    if not raw_path:
        return jsonify({'error': 'Ruta no especificada'}), 400

    root = Path(raw_path)
    if not root.exists():
        return jsonify({'error': f'Ruta no encontrada: {raw_path}'}), 400
    if not root.is_dir():
        return jsonify({'error': f'No es una carpeta: {raw_path}'}), 400

    files, skipped = [], []

    try:
        for dirpath, dirnames, filenames in os.walk(str(root), topdown=True):
            dirnames[:] = [d for d in dirnames if not skip_dir(d)]

            for fname in filenames:
                ext = Path(fname).suffix.lower()
                if ext not in ALL_PERSONAL_EXTS:
                    continue
                fpath = Path(dirpath) / fname
                try:
                    stat  = fpath.stat()
                    mtime = datetime.fromtimestamp(stat.st_mtime)
                    files.append({
                        'path':     str(fpath),
                        'name':     fname,
                        'ext':      ext,
                        'category': get_category(ext),
                        'size':     stat.st_size,
                        'year':     mtime.year,
                        'modified': mtime.strftime('%Y-%m-%d'),
                    })
                except (PermissionError, OSError):
                    skipped.append(str(fpath))

    except PermissionError:
        return jsonify({'error': f'Sin permisos para leer: {raw_path}'}), 403

    return jsonify({'root': str(root), 'total': len(files), 'files': files, 'skipped': skipped[:30]})

# ─── POST /organize ───────────────────────────────────────────────────────────
@app.route('/organize', methods=['POST'])
def organize():
    body  = request.get_json(silent=True) or {}
    moves = body.get('moves', [])

    if not moves:
        return jsonify({'error': 'Sin movimientos especificados'}), 400

    done, failed = [], []

    for move in moves:
        src = Path(move.get('src', ''))
        dst = Path(move.get('dst', ''))

        if not src.exists():
            failed.append({'src': str(src), 'reason': 'Archivo no encontrado'})
            continue
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            final_dst = dst
            if final_dst.exists():
                stem, suffix, counter = dst.stem, dst.suffix, 1
                while final_dst.exists():
                    final_dst = dst.parent / f'{stem}_{counter}{suffix}'
                    counter += 1
            shutil.move(str(src), str(final_dst))
            done.append({'src': str(src), 'dst': str(final_dst)})
        except PermissionError:
            failed.append({'src': str(src), 'reason': 'Sin permisos'})
        except Exception as e:
            failed.append({'src': str(src), 'reason': str(e)})

    return jsonify({'done': len(done), 'failed': len(failed), 'moved': done, 'errors': failed})

# ─── Main ─────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    # Cuando se compila con PyInstaller --onefile, sys.frozen == True
    is_exe = getattr(sys, 'frozen', False)

    print('╔══════════════════════════════════════════╗')
    print('║      🗂  Disk Organizer — Backend  v1.1  ║')
    print('╠══════════════════════════════════════════╣')
    print('║   Escuchando en http://localhost:5000    ║')
    print('║   Mantén esta ventana abierta            ║')
    print('║   Ciérrala para detener el servidor      ║')
    print('╚══════════════════════════════════════════╝')

    # debug=False es obligatorio para .exe (no hay recarga de módulos en PyInstaller)
    app.run(host='localhost', port=5000, debug=False, use_reloader=False)
