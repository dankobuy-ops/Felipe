'use strict';

const API = 'http://localhost:5000';
let scanData   = null;
let chartType  = null;
let chartFoldr = null;
let proposal   = [];

// ─── Helpers ──────────────────────────────────────────────────────────────────
function fmtBytes(bytes) {
  if (!bytes) return '0 B';
  const k = 1024, sizes = ['B','KB','MB','GB','TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
}

function catIcon(cat) {
  return { images:'🖼', documents:'📄', audio:'🎵', video:'🎬', other:'📦' }[cat] || '📦';
}

function cssVar(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

// ─── Connection check ─────────────────────────────────────────────────────────
async function checkConnection() {
  const pill         = document.getElementById('statusPill');
  const dot          = document.getElementById('statusDot');
  const text         = document.getElementById('statusText');
  const instructions = document.getElementById('backendInstructions');
  const btnScan      = document.getElementById('btnScan');

  try {
    const res = await fetch(`${API}/ping`, { signal: AbortSignal.timeout(2500) });
    if (res.ok) {
      pill.className       = 'status-pill online';
      dot.className        = 'status-dot';
      text.textContent     = 'Backend online';
      instructions?.classList.add('hidden');
      btnScan.disabled     = false;
      return true;
    }
  } catch { /* offline */ }

  pill.className       = 'status-pill offline';
  dot.className        = 'status-dot';
  text.textContent     = 'Backend offline';
  instructions?.classList.remove('hidden');
  btnScan.disabled     = true;
  return false;
}

// ─── Scan ─────────────────────────────────────────────────────────────────────
async function scanPath() {
  const path = document.getElementById('inputPath').value.trim();
  if (!path) { alert('Escribe una ruta válida (ej: D:\\ o C:\\Users\\Nombre)'); return; }

  const btn      = document.getElementById('btnScan');
  const progress = document.getElementById('scanProgress');

  btn.disabled     = true;
  btn.textContent  = '⏳ Escaneando…';
  progress.classList.remove('hidden');

  // Hide previous results
  document.getElementById('sectionDashboard').hidden  = true;
  document.getElementById('sectionOrganize').hidden   = true;
  document.getElementById('sectionResult').hidden     = true;

  try {
    const res  = await fetch(`${API}/scan`, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ path }),
    });
    const data = await res.json();

    if (!res.ok || data.error) { alert('Error: ' + (data.error || 'Sin respuesta')); return; }

    scanData = data;
    localStorage.setItem('lastScan', JSON.stringify({
      path, timestamp: Date.now(), total: data.total,
    }));
    document.getElementById('lastScanInfo').textContent =
      `Último escaneo: ${new Date().toLocaleString()} · ${data.total.toLocaleString()} archivos encontrados`;

    renderDashboard(data);
    buildProposal(data);

  } catch (e) {
    alert('No se pudo conectar al backend.\n' + e.message);
  } finally {
    btn.disabled    = false;
    btn.textContent = '🔍 Escanear';
    progress.classList.add('hidden');
  }
}

// ─── Dashboard ────────────────────────────────────────────────────────────────
function renderDashboard(data) {
  document.getElementById('sectionDashboard').hidden = false;
  document.getElementById('dashboardSub').textContent =
    `${data.total.toLocaleString()} archivos personales encontrados en ${data.root}`;

  // ── Aggregate ──
  const catSizes  = { images:0, documents:0, audio:0, video:0, other:0 };
  const catCounts = { images:0, documents:0, audio:0, video:0, other:0 };
  const folderMap = {};

  for (const f of data.files) {
    catSizes[f.category]  = (catSizes[f.category]  || 0) + f.size;
    catCounts[f.category] = (catCounts[f.category] || 0) + 1;
    const sep    = f.path.includes('\\') ? '\\' : '/';
    const folder = f.path.substring(0, f.path.lastIndexOf(sep));
    folderMap[folder] = (folderMap[folder] || 0) + f.size;
  }

  const totalSize = Object.values(catSizes).reduce((a,b) => a + b, 0);

  // ── KPIs ──
  document.getElementById('statTotal').textContent    = data.total.toLocaleString();
  document.getElementById('statSize').textContent     = fmtBytes(totalSize);
  document.getElementById('statFolders').textContent  = Object.keys(folderMap).length.toLocaleString();
  document.getElementById('countImages').textContent  = catCounts.images.toLocaleString();
  document.getElementById('countDocuments').textContent = catCounts.documents.toLocaleString();
  document.getElementById('countAudio').textContent   = catCounts.audio.toLocaleString();
  document.getElementById('countVideo').textContent   = catCounts.video.toLocaleString();

  // ── Donut chart ──
  const typeCtx = document.getElementById('chartTypes').getContext('2d');
  if (chartType) chartType.destroy();
  chartType = new Chart(typeCtx, {
    type: 'doughnut',
    data: {
      labels: ['🖼 Imágenes','📄 Documentos','🎵 Audio','🎬 Video','📦 Otros'],
      datasets: [{
        data: [catSizes.images, catSizes.documents, catSizes.audio, catSizes.video, catSizes.other]
              .map(v => +(v / 1024 / 1024).toFixed(1)),
        backgroundColor: ['#3b82f6','#0969da','#8b5cf6','#ef4444','#9ca3af'],
        borderWidth: 2,
        borderColor: 'transparent',
      }],
    },
    options: {
      responsive: false,
      plugins: {
        legend: {
          position: 'bottom',
          labels: { color: cssVar('--text'), font: { size: 11 }, padding: 10, boxWidth: 12 },
        },
        tooltip: { callbacks: { label: c => ` ${c.label}: ${fmtBytes(c.raw * 1024 * 1024)}` } },
      },
      cutout: '60%',
    },
  });

  // ── Bar chart (top folders) ──
  const topFolders = Object.entries(folderMap)
    .sort(([,a],[,b]) => b - a)
    .slice(0, 10);

  const folderCtx = document.getElementById('chartFolders').getContext('2d');
  if (chartFoldr) chartFoldr.destroy();
  chartFoldr = new Chart(folderCtx, {
    type: 'bar',
    data: {
      labels: topFolders.map(([p]) => {
        const parts = p.split(/[\\\/]/);
        return parts.slice(-2).join('/') || p;
      }),
      datasets: [{
        label: 'MB',
        data: topFolders.map(([,s]) => +(s / 1024 / 1024).toFixed(1)),
        backgroundColor: cssVar('--accent'),
        borderRadius: 4,
      }],
    },
    options: {
      indexAxis: 'y',
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: { label: c => ` ${fmtBytes(c.raw * 1024 * 1024)}` } },
      },
      scales: {
        x: {
          ticks: { color: cssVar('--muted') },
          grid:  { color: 'rgba(128,128,128,.1)' },
        },
        y: {
          ticks: { color: cssVar('--text'), font: { size: 11 } },
          grid:  { display: false },
        },
      },
    },
  });
}

// ─── Build proposal ───────────────────────────────────────────────────────────
function buildProposal(data) {
  const sep  = data.root.includes('\\') ? '\\' : '/';
  const root = data.root.endsWith(sep) ? data.root : data.root + sep;
  const dest = root + '_Organizado';

  proposal = data.files.map(f => ({
    src:      f.path,
    dst:      proposedDst(f, dest, sep),
    category: f.category,
    name:     f.name,
    size:     f.size,
  }));

  // Group by destination folder
  const groups = {};
  for (const move of proposal) {
    const folder = move.dst.substring(0, move.dst.lastIndexOf(sep));
    if (!groups[folder]) groups[folder] = [];
    groups[folder].push(move);
  }

  const container = document.getElementById('proposalTree');
  container.innerHTML = '';

  for (const [folder, moves] of Object.entries(groups).sort()) {
    const label = folder.replace(dest, '📁 _Organizado');
    const size  = moves.reduce((a,b) => a + b.size, 0);
    const el    = document.createElement('details');
    el.className = 'proposal-group';
    el.innerHTML = `
      <summary class="proposal-summary">
        <span class="proposal-folder">${label}</span>
        <span class="proposal-meta">${moves.length} archivo${moves.length !== 1 ? 's' : ''} · ${fmtBytes(size)}</span>
      </summary>
      <ul class="proposal-files">
        ${moves.slice(0, 50).map(m => `
          <li class="proposal-file">
            <span class="pf-icon">${catIcon(m.category)}</span>
            <span class="pf-name" title="${m.src}">${m.name}</span>
            <span class="pf-size">${fmtBytes(m.size)}</span>
          </li>`).join('')}
        ${moves.length > 50 ? `<li class="proposal-more">… y ${moves.length - 50} archivos más</li>` : ''}
      </ul>`;
    container.appendChild(el);
  }

  const groupCount = Object.keys(groups).length;
  document.getElementById('propSummary').textContent =
    `${proposal.length.toLocaleString()} archivos → ${groupCount} carpetas en _Organizado`;

  document.getElementById('sectionOrganize').hidden = false;
  document.getElementById('btnExecute').disabled    = proposal.length === 0;
}

function proposedDst(file, dest, sep) {
  const year = file.year || 'Sin_fecha';
  const name = file.name.toLowerCase();

  switch (file.category) {
    case 'images':    return `${dest}${sep}Imágenes${sep}${year}${sep}${file.name}`;
    case 'video':     return `${dest}${sep}Videos${sep}${year}${sep}${file.name}`;
    case 'audio':     return `${dest}${sep}Música${sep}${year}${sep}${file.name}`;
    case 'documents': {
      if (/factura|boleta|recibo|cotiz/.test(name))  return `${dest}${sep}Documentos${sep}Facturas${sep}${year}${sep}${file.name}`;
      if (/contrato|convenio|acuerdo/.test(name))    return `${dest}${sep}Documentos${sep}Contratos${sep}${file.name}`;
      if (/cv|curriculum|resume/.test(name))         return `${dest}${sep}Documentos${sep}CV${sep}${file.name}`;
      return `${dest}${sep}Documentos${sep}${year}${sep}${file.name}`;
    }
    default: return `${dest}${sep}Otros${sep}${year}${sep}${file.name}`;
  }
}

// ─── Execute ──────────────────────────────────────────────────────────────────
async function executeOrganize() {
  if (!proposal.length) return;

  const sep       = proposal[0].dst.includes('\\') ? '\\' : '/';
  const destRoot  = proposal[0].dst.split(sep + '_Organizado' + sep)[0] + sep + '_Organizado';

  const confirmed = confirm(
    `¿Confirmas mover ${proposal.length.toLocaleString()} archivos a:\n${destRoot}\n\n` +
    `Los originales serán MOVIDOS (no eliminados).\nPuedes deshacer moviendo la carpeta _Organizado de vuelta.`
  );
  if (!confirmed) return;

  const btn = document.getElementById('btnExecute');
  btn.disabled    = true;
  btn.textContent = '⏳ Organizando archivos…';

  try {
    const res  = await fetch(`${API}/organize`, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ moves: proposal }),
    });
    const data = await res.json();

    const section = document.getElementById('sectionResult');
    section.hidden = false;
    section.scrollIntoView({ behavior: 'smooth', block: 'start' });

    const msgEl = document.getElementById('resultMsg');
    if (data.done > 0) {
      msgEl.innerHTML = `
        <div class="result-success">
          <div class="result-icon">✅</div>
          <div>
            <p class="result-title">${data.done.toLocaleString()} archivo${data.done !== 1 ? 's' : ''} organizados correctamente</p>
            ${data.failed > 0
              ? `<p class="result-sub">⚠️ ${data.failed} archivo${data.failed !== 1 ? 's' : ''} no pudieron moverse — revisa permisos</p>`
              : '<p class="result-sub">Todos los archivos fueron movidos sin errores.</p>'}
          </div>
        </div>`;
    } else {
      const errs = (data.errors || []).map(e => `${e.src}: ${e.reason}`).join('\n');
      msgEl.innerHTML = `
        <div class="result-error">
          <div class="result-icon">❌</div>
          <div>
            <p class="result-title">No se pudo organizar ningún archivo</p>
            ${errs ? `<pre class="result-errors">${errs}</pre>` : ''}
          </div>
        </div>`;
    }
  } catch (e) {
    alert('Error al ejecutar: ' + e.message);
  } finally {
    btn.disabled    = false;
    btn.textContent = '🚀 Ejecutar Ordenamiento Seguro';
  }
}

// ─── Init ─────────────────────────────────────────────────────────────────────
const lastScan = JSON.parse(localStorage.getItem('lastScan') || 'null');
if (lastScan?.path) {
  document.getElementById('inputPath').value = lastScan.path;
  const ago = Math.round((Date.now() - lastScan.timestamp) / 60000);
  document.getElementById('lastScanInfo').textContent =
    `Último escaneo: hace ${ago < 60 ? ago + ' min' : Math.round(ago/60) + ' h'} · ${(lastScan.total || 0).toLocaleString()} archivos`;
}

checkConnection();
setInterval(checkConnection, 5000);
