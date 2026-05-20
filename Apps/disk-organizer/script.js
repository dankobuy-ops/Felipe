'use strict';

const API = 'http://localhost:5000';
let scanData   = null;
let chartType  = null;
let chartFoldr = null;
let proposal   = [];
let pollTimer  = null;   // intervalo de reintento automático mientras offline

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

// ─── Estado UI ────────────────────────────────────────────────────────────────
function showConnected() {
  // Navbar pill
  const pill = document.getElementById('statusPill');
  const text = document.getElementById('statusText');
  pill.className   = 'status-pill online';
  text.textContent = 'Motor conectado';

  // Paneles
  document.getElementById('assistantPanel').hidden = true;
  document.getElementById('scanPanel').hidden      = false;

  // Detener polling automático
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
}

function showDisconnected() {
  // Navbar pill
  const pill = document.getElementById('statusPill');
  const text = document.getElementById('statusText');
  pill.className   = 'status-pill offline';
  text.textContent = 'Motor offline';

  // Paneles
  document.getElementById('assistantPanel').hidden = false;
  document.getElementById('scanPanel').hidden      = true;

  // Iniciar polling automático (cada 5 s) para detectar cuando arranquen el .exe
  if (!pollTimer) {
    pollTimer = setInterval(async () => {
      const ok = await pingBackend();
      if (ok) showConnected();
    }, 5000);
  }
}

// ─── Ping al backend ─────────────────────────────────────────────────────────
async function pingBackend() {
  try {
    const res = await fetch(`${API}/ping`, { signal: AbortSignal.timeout(2500) });
    return res.ok;
  } catch {
    return false;
  }
}

// ─── Check silencioso al cargar ───────────────────────────────────────────────
async function initialCheck() {
  const ok = await pingBackend();
  ok ? showConnected() : showDisconnected();
}

// ─── Botón "Verificar Conexión" (Paso 3 del asistente) ───────────────────────
async function verifyConnection() {
  const btn     = document.getElementById('btnVerify');
  const spinner = document.getElementById('verifySpinner');
  const label   = document.getElementById('verifyLabel');
  const errMsg  = document.getElementById('verifyError');

  // Estado: cargando
  btn.disabled = true;
  spinner.classList.remove('hidden');
  label.textContent = 'Verificando…';
  errMsg.classList.add('hidden');

  const ok = await pingBackend();

  if (ok) {
    showConnected();
  } else {
    // Estado: error
    spinner.classList.add('hidden');
    label.textContent = '🔌 Verificar Conexión';
    errMsg.classList.remove('hidden');
    btn.disabled = false;
  }
}

// ─── Escaneo ──────────────────────────────────────────────────────────────────
async function scanPath() {
  const path = document.getElementById('inputPath').value.trim();
  if (!path) { alert('Escribe una ruta válida (ej: D:\\ o C:\\Users\\Nombre)'); return; }

  const btn      = document.getElementById('btnScan');
  const progress = document.getElementById('scanProgress');

  btn.disabled    = true;
  btn.textContent = '⏳ Escaneando…';
  progress.classList.remove('hidden');

  document.getElementById('sectionDashboard').hidden = true;
  document.getElementById('sectionOrganize').hidden  = true;
  document.getElementById('sectionResult').hidden    = true;

  try {
    const res  = await fetch(`${API}/scan`, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ path }),
    });
    const data = await res.json();
    if (!res.ok || data.error) { alert('Error: ' + (data.error || 'Sin respuesta')); return; }

    scanData = data;
    localStorage.setItem('lastScan', JSON.stringify({ path, timestamp: Date.now(), total: data.total }));
    document.getElementById('lastScanInfo').textContent =
      `Último escaneo: ${new Date().toLocaleString()} · ${data.total.toLocaleString()} archivos`;

    renderDashboard(data);
    buildProposal(data);
  } catch (e) {
    // Si falla el scan, el backend se cayó — volver al asistente
    showDisconnected();
    alert('Se perdió la conexión con el motor local.\n' + e.message);
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
    `${data.total.toLocaleString()} archivos personales en ${data.root}`;

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

  const totalSize = Object.values(catSizes).reduce((a,b) => a+b, 0);
  document.getElementById('statTotal').textContent    = data.total.toLocaleString();
  document.getElementById('statSize').textContent     = fmtBytes(totalSize);
  document.getElementById('statFolders').textContent  = Object.keys(folderMap).length.toLocaleString();
  document.getElementById('countImages').textContent  = catCounts.images.toLocaleString();
  document.getElementById('countDocuments').textContent = catCounts.documents.toLocaleString();
  document.getElementById('countAudio').textContent   = catCounts.audio.toLocaleString();
  document.getElementById('countVideo').textContent   = catCounts.video.toLocaleString();

  // Donut
  const typeCtx = document.getElementById('chartTypes').getContext('2d');
  if (chartType) chartType.destroy();
  chartType = new Chart(typeCtx, {
    type: 'doughnut',
    data: {
      labels: ['🖼 Imágenes','📄 Documentos','🎵 Audio','🎬 Video','📦 Otros'],
      datasets: [{
        data: [catSizes.images, catSizes.documents, catSizes.audio, catSizes.video, catSizes.other]
              .map(v => +(v/1024/1024).toFixed(1)),
        backgroundColor: ['#3b82f6','#0969da','#8b5cf6','#ef4444','#9ca3af'],
        borderWidth: 2, borderColor: 'transparent',
      }],
    },
    options: {
      responsive: false,
      plugins: {
        legend: { position:'bottom', labels:{ color:cssVar('--text'), font:{size:11}, padding:10, boxWidth:12 } },
        tooltip: { callbacks:{ label: c => ` ${c.label}: ${fmtBytes(c.raw*1024*1024)}` } },
      },
      cutout: '60%',
    },
  });

  // Barras top carpetas
  const topFolders = Object.entries(folderMap).sort(([,a],[,b])=>b-a).slice(0,10);
  const folderCtx  = document.getElementById('chartFolders').getContext('2d');
  if (chartFoldr) chartFoldr.destroy();
  chartFoldr = new Chart(folderCtx, {
    type: 'bar',
    data: {
      labels: topFolders.map(([p]) => { const parts = p.split(/[\\\/]/); return parts.slice(-2).join('/') || p; }),
      datasets: [{ label:'MB', data: topFolders.map(([,s]) => +(s/1024/1024).toFixed(1)),
        backgroundColor: cssVar('--accent'), borderRadius: 4 }],
    },
    options: {
      indexAxis: 'y', responsive: true, maintainAspectRatio: false,
      plugins: { legend:{display:false}, tooltip:{ callbacks:{ label:c=>` ${fmtBytes(c.raw*1024*1024)}` } } },
      scales: {
        x: { ticks:{color:cssVar('--muted')}, grid:{color:'rgba(128,128,128,.1)'} },
        y: { ticks:{color:cssVar('--text'), font:{size:11}}, grid:{display:false} },
      },
    },
  });
}

// ─── Propuesta ────────────────────────────────────────────────────────────────
function buildProposal(data) {
  const sep  = data.root.includes('\\') ? '\\' : '/';
  const root = data.root.endsWith(sep) ? data.root : data.root + sep;
  const dest = root + '_Organizado';

  proposal = data.files.map(f => ({
    src: f.path, dst: proposedDst(f, dest, sep),
    category: f.category, name: f.name, size: f.size,
  }));

  const groups = {};
  for (const m of proposal) {
    const folder = m.dst.substring(0, m.dst.lastIndexOf(sep));
    if (!groups[folder]) groups[folder] = [];
    groups[folder].push(m);
  }

  const container = document.getElementById('proposalTree');
  container.innerHTML = '';

  for (const [folder, moves] of Object.entries(groups).sort()) {
    const label = folder.replace(dest, '📁 _Organizado');
    const size  = moves.reduce((a,b) => a+b.size, 0);
    const el    = document.createElement('details');
    el.className = 'proposal-group';
    el.innerHTML = `
      <summary class="proposal-summary">
        <span class="proposal-folder">${label}</span>
        <span class="proposal-meta">${moves.length} archivo${moves.length!==1?'s':''} · ${fmtBytes(size)}</span>
      </summary>
      <ul class="proposal-files">
        ${moves.slice(0,50).map(m=>`
          <li class="proposal-file">
            <span class="pf-icon">${catIcon(m.category)}</span>
            <span class="pf-name" title="${m.src}">${m.name}</span>
            <span class="pf-size">${fmtBytes(m.size)}</span>
          </li>`).join('')}
        ${moves.length>50?`<li class="proposal-more">… y ${moves.length-50} archivos más</li>`:''}
      </ul>`;
    container.appendChild(el);
  }

  document.getElementById('propSummary').textContent =
    `${proposal.length.toLocaleString()} archivos → ${Object.keys(groups).length} carpetas en _Organizado`;
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
    case 'documents':
      if (/factura|boleta|recibo|cotiz/.test(name))  return `${dest}${sep}Documentos${sep}Facturas${sep}${year}${sep}${file.name}`;
      if (/contrato|convenio|acuerdo/.test(name))    return `${dest}${sep}Documentos${sep}Contratos${sep}${file.name}`;
      if (/cv|curriculum|resume/.test(name))         return `${dest}${sep}Documentos${sep}CV${sep}${file.name}`;
      return `${dest}${sep}Documentos${sep}${year}${sep}${file.name}`;
    default: return `${dest}${sep}Otros${sep}${year}${sep}${file.name}`;
  }
}

// ─── Ejecutar ─────────────────────────────────────────────────────────────────
async function executeOrganize() {
  if (!proposal.length) return;
  const sep      = proposal[0].dst.includes('\\') ? '\\' : '/';
  const destRoot = proposal[0].dst.split(sep+'_Organizado'+sep)[0] + sep + '_Organizado';

  if (!confirm(
    `¿Confirmas mover ${proposal.length.toLocaleString()} archivos a:\n${destRoot}\n\n` +
    `Los originales serán MOVIDOS (no eliminados).`
  )) return;

  const btn = document.getElementById('btnExecute');
  btn.disabled    = true;
  btn.textContent = '⏳ Organizando archivos…';

  try {
    const res  = await fetch(`${API}/organize`, {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ moves: proposal }),
    });
    const data = await res.json();
    const section = document.getElementById('sectionResult');
    section.hidden = false;
    section.scrollIntoView({ behavior:'smooth', block:'start' });
    document.getElementById('resultMsg').innerHTML = data.done > 0
      ? `<div class="result-success">
           <div class="result-icon">✅</div>
           <div>
             <p class="result-title">${data.done.toLocaleString()} archivo${data.done!==1?'s':''} organizados correctamente</p>
             ${data.failed>0?`<p class="result-sub">⚠️ ${data.failed} archivo${data.failed!==1?'s':''} no pudieron moverse</p>`:'<p class="result-sub">Sin errores.</p>'}
           </div>
         </div>`
      : `<div class="result-error">
           <div class="result-icon">❌</div>
           <div>
             <p class="result-title">No se pudo organizar ningún archivo</p>
             <pre class="result-errors">${(data.errors||[]).map(e=>e.src+': '+e.reason).join('\n')}</pre>
           </div>
         </div>`;
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
  const input = document.getElementById('inputPath');
  if (input) input.value = lastScan.path;
  const ago = Math.round((Date.now() - lastScan.timestamp) / 60000);
  const info = document.getElementById('lastScanInfo');
  if (info) info.textContent =
    `Último escaneo: hace ${ago < 60 ? ago + ' min' : Math.round(ago/60) + ' h'} · ${(lastScan.total||0).toLocaleString()} archivos`;
}

// Check silencioso al cargar — muestra el panel correcto según el estado
initialCheck();
