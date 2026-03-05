/**
 * Gemini site adapter — selectors and hooks for gemini.google.com.
 */

import type { SiteAdapter } from "../interceptor";

export const geminiAdapter: SiteAdapter = {
  name: "gemini",
  matches: ["gemini.google.com"],

  getInputElement(): HTMLElement | null {
    const rich = document.querySelector("rich-textarea");
    if (rich) {
      return rich.querySelector("textarea") as HTMLElement | null ?? rich as HTMLElement;
    }
    return document.querySelector(".ql-editor") as HTMLElement | null;
  },

  getSubmitButton(): HTMLElement | null {
    return document.querySelector(".send-button, [aria-label='Send message']") as HTMLElement | null;
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
