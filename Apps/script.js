'use strict';

// ─── State ──────────────────────────────────────────────────────────────────
const files = []; // { file: File, id: number }
let nextId = 0;

// ─── DOM refs ────────────────────────────────────────────────────────────────
const schemaInput   = document.getElementById('schema-name');
const previewName   = document.getElementById('preview-name');
const dropZone      = document.getElementById('drop-zone');
const fileInput     = document.getElementById('file-input');
const fileListEl    = document.getElementById('file-list');
const clearBtn      = document.getElementById('clear-btn');
const processBtn    = document.getElementById('process-btn');
const logCard       = document.getElementById('log-card');
const logTitle      = document.getElementById('log-title');
const logStatusIcon = document.getElementById('log-status-icon');
const logList       = document.getElementById('log-list');
const logFooter     = document.getElementById('log-footer');
const logSummary    = document.getElementById('log-summary');

// ─── Schema name → preview ───────────────────────────────────────────────────
schemaInput.addEventListener('input', () => {
  const v = schemaInput.value.trim();
  previewName.textContent = v ? `${sanitizeName(v)}_consolidado.csv` : 'esquema_consolidado.csv';
});

function sanitizeName(name) {
  return name.replace(/[\\/:*?"<>|]/g, '_').replace(/\s+/g, '_');
}

// ─── Drag & Drop ─────────────────────────────────────────────────────────────
dropZone.addEventListener('click', () => fileInput.click());
dropZone.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') fileInput.click(); });

dropZone.addEventListener('dragover', e => {
  e.preventDefault();
  dropZone.classList.add('dragover');
});
dropZone.addEventListener('dragleave', () => dropZone.classList.remove('dragover'));
dropZone.addEventListener('drop', e => {
  e.preventDefault();
  dropZone.classList.remove('dragover');
  addFiles([...e.dataTransfer.files]);
});

fileInput.addEventListener('change', () => {
  addFiles([...fileInput.files]);
  fileInput.value = '';
});

// ─── File management ─────────────────────────────────────────────────────────
function addFiles(incoming) {
  const csvFiles = incoming.filter(f => f.name.toLowerCase().endsWith('.csv'));
  const rejected = incoming.length - csvFiles.length;

  if (rejected > 0) {
    log(`⚠ ${rejected} archivo(s) ignorado(s): solo se aceptan .csv`, 'warn');
  }

  csvFiles.forEach(f => {
    const alreadyAdded = files.some(entry => entry.file.name === f.name && entry.file.size === f.size);
    if (alreadyAdded) {
      log(`— "${f.name}" ya está en la lista, omitido.`, 'warn');
      return;
    }
    const id = nextId++;
    files.push({ file: f, id });
    renderFileItem(f, id);
  });

  updateUI();
}

function removeFile(id) {
  const idx = files.findIndex(e => e.id === id);
  if (idx !== -1) files.splice(idx, 1);
  const el = document.querySelector(`[data-file-id="${id}"]`);
  if (el) el.remove();
  if (files.length === 0) fileListEl.hidden = true;
  updateUI();
}

function renderFileItem(file, id) {
  fileListEl.hidden = false;
  const li = document.createElement('li');
  li.className = 'file-item';
  li.dataset.fileId = id;
  li.innerHTML = `
    <span class="file-item__icon">📄</span>
    <span class="file-item__name" title="${escapeHtml(file.name)}">${escapeHtml(file.name)}</span>
    <span class="file-item__size">${formatBytes(file.size)}</span>
    <button class="file-item__remove" title="Quitar archivo" aria-label="Quitar ${escapeHtml(file.name)}">✕</button>
  `;
  li.querySelector('.file-item__remove').addEventListener('click', () => removeFile(id));
  fileListEl.appendChild(li);
}

function updateUI() {
  const hasFiles = files.length > 0;
  clearBtn.disabled   = !hasFiles;
  processBtn.disabled = !hasFiles;
}

// ─── Clear ───────────────────────────────────────────────────────────────────
clearBtn.addEventListener('click', () => {
  files.length = 0;
  fileListEl.innerHTML = '';
  fileListEl.hidden = true;
  logCard.hidden = true;
  logList.innerHTML = '';
  logFooter.hidden = true;
  updateUI();
});

// ─── Process ─────────────────────────────────────────────────────────────────
processBtn.addEventListener('click', processFiles);

async function processFiles() {
  if (files.length === 0) return;

  const rawSchema = schemaInput.value.trim();
  if (!rawSchema) {
    alert('Por favor, escribe el nombre del esquema o grupo antes de consolidar.');
    schemaInput.focus();
    return;
  }

  const schemaName = sanitizeName(rawSchema);

  // Reset log
  logCard.hidden = false;
  logList.innerHTML = '';
  logFooter.hidden = true;
  logStatusIcon.textContent = '🔄';
  logTitle.textContent = 'Procesando…';

  processBtn.disabled = true;
  clearBtn.disabled   = true;

  log(`Iniciando consolidación de ${files.length} archivo(s)…`, 'info');

  const chunks = [];
  let globalHeader = null;
  let totalRows = 0;
  let errors = 0;

  for (let i = 0; i < files.length; i++) {
    const { file } = files[i];
    const origin = fileNameWithoutExt(file.name);
    log(`Leyendo: ${file.name} (${formatBytes(file.size)})`);

    try {
      const text = await readFileUTF8(file);
      const rows = parseCSV(text);

      if (rows.length === 0) {
        log(`⚠ "${file.name}" está vacío o sin datos, omitido.`, 'warn');
        errors++;
        continue;
      }

      const header = rows[0];
      const dataRows = rows.slice(1).filter(r => r.some(cell => cell !== ''));

      if (i === 0) {
        // First file: write header with "Origen" prepended
        globalHeader = ['Origen', ...header];
        chunks.push(rowToCSV(globalHeader));
        log(`  Esquema detectado: ${header.length} columna(s)`, 'info');
      } else {
        // Validate column count (warn but continue)
        if (header.length !== (globalHeader.length - 1)) {
          log(`⚠ "${file.name}" tiene ${header.length} columnas vs ${globalHeader.length - 1} esperadas — se incluye de todas formas.`, 'warn');
        }
      }

      for (const row of dataRows) {
        chunks.push(rowToCSV([origin, ...row]));
        totalRows++;
      }

      log(`  ✓ ${dataRows.length} fila(s) añadidas`, 'ok');

    } catch (err) {
      log(`✗ Error leyendo "${file.name}": ${err.message}`, 'error');
      errors++;
    }
  }

  if (chunks.length <= 1) {
    log('No se encontraron datos válidos para consolidar.', 'error');
    logStatusIcon.textContent = '❌';
    logTitle.textContent = 'Sin resultados';
    processBtn.disabled = false;
    clearBtn.disabled   = false;
    return;
  }

  // Build CSV content with UTF-8 BOM for Excel compatibility
  const csvContent = '﻿' + chunks.join('\n');
  const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
  const filename = `${schemaName}_consolidado.csv`;

  downloadBlob(blob, filename);

  const warnMsg = errors > 0 ? ` (${errors} archivo(s) con advertencias)` : '';
  log(`Archivo listo: ${filename}`, 'ok');

  logStatusIcon.textContent = '✅';
  logTitle.textContent = 'Completado';
  logFooter.hidden = false;
  logSummary.textContent = `✓ ${totalRows.toLocaleString()} filas consolidadas de ${files.length} archivo(s) → ${filename}${warnMsg}`;

  processBtn.disabled = false;
  clearBtn.disabled   = false;
}

// ─── CSV Parser ───────────────────────────────────────────────────────────────
// Handles quoted fields, embedded commas, and embedded newlines.
function parseCSV(text) {
  const rows = [];
  const normalized = text.replace(/\r\n/g, '\n').replace(/\r/g, '\n').trimEnd();
  if (!normalized) return rows;

  let row = [];
  let i = 0;
  const n = normalized.length;

  while (i < n) {
    if (normalized[i] === '"') {
      // Quoted field
      i++; // skip opening quote
      let field = '';
      while (i < n) {
        if (normalized[i] === '"') {
          if (normalized[i + 1] === '"') {
            field += '"';
            i += 2;
          } else {
            i++; // skip closing quote
            break;
          }
        } else {
          field += normalized[i++];
        }
      }
      row.push(field);
      // Skip comma or newline after closing quote
      if (normalized[i] === ',') i++;
      else if (normalized[i] === '\n') { rows.push(row); row = []; i++; }
    } else {
      // Unquoted field
      let field = '';
      while (i < n && normalized[i] !== ',' && normalized[i] !== '\n') {
        field += normalized[i++];
      }
      row.push(field.trim());
      if (normalized[i] === ',') i++;
      else if (normalized[i] === '\n') { rows.push(row); row = []; i++; }
    }
  }
  if (row.length > 0) rows.push(row);

  return rows;
}

// ─── CSV Writer ───────────────────────────────────────────────────────────────
function rowToCSV(fields) {
  return fields.map(f => {
    const s = String(f == null ? '' : f);
    if (s.includes(',') || s.includes('"') || s.includes('\n') || s.includes('\r')) {
      return '"' + s.replace(/"/g, '""') + '"';
    }
    return s;
  }).join(',');
}

// ─── File reader (UTF-8) ──────────────────────────────────────────────────────
function readFileUTF8(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload  = e => resolve(e.target.result);
    reader.onerror = () => reject(new Error('Error de lectura'));
    reader.readAsText(file, 'UTF-8');
  });
}

// ─── Download ─────────────────────────────────────────────────────────────────
function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  setTimeout(() => URL.revokeObjectURL(url), 10_000);
}

// ─── Log helper ───────────────────────────────────────────────────────────────
function log(msg, type = '') {
  const li = document.createElement('li');
  li.className = 'log-entry' + (type ? ` log-entry--${type}` : '');
  li.textContent = msg;
  logList.appendChild(li);
  logList.scrollTop = logList.scrollHeight;
}

// ─── Utilities ────────────────────────────────────────────────────────────────
function fileNameWithoutExt(name) {
  return name.replace(/\.csv$/i, '');
}

function formatBytes(bytes) {
  if (bytes < 1024) return bytes + ' B';
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
  return (bytes / (1024 * 1024)).toFixed(2) + ' MB';
}

function escapeHtml(str) {
  return str.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}
