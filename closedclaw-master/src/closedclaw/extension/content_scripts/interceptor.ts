/**
 * Content script interceptor — hooks AI chat submit buttons to enrich
 * prompts with memory context before they reach the provider.
 *
 * Detects the current site, loads the appropriate adapter, and intercepts
 * form submissions to run through the Openclaw pipeline.
 */

import { chatgptAdapter } from "./sites/chatgpt";
import { claudeAdapter } from "./sites/claude";
import { geminiAdapter } from "./sites/gemini";
import { genericAdapter } from "./sites/generic";
import { injectEnrichedPrompt } from "./injector";
import { showConsentUI } from "./consent_ui";

// ── Site Adapter Interface ───────────────────────────────────────────

export interface SiteAdapter {
  name: string;
  matches: string[];
  getInputElement(): HTMLElement | null;
  getSubmitButton(): HTMLElement | null;
  getPromptText(el: HTMLElement): string;
  setPromptText(el: HTMLElement, text: string): void;
}

// ── Adapter Selection ────────────────────────────────────────────────

const adapters: SiteAdapter[] = [chatgptAdapter, claudeAdapter, geminiAdapter];

function detectAdapter(): SiteAdapter {
  const host = window.location.hostname;
  for (const adapter of adapters) {
    if (adapter.matches.some((m) => host.includes(m))) return adapter;
  }
  return genericAdapter;
}

// ── Interception Logic ───────────────────────────────────────────────

let interceptActive = false;

async function interceptSubmit(adapter: SiteAdapter): Promise<void> {
  const input = adapter.getInputElement();
  if (!input) return;

  const prompt = adapter.getPromptText(input);
  if (!prompt) return;

  try {
    const response = await chrome.runtime.sendMessage({
      type: "PROCESS_PROMPT",
      payload: {
        prompt,
        site: adapter.name,
        url: window.location.href,
      },
    });

    if (!response?.success || !response.data) return;

    const { data } = response;

    // Handle consent requirement
    if (data.consent_required) {
      const userConsent = await showConsentUI(data.consent_message || "Allow memory access?");
      if (!userConsent) return;
    }

    // Inject enriched prompt if server returned one
    if (data.sanitized_context || data.system_prefix) {
      injectEnrichedPrompt(adapter, input, data);
    }
  } catch {
    // Silently fail — don't block the user's chat
  }
}

// ── Submit Button Hook ───────────────────────────────────────────────

function hookSubmitButton(adapter: SiteAdapter): void {
  const observer = new MutationObserver(() => {
    const btn = adapter.getSubmitButton();
    if (!btn || btn.dataset.openclawHooked) return;

    btn.dataset.openclawHooked = "true";
    btn.addEventListener(
      "click",
      (e) => {
        if (interceptActive) return;
        interceptActive = true;

        // Don't prevent default — let the submit go through after enrichment
        interceptSubmit(adapter).finally(() => {
          interceptActive = false;
        });
      },
      { capture: true }
    );
  });

  observer.observe(document.body, { childList: true, subtree: true });

  // Also hook Enter key on the input
  document.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey && !interceptActive) {
      const input = adapter.getInputElement();
      if (input && document.activeElement === input) {
        interceptActive = true;
        interceptSubmit(adapter).finally(() => {
          interceptActive = false;
        });
      }
    }
  }, { capture: true });
}

// ── Init ─────────────────────────────────────────────────────────────

function init(): void {
  const adapter = detectAdapter();

  // Check if extension is enabled
  chrome.runtime.sendMessage({ type: "GET_STATUS" }, (resp) => {
    if (resp?.data?.enabled === false) return;
    hookSubmitButton(adapter);
  });
}

// Run when DOM is ready
if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", init);
} else {
  init();
}
