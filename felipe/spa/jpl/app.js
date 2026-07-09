// ── Config ────────────────────────────────────────────────────────────────────
const GH_REPO          = "dankobuy-ops/Felipe";
const BATCH_WORKFLOW   = "scrape-all.yml";
const SHEET_ID         = "1SqP0w1XjvMGoEpBnbXI16EuneJMhrrSJq3hvvw_Azuo";
const POLL_INTERVAL_MS = 8000;

// ── Token storage ─────────────────────────────────────────────────────────────
const getPAT = ()  => localStorage.getItem("gh_pat") || "";
const setPAT = (v) => localStorage.setItem("gh_pat", v);

// Bounce back to the token screen when GitHub rejects the saved PAT (401).
function reauth(msg) {
  localStorage.removeItem("gh_pat");
  showScreen("screen-setup");
  const err = document.getElementById("setup-error");
  if (err) {
    err.textContent = msg || "Token de GitHub inválido o expirado. Ingresa uno nuevo.";
    err.classList.remove("hidden");
  }
}

// ── Sheet access (gviz CSV) — only to show a live causa count ──────────────────
function parseCSV(text) {
  const rows = []; let row = [], field = "", inQ = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (inQ) {
      if (c === '"') { if (text[i + 1] === '"') { field += '"'; i++; } else inQ = false; }
      else field += c;
    } else if (c === '"') inQ = true;
    else if (c === ",") { row.push(field); field = ""; }
    else if (c === "\r") { /* skip */ }
    else if (c === "\n") { row.push(field); rows.push(row); row = []; field = ""; }
    else field += c;
  }
  if (field.length || row.length) { row.push(field); rows.push(row); }
  return rows;
}

function csvRowCount(text) {
  const rows = parseCSV(text);
  if (rows.length <= 1) return 0;                 // header only / empty
  let n = 0;
  for (let r = 1; r < rows.length; r++) {
    if (rows[r].length === 1 && rows[r][0] === "") continue;
    n++;
  }
  return n;
}

async function causaCount() {
  try {
    const cb  = `${Date.now()}_${Math.random().toString(36).slice(2)}`;
    const url = `https://docs.google.com/spreadsheets/d/${SHEET_ID}/gviz/tq?tqx=out:csv&sheet=Causas&cb=${cb}`;
    const r = await fetch(url, { cache: "no-store" });
    if (!r.ok) return null;
    return csvRowCount(await r.text());
  } catch (_) { return null; }
}

// ── Screen router ─────────────────────────────────────────────────────────────
function showScreen(id) {
  document.querySelectorAll(".screen").forEach((s) => {
    s.classList.toggle("hidden", s.id !== id);
  });
}

// ── Batch job: dispatch scrape-all.yml + live running indicator ────────────────
let batchPollTimer = null;

async function batchLatestRun() {
  const r = await fetch(
    `https://api.github.com/repos/${GH_REPO}/actions/workflows/${BATCH_WORKFLOW}/runs?per_page=1`,
    { headers: { Authorization: `Bearer ${getPAT()}`, Accept: "application/vnd.github+json" } }
  );
  if (r.status === 401) { reauth(); return null; }
  if (!r.ok) return null;
  const { workflow_runs = [] } = await r.json();
  return workflow_runs[0] || null;
}

function _batchSpinner(on) {
  const sp = document.querySelector("#batch-status .spinner");
  if (sp) sp.classList.toggle("hidden", !on);
}

// Poll the batch workflow's latest run; reflect running/idle + live causa count.
async function pollBatch() {
  clearTimeout(batchPollTimer);
  const btn = document.getElementById("batch-run-btn");
  if (!btn) return;
  const statusWrap = document.getElementById("batch-status");
  const statusText = document.getElementById("batch-status-text");
  const barWrap    = document.getElementById("batch-progress-wrap");

  let run = null;
  try { run = await batchLatestRun(); } catch (_) {}
  const active = run && ["in_progress", "queued", "requested", "waiting", "pending"].includes(run.status);
  const count  = await causaCount();
  const countTxt = count == null ? "" : ` · ${count} causas en la planilla`;

  statusWrap.classList.remove("hidden");
  if (active) {
    btn.disabled = true;
    btn.textContent = "⏳ Consulta en curso…";
    _batchSpinner(true);
    barWrap.classList.remove("hidden");
    statusText.textContent = `Ejecutando en GitHub${countTxt}`;
    batchPollTimer = setTimeout(pollBatch, POLL_INTERVAL_MS);
  } else {
    btn.disabled = false;
    btn.textContent = "▶️ Iniciar consulta masiva — todos los RUT (2020+)";
    _batchSpinner(false);
    barWrap.classList.add("hidden");
    if (run) {
      const when  = run.updated_at ? new Date(run.updated_at).toLocaleString() : "";
      const concl = run.conclusion === "success"   ? "completada ✓"
                  : run.conclusion === "cancelled" ? "detenida"
                  : run.conclusion ? run.conclusion : "—";
      statusText.textContent = `Última consulta: ${concl}${countTxt}${when ? " · " + when : ""}`;
    } else {
      statusWrap.classList.add("hidden");
    }
  }
}

function startBatchWatch() {
  if (getPAT()) pollBatch();
}

document.getElementById("batch-run-btn").addEventListener("click", async () => {
  const btn = document.getElementById("batch-run-btn");
  btn.disabled = true;
  btn.textContent = "Iniciando…";
  try {
    const r = await fetch(
      `https://api.github.com/repos/${GH_REPO}/actions/workflows/${BATCH_WORKFLOW}/dispatches`,
      {
        method: "POST",
        headers: {
          Authorization: `Bearer ${getPAT()}`,
          Accept: "application/vnd.github+json",
          "Content-Type": "application/json",
          "X-GitHub-Api-Version": "2022-11-28",
        },
        body: JSON.stringify({ ref: "main", inputs: {} }),
      }
    );
    if (!r.ok) {
      const body = await r.text().catch(() => "");
      if (r.status === 401) reauth();
      throw new Error(`GitHub ${r.status}: ${body || "sin detalle"}`);
    }
    document.getElementById("batch-status").classList.remove("hidden");
    _batchSpinner(true);
    document.getElementById("batch-status-text").textContent = "Iniciando en GitHub…";
    // Give GitHub a few seconds to register the run, then start polling.
    clearTimeout(batchPollTimer);
    batchPollTimer = setTimeout(pollBatch, 5000);
  } catch (ex) {
    btn.disabled = false;
    btn.textContent = "Error — reintentar";
    btn.title = ex.message;
  }
});

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
    startBatchWatch();
  } catch (ex) {
    err.textContent = ex.message;
    err.classList.remove("hidden");
  }
});

// ── Boot ──────────────────────────────────────────────────────────────────────
function init() {
  if (!getPAT()) {
    showScreen("screen-setup");
  } else {
    showScreen("screen-trigger");
    startBatchWatch();
  }
}

init();
