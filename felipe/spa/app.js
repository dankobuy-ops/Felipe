// ── Config ────────────────────────────────────────────────────────────────────
const SHEETS_WEBHOOK = "https://script.google.com/macros/s/AKfycbzjJK-QoDiyDygjaDy6Dt7dk8a8c5WD_gnV1u1fixug2VqbIUcg1nEGMycNmkmApJCy/exec";
const SHEET_ID       = "1qWNiprgWcYOC4MPQ8VeqOqZebn4GXxdRzhNADNQFGKY";

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

const SUPABASE_URL     = "https://xjlpsgchgfxryvhhrklx.supabase.co";
const SUPABASE_ANON    = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InhqbHBzZ2NoZ2Z4cnl2aGhya2x4Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODA1MDU2NzAsImV4cCI6MjA5NjA4MTY3MH0.LVxF3eX8S8FqcLHHHr7l_LkM1R3fJ7SSbg0ZNM1hM-g";
const GH_REPO          = "dankobuy-ops/Felipe";
const WORKFLOW_FILE    = "scrape.yml";
const ENRICH_WORKFLOW   = "enrich.yml";
const PATENTE_WORKFLOW  = "patente.yml";
const POLL_INTERVAL_MS  = 8000;

// ── Storage helpers ───────────────────────────────────────────────────────────
const getPAT = ()  => localStorage.getItem("gh_pat") || "";
const setPAT = (v) => localStorage.setItem("gh_pat", v);

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
let _patentesData  = {};   // patente string → enriched row from `patentes` table
let _patenteCancelled = false;

function showResultsScreen(jobId, rut, year = "", juzgado = "") {
  _currentJuzgado = juzgado || _currentJuzgado;
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
  pollResults(jobId);
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
  if (!confirm("¿Limpiar todos los datos de Supabase?")) return;
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

  // Pull every job's status + meta from Supabase (cross-device, includes jobs
  // not started from this browser). Merge with local rut/year/date.
  const byId = {};
  for (const j of local) {
    byId[j.jobId] = { jobId: j.jobId, rut: j.rut, year: j.year, juzgado: j.juzgado || "", ts: j.startedAt, status: "" };
  }
  try {
    const r = await fetch(
      `${SUPABASE_URL}/rest/v1/checkpoints?record_id=in.(__job__,__meta__)&select=job_id,record_id,status,text`,
      { headers: { apikey: SUPABASE_ANON, Authorization: `Bearer ${SUPABASE_ANON}` } }
    );
    if (r.ok) {
      for (const row of await r.json()) {
        const e = byId[row.job_id] || (byId[row.job_id] = { jobId: row.job_id, rut: "", year: "", juzgado: "", ts: "", status: "" });
        if (row.record_id === "__job__") e.status = row.status;
        else if (row.record_id === "__meta__") {
          let m = {}; try { m = JSON.parse(row.text || "{}"); } catch (_) {}
          e.rut     = e.rut     || m.rut     || "";
          e.year    = e.year    || m.year    || "";
          e.juzgado = e.juzgado || m.juzgado || "";
          e.ts      = e.ts      || m.ts      || "";
        }
      }
    }
  } catch (_) { /* offline / RLS — fall back to local-only list */ }

  // Populate RUT select with checkmarks for RUTs that have completed jobs for this juzgado
  const doneRuts = new Set(
    Object.values(byId)
      .filter(j => (j.juzgado === _selectedJuzgado || (_selectedJuzgado === "vitacura" && !j.juzgado)) && j.status === "complete")
      .map(j => normR(j.rut))
  );
  populateRutSelect(doneRuts);

  const clearedAt = localStorage.getItem(CLEARED_AT_KEY) || "";
  const jobs = Object.values(byId)
    .filter(j => j.juzgado === _selectedJuzgado || (_selectedJuzgado === "vitacura" && !j.juzgado))
    .filter(j => !clearedAt || (j.ts && j.ts > clearedAt) || local.some(l => l.jobId === j.jobId))
    .sort((a, b) => (b.ts || "").localeCompare(a.ts || ""));
  if (!jobs.length) { block.classList.add("hidden"); return; }
  block.classList.remove("hidden");

  const labelMap = { complete: "completado", stalled: "detenido", running: "ejecutando", "": "—" };
  list.innerHTML = "";
  for (const j of jobs) {
    const li = document.createElement("li");
    li.className = "history-item";
    const when = j.ts ? new Date(j.ts).toLocaleString() : "";
    const st   = j.status || "running";
    li.innerHTML = `
      <div class="hi-main">
        <span class="hi-rut">${esc(j.rut || j.jobId.slice(0, 8))}</span>
        ${j.year ? `<span class="hi-year">año ${esc(j.year)}</span>` : ""}
        <span class="badge ${st === "complete" ? "complete" : st === "stalled" ? "stalled" : ""}">${esc(labelMap[j.status] || st)}</span>
        <button class="hi-del link-btn" title="Eliminar" data-job="${esc(j.jobId)}">🗑</button>
      </div>
      <div class="hi-sub">${esc(when)}</div>`;
    li.addEventListener("click", (e) => {
      if (e.target.closest(".hi-del")) return;
      showResultsScreen(j.jobId, j.rut || "", j.year || "", j.juzgado || "");
    });
    li.querySelector(".hi-del").addEventListener("click", async (e) => {
      e.stopPropagation();
      const btn = e.currentTarget;
      btn.disabled = true;
      btn.textContent = "⏳";
      // Remove from localStorage
      const updated = getLocalJobs().filter(l => l.jobId !== j.jobId);
      localStorage.setItem(HISTORY_KEY, JSON.stringify(updated));
      // Dispatch wipe workflow for this job_id
      try {
        await fetch(
          `https://api.github.com/repos/${GH_REPO}/actions/workflows/wipe.yml/dispatches`,
          {
            method: "POST",
            headers: {
              Authorization: `Bearer ${getPAT()}`,
              Accept: "application/vnd.github+json",
              "Content-Type": "application/json",
            },
            body: JSON.stringify({ ref: "main", inputs: { job_id: j.jobId } }),
          }
        );
      } catch (_) {}
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

async function countEnrichProgress(jobId) {
  try {
    const rows = await fetchCheckpoints(jobId);
    let total = 0, found = 0;
    for (const row of rows) {
      if (row.record_id === "__job__" || row.record_id === "__meta__") continue;
      try {
        const d = JSON.parse(row.text || "{}");
        for (const dem of d.demandados || []) { total++; if (dem.email) found++; }
      } catch (_) {}
    }
    return { total, found };
  } catch (_) { return null; }
}

function setEnrichStatus(text) {
  document.getElementById("enrich-status").textContent = text;
  document.getElementById("enrich-status").classList.toggle("hidden", !text);
}

document.getElementById("enrich-btn").addEventListener("click", async () => {
  const jobId = document.getElementById("job-id-display").textContent.trim();
  if (!jobId) return;
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
    pollEnrich(btn, jobId, dispatchedAt);
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

async function pollEnrich(btn, jobId, dispatchedAt, attempt = 0) {
  if (_enrichCancelled) return;
  if (attempt > 60) {
    _enrichDone(btn);
    btn.disabled = false;
    btn.textContent = "Timeout — reintentar";
    return;
  }

  // Update live email count from Supabase on every tick
  const progress = await countEnrichProgress(jobId);
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
      setTimeout(() => pollEnrich(btn, jobId, dispatchedAt, attempt + 1), 8_000);
      return;
    }
    if (!run.conclusion) {
      setTimeout(() => pollEnrich(btn, jobId, dispatchedAt, attempt + 1), 10_000);
      return;
    }
    // Workflow finished — do one final count
    const final = await countEnrichProgress(jobId);
    if (run.conclusion === "success") {
      const label = final ? `✓ ${final.found}/${final.total} emails` : "✓ Listo";
      btn.textContent = label;
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

function setPatenteStatus(text) {
  const el = document.getElementById("patente-status");
  el.textContent = text;
  el.classList.toggle("hidden", !text);
}

function _patenteDone(btn) {
  document.getElementById("stop-patente-btn").classList.add("hidden");
  setPatenteStatus("");
}

document.getElementById("stop-patente-btn").addEventListener("click", () => {
  // The search runs on your PC via the watcher; "stop" just stops the app from
  // following along (the watcher finishes whatever plate it's mid-way through).
  _patenteCancelled = true;
  document.getElementById("stop-patente-btn").classList.add("hidden");
  const btn = document.getElementById("patente-btn");
  btn.disabled = false;
  btn.textContent = "Buscar Patentes";
  btn.className = "secondary";
  setPatenteStatus("");
});

document.getElementById("patente-btn").addEventListener("click", async () => {
  const jobId = document.getElementById("job-id-display").textContent.trim();
  if (!jobId) return;
  const btn = document.getElementById("patente-btn");
  btn.disabled = true;
  btn.textContent = "Iniciando…";
  setPatenteStatus("");

  try {
    // patentechile.com is behind Cloudflare, so the scrape can't run in the cloud.
    // Instead we queue a request row; the local watcher (running on your PC) picks
    // it up, does the search in a real browser, and saves results to Supabase.
    const r = await fetch(`${SUPABASE_URL}/rest/v1/patente_requests`, {
      method: "POST",
      headers: {
        apikey: SUPABASE_ANON,
        Authorization: `Bearer ${SUPABASE_ANON}`,
        "Content-Type": "application/json",
        Prefer: "return=representation",
      },
      body: JSON.stringify({ job_id: jobId }),
    });
    if (!r.ok) {
      const body = await r.text().catch(() => "");
      throw new Error(`Supabase ${r.status}: ${body || "sin detalle"}`);
    }
    const [req] = await r.json();
    btn.textContent = "En cola…";
    _patenteCancelled = false;
    setPatenteStatus("Solicitud en cola — el watcher debe estar corriendo en tu PC.");
    document.getElementById("stop-patente-btn").classList.remove("hidden");
    pollPatente(btn, jobId, req.id);
  } catch (ex) {
    btn.disabled = false;
    btn.textContent = "Error — reintentar";
    btn.title = ex.message;
  }
});

async function pollPatente(btn, jobId, reqId, attempt = 0) {
  if (_patenteCancelled) return;
  if (attempt > 120) {  // ~20 min at 10s/poll
    _patenteDone(btn);
    btn.disabled = false;
    btn.textContent = "Timeout — ¿watcher corriendo?";
    return;
  }

  // Read the request's status (set by the local watcher) + live progress.
  let req = null;
  try {
    const r = await fetch(
      `${SUPABASE_URL}/rest/v1/patente_requests?id=eq.${reqId}&select=status,message`,
      { headers: { apikey: SUPABASE_ANON, Authorization: `Bearer ${SUPABASE_ANON}` } }
    );
    if (r.ok) req = (await r.json())[0];
  } catch (_) {}

  const status = req?.status || "pending";
  if (status === "done" || status === "error") {
    await fetchPatentesForJob();
    const final = await countPatentesProgress(jobId);
    if (status === "done") {
      btn.textContent = final ? `✓ ${final.found}/${final.total} patentes` : "✓ Listo";
      btn.className = "btn-done";
    } else {
      btn.textContent = "Falló — reintentar";
      btn.className = "secondary";
      btn.title = req?.message || "";
    }
    btn.disabled = false;
    _patenteDone(btn);
    return;
  }

  if (status === "running") {
    const progress = await countPatentesProgress(jobId);
    btn.textContent = progress && progress.total
      ? `Buscando… ${progress.found}/${progress.total}` : "Buscando…";
  } else {
    btn.textContent = "En cola…";
  }
  setTimeout(() => pollPatente(btn, jobId, reqId, attempt + 1), 10_000);
}

async function cancelWorkflowRuns(workflow) {
  const r = await fetch(
    `https://api.github.com/repos/${GH_REPO}/actions/workflows/${workflow}/runs?per_page=5&status=in_progress`,
    { headers: { Authorization: `Bearer ${getPAT()}`, Accept: "application/vnd.github+json" } }
  );
  if (!r.ok) throw new Error(`GitHub ${r.status}`);
  const { workflow_runs = [] } = await r.json();
  await Promise.all(workflow_runs.map((w) =>
    fetch(`https://api.github.com/repos/${GH_REPO}/actions/runs/${w.id}/cancel`, {
      method: "POST",
      headers: { Authorization: `Bearer ${getPAT()}`, Accept: "application/vnd.github+json" },
    })
  ));
}

async function pollResults(jobId) {
  try {
    const rows = await fetchCheckpoints(jobId);
    renderResults(rows);
    const jobRow = rows.find((r) => r.record_id === "__job__");
    const status = jobRow ? jobRow.status : "running";
    if (status !== "complete" && status !== "stalled") {
      pollTimer = setTimeout(() => pollResults(jobId), POLL_INTERVAL_MS);
    } else {
      setSpinner(false);
      document.getElementById("stop-btn").classList.add("hidden");
    }
  } catch (ex) {
    document.getElementById("results-error").textContent = "Error al leer resultados: " + ex.message;
    document.getElementById("results-error").classList.remove("hidden");
    pollTimer = setTimeout(() => pollResults(jobId), POLL_INTERVAL_MS);
  }
}

async function fetchCheckpoints(jobId) {
  const r = await fetch(
    `${SUPABASE_URL}/rest/v1/checkpoints?job_id=eq.${encodeURIComponent(jobId)}&select=record_id,status,text,pdf_url`,
    { headers: { apikey: SUPABASE_ANON, Authorization: `Bearer ${SUPABASE_ANON}` } }
  );
  if (!r.ok) throw new Error(`Supabase ${r.status}`);
  return r.json();
}

function _extractPlates(text) {
  return (text || "").split("\n").map(s => s.trim().toUpperCase()).filter(s => /^[A-Z]{2,4}\d{2,4}$/.test(s));
}

function _allPlatesFromData(data) {
  const plates = new Set();
  for (const row of data) {
    const causa = row._data?.causa || {};
    _extractPlates(causa.placa_patente || "").forEach(p => plates.add(p));
    for (const dem of row._data?.demandados || [])
      _extractPlates(dem.patente || dem.placa_patente || "").forEach(p => plates.add(p));
  }
  return plates;
}

async function fetchPatentesForJob() {
  if (!_allData.length) return;
  const plates = _allPlatesFromData(_allData);
  if (!plates.size) return;
  try {
    const r = await fetch(
      `${SUPABASE_URL}/rest/v1/patentes?patente=in.(${[...plates].join(",")})&select=*`,
      { headers: { apikey: SUPABASE_ANON, Authorization: `Bearer ${SUPABASE_ANON}` } }
    );
    if (!r.ok) return;
    const rows = await r.json();
    _patentesData = {};
    for (const row of rows) _patentesData[row.patente] = row;
  } catch (_) {}
}

async function countPatentesProgress(jobId) {
  try {
    const rows = await fetchCheckpoints(jobId);
    const plates = new Set();
    for (const row of rows) {
      if (row.record_id?.startsWith("__")) continue;
      try {
        const d = JSON.parse(row.text || "{}");
        _extractPlates((d.causa?.placa_patente || d.placa_patente || "")).forEach(p => plates.add(p));
        for (const dem of d.demandados || [])
          _extractPlates(dem.patente || dem.placa_patente || "").forEach(p => plates.add(p));
      } catch (_) {}
    }
    if (!plates.size) return { total: 0, found: 0 };
    const r = await fetch(
      `${SUPABASE_URL}/rest/v1/patentes?patente=in.(${[...plates].join(",")})&select=patente`,
      { headers: { apikey: SUPABASE_ANON, Authorization: `Bearer ${SUPABASE_ANON}` } }
    );
    if (!r.ok) return null;
    return { total: plates.size, found: (await r.json()).length };
  } catch (_) { return null; }
}

function renderResults(rows) {
  const RESERVED = new Set(["__job__", "__meta__"]);
  const metaRow  = rows.find((r) => r.record_id === "__meta__");
  const jobRow   = rows.find((r) => r.record_id === "__job__");
  const dataRows = rows.filter((r) => !RESERVED.has(r.record_id));
  const status   = jobRow ? jobRow.status : "running";

  // Badge
  const badge     = document.getElementById("job-status-badge");
  const labelMap  = { complete: "completado", stalled: "detenido", running: "ejecutando" };
  badge.textContent = labelMap[status] || status;
  badge.className   = "badge " + (status === "complete" ? "complete" : status === "stalled" ? "stalled" : "");

  // Spinner — visible while running
  const isRunning = status !== "complete" && status !== "stalled";
  setSpinner(isRunning);
  if (!isRunning) document.getElementById("stop-btn").classList.add("hidden");

  // Progress — use __meta__ total when available so count is accurate from the start
  let total = 0;
  if (metaRow) {
    try {
      const m = JSON.parse(metaRow.text || "{}");
      total = m.total || 0;
      if (m.juzgado && !_currentJuzgado) _currentJuzgado = m.juzgado;
    } catch (_) {}
  }
  if (!total) total = dataRows.length;  // fallback for old jobs without __meta__
  const done = dataRows.filter((r) => r.status === "done").length;
  const pct  = total ? Math.round((done / total) * 100) : 0;
  document.getElementById("progress-bar").style.width = pct + "%";
  document.getElementById("progress-label").textContent =
    total
      ? `${done} / ${total} causas procesadas`
      : "Esperando primeros resultados…";

  document.getElementById("results-empty").classList.toggle("hidden", dataRows.length > 0);

  // Parse and store for CSV/export
  _allData = dataRows.map((row) => {
    let data = {};
    try { data = JSON.parse(row.text || "{}"); } catch (_) {}
    return { ...row, _data: data };
  });

  // Refresh vehicle data in background (non-blocking)
  fetchPatentesForJob().catch(() => {});

  const tbody = document.getElementById("results-body");
  tbody.innerHTML = "";

  _allData.forEach((row) => {
    const data  = row._data;
    const causa = (typeof data.causa === "object" && data.causa) ? data.causa : {};

    // Main summary row (clickable)
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

    // Detail row (hidden until clicked)
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

  // Sección B — datos de la causa
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

  // Vehículos — enriched data from patentes table
  const plates = _extractPlates(causa.placa_patente || "");
  const enriched = plates.map(p => _patentesData[p]).filter(Boolean);
  if (enriched.length) {
    const vrows = enriched.map((v) => `
      <div class="party-row">
        <strong>${esc(v.patente)}</strong>
        ${[v.marca, v.modelo, v.anio].filter(Boolean).map(s => `<span class="pl">${esc(s)}</span>`).join("")}
        ${v.color       ? `<span class="pl">Color: ${esc(v.color)}</span>` : ""}
        ${v.tipo        ? `<span class="pl">Tipo: ${esc(v.tipo)}</span>` : ""}
        ${v.combustible ? `<span class="pl">Combustible: ${esc(v.combustible)}</span>` : ""}
        ${v.rut         ? `<span class="pl">RUT prop.: ${esc(v.rut)}</span>` : ""}
        ${v.num_motor   ? `<span class="pl">Motor: ${esc(v.num_motor)}</span>` : ""}
        ${v.num_chasis  ? `<span class="pl">Chasis: ${esc(v.num_chasis)}</span>` : ""}
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
      // Link to the downloaded Supabase PDF, not the login-gated source viewer.
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
      // Link to the downloaded Supabase PDF, not the login-gated source viewer.
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

// ── Google Sheets export ──────────────────────────────────────────────────────

const RUTS_HEADER      = ["RUT", "Nombre"];
const JUZGADOS_HEADER  = ["Juzgado ID", "Nombre", "URL"];
const CAUSAS_HEADER = [
  "Caso ID", "ROL",
  "Juzgado",
  "Demandante",
  "Materia",
  "Fecha Causa", "Fecha Citación", "Fecha Estado", "Estado",
  "Boleta N°", "Fecha Boleta",
  "Monto Demandado",
];
const DEMANDADOS_HEADER = [
  "Caso ID", "ROL",
  "Nombre", "Segundo Nombre", "Ap. Paterno", "Ap. Materno",
  "RUT", "Email", "Teléfono", "Domicilio",
  "Marca", "Modelo", "Año", "Patente", "Uso",
];
const TRAMITES_HEADER   = ["Caso ID", "ROL", "Fecha", "Descripción", "Link PDF"];
const DOCUMENTOS_HEADER = ["Caso ID", "ROL", "Descripción", "Link PDF"];
const PATENTES_HEADER   = ["Patente", "RUT Propietario", "Tipo", "Marca", "Modelo", "Año", "Color", "N° Motor", "N° Chasis", "Combustible"];

function buildSheetsPayload(jobId, allData) {
  const rutDemandante = document.getElementById("rut-display").textContent;
  const juzgadoName   = JUZGADOS[_currentJuzgado]?.name || _currentJuzgado || "";

  function casoId(job, rol) { return `${(job || "").slice(0, 8)}/${rol}`; }

  function toTitle(s) {
    return String(s || "").trim().replace(/\w\S*/g, (t) => t.charAt(0).toUpperCase() + t.slice(1).toLowerCase());
  }

  function splitName(nombre) {
    if (!nombre) return ["", "", "", ""];
    const s = String(nombre).trim();
    if (s.includes(",")) {
      const apellidosParts = s.slice(0, s.indexOf(",")).trim().split(/\s+/);
      const nombresParts   = s.slice(s.indexOf(",") + 1).trim().split(/\s+/);
      return [
        toTitle(nombresParts[0] || ""),
        nombresParts.slice(1).map(toTitle).join(" "),
        toTitle(apellidosParts[0] || ""),
        toTitle(apellidosParts[1] || ""),
      ];
    }
    // No comma — Chilean courts use PATERNO MATERNO NOMBRE [SEGUNDO] order
    const parts = s.split(/\s+/);
    const n = parts.length;
    if (n <= 1) return [toTitle(parts[0] || ""), "", "", ""];
    if (n === 2) return [toTitle(parts[1]), "", toTitle(parts[0]), ""];
    if (n === 3) return [toTitle(parts[2]), "", toTitle(parts[0]), toTitle(parts[1])];
    return [toTitle(parts[2]), parts.slice(3).map(toTitle).join(" "), toTitle(parts[0]), toTitle(parts[1])];
  }

  function domicilio(party) {
    return [party.direccion, party.comuna].filter(Boolean).join(", ");
  }

  function firstOf(obj, ...keys) {
    for (const k of keys) { const v = obj[k]; if (v) return v; }
    return "";
  }

  function dedupValue(val) {
    if (!val) return "";
    const s = String(val).trim();
    // Space/newline-separated duplicate: "AB1234 AB1234" → "AB1234"
    const parts = s.split(/[\s\n\r]+/).filter(Boolean);
    const unique = [...new Set(parts)];
    if (unique.length < parts.length) return unique.join(" ");
    // Concatenated duplicate: "AB1234AB1234" → "AB1234"
    if (s.length % 2 === 0 && s.slice(0, s.length / 2) === s.slice(s.length / 2))
      return s.slice(0, s.length / 2);
    return s;
  }

  // Normalize RUT for comparison: strip dots/spaces, lowercase
  function normRut(r) { return String(r || "").replace(/[.\s]/g, "").toLowerCase(); }
  const rutNorm = normRut(rutDemandante);

  const causas = [], demandados = [], tramites = [], documentos = [];
  let nombreDemandante = "";

  for (const row of allData) {
    const data  = row._data;
    const rol   = data.rol || row.record_id;
    const cid   = casoId(jobId, rol);
    const causa = (typeof data.causa === "object" && data.causa) ? data.causa : {};
    const veh   = {
      marca:   firstOf(causa, "marca", "marca_vehiculo", "marca_vehículo"),
      modelo:  firstOf(causa, "modelo", "modelo_vehiculo", "modelo_vehículo"),
      año:     firstOf(causa, "año", "ano", "año_vehiculo", "año_vehículo"),
      patente: dedupValue(firstOf(causa, "placa_patente")),
      uso:     firstOf(causa, "uso", "uso_vehiculo", "uso_vehículo"),
    };

    // Get demandante name from Section A.2 (demandantes array), fall back to remisor
    if (!nombreDemandante) {
      const match = (data.demandantes || []).find(d => normRut(d.rut) === rutNorm);
      nombreDemandante = (match && match.nombre) || firstOf(causa, "remisor");
    }

    causas.push([
      cid, rol,
      juzgadoName,
      rutDemandante,
      data.descripcion || causa.descripcion || causa["descripción"] || firstOf(causa, "materia", "materia_causa", "materia_de_la_causa") || "",
      firstOf(causa, "fecha_causa"),
      firstOf(causa, "fecha_citacion", "fecha_citación"),
      firstOf(causa, "fecha_estado"),
      causa.estado || "",
      causa.boleta_numero || "",
      causa.boleta_fecha || "",
      firstOf(causa, "monto", "monto_demandado", "cuantia", "cuantía", "monto_multa"),
    ]);

    // Exclude the demandante (search RUT) — it leaks into Section A.1 on some layouts
    const demList = (data.demandados || []).filter(d => normRut(d.rut) !== rutNorm);
    if (!demList.length) {
      demandados.push([`${cid}/d1`, rol, "", "", "", "", "", "", "", "", veh.marca, veh.modelo, veh.año, veh.patente, veh.uso]);
    } else {
      const demMap = new Map();
      for (const dem of demList) {
        const key = dem.rut || dem.nombre || "";
        const [nombre1, segundo, apPaterno, apMaterno] = splitName(dem.nombre);
        const row = [
          null, rol,  // placeholder — index assigned below
          nombre1, segundo, apPaterno, apMaterno,
          dem.rut || "", dem.email || "", dem.telefono || "", domicilio(dem),
          dem.marca || veh.marca, dem.modelo || veh.modelo,
          dem.año || veh.año, dedupValue(dem.patente || veh.patente), dem.uso || veh.uso,
        ];
        const existing = demMap.get(key);
        if (!existing) {
          demMap.set(key, row);
        } else {
          demMap.set(key, existing.map((v, i) => v || row[i]));
        }
      }
      let di = 0;
      for (const row of demMap.values()) {
        row[0] = `${cid}/d${++di}`;
        demandados.push(row);
      }
    }

    let ti = 0;
    for (const t of (data.tramites || [])) {
      tramites.push([`${cid}/t${++ti}`, rol, t.fecha || "", t.descripcion || "", t.pdf_url || ""]);
    }
    let xi = 0;
    for (const a of (data.adjuntos || [])) {
      if (a.pdf_url) documentos.push([`${cid}/x${++xi}`, rol, a.descripcion || "", a.pdf_url]);
    }
  }

  // Collect unique patentes from this job (enriched data from _patentesData)
  const seenPlates = new Set();
  const patentesRows = [];
  for (const row of allData) {
    const causa = (typeof row._data.causa === "object" && row._data.causa) ? row._data.causa : {};
    for (const p of _extractPlates(causa.placa_patente || "")) {
      if (seenPlates.has(p)) continue;
      seenPlates.add(p);
      const v = _patentesData[p] || {};
      patentesRows.push([
        p,
        v.rut || "", v.tipo || "", v.marca || "", v.modelo || "",
        v.anio || "", v.color || "", v.num_motor || "", v.num_chasis || "", v.combustible || "",
      ]);
    }
  }

  return {
    juzgados:   { header: JUZGADOS_HEADER,   rows: Object.entries(JUZGADOS).map(([id, j]) => [id, j.name, j.url]) },
    ruts:       { header: RUTS_HEADER,        rows: [[rutDemandante, nombreDemandante]] },
    causas:     { header: CAUSAS_HEADER,      rows: causas },
    demandados: { header: DEMANDADOS_HEADER,  rows: demandados },
    tramites:   { header: TRAMITES_HEADER,    rows: tramites },
    documentos: { header: DOCUMENTOS_HEADER,  rows: documentos },
    patentes:   { header: PATENTES_HEADER,    rows: patentesRows },
  };
}

document.getElementById("sheets-btn").addEventListener("click", async () => {
  if (!_allData.length) return;

  const btn = document.getElementById("sheets-btn");
  btn.disabled = true;
  btn.textContent = "Enviando…";

  const jobId   = document.getElementById("job-id-display").textContent;
  const payload = { spreadsheet_id: SHEET_ID, ...buildSheetsPayload(jobId, _allData) };

  try {
    // no-cors: Apps Script receives body as plain text; response is opaque but script runs.
    await fetch(SHEETS_WEBHOOK, {
      method:  "POST",
      mode:    "no-cors",
      headers: { "Content-Type": "text/plain" },
      body:    JSON.stringify(payload),
    });
    btn.textContent = "¡Exportado!";
    setTimeout(() => { btn.textContent = "Exportar a Sheets"; btn.disabled = false; }, 3000);
  } catch (ex) {
    console.error("Sheets export error:", ex);
    btn.textContent = "Error — revisar consola";
    setTimeout(() => { btn.textContent = "Exportar a Sheets"; btn.disabled = false; }, 4000);
  }
});

// ── CSV export ────────────────────────────────────────────────────────────────
document.getElementById("csv-btn").addEventListener("click", () => {
  if (!_allData.length) return;
  const headers = [
    "rol", "carátula", "fecha_proceso", "juzgado", "estado", "fecha_estado",
    "placa_patente", "actuario", "remisor", "fecha_citacion",
    "boleta_numero", "boleta_fecha", "demandados", "demandantes", "tramites", "pdf_url",
  ];
  const csvRows = [headers.join(",")];
  _allData.forEach(({ _data: data, record_id, pdf_url }) => {
    const causa     = (typeof data.causa === "object" && data.causa) ? data.causa : {};
    const demandados  = (data.demandados  || []).map((p) => p.nombre).join("; ");
    const demandantes = (data.demandantes || []).map((p) => p.nombre).join("; ");
    const tramites    = (data.tramites    || []).map((t) => t.descripcion).join("; ");
    const values = [
      data.rol || record_id,
      data.descripcion || causa.descripcion || "",
      data.fecha_proceso || causa.fecha_causa || "",
      data.juzgado || "",
      causa.estado || "",
      causa.fecha_estado || "",
      causa.placa_patente || "",
      causa.actuario || "",
      causa.remisor || "",
      causa.fecha_citacion || causa["fecha_citación"] || "",
      causa.boleta_numero || "",
      causa.boleta_fecha || "",
      demandados,
      demandantes,
      tramites,
      pdf_url || "",
    ].map((v) => `"${String(v ?? "").replace(/"/g, '""')}"`);
    csvRows.push(values.join(","));
  });
  const blob = new Blob(["﻿" + csvRows.join("\r\n")], { type: "text/csv;charset=utf-8;" });
  const url  = URL.createObjectURL(blob);
  const a    = document.createElement("a");
  a.href = url;
  a.download = `causas_${new Date().toISOString().slice(0, 10)}.csv`;
  a.click();
  URL.revokeObjectURL(url);
});

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
