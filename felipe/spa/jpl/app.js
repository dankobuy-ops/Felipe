// ── Config ────────────────────────────────────────────────────────────────────
const JUZGADOS = {
  vitacura:    { name: "Vitacura",     url: "https://vitacura.cl/municipalidad/juzgado/juzgado-policia-local/" },
  lobarnechea: { name: "Lo Barnechea", url: "https://mlobarnechea.custhelp.com/app/answers/detail/a_id/83/incidents.c$tipo_atencion/221" },
};

const RUTS = [
  { name: "Autopista Central",        rut: "96945440-8" },
  { name: "Costanera Norte",          rut: "76496130-7" },
  { name: "Vespucio Norte",           rut: "96992030-1" },
  { name: "Vespucio Sur",             rut: "76052927-3" },
  { name: "Vespucio Oriente (AVO 1)", rut: "76376061-8" },
  { name: "Vespucio Oriente (AVO 2)", rut: "76870948-3" },
  { name: "Autopista Nororiente",     rut: "99548570-2" },
  { name: "Acceso Vial AMB",          rut: "76706496-9" },
];

function normR(r) { return String(r || "").replace(/[.\s]/g, "").toLowerCase(); }

function populateRutSelect(doneRuts) {
  const sel  = document.getElementById("search-code");
  const prev = sel.value;
  sel.innerHTML = '<option value="" disabled selected>— Selecciona RUT —</option>';
  for (const r of RUTS) {
    const done = doneRuts.has(normR(r.rut));
    const opt  = document.createElement("option");
    opt.value       = r.rut;
    opt.textContent = (done ? "✓  " : "      ") + r.name + "   " + r.rut;
    if (r.rut === prev) opt.selected = true;
    sel.appendChild(opt);
  }
  sel.disabled = false;
}

// Data store is the public Google Sheet (read as gviz CSV). The scraper writes it
// directly now — no Supabase. The page only reads.
const SHEET_ID   = "1SqP0w1XjvMGoEpBnbXI16EuneJMhrrSJq3hvvw_Azuo";
const SHEET_TABS = ["Causas", "CausaXRut", "Ruts", "Tramites", "Documentos",
                    "CausaXPatente", "Patentes"];

const GH_REPO          = "dankobuy-ops/Felipe";
const WORKFLOW_FILE    = "scrape.yml";
const ENRICH_WORKFLOW   = "enrich.yml";
const POLL_INTERVAL_MS  = 8000;

// ── Storage helpers ───────────────────────────────────────────────────────────
const getPAT = ()  => localStorage.getItem("gh_pat") || "";
const setPAT = (v) => localStorage.setItem("gh_pat", v);

// Bounce back to the token screen when GitHub rejects the saved PAT (401), so a
// stale/expired token can be replaced from any device (incl. the phone).
function reauth(msg) {
  localStorage.removeItem("gh_pat");
  showScreen("screen-setup");
  const err = document.getElementById("setup-error");
  if (err) {
    err.textContent = msg || "Token de GitHub inválido o expirado. Ingresa uno nuevo.";
    err.classList.remove("hidden");
  }
}

document.getElementById("change-token").addEventListener("click",
  () => reauth("Ingresa un nuevo token de GitHub."));

// Local job history (rut/year/date per job triggered from this browser).
const HISTORY_KEY    = "job_history";
const CLEARED_AT_KEY = "history_cleared_at";
function getLocalJobs() {
  try { return JSON.parse(localStorage.getItem(HISTORY_KEY) || "[]"); } catch (_) { return []; }
}
function saveLocalJob(jobId, rut, year, juzgado) {
  const jobs = getLocalJobs().filter((j) => j.jobId !== jobId);
  jobs.unshift({ jobId, rut, year, juzgado, startedAt: new Date().toISOString() });
  localStorage.setItem(HISTORY_KEY, JSON.stringify(jobs.slice(0, 50)));
}

// ── Sheet access (gviz CSV) ─────────────────────────────────────────────────—
function parseCSV(text) {
  const rows = []; let row = [], field = "", inQ = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (inQ) {
      if (c === '"') {
        if (text[i + 1] === '"') { field += '"'; i++; }
        else inQ = false;
      } else field += c;
    } else if (c === '"') inQ = true;
    else if (c === ",") { row.push(field); field = ""; }
    else if (c === "\r") { /* skip */ }
    else if (c === "\n") { row.push(field); rows.push(row); row = []; field = ""; }
    else field += c;
  }
  if (field.length || row.length) { row.push(field); rows.push(row); }
  return rows;
}

function csvToObjects(text) {
  const rows = parseCSV(text);
  if (!rows.length) return [];
  const headers = rows[0].map((h) => h.trim());
  const out = [];
  for (let r = 1; r < rows.length; r++) {
    if (rows[r].length === 1 && rows[r][0] === "") continue;
    const o = {};
    headers.forEach((h, c) => { o[h] = rows[r][c] !== undefined ? rows[r][c] : ""; });
    out.push(o);
  }
  return out;
}

async function fetchTab(tab) {
  const cb  = `${Date.now()}_${Math.random().toString(36).slice(2)}`;
  const url = `https://docs.google.com/spreadsheets/d/${SHEET_ID}/gviz/tq?tqx=out:csv&sheet=${encodeURIComponent(tab)}&cb=${cb}`;
  const r = await fetch(url, { cache: "no-store" });
  if (!r.ok) throw new Error(`Hoja ${tab} ${r.status}`);
  return csvToObjects(await r.text());
}

let _sheet = {};
async function loadSheet() {
  const results = await Promise.all(SHEET_TABS.map((t) => fetchTab(t)));
  const s = {};
  SHEET_TABS.forEach((t, i) => { s[t] = results[i]; });
  _sheet = s;
  return s;
}

function fullName(rr) {
  const parts = [rr.nombre, rr.ap_paterno, rr.ap_materno].filter(Boolean);
  return parts.join(" ").trim() || rr.razon_social || "";
}

// Join the relational tabs into the per-causa object shape the renderer expects,
// for the causas where `searchRut` is the demandante.
async function buildRowsForRut(searchRut) {
  const s = await loadSheet();
  const norm = normR(searchRut);

  const rutsByRut = {};
  for (const r of s.Ruts) rutsByRut[r.rut] = r;
  const byCaso = (arr) => {
    const m = {};
    for (const x of arr) (m[x.caso_id] = m[x.caso_id] || []).push(x);
    return m;
  };
  const tramByCaso = byCaso(s.Tramites);
  const docByCaso  = byCaso(s.Documentos);
  const cxrByCaso  = byCaso(s.CausaXRut);
  const cxpByCaso  = byCaso(s.CausaXPatente);

  _patentesData = {};
  for (const p of s.Patentes) if (p.patente) _patentesData[p.patente] = p;

  const wanted = new Set(
    s.CausaXRut
      .filter((x) => x.rol_parte === "demandante" && normR(x.rut) === norm)
      .map((x) => x.caso_id)
  );

  const rows = [];
  for (const causa of s.Causas) {
    if (!wanted.has(causa.caso_id)) continue;
    const cid   = causa.caso_id;
    const links = cxrByCaso[cid] || [];
    const demandados = links.filter((l) => l.rol_parte === "demandado").map((l) => {
      const rr = rutsByRut[l.rut] || {};
      return { nombre: fullName(rr), rut: l.rut, direccion: rr.domicilio || "", comuna: "" };
    });
    const demandantes = links.filter((l) => l.rol_parte === "demandante").map((l) => {
      const rr = rutsByRut[l.rut] || {};
      return { nombre: rr.razon_social || fullName(rr), rut: l.rut };
    });
    const tramites = (tramByCaso[cid] || []).map((t) => ({
      fecha: t.fecha, descripcion: t.descripcion, pdf_url: t.pdf_url,
    }));
    const adjuntos = (docByCaso[cid] || []).map((d) => ({
      descripcion: d.descripcion, pdf_url: d.pdf_url,
    }));
    const plates = (cxpByCaso[cid] || []).map((x) => x.patente).filter(Boolean);

    const causaObj = {
      fecha_causa: causa.fecha_causa, placa_patente: plates.join("\n"),
      actuario: "", remisor: "",
      fecha_citacion: causa.fecha_citacion, fecha_estado: causa.fecha_estado,
      boleta_numero: causa.boleta_numero, boleta_fecha: causa.boleta_fecha,
      descripcion: causa.materia, estado: causa.estado,
    };
    const caseData = {
      rol: causa.rol, descripcion: causa.materia, fecha_proceso: causa.fecha_causa,
      causa: causaObj, demandados, demandantes, tramites, adjuntos,
    };
    const firstPdf = (tramites.find((t) => t.pdf_url) || adjuntos.find((a) => a.pdf_url) || {}).pdf_url || "";
    rows.push({ record_id: causa.rol, status: "done", pdf_url: firstPdf, text: JSON.stringify(caseData) });
  }
  return rows;
}

// ── Juzgado selector ──────────────────────────────────────────────────────────
let _selectedJuzgado = null;
let _currentJuzgado  = null;

document.querySelectorAll(".juzgado-btn").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".juzgado-btn").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    _selectedJuzgado = btn.dataset.juzgado;
    const sel = document.getElementById("search-code");
    sel.innerHTML = '<option value="">Cargando…</option>';
    sel.disabled = true;
    renderJobHistory();
  });
});

// ── Screen router ─────────────────────────────────────────────────────────────
function showScreen(id) {
  document.querySelectorAll(".screen").forEach((s) => {
    s.classList.toggle("hidden", s.id !== id);
  });
}

function init() {
  if (!getPAT()) {
    showScreen("screen-setup");
  } else {
    showScreen("screen-trigger");
    renderJobHistory();
  }
}

// ── Setup screen ──────────────────────────────────────────────────────────────
document.getElementById("setup-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const pat = document.getElementById("pat-input").value.trim();
  const err = document.getElementById("setup-error");
  err.classList.add("hidden");
  try {
    const r = await fetch(`https://api.github.com/repos/${GH_REPO}/actions/workflows`, {
      headers: { Authorization: `Bearer ${pat}`, Accept: "application/vnd.github+json" },
    });
    if (!r.ok) throw new Error(`GitHub rechazó el token (${r.status})`);
    setPAT(pat);
    showScreen("screen-trigger");
    renderJobHistory();
  } catch (ex) {
    err.textContent = ex.message;
    err.classList.remove("hidden");
  }
});

// ── Trigger screen ────────────────────────────────────────────────────────────
document.getElementById("trigger-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const btn   = document.getElementById("submit-btn");
  const err   = document.getElementById("trigger-error");
  const rut   = document.getElementById("search-code").value.trim();
  const year  = document.getElementById("year-filter").value.trim();
  const jobId = crypto.randomUUID();

  if (!_selectedJuzgado) {
    err.textContent = "Selecciona un juzgado primero.";
    err.classList.remove("hidden");
    return;
  }
  if (!rut) {
    err.textContent = "Selecciona un RUT.";
    err.classList.remove("hidden");
    return;
  }

  const juzgado = _selectedJuzgado;
  const url     = JUZGADOS[juzgado].url;

  btn.disabled = true;
  btn.textContent = "Iniciando…";
  err.classList.add("hidden");

  try {
    await triggerWorkflow(jobId, rut, url, year, juzgado);
    saveLocalJob(jobId, rut, year, juzgado);
    showResultsScreen(jobId, rut, year, juzgado);
  } catch (ex) {
    err.textContent = ex.message;
    err.classList.remove("hidden");
    btn.disabled = false;
    btn.textContent = "Consultar";
  }
});

async function triggerWorkflow(jobId, rut, targetUrl, year = "", juzgado = "") {
  const rutClean = rut.replace(/\./g, "");
  const r = await fetch(
    `https://api.github.com/repos/${GH_REPO}/actions/workflows/${WORKFLOW_FILE}/dispatches`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${getPAT()}`,
        Accept: "application/vnd.github+json",
        "Content-Type": "application/json",
        "X-GitHub-Api-Version": "2022-11-28",
      },
      body: JSON.stringify({
        ref: "main",
        inputs: {
          job_id:         jobId,
          search_code:    rutClean,
          target_url:     targetUrl,
          resume_attempt: "0",
          year:           year,
          juzgado:        juzgado,
        },
      }),
    }
  );
  if (!r.ok) {
    const body = await r.text().catch(() => "");
    if (r.status === 401) reauth();
    throw new Error(`GitHub error ${r.status}: ${body || "sin detalle"}`);
  }
}

// ── Stop button — cancels ALL active runs for this workflow ───────────────────
async function cancelAllRuns() {
  const r = await fetch(
    `https://api.github.com/repos/${GH_REPO}/actions/runs?per_page=50`,
    { headers: { Authorization: `Bearer ${getPAT()}`, Accept: "application/vnd.github+json" } }
  );
  if (!r.ok) throw new Error(`GitHub ${r.status}`);
  const { workflow_runs = [] } = await r.json();
  const active = workflow_runs.filter(
    (w) => w.status === "in_progress" || w.status === "queued"
  );
  await Promise.all(active.map((w) =>
    fetch(`https://api.github.com/repos/${GH_REPO}/actions/runs/${w.id}/cancel`, {
      method: "POST",
      headers: { Authorization: `Bearer ${getPAT()}`, Accept: "application/vnd.github+json" },
    })
  ));
  return active.length;
}

document.getElementById("stop-btn").addEventListener("click", async () => {
  const btn = document.getElementById("stop-btn");
  btn.disabled = true;
  btn.textContent = "Deteniendo…";
  try {
    await cancelAllRuns();
    btn.textContent = "Detenido";
    setSpinner(false);
    clearTimeout(pollTimer);
    document.getElementById("job-status-badge").textContent = "detenido";
    document.getElementById("job-status-badge").className   = "badge stalled";
  } catch (ex) {
    btn.disabled = false;
    btn.textContent = "Detener";
  }
});

// ── Results screen ────────────────────────────────────────────────────────────
let pollTimer      = null;
let _allData       = [];
let _patentesData  = {};   // patente string → enriched row from the Patentes tab
let _patenteCancelled = false;
let _resultsRut         = "";
let _resultsDispatchedAt = "";

function showResultsScreen(jobId, rut, year = "", juzgado = "") {
  _currentJuzgado = juzgado || _currentJuzgado;
  _resultsRut = rut;
  // 60s back-buffer so a client clock ahead of GitHub's still matches a run we
  // just created when deciding whether a scrape is still in progress.
  _resultsDispatchedAt = new Date(Date.now() - 60_000).toISOString();
  document.getElementById("job-id-display").textContent   = jobId;
  document.getElementById("rut-display").textContent      = rut;
  document.getElementById("year-display").textContent     = year || "todos";
  document.getElementById("job-status-badge").textContent = "ejecutando";
  document.getElementById("job-status-badge").className   = "badge";
  document.getElementById("results-body").innerHTML = "";
  document.getElementById("progress-bar").style.width = "0%";
  document.getElementById("progress-label").textContent = "Iniciando…";
  document.getElementById("results-empty").classList.add("hidden");
  document.getElementById("results-error").classList.add("hidden");
  document.getElementById("stop-btn").classList.remove("hidden");
  document.getElementById("stop-btn").disabled = false;
  document.getElementById("stop-btn").textContent = "Detener";
  // Reset enrichment buttons to clean state
  const enrichBtn = document.getElementById("enrich-btn");
  enrichBtn.disabled = false; enrichBtn.textContent = "Buscar Emails"; enrichBtn.className = "secondary";
  document.getElementById("stop-enrich-btn").classList.add("hidden");
  setEnrichStatus("");
  const patenteBtn = document.getElementById("patente-btn");
  patenteBtn.disabled = false; patenteBtn.textContent = "Buscar Patentes"; patenteBtn.className = "secondary";
  document.getElementById("stop-patente-btn").classList.add("hidden");
  setPatenteStatus("");
  _allData = [];
  setSpinner(true);
  showScreen("screen-results");
  pollResults();
}

document.getElementById("back-btn").addEventListener("click", () => {
  clearTimeout(pollTimer);
  setSpinner(false);
  document.getElementById("stop-btn").classList.add("hidden");
  document.getElementById("submit-btn").disabled = false;
  document.getElementById("submit-btn").textContent = "Consultar";
  showScreen("screen-trigger");
  renderJobHistory();
});

// ── Job history (previous jobs) ───────────────────────────────────────────────
document.getElementById("history-refresh").addEventListener("click", renderJobHistory);
document.getElementById("history-clear").addEventListener("click", () => {
  localStorage.removeItem(HISTORY_KEY);
  localStorage.setItem(CLEARED_AT_KEY, new Date().toISOString());
  renderJobHistory();
});
document.getElementById("supabase-wipe").addEventListener("click", async () => {
  if (!confirm("¿Limpiar todos los datos?")) return;
  const btn = document.getElementById("supabase-wipe");
  btn.disabled = true;
  btn.textContent = "⏳";
  try {
    const r = await fetch(
      `https://api.github.com/repos/${GH_REPO}/actions/workflows/wipe.yml/dispatches`,
      {
        method: "POST",
        headers: {
          Authorization: `Bearer ${getPAT()}`,
          Accept: "application/vnd.github+json",
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ ref: "main" }),
      }
    );
    if (r.status === 204) {
      btn.textContent = "✓";
      localStorage.removeItem(HISTORY_KEY);
      localStorage.setItem(CLEARED_AT_KEY, new Date().toISOString());
      setTimeout(() => { btn.textContent = "🧹"; btn.disabled = false; renderJobHistory(); }, 2000);
    } else {
      alert(`Error ${r.status}`);
      btn.textContent = "🧹";
      btn.disabled = false;
    }
  } catch (err) {
    alert(String(err));
    btn.textContent = "🧹";
    btn.disabled = false;
  }
});

async function renderJobHistory() {
  const block = document.getElementById("history-block");
  const list  = document.getElementById("history-list");
  if (!_selectedJuzgado) { block.classList.add("hidden"); return; }
  const local = getLocalJobs();

  // Which RUTs already have causas in the Sheet (for this juzgado) → checkmarks.
  // caso_id = "<juzgado>/<rol>", so filter demandante links by that prefix.
  let doneRuts = new Set();
  try {
    const s = await loadSheet();
    doneRuts = new Set(
      s.CausaXRut
        .filter((x) => x.rol_parte === "demandante" &&
                       String(x.caso_id).startsWith(_selectedJuzgado + "/"))
        .map((x) => normR(x.rut))
    );
  } catch (_) { /* offline — fall back to empty (no checkmarks) */ }
  populateRutSelect(doneRuts);

  const clearedAt = localStorage.getItem(CLEARED_AT_KEY) || "";
  const jobs = local
    .filter((j) => (j.juzgado || "vitacura") === _selectedJuzgado)
    .filter((j) => !clearedAt || (j.startedAt && j.startedAt > clearedAt))
    .sort((a, b) => (b.startedAt || "").localeCompare(a.startedAt || ""));
  if (!jobs.length) { block.classList.add("hidden"); return; }
  block.classList.remove("hidden");

  list.innerHTML = "";
  for (const j of jobs) {
    const li = document.createElement("li");
    li.className = "history-item";
    const when = j.startedAt ? new Date(j.startedAt).toLocaleString() : "";
    const done = doneRuts.has(normR(j.rut));
    const st   = done ? "complete" : "";
    const lbl  = done ? "con datos" : "—";
    li.innerHTML = `
      <div class="hi-main">
        <span class="hi-rut">${esc(j.rut || j.jobId.slice(0, 8))}</span>
        ${j.year ? `<span class="hi-year">año ${esc(j.year)}</span>` : ""}
        <span class="badge ${st}">${esc(lbl)}</span>
        <button class="hi-del link-btn" title="Eliminar" data-job="${esc(j.jobId)}">🗑</button>
      </div>
      <div class="hi-sub">${esc(when)}</div>`;
    li.addEventListener("click", (e) => {
      if (e.target.closest(".hi-del")) return;
      showResultsScreen(j.jobId, j.rut || "", j.year || "", j.juzgado || "");
    });
    li.querySelector(".hi-del").addEventListener("click", (e) => {
      e.stopPropagation();
      const updated = getLocalJobs().filter((l) => l.jobId !== j.jobId);
      localStorage.setItem(HISTORY_KEY, JSON.stringify(updated));
      li.remove();
      if (!list.children.length) block.classList.add("hidden");
    });
    list.appendChild(li);
  }
}

// ── Enrich emails button ──────────────────────────────────────────────────────
let _enrichCancelled = false;

async function cancelEnrichRuns() {
  const r = await fetch(
    `https://api.github.com/repos/${GH_REPO}/actions/workflows/${ENRICH_WORKFLOW}/runs?per_page=10`,
    { headers: { Authorization: `Bearer ${getPAT()}`, Accept: "application/vnd.github+json" } }
  );
  if (!r.ok) throw new Error(`GitHub ${r.status}`);
  const { workflow_runs = [] } = await r.json();
  const active = workflow_runs.filter((w) => w.status === "in_progress" || w.status === "queued");
  await Promise.all(active.map((w) =>
    fetch(`https://api.github.com/repos/${GH_REPO}/actions/runs/${w.id}/cancel`, {
      method: "POST",
      headers: { Authorization: `Bearer ${getPAT()}`, Accept: "application/vnd.github+json" },
    })
  ));
  return active.length;
}

document.getElementById("stop-enrich-btn").addEventListener("click", async () => {
  const stopBtn = document.getElementById("stop-enrich-btn");
  stopBtn.disabled = true;
  stopBtn.textContent = "Deteniendo…";
  _enrichCancelled = true;
  try {
    await cancelEnrichRuns();
  } catch (_) {}
  stopBtn.classList.add("hidden");
  stopBtn.disabled = false;
  stopBtn.textContent = "Detener búsqueda";
  const btn = document.getElementById("enrich-btn");
  btn.disabled = false;
  btn.textContent = "Buscar Emails";
  btn.className = "secondary";
  setEnrichStatus("");
});

// Email-enrichment progress from the Ruts tab: personas with vs. without email.
async function countEnrichProgress() {
  try {
    const s = await loadSheet();
    let total = 0, found = 0;
    for (const r of s.Ruts) if (r.tipo === "persona") { total++; if (r.email) found++; }
    return { total, found };
  } catch (_) { return null; }
}

function setEnrichStatus(text) {
  document.getElementById("enrich-status").textContent = text;
  document.getElementById("enrich-status").classList.toggle("hidden", !text);
}

document.getElementById("enrich-btn").addEventListener("click", async () => {
  const jobId = document.getElementById("job-id-display").textContent.trim();
  const btn = document.getElementById("enrich-btn");
  btn.disabled = true;
  btn.textContent = "Iniciando…";
  btn.className = "secondary";
  setEnrichStatus("");

  try {
    const dispatchedAt = new Date().toISOString();
    const r = await fetch(
      `https://api.github.com/repos/${GH_REPO}/actions/workflows/${ENRICH_WORKFLOW}/dispatches`,
      {
        method: "POST",
        headers: {
          Authorization: `Bearer ${getPAT()}`,
          Accept: "application/vnd.github+json",
          "Content-Type": "application/json",
          "X-GitHub-Api-Version": "2022-11-28",
        },
        body: JSON.stringify({ ref: "main", inputs: { job_id: jobId } }),
      }
    );
    if (!r.ok) {
      const body = await r.text().catch(() => "");
      throw new Error(`GitHub ${r.status}: ${body || "sin detalle"}`);
    }
    btn.textContent = "Buscando…";
    _enrichCancelled = false;
    document.getElementById("stop-enrich-btn").classList.remove("hidden");
    pollEnrich(btn, dispatchedAt);
  } catch (ex) {
    btn.disabled = false;
    btn.textContent = "Error — reintentar";
    btn.title = ex.message;
  }
});

function _enrichDone(btn) {
  document.getElementById("stop-enrich-btn").classList.add("hidden");
  setEnrichStatus("");
}

async function pollEnrich(btn, dispatchedAt, attempt = 0) {
  if (_enrichCancelled) return;
  if (attempt > 60) {
    _enrichDone(btn);
    btn.disabled = false;
    btn.textContent = "Timeout — reintentar";
    return;
  }

  const progress = await countEnrichProgress();
  if (progress) {
    const { total, found } = progress;
    btn.textContent = total ? `Buscando… ${found}/${total}` : "Buscando…";
  }

  try {
    const r = await fetch(
      `https://api.github.com/repos/${GH_REPO}/actions/workflows/${ENRICH_WORKFLOW}/runs?per_page=5&event=workflow_dispatch`,
      { headers: { Authorization: `Bearer ${getPAT()}`, Accept: "application/vnd.github+json" } }
    );
    if (!r.ok) throw new Error(`GitHub ${r.status}`);
    const { workflow_runs = [] } = await r.json();
    const run = workflow_runs.find((w) => w.created_at >= dispatchedAt);
    if (!run) {
      setTimeout(() => pollEnrich(btn, dispatchedAt, attempt + 1), 8_000);
      return;
    }
    if (!run.conclusion) {
      setTimeout(() => pollEnrich(btn, dispatchedAt, attempt + 1), 10_000);
      return;
    }
    const final = await countEnrichProgress();
    if (run.conclusion === "success") {
      btn.textContent = final ? `✓ ${final.found}/${final.total} emails` : "✓ Listo";
      btn.className = "btn-done";
      btn.disabled = false;
      _enrichDone(btn);
    } else {
      btn.textContent = "Falló — reintentar";
      btn.disabled = false;
      btn.className = "secondary";
      _enrichDone(btn);
    }
  } catch (_) {
    setTimeout(() => pollEnrich(btn, dispatchedAt, attempt + 1), 10_000);
  }
}

// ── Patente enrichment ────────────────────────────────────────────────────────
// The local watcher (patente_watcher.py on your PC) auto-fills the Patentes tab —
// patentechile.com is behind Cloudflare and can't be scraped from the cloud. So
// the button just re-reads the Sheet to surface whatever the watcher has filled.

function setPatenteStatus(text) {
  const el = document.getElementById("patente-status");
  el.textContent = text;
  el.classList.toggle("hidden", !text);
}

document.getElementById("stop-patente-btn").addEventListener("click", () => {
  _patenteCancelled = true;
  document.getElementById("stop-patente-btn").classList.add("hidden");
  const btn = document.getElementById("patente-btn");
  btn.disabled = false;
  btn.textContent = "Buscar Patentes";
  btn.className = "secondary";
  setPatenteStatus("");
});

document.getElementById("patente-btn").addEventListener("click", async () => {
  const btn = document.getElementById("patente-btn");
  btn.disabled = true;
  btn.textContent = "Actualizando…";
  setPatenteStatus("El watcher local completa las patentes; actualizando desde la hoja…");
  try {
    clearTimeout(pollTimer);
    await pollResults();   // re-reads the Sheet (incl. Patentes) and re-renders
    const n = Object.values(_patentesData)
      .filter((p) => p.marca || p.modelo || p.rut_propietario).length;
    setPatenteStatus(`Patentes con datos: ${n}.`);
    btn.textContent = "Buscar Patentes";
    btn.className = "secondary";
  } catch (ex) {
    setPatenteStatus("Error al actualizar: " + ex.message);
    btn.textContent = "Buscar Patentes";
  }
  btn.disabled = false;
});

// ── Results polling (reads the Sheet; GitHub run status drives the spinner) ────
async function scrapeRunning(dispatchedAt) {
  try {
    const r = await fetch(
      `https://api.github.com/repos/${GH_REPO}/actions/workflows/${WORKFLOW_FILE}/runs?per_page=10`,
      { headers: { Authorization: `Bearer ${getPAT()}`, Accept: "application/vnd.github+json" } }
    );
    if (!r.ok) return false;
    const { workflow_runs = [] } = await r.json();
    return workflow_runs.some((w) =>
      (w.created_at >= dispatchedAt) &&
      ["in_progress", "queued", "requested", "waiting", "pending"].includes(w.status)
    );
  } catch (_) { return false; }
}

async function pollResults() {
  try {
    const rows    = await buildRowsForRut(_resultsRut);
    const running = await scrapeRunning(_resultsDispatchedAt);
    renderResults(rows, running ? "running" : "complete");
    if (running) {
      pollTimer = setTimeout(pollResults, POLL_INTERVAL_MS);
    } else {
      setSpinner(false);
      document.getElementById("stop-btn").classList.add("hidden");
    }
  } catch (ex) {
    document.getElementById("results-error").textContent = "Error al leer resultados: " + ex.message;
    document.getElementById("results-error").classList.remove("hidden");
    pollTimer = setTimeout(pollResults, POLL_INTERVAL_MS);
  }
}

function _extractPlates(text) {
  return (text || "").split("\n").map((s) => s.trim().toUpperCase())
    .filter((s) => /^[A-Z]{2,4}\d{2,4}$/.test(s));
}

function renderResults(rows, status) {
  // Badge
  const badge    = document.getElementById("job-status-badge");
  const labelMap = { complete: "completado", stalled: "detenido", running: "ejecutando" };
  badge.textContent = labelMap[status] || status;
  badge.className   = "badge " + (status === "complete" ? "complete" : status === "stalled" ? "stalled" : "");

  const isRunning = status !== "complete" && status !== "stalled";
  setSpinner(isRunning);
  if (!isRunning) document.getElementById("stop-btn").classList.add("hidden");

  const done = rows.length;
  document.getElementById("progress-bar").style.width = (isRunning ? 60 : 100) + "%";
  document.getElementById("progress-label").textContent =
    done
      ? `${done} causa${done === 1 ? "" : "s"}${isRunning ? " — buscando…" : ""}`
      : (isRunning ? "Esperando primeros resultados…" : "Sin resultados");

  document.getElementById("results-empty").classList.toggle("hidden", done > 0);

  _allData = rows.map((row) => {
    let data = {};
    try { data = JSON.parse(row.text || "{}"); } catch (_) {}
    return { ...row, _data: data };
  });

  const tbody = document.getElementById("results-body");
  tbody.innerHTML = "";

  _allData.forEach((row) => {
    const data  = row._data;
    const causa = (typeof data.causa === "object" && data.causa) ? data.causa : {};

    const tr = document.createElement("tr");
    tr.className = "row-main";
    tr.innerHTML = `
      <td>${esc(data.rol || row.record_id)}</td>
      <td>${esc(data.descripcion || causa.descripcion || "—")}</td>
      <td>${esc(data.fecha_proceso || causa.fecha_causa || "—")}</td>
      <td class="status-${esc(row.status)}">${esc(causa.estado || row.status)}</td>
      <td class="expand-cell"><span class="expand-icon">▸</span></td>
    `;
    tbody.appendChild(tr);

    const trDetail = document.createElement("tr");
    trDetail.className = "row-detail hidden";
    const td = document.createElement("td");
    td.colSpan = 5;
    td.innerHTML = buildDetail(data, causa);
    trDetail.appendChild(td);
    tbody.appendChild(trDetail);

    tr.addEventListener("click", () => {
      const nowHidden = trDetail.classList.toggle("hidden");
      tr.querySelector(".expand-icon").textContent = nowHidden ? "▸" : "▾";
    });
  });
}

// ── Detail panel builder ──────────────────────────────────────────────────────
function buildDetail(data, causa) {
  const sections = [];

  const causeFields = [
    ["Fecha causa",    causa.fecha_causa],
    ["Placa patente",  causa.placa_patente],
    ["Actuario",       causa.actuario],
    ["Remisor",        causa.remisor],
    ["Fecha citación", causa.fecha_citacion || causa["fecha_citación"]],
    ["Fecha estado",   causa.fecha_estado],
    ["Boleta N°",      causa.boleta_numero],
    ["Fecha boleta",   causa.boleta_fecha],
  ].filter(([, v]) => v);

  if (causeFields.length) {
    sections.push(`
      <div class="detail-section">
        <div class="detail-title">Datos de la causa</div>
        <div class="detail-grid">
          ${causeFields.map(([l, v]) => `<span class="dl">${esc(l)}</span><span>${esc(v)}</span>`).join("")}
        </div>
      </div>`);
  }

  function renderParties(list, title) {
    if (!list || !list.length) return "";
    return `
      <div class="detail-section">
        <div class="detail-title">${title}</div>
        ${list.map((p) => `
          <div class="party-row">
            <strong>${esc(p.nombre || "")}</strong>
            ${p.rut       ? `<span class="pl">RUT: ${esc(p.rut)}</span>` : ""}
            ${p.direccion ? `<span class="pl">${esc(p.direccion)}</span>` : ""}
            ${p.comuna    ? `<span class="pl">${esc(p.comuna)}</span>` : ""}
          </div>`).join("")}
      </div>`;
  }

  sections.push(renderParties(data.demandados,  "Demandados"));
  sections.push(renderParties(data.demandantes, "Demandantes"));

  // Vehículos — enriched data from the Patentes tab
  const plates = _extractPlates(causa.placa_patente || "");
  const enriched = plates.map((p) => _patentesData[p]).filter(Boolean);
  if (enriched.length) {
    const vrows = enriched.map((v) => `
      <div class="party-row">
        <strong>${esc(v.patente)}</strong>
        ${[v.marca, v.modelo, v.anio].filter(Boolean).map((s) => `<span class="pl">${esc(s)}</span>`).join("")}
        ${v.color           ? `<span class="pl">Color: ${esc(v.color)}</span>` : ""}
        ${v.tipo            ? `<span class="pl">Tipo: ${esc(v.tipo)}</span>` : ""}
        ${v.combustible     ? `<span class="pl">Combustible: ${esc(v.combustible)}</span>` : ""}
        ${v.rut_propietario ? `<span class="pl">RUT prop.: ${esc(v.rut_propietario)}</span>` : ""}
        ${v.num_motor       ? `<span class="pl">Motor: ${esc(v.num_motor)}</span>` : ""}
        ${v.num_chasis      ? `<span class="pl">Chasis: ${esc(v.num_chasis)}</span>` : ""}
      </div>`).join("");
    sections.push(`
      <div class="detail-section">
        <div class="detail-title">Vehículos (${enriched.length})</div>
        ${vrows}
      </div>`);
  }

  // Trámites (Sección C)
  const tramites = data.tramites || [];
  if (tramites.length) {
    const trows = tramites.map((t) => {
      const href = safeHref(t.pdf_url);
      return `<tr>
        <td>${esc(t.fecha || "")}</td>
        <td>${esc(t.descripcion || "")}</td>
        <td>${href ? `<a href="${href}" target="_blank" rel="noopener" class="doc-link">Abrir</a>` : "—"}</td>
      </tr>`;
    }).join("");
    sections.push(`
      <div class="detail-section">
        <div class="detail-title">Trámites (${tramites.length})</div>
        <table class="sub-table">
          <thead><tr><th>Fecha</th><th>Descripción</th><th>Doc</th></tr></thead>
          <tbody>${trows}</tbody>
        </table>
      </div>`);
  }

  // Adjuntos (Sección D)
  const adjuntos = data.adjuntos || [];
  if (adjuntos.length) {
    const arows = adjuntos.map((a) => {
      const href = safeHref(a.pdf_url);
      return `<tr>
        <td>${esc(a.descripcion || "")}</td>
        <td>${href ? `<a href="${href}" target="_blank" rel="noopener" class="doc-link">Abrir</a>` : "—"}</td>
      </tr>`;
    }).join("");
    sections.push(`
      <div class="detail-section">
        <div class="detail-title">Adjuntos (${adjuntos.length})</div>
        <table class="sub-table">
          <thead><tr><th>Descripción</th><th>Doc</th></tr></thead>
          <tbody>${arows}</tbody>
        </table>
      </div>`);
  }

  return `<div class="detail-panel">${sections.join("")}</div>`;
}

// ── Helpers ───────────────────────────────────────────────────────────────────
function setSpinner(on) {
  document.getElementById("spinner").classList.toggle("hidden", !on);
}

function esc(str) {
  return String(str ?? "")
    .replace(/&/g, "&amp;").replace(/</g, "&lt;")
    .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function safeHref(url) {
  if (!url) return "";
  const s = String(url).trim();
  return /^https?:\/\//i.test(s) ? s.replace(/"/g, "%22") : "";
}

const delay = (ms) => new Promise((res) => setTimeout(res, ms));

// ── Boot ──────────────────────────────────────────────────────────────────────
init();
