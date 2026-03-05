/**
 * Background service worker — message routing, session lifecycle, and
 * periodic token refresh for the Openclaw browser extension.
 *
 * Handles messages from content scripts and popup via chrome.runtime.
 */

import { authenticate, apiCall, isAuthenticated, logout, getSession } from "./handshake";

// ── Message Types ────────────────────────────────────────────────────

interface ExtensionMessage {
  type: string;
  payload?: Record<string, unknown>;
}

type MessageResponse = {
  success: boolean;
  data?: unknown;
  error?: string;
};

// ── Enabled State ────────────────────────────────────────────────────

let enabled = true;

async function loadEnabledState(): Promise<void> {
  const stored = await chrome.storage.local.get("openclaw_enabled");
  enabled = stored.openclaw_enabled !== false;
}

// ── Message Handler ──────────────────────────────────────────────────

chrome.runtime.onMessage.addListener(
  (msg: ExtensionMessage, _sender, sendResponse) => {
    handleMessage(msg).then(sendResponse).catch((err) =>
      sendResponse({ success: false, error: err.message })
    );
    return true; // Keep channel open for async response
  }
);

async function handleMessage(msg: ExtensionMessage): Promise<MessageResponse> {
  switch (msg.type) {
    case "PROCESS_PROMPT":
      return handleProcessPrompt(msg.payload as { prompt: string; site: string; url: string });

    case "CAPTURE_MEMORY":
      return handleCaptureMemory(msg.payload as { content: string; source: string; sensitivity?: number });

    case "QUERY_MEMORY":
      return handleQueryMemory(msg.payload as { query: string; limit?: number });

    case "GET_STATUS":
      return handleGetStatus();

    case "TOGGLE_ENABLED":
      return handleToggle(msg.payload as { enabled: boolean });

    case "LOGOUT":
      await logout();
      return { success: true };

    case "AUTHENTICATE":
      await authenticate();
      return { success: true, data: { authenticated: isAuthenticated() } };

    default:
      return { success: false, error: `Unknown message type: ${msg.type}` };
  }
}

// ── Handlers ─────────────────────────────────────────────────────────

async function handleProcessPrompt(
  payload: { prompt: string; site: string; url: string }
): Promise<MessageResponse> {
  if (!enabled) return { success: true, data: { enriched: null, skipped: true } };

  const resp = await apiCall("/addon/process", {
    method: "POST",
    body: JSON.stringify({
      prompt: payload.prompt,
      site: payload.site,
      url: payload.url,
    }),
  });

  if (!resp.ok) {
    return { success: false, error: `Server returned ${resp.status}` };
  }

  const data = await resp.json();
  return { success: true, data };
}

async function handleCaptureMemory(
  payload: { content: string; source: string; sensitivity?: number }
): Promise<MessageResponse> {
  const resp = await apiCall("/addon/memory/capture", {
    method: "POST",
    body: JSON.stringify(payload),
  });

  if (!resp.ok) {
    return { success: false, error: `Capture failed: ${resp.status}` };
  }

  const data = await resp.json();
  return { success: true, data };
}

async function handleQueryMemory(
  payload: { query: string; limit?: number }
): Promise<MessageResponse> {
  const params = new URLSearchParams({ query: payload.query });
  if (payload.limit) params.set("limit", String(payload.limit));

  const resp = await apiCall(`/addon/memory/query?${params.toString()}`);

  if (!resp.ok) {
    return { success: false, error: `Query failed: ${resp.status}` };
  }

  const data = await resp.json();
  return { success: true, data };
}

async function handleGetStatus(): Promise<MessageResponse> {
  try {
    const resp = await apiCall("/addon/status");
    if (!resp.ok) throw new Error(`Status ${resp.status}`);
    const data = await resp.json();
    return { success: true, data: { ...data, enabled, authenticated: isAuthenticated() } };
  } catch {
    return {
      success: true,
      data: { enabled, authenticated: false, server_reachable: false },
    };
  }
}

async function handleToggle(
  payload: { enabled: boolean }
): Promise<MessageResponse> {
  enabled = payload.enabled;
  await chrome.storage.local.set({ openclaw_enabled: enabled });

  // Update badge
  chrome.action.setBadgeText({ text: enabled ? "" : "OFF" });
  chrome.action.setBadgeBackgroundColor({ color: "#888" });

  return { success: true, data: { enabled } };
}

// ── Session Refresh Alarm ────────────────────────────────────────────

chrome.alarms.create("openclaw_session_refresh", { periodInMinutes: 50 });

chrome.alarms.onAlarm.addListener(async (alarm) => {
  if (alarm.name === "openclaw_session_refresh" && enabled) {
    try {
      await authenticate();
    } catch {
      // Will retry next alarm
    }
  }
});

// ── Startup ──────────────────────────────────────────────────────────

loadEnabledState();
