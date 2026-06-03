// Trigger endpoint — the thin backend hop that holds the PAT and fires workflow_dispatch.
// Set this to wherever your backend is running (local script, Cloud Run, etc.)
const TRIGGER_ENDPOINT = "/api/trigger";

// Polling interval for results (ms)
const POLL_INTERVAL = 8000;

// ── Screens ──────────────────────────────────────────────────────────────────

function showScreen(id) {
  document.querySelectorAll(".screen").forEach((s) => {
    s.classList.toggle("active", s.id === id);
    s.classList.toggle("hidden", s.id !== id);
  });
}

// ── Screen 1: Trigger ────────────────────────────────────────────────────────

document.getElementById("trigger-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const btn = document.getElementById("submit-btn");
  const errEl = document.getElementById("trigger-error");

  btn.disabled = true;
  btn.textContent = "Starting…";
  errEl.classList.add("hidden");

  const searchCode = document.getElementById("search-code").value.trim();
  const targetUrl = document.getElementById("target-url").value.trim();
  const jobId = crypto.randomUUID();

  try {
    const res = await fetch(TRIGGER_ENDPOINT, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ job_id: jobId, search_code: searchCode, target_url: targetUrl }),
    });

    if (!res.ok) {
      const body = await res.text();
      throw new Error(`Trigger failed (${res.status}): ${body}`);
    }

    startResultsScreen(jobId, searchCode);
  } catch (err) {
    errEl.textContent = err.message;
    errEl.classList.remove("hidden");
    btn.disabled = false;
    btn.textContent = "Start scrape";
  }
});

// ── Screen 2: Results ────────────────────────────────────────────────────────

let pollTimer = null;

function startResultsScreen(jobId, searchCode) {
  document.getElementById("job-id-display").textContent = jobId;
  document.getElementById("job-status-badge").textContent = "running";
  document.getElementById("job-status-badge").className = "badge";
  document.getElementById("results-body").innerHTML = "";
  document.getElementById("progress-label").textContent = "Loading…";
  document.getElementById("progress-bar").style.width = "0%";
  showScreen("screen-results");
  pollResults(jobId);
}

document.getElementById("back-btn").addEventListener("click", () => {
  clearTimeout(pollTimer);
  showScreen("screen-trigger");
});

async function pollResults(jobId) {
  try {
    const res = await fetch(`/api/results?job_id=${encodeURIComponent(jobId)}`);
    if (!res.ok) throw new Error(`Results fetch failed (${res.status})`);
    const data = await res.json();
    renderResults(data);

    if (data.status !== "complete" && data.status !== "stalled") {
      pollTimer = setTimeout(() => pollResults(jobId), POLL_INTERVAL);
    }
  } catch (err) {
    document.getElementById("results-error").textContent = err.message;
    document.getElementById("results-error").classList.remove("hidden");
    pollTimer = setTimeout(() => pollResults(jobId), POLL_INTERVAL);
  }
}

function renderResults(data) {
  // Badge
  const badge = document.getElementById("job-status-badge");
  badge.textContent = data.status;
  badge.className = "badge " + (data.status === "complete" ? "complete" : data.status === "stalled" ? "stalled" : "");

  // Progress bar
  const records = data.records || [];
  const done = records.filter((r) => r.status === "done").length;
  const pct = records.length ? Math.round((done / records.length) * 100) : 0;
  document.getElementById("progress-bar").style.width = pct + "%";
  document.getElementById("progress-label").textContent =
    records.length ? `${done} / ${records.length} records done` : "Waiting for first record…";

  // Table
  const tbody = document.getElementById("results-body");
  tbody.innerHTML = "";
  records.forEach((r, i) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${i + 1}</td>
      <td>${escHtml(r.record_id)}</td>
      <td class="status-${r.status}">${r.status}</td>
      <td>${escHtml(r.text || "")}</td>
      <td>${r.pdf_url ? `<a class="pdf-link" href="${escHtml(r.pdf_url)}" target="_blank">PDF</a>` : "—"}</td>
    `;
    tbody.appendChild(tr);
  });
}

function escHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
