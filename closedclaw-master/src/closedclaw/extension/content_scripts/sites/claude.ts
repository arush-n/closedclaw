/**
 * Claude.ai site adapter — selectors and hooks for claude.ai.
 */

import type { SiteAdapter } from "../interceptor";

export const claudeAdapter: SiteAdapter = {
  name: "claude",
  matches: ["claude.ai"],

  getInputElement(): HTMLElement | null {
    return document.querySelector(".ProseMirror") as HTMLElement | null;
  },

  getSubmitButton(): HTMLElement | null {
    return document.querySelector('button[aria-label="Send Message"]') as HTMLElement | null;
  },

  getPromptText(el: HTMLElement): string {
    return el.innerText?.trim() ?? "";
  },

  setPromptText(el: HTMLElement, text: string): void {
    el.innerText = text;
    el.dispatchEvent(new Event("input", { bubbles: true }));
  },
};
