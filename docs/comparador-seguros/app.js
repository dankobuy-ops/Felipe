const AppState = {
  policies: []
};

function dispatch(type, payload) {
  switch (type) {
    case 'ADD_POLICY':
      AppState.policies.push(payload);
      break;
    case 'UPDATE_POLICY': {
      const idx = AppState.policies.findIndex(p => p.id === payload.id);
      if (idx !== -1) AppState.policies[idx] = { ...AppState.policies[idx], ...payload };
      break;
    }
    case 'CLEAR_ALL':
      AppState.policies = [];
      break;
  }
  render();
}

function render() {
  UIRenderer.renderAll(AppState.policies);
  updateUploadActions();
}

function updateUploadActions() {
  const actions = document.getElementById('uploadActions');
  const notice = document.getElementById('privacyNotice');
  const section = document.getElementById('resultsSection');
  const hasPolicies = AppState.policies.length > 0;
  const hasPending = AppState.policies.some(p => p.status === 'pending');
  const isProcessing = AppState.policies.some(p => ['extracting', 'analyzing'].includes(p.status));

  if (actions) {
    actions.style.display = hasPolicies ? 'flex' : 'none';
    const btnAnalyze = document.getElementById('btnAnalyze');
    if (btnAnalyze) {
      btnAnalyze.disabled = !hasPending || isProcessing;
      btnAnalyze.textContent = isProcessing ? '⏳ Analizando...' : '🔍 Analizar';
    }
  }

  if (notice) notice.style.display = hasPolicies ? 'block' : 'none';
  if (section) section.style.display = hasPolicies ? 'block' : 'none';
}

function mapError(err) {
  const msg = err.message || '';
  if (msg === 'INVALID_FILE_TYPE') return 'Solo se aceptan archivos PDF (.pdf)';
  if (msg === 'FILE_TOO_LARGE') return `El archivo supera el límite de ${CONFIG.PDF_MAX_SIZE_MB}MB`;
  if (msg === 'PDF_ENCRYPTED') return 'El PDF está protegido con contraseña. Quítala e intenta de nuevo';
  if (msg === 'PDF_LOAD_ERROR') return 'No se pudo abrir el PDF. Verifica que no esté dañado';
  if (msg === 'PDF_LIB_NOT_LOADED') return 'Error al cargar la librería PDF. Recarga la página';
  if (msg.startsWith('PARSE_ERROR')) return 'Error al procesar el documento. Intenta de nuevo';
  return `Error: ${msg.split('|')[0]}`;
}

function showToast(message, type = 'info') {
  const container = document.getElementById('toastContainer');
  if (!container) return;
  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  toast.textContent = message;
  container.appendChild(toast);
  requestAnimationFrame(() => toast.classList.add('toast-visible'));
  setTimeout(() => {
    toast.classList.remove('toast-visible');
    setTimeout(() => toast.remove(), 300);
  }, 4000);
}

async function processFiles(files) {
  for (const file of files) {
    const id = crypto.randomUUID();
    dispatch('ADD_POLICY', {
      id, fileName: file.name, rawText: '', pageCount: 0,
      extractionMethod: 'text', analysis: null, status: 'pending', error: null
    });

    dispatch('UPDATE_POLICY', { id, status: 'extracting' });

    let extracted;
    try {
      extracted = await PdfHandler.extractText(file);
    } catch (err) {
      dispatch('UPDATE_POLICY', { id, status: 'error', error: mapError(err) });
      showToast(`Error en ${file.name}: ${mapError(err)}`, 'error');
      continue;
    }

    dispatch('UPDATE_POLICY', {
      id,
      rawText: extracted.text,
      pageCount: extracted.pageCount,
      extractionMethod: extracted.extractionMethod,
      status: 'analyzing'
    });

    try {
      const analysis = await ClaudeAPI.analyzePolicy(
        extracted.text,
        file.name,
        extracted.extractionMethod
      );
      dispatch('UPDATE_POLICY', { id, analysis, status: 'done' });
    } catch (err) {
      dispatch('UPDATE_POLICY', { id, status: 'error', error: mapError(err) });
      showToast(`Error al analizar ${file.name}: ${mapError(err)}`, 'error');
    }
  }
}

function addFilesToQueue(files) {
  const currentCount = AppState.policies.length;
  const available = CONFIG.PDF_MAX_FILES - currentCount;

  if (available <= 0) {
    showToast(`Máximo ${CONFIG.PDF_MAX_FILES} pólizas simultáneas`, 'warning');
    return;
  }

  const toAdd = Array.from(files).slice(0, available);
  if (toAdd.length < files.length) {
    showToast(`Solo se agregarán ${toAdd.length} de ${files.length} archivos (límite: ${CONFIG.PDF_MAX_FILES})`, 'warning');
  }

  for (const file of toAdd) {
    const id = crypto.randomUUID();
    dispatch('ADD_POLICY', {
      id, fileName: file.name, rawText: '', pageCount: 0,
      extractionMethod: 'text', analysis: null, status: 'pending', error: null,
      _file: file
    });
  }

  renderFileList();
}

function renderFileList() {
  const list = document.getElementById('fileList');
  if (!list) return;

  const pending = AppState.policies.filter(p => p.status === 'pending');
  if (!pending.length) {
    list.innerHTML = '';
    return;
  }

  list.innerHTML = pending.map(p => `
    <div class="file-chip" id="chip-${p.id}">
      <span class="file-chip-icon">📄</span>
      <span class="file-chip-name">${escapeHtml(p.fileName)}</span>
      <button class="file-chip-remove" data-id="${p.id}" title="Quitar">✕</button>
    </div>`).join('');

  list.querySelectorAll('.file-chip-remove').forEach(btn => {
    btn.addEventListener('click', () => {
      AppState.policies = AppState.policies.filter(p => p.id !== btn.dataset.id);
      renderFileList();
      updateUploadActions();
    });
  });
}

function escapeHtml(str) {
  return (str || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function initDragAndDrop() {
  const dropZone = document.getElementById('dropZone');
  const fileInput = document.getElementById('fileInput');

  dropZone.addEventListener('click', () => fileInput.click());

  dropZone.addEventListener('dragover', e => {
    e.preventDefault();
    dropZone.classList.add('drag-over');
  });

  dropZone.addEventListener('dragleave', e => {
    if (!dropZone.contains(e.relatedTarget)) {
      dropZone.classList.remove('drag-over');
    }
  });

  dropZone.addEventListener('drop', e => {
    e.preventDefault();
    dropZone.classList.remove('drag-over');
    const files = Array.from(e.dataTransfer.files).filter(f =>
      f.name.toLowerCase().endsWith('.pdf') || f.type === 'application/pdf'
    );
    if (!files.length) {
      showToast('Solo se aceptan archivos PDF', 'warning');
      return;
    }
    addFilesToQueue(files);
    updateUploadActions();
  });

  fileInput.addEventListener('change', () => {
    if (fileInput.files.length) {
      addFilesToQueue(fileInput.files);
      fileInput.value = '';
      updateUploadActions();
    }
  });
}

function initButtons() {
  document.getElementById('btnAnalyze')?.addEventListener('click', async () => {
    const pending = AppState.policies.filter(p => p.status === 'pending');
    if (!pending.length) return;

    const files = pending.map(p => p._file).filter(Boolean);

    AppState.policies = AppState.policies.filter(p => p.status !== 'pending');
    renderFileList();

    document.getElementById('resultsSection').style.display = 'block';

    await processFiles(files);
  });

  document.getElementById('btnClear')?.addEventListener('click', () => {
    dispatch('CLEAR_ALL');
    renderFileList();
    document.getElementById('fileList').innerHTML = '';
    document.getElementById('resultsSection').style.display = 'none';
  });
}

document.addEventListener('DOMContentLoaded', () => {
  PdfHandler.init();
  initDragAndDrop();
  initButtons();
});
