/**
 * Popup script — handles the extension popup UI interactions.
 */

// ── DOM Elements ─────────────────────────────────────────────────────

const enableToggle = document.getElementById("enableToggle") as HTMLInputElement;
const statusDot = document.getElementById("statusDot")!;
const statusText = document.getElementById("statusText")!;
const searchInput = document.getElementById("searchInput") as HTMLInputElement;
const searchBtn = document.getElementById("searchBtn")!;
const searchResults = document.getElementById("searchResults")!;
const rulesCount = document.getElementById("rulesCount")!;
const agentsCount = document.getElementById("agentsCount")!;

// ── Status ───────────────────────────────────────────────────────────

async function refreshStatus(): Promise<void> {
  const resp = await chrome.runtime.sendMessage({ type: "GET_STATUS" });

  if (resp?.success && resp.data) {
    const d = resp.data;
    enableToggle.checked = d.enabled !== false;

    if (d.authenticated) {
      statusDot.className = "dot connected";
      statusText.textContent = "Connected to server";
    } else {
      statusDot.className = "dot disconnected";
      statusText.textContent = d.server_reachable === false
        ? "Server not running"
        : "Not authenticated";
    }

    rulesCount.textContent = String(d.active_rules ?? d.constitution_principles ?? "-");
    agentsCount.textContent = String(d.agents_loaded ?? d.total_agents ?? "-");
  } else {
    statusDot.className = "dot disconnected";
    statusText.textContent = "Unable to connect";
  }
}

// ── Toggle ───────────────────────────────────────────────────────────

enableToggle.addEventListener("change", async () => {
  await chrome.runtime.sendMessage({
    type: "TOGGLE_ENABLED",
    payload: { enabled: enableToggle.checked },
  });
  await refreshStatus();
});

// ── Memory Search ────────────────────────────────────────────────────

async function doSearch(): Promise<void> {
  const query = searchInput.value.trim();
  if (!query) return;

  searchResults.innerHTML = '<div class="result-item">Searching...</div>';

  const resp = await chrome.runtime.sendMessage({
    type: "QUERY_MEMORY",
    payload: { query, limit: 5 },
  });

  if (resp?.success && resp.data?.results) {
    const results = resp.data.results as Array<{ memory?: string; content?: string; score?: number }>;
    if (results.length === 0) {
      searchResults.innerHTML = '<div class="result-item">No memories found.</div>';
      return;
    }
    searchResults.innerHTML = results
      .map((r) => {
        const text = r.memory || r.content || "";
        const score = r.score ? ` (${(r.score * 100).toFixed(0)}%)` : "";
        return `<div class="result-item">${escapeHtml(text.slice(0, 200))}${score}</div>`;
      })
      .join("");
  } else {
    searchResults.innerHTML = '<div class="result-item">Search failed. Is the server running?</div>';
  }
}

searchBtn.addEventListener("click", doSearch);
searchInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") doSearch();
});

// ── Helpers ──────────────────────────────────────────────────────────

function escapeHtml(s: string): string {
  const div = document.createElement("div");
  div.textContent = s;
  return div.innerHTML;
}

// ── Init ─────────────────────────────────────────────────────────────

refreshStatus();
