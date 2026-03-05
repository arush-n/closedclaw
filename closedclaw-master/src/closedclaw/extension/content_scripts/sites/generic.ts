/**
 * Generic fallback site adapter — works with standard textarea / contenteditable.
 */

import type { SiteAdapter } from "../interceptor";

export const genericAdapter: SiteAdapter = {
  name: "generic",
  matches: [],

  getInputElement(): HTMLElement | null {
    // Try common patterns
    const candidates = [
      'textarea[placeholder*="message" i]',
      'div[contenteditable="true"]',
      'textarea',
    ];
    for (const sel of candidates) {
      const el = document.querySelector(sel) as HTMLElement | null;
      if (el) return el;
    }
    return null;
  },

  getSubmitButton(): HTMLElement | null {
    return document.querySelector('button[type="submit"]') as HTMLElement | null;
  },

  getPromptText(el: HTMLElement): string {
    if (el instanceof HTMLTextAreaElement) return el.value.trim();
    return el.innerText?.trim() ?? "";
  },

  setPromptText(el: HTMLElement, text: string): void {
    if (el instanceof HTMLTextAreaElement) {
      el.value = text;
    } else {
      el.innerText = text;
    }
    el.dispatchEvent(new Event("input", { bubbles: true }));
  },
};
