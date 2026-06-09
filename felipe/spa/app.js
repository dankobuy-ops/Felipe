// ── Config ────────────────────────────────────────────────────────────────────
const SUPABASE_URL     = "https://xjlpsgchgfxryvhhrklx.supabase.co";
const SUPABASE_ANON    = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InhqbHBzZ2NoZ2Z4cnl2aGhya2x4Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODA1MDU2NzAsImV4cCI6MjA5NjA4MTY3MH0.LVxF3eX8S8FqcLHHHr7l_LkM1R3fJ7SSbg0ZNM1hM-g";
const GH_REPO          = "dankobuy-ops/Felipe";
const WORKFLOW_FILE    = "scrape.yml";
const POLL_INTERVAL_MS = 8000;

// ── Storage helpers ───────────────────────────────────────────────────────────
const getPAT = () => localStorage.getItem("gh_pat") || "";
const setPAT = (v) => localStorage.setItem("gh_pat", v);

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
  const btn   = document.getElementById("submit-btn");
  const err   = document.getElementById("trigger-error");
  const rut   = document.getElementById("search-code").value.trim();
  const url   = document.getElementById("target-url").value.trim();
  const year  = document.getElementById("year-filter").value.trim();
  const jobId = crypto.randomUUID();

  btn.disabled = true;
  btn.textContent = "Iniciando…";
  err.classList.add("hidden");

  try {
    await triggerWorkflow(jobId, rut, url, year);
    showResultsScreen(jobId, rut, year);
  } catch (ex) {
    err.textContent = ex.message;
    err.classList.remove("hidden");
    btn.disabled = false;
    btn.textContent = "Consultar";
  }
});

async function triggerWorkflow(jobId, rut, targetUrl, year = "") {
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
          year:           year,
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
let pollTimer = null;
let _allData  = [];

function showResultsScreen(jobId, rut, year = "") {
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
});

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
    try { total = JSON.parse(metaRow.text || "{}")?.total || 0; } catch (_) {}
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

  // Parse and store for CSV
  _allData = dataRows.map((row) => {
    let data = {};
    try { data = JSON.parse(row.text || "{}"); } catch (_) {}
    return { ...row, _data: data };
  });

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

  // Trámites (Sección C)
  const tramites = data.tramites || [];
  if (tramites.length) {
    const trows = tramites.map((t) => {
      const href = safeHref(t.href);
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
      const href = safeHref(a.href);
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
