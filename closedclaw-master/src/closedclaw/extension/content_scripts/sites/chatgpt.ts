/**
 * ChatGPT site adapter — selectors and hooks for chat.openai.com / chatgpt.com.
 */

import type { SiteAdapter } from "../interceptor";

export const chatgptAdapter: SiteAdapter = {
  name: "chatgpt",
  matches: ["chat.openai.com", "chatgpt.com"],

  getInputElement(): HTMLElement | null {
    return document.querySelector("#prompt-textarea") as HTMLElement | null;
  },

  getSubmitButton(): HTMLElement | null {
    return document.querySelector('[data-testid="send-button"]') as HTMLElement | null;
  },

  getPromptText(el: HTMLElement): string {
    // ChatGPT uses a contenteditable div
    return el.innerText?.trim() ?? "";
  },

  setPromptText(el: HTMLElement, text: string): void {
    el.innerText = text;
    // Dispatch input event so React picks up the change
    el.dispatchEvent(new Event("input", { bubbles: true }));
  },
};
