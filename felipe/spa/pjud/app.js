// PJUD — dispatch a scrape on GitHub Actions and watch it run.
//
// Same shape as the JPL app: a PAT in localStorage, the REST API for dispatch, polling for
// status. The difference is that this workflow takes real inputs (a date window, a procedimiento
// filter, how many runners) and can run for hours, so the progress panel reports STEPS and
// elapsed time rather than just "running".
//
// ⚠️ A running job's LOG is not readable through the API — GitHub only serves logs once the job
// finishes. So "progress" here is honest about what it can see: which step is active and for how
// long. Do not add a causa counter that pretends to read the log live.

const GH_REPO   = "dankobuy-ops/Felipe";
const WORKFLOW  = "pjud-censo.yml";
const REF       = "main";
const POLL_MS   = 10000;

// ── The passes. `wired:false` ones exist in the UI but have no workflow behind them yet —
// dispatching them would start a job that does nothing, so the button refuses instead. ────────
const MODES = [
  {
    id: "meta",
    name: "Metadata + ebook",
    desc: "Abre cada causa de banco, guarda litigantes, cuadernos e historia, y baja el ebook.",
    wired: true,
    inputs: { detail: "true" },
  },
  {
    id: "docs",
    name: "Todos los PDFs + georreferencia",
    desc: "Demanda, certificado, mandamiento y el resto de documentos, más la dirección del demandado.",
    wired: false,
    note: "Es el trabajo del worker B, que todavía no está conectado a este sitio.",
  },
  {
    id: "update",
    name: "Actualizar",
    desc: "Revisa causas ya guardadas y trae lo que haya cambiado desde la última pasada.",
    wired: false,
    note: "Falta definir qué cuenta como cambio antes de conectarlo.",
  },
];

let mode = MODES[0].id;
let pollTimer = null;

// ── Token ─────────────────────────────────────────────────────────────────────
const getPAT = () => localStorage.getItem("gh_pat") || "";
const setPAT = (v) => localStorage.setItem("gh_pat", v);

function reauth(msg) {
  localStorage.removeItem("gh_pat");
  showScreen("screen-setup");
  const err = document.getElementById("setup-error");
  err.textContent = msg || "GitHub rechazó el token. Ingresa uno nuevo.";
  err.classList.remove("hidden");
}

async function gh(path, opts = {}) {
  const r = await fetch(`https://api.github.com/repos/${GH_REPO}${path}`, {
    ...opts,
    headers: {
      Authorization: `Bearer ${getPAT()}`,
      Accept: "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
      ...(opts.headers || {}),
    },
  });
  if (r.status === 401) { reauth(); throw new Error("token inválido"); }
  return r;
}

function showScreen(id) {
  document.querySelectorAll(".screen").forEach((s) => s.classList.toggle("hidden", s.id !== id));
}

// ── Dates ─────────────────────────────────────────────────────────────────────
// The workflow wants dd/mm/aaaa; <input type=date> gives aaaa-mm-dd.
const toCL = (iso) => { const [y, m, d] = iso.split("-"); return `${d}/${m}/${y}`; };

function defaultDates() {
  const now = new Date();
  const first = new Date(now.getFullYear(), now.getMonth() - 1, 1);
  const last  = new Date(now.getFullYear(), now.getMonth(), 0);
  const iso = (d) => d.toISOString().slice(0, 10);
  document.getElementById("desde").value = iso(first);
  document.getElementById("hasta").value = iso(last);
}

function readDates() {
  const d = document.getElementById("desde").value;
  const h = document.getElementById("hasta").value;
  const err = document.getElementById("date-error");
  err.classList.add("hidden");
  if (!d || !h) { err.textContent = "Faltan las fechas."; err.classList.remove("hidden"); return null; }
  if (d > h)    { err.textContent = "«Desde» es posterior a «Hasta»."; err.classList.remove("hidden"); return null; }
  return { desde: toCL(d), hasta: toCL(h) };
}

// ── Mode cards ────────────────────────────────────────────────────────────────
function renderModes() {
  const grid = document.getElementById("mode-grid");
  grid.innerHTML = "";
  MODES.forEach((m) => {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "mode-btn" + (m.id === mode ? " active" : "") + (m.wired ? "" : " pending");
    b.innerHTML =
      `<span class="mb-name">${m.name}${m.wired ? "" : ' <span class="tag">sin conectar</span>'}</span>` +
      `<span class="mb-desc">${m.desc}</span>`;
    b.addEventListener("click", () => { mode = m.id; renderModes(); syncRunButton(); });
    grid.appendChild(b);
  });
}

function currentMode() { return MODES.find((m) => m.id === mode); }

function syncRunButton() {
  const m = currentMode();
  const btn = document.getElementById("run-btn");
  const note = document.getElementById("mode-note");
  btn.disabled = !m.wired;
  btn.textContent = m.wired ? "▶️ Iniciar" : "No disponible todavía";
  note.textContent = m.wired ? "" : m.note;
  note.classList.toggle("hidden", m.wired);
}

// ── Dispatch ──────────────────────────────────────────────────────────────────
document.getElementById("run-btn").addEventListener("click", async () => {
  const m = currentMode();
  if (!m.wired) return;
  const dates = readDates();
  if (!dates) return;

  const btn = document.getElementById("run-btn");
  const err = document.getElementById("run-error");
  err.classList.add("hidden");
  btn.disabled = true;
  btn.textContent = "Iniciando…";

  const inputs = {
    ...dates,
    ...m.inputs,
    shards: document.getElementById("shards").value,
    only_proc: document.getElementById("only-proc").value.trim(),
    resume: document.getElementById("resume").checked ? "true" : "false",
  };

  try {
    const r = await gh(`/actions/workflows/${WORKFLOW}/dispatches`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ref: REF, inputs }),
    });
    if (!r.ok) throw new Error(`GitHub ${r.status}: ${(await r.text()) || "sin detalle"}`);
    btn.textContent = "Iniciando…";
    // GitHub needs a moment to register the run before it appears in the list.
    clearTimeout(pollTimer);
    pollTimer = setTimeout(poll, 4000);
  } catch (ex) {
    btn.disabled = false;
    btn.textContent = "▶️ Iniciar";
    err.textContent = ex.message;
    err.classList.remove("hidden");
  }
});

// ── Progress ──────────────────────────────────────────────────────────────────
const ACTIVE = ["in_progress", "queued", "requested", "waiting", "pending"];

function human(ms) {
  const s = Math.floor(ms / 1000);
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60);
  return h ? `${h} h ${m} min` : `${m} min`;
}

function conclusionLabel(c) {
  return { success: "completada ✓", failure: "falló", cancelled: "detenida",
           timed_out: "expiró", skipped: "omitida" }[c] || c || "—";
}

async function runSteps(runId) {
  try {
    const r = await gh(`/actions/runs/${runId}/jobs`);
    if (!r.ok) return null;
    const { jobs = [] } = await r.json();
    // The matrix job is the one doing the work; the tiny `plan` job is noise.
    return jobs.find((j) => j.name.toLowerCase().startsWith("censo")) || jobs[0] || null;
  } catch (_) { return null; }
}

function renderSteps(job) {
  const ol = document.getElementById("prog-steps");
  ol.innerHTML = "";
  if (!job || !job.steps) return;
  job.steps
    .filter((s) => !/^(Post |Complete job|Set up job)/.test(s.name))
    .forEach((s) => {
      const li = document.createElement("li");
      const state = s.status !== "completed" ? "run"
                  : s.conclusion === "success" ? "ok"
                  : s.conclusion === "skipped" ? "skip" : "bad";
      const mark = { run: "◐", ok: "✓", skip: "·", bad: "✕" }[state];
      let extra = "";
      if (s.status === "in_progress" && s.started_at) {
        extra = ` — ${human(Date.now() - new Date(s.started_at))}`;
      }
      li.className = `step ${state}`;
      li.innerHTML = `<span class="sm">${mark}</span><span>${s.name}${extra}</span>`;
      ol.appendChild(li);
    });
}

async function poll() {
  clearTimeout(pollTimer);
  if (!getPAT()) return;

  let runs = [];
  try {
    const r = await gh(`/actions/workflows/${WORKFLOW}/runs?per_page=8`);
    if (r.ok) ({ workflow_runs: runs = [] } = await r.json());
  } catch (_) { return; }

  const run = runs[0];
  const card = document.getElementById("progress-card");
  const btn  = document.getElementById("run-btn");

  if (!run) { card.classList.add("hidden"); renderHistory(runs); syncRunButton(); return; }

  const active = ACTIVE.includes(run.status);
  card.classList.remove("hidden");
  document.getElementById("prog-spinner").classList.toggle("hidden", !active);
  document.getElementById("prog-link").href = run.html_url;

  const badge = document.getElementById("prog-badge");
  badge.textContent = active ? "en curso" : conclusionLabel(run.conclusion);
  badge.className = "badge" + (active ? "" : run.conclusion === "success" ? " complete" : " stalled");

  const started = run.run_started_at ? new Date(run.run_started_at) : null;
  const ended   = active ? null : new Date(run.updated_at);
  document.getElementById("prog-title").textContent = active ? "Corrida en curso" : "Última corrida";
  document.getElementById("prog-meta").textContent =
    (started ? `Inició ${started.toLocaleString()}` : "") +
    (started ? ` · ${human((ended || new Date()) - started)}` : "");

  if (active) {
    btn.disabled = true;
    btn.textContent = "⏳ Corriendo…";
    renderSteps(await runSteps(run.id));
    pollTimer = setTimeout(poll, POLL_MS);
  } else {
    syncRunButton();
    renderSteps(await runSteps(run.id));
  }
  renderHistory(runs);
}

function renderHistory(runs) {
  const ul = document.getElementById("history");
  ul.innerHTML = "";
  runs.slice(0, 8).forEach((r) => {
    const li = document.createElement("li");
    li.className = "history-item";
    const active = ACTIVE.includes(r.status);
    const cls = active ? "" : r.conclusion === "success" ? " complete" : " stalled";
    const dur = r.run_started_at
      ? human(new Date(r.updated_at) - new Date(r.run_started_at)) : "";
    li.innerHTML =
      `<div class="hi-main">` +
        `<span class="hi-rut">#${r.run_number}</span>` +
        `<span class="hi-year">${new Date(r.run_started_at || r.created_at).toLocaleString()}</span>` +
        `<span class="badge${cls}">${active ? "en curso" : conclusionLabel(r.conclusion)}</span>` +
      `</div>` +
      `<div class="hi-sub">${dur}${r.head_branch ? " · " + r.head_branch : ""}</div>`;
    li.addEventListener("click", () => window.open(r.html_url, "_blank", "noopener"));
    ul.appendChild(li);
  });
}

// ── Setup ─────────────────────────────────────────────────────────────────────
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
    boot();
  } catch (ex) {
    err.textContent = ex.message;
    err.classList.remove("hidden");
  }
});

document.getElementById("btn-forget").addEventListener("click", () => {
  if (confirm("¿Olvidar el token en este dispositivo?")) reauth("Token borrado.");
});
document.getElementById("btn-refresh").addEventListener("click", () => poll());

// ── Boot ──────────────────────────────────────────────────────────────────────
function boot() {
  if (!getPAT()) { showScreen("screen-setup"); return; }
  showScreen("screen-main");
  defaultDates();
  renderModes();
  syncRunButton();
  poll();
}

boot();
