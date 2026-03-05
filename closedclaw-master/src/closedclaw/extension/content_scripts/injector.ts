/**
 * Prompt injector — inserts enriched context from the Openclaw pipeline
 * into the AI chat input before submission.
 *
 * The injection is invisible to the user (context is prepended as a
 * system-style block that most AI providers will parse as instructions).
 */

import type { SiteAdapter } from "./interceptor";

interface ProcessResponse {
  sanitized_context?: string;
  system_prefix?: string;
  copyright_citations?: Array<{ source: string; citation: string }>;
}

export function injectEnrichedPrompt(
  adapter: SiteAdapter,
  inputEl: HTMLElement,
  data: ProcessResponse
): void {
  const originalPrompt = adapter.getPromptText(inputEl);
  if (!originalPrompt) return;

  const parts: string[] = [];

  // Add system prefix (rules + memory context)
  if (data.system_prefix) {
    parts.push(data.system_prefix);
  } else if (data.sanitized_context) {
    parts.push(`[CONTEXT]\n${data.sanitized_context}\n[/CONTEXT]`);
  }

  // Add copyright citations if any
  if (data.copyright_citations?.length) {
    const cites = data.copyright_citations
      .map((c) => `- ${c.citation || c.source}`)
      .join("\n");
    parts.push(`[SOURCES]\n${cites}\n[/SOURCES]`);
  }

  // Prepend context to original prompt
  if (parts.length > 0) {
    const enriched = parts.join("\n\n") + "\n\n" + originalPrompt;
    adapter.setPromptText(inputEl, enriched);
  }
}
