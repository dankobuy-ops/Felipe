// ── Config ────────────────────────────────────────────────────────────────────
const SUPABASE_URL     = "https://xjlpsgchgfxryvhhrklx.supabase.co";
const SUPABASE_ANON    = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InhqbHBzZ2NoZ2Z4cnl2aGhya2x4Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODA1MDU2NzAsImV4cCI6MjA5NjA4MTY3MH0.LVxF3eX8S8FqcLHHHr7l_LkM1R3fJ7SSbg0ZNM1hM-g";
const GH_REPO          = "dankobuy-ops/Felipe";
const WORKFLOW_FILE    = "scrape.yml";
const POLL_INTERVAL_MS = 8000;

// ── Storage helpers ───────────────────────────────────────────────────────────
const getPAT  = () => localStorage.getItem("gh_pat") || "";
const setPAT  = (v) => localStorage.setItem("gh_pat", v);

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
  }
}

// ── Setup screen ──────────────────────────────────────────────────────────────
document.getElementById("setup-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const pat = document.getElementById("pat-input").value.trim();
  const err = document.getElementById("setup-error");
  err.classList.add("hidden");

  // Quick validation — try listing workflows
  try {
    const r = await fetch(`https://api.github.com/repos/${GH_REPO}/actions/workflows`, {
      headers: { Authorization: `Bearer ${pat}`, Accept: "application/vnd.github+json" },
    });
    if (!r.ok) throw new Error(`GitHub rechazó el token (${r.status})`);
    setPAT(pat);
    showScreen("screen-trigger");
  } catch (ex) {
    err.textContent = ex.message;
    err.classList.remove("hidden");
  }
});

document.getElementById("settings-btn").addEventListener("click", () => {
  document.getElementById("pat-input").value = getPAT();
  showScreen("screen-setup");
});

// ── Trigger screen ────────────────────────────────────────────────────────────
document.getElementById("trigger-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const btn    = document.getElementById("submit-btn");
  const err    = document.getElementById("trigger-error");
  const rut    = document.getElementById("search-code").value.trim();
  const url    = document.getElementById("target-url").value.trim();
  const jobId  = crypto.randomUUID();

  btn.disabled = true;
  btn.textContent = "Iniciando…";
  err.classList.add("hidden");

  try {
    await triggerWorkflow(jobId, rut, url);
    showResultsScreen(jobId, rut);
  } catch (ex) {
    err.textContent = ex.message;
    err.classList.remove("hidden");
    btn.disabled = false;
    btn.textContent = "Consultar";
  }
});

async function triggerWorkflow(jobId, rut, targetUrl) {
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
          search_code:    rut,
          target_url:     targetUrl,
          resume_attempt: "0",
        },
      }),
    }
  );
  if (!r.ok) {
    const body = await r.text().catch(() => "");
    throw new Error(`GitHub error ${r.status}: ${body || "sin detalle"}`);
  }
}

// ── Results screen ────────────────────────────────────────────────────────────
let pollTimer = null;

function showResultsScreen(jobId, rut) {
  document.getElementById("job-id-display").textContent = jobId;
  document.getElementById("rut-display").textContent    = rut;
  document.getElementById("job-status-badge").textContent = "ejecutando";
  document.getElementById("job-status-badge").className   = "badge";
  document.getElementById("results-body").innerHTML = "";
  document.getElementById("progress-bar").style.width = "0%";
  document.getElementById("progress-label").textContent = "Iniciando…";
  document.getElementById("results-empty").classList.add("hidden");
  document.getElementById("results-error").classList.add("hidden");
  showScreen("screen-results");
  pollResults(jobId);
}

document.getElementById("back-btn").addEventListener("click", () => {
  clearTimeout(pollTimer);
  document.getElementById("submit-btn").disabled = false;
  document.getElementById("submit-btn").textContent = "Consultar";
  showScreen("screen-trigger");
});

async function pollResults(jobId) {
  try {
    const rows = await fetchCheckpoints(jobId);
    renderResults(rows);
    const jobRow = rows.find((r) => r.record_id === "__job__");
    const status = jobRow ? jobRow.status : "running";
    if (status !== "complete" && status !== "stalled") {
      pollTimer = setTimeout(() => pollResults(jobId), POLL_INTERVAL_MS);
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
    {
      headers: {
        apikey: SUPABASE_ANON,
        Authorization: `Bearer ${SUPABASE_ANON}`,
      },
    }
  );
  if (!r.ok) throw new Error(`Supabase ${r.status}`);
  return r.json();
}

function renderResults(rows) {
  const dataRows  = rows.filter((r) => r.record_id !== "__job__");
  const jobRow    = rows.find((r) => r.record_id === "__job__");
  const status    = jobRow ? jobRow.status : "running";

  // Badge
  const badge = document.getElementById("job-status-badge");
  const labelMap = { complete: "completado", stalled: "detenido", running: "ejecutando" };
  badge.textContent = labelMap[status] || status;
  badge.className   = "badge " + (status === "complete" ? "complete" : status === "stalled" ? "stalled" : "");

  // Progress
  const done = dataRows.filter((r) => r.status === "done").length;
  const pct  = dataRows.length ? Math.round((done / dataRows.length) * 100) : 0;
  document.getElementById("progress-bar").style.width = pct + "%";
  document.getElementById("progress-label").textContent =
    dataRows.length ? `${done} / ${dataRows.length} causas procesadas` : "Esperando primeros resultados…";

  const empty = document.getElementById("results-empty");
  empty.classList.toggle("hidden", dataRows.length > 0);

  // Table
  const tbody = document.getElementById("results-body");
  tbody.innerHTML = "";
  dataRows.forEach((row) => {
    let data = {};
    try { data = JSON.parse(row.text || "{}"); } catch (_) {}

    const causa = (typeof data.causa === "object" && data.causa) ? data.causa : {};
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${esc(data.rol || row.record_id)}</td>
      <td>${esc(data.descripcion || causa.descripcion || "—")}</td>
      <td>${esc(data.fecha_proceso || causa.fecha_causa || "—")}</td>
      <td class="status-${esc(row.status)}">${esc(causa.estado || row.status)}</td>
      <td>${esc(data.juzgado || "—")}</td>
      <td>${row.pdf_url ? `<a class="pdf-link" href="${esc(row.pdf_url)}" target="_blank">PDF</a>` : "—"}</td>
    `;
    tbody.appendChild(tr);
  });
}

function esc(str) {
  return String(str ?? "")
    .replace(/&/g, "&amp;").replace(/</g, "&lt;")
    .replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

// ── Boot ──────────────────────────────────────────────────────────────────────
init();
