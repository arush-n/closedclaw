/**
 * OpenMemory (openmemory-mcp) fetch helpers
 * Provides request/json methods for calling the openmemory API without auth
 */

const DEFAULT_OPENMEMORY_URL = "http://localhost:8766";
const DEFAULT_TIMEOUT_MS = 8_000;

export function getOpenMemoryUrl(): string {
  return process.env.OPENMEMORY_API_URL || DEFAULT_OPENMEMORY_URL;
}

/**
 * Raw fetch request to openmemory-mcp, returns Response
 */
export async function openMemoryRequest(
  pathname: string,
  init?: RequestInit & { timeoutMs?: number }
): Promise<Response> {
  const url = `${getOpenMemoryUrl()}${pathname}`;
  const timeoutMs = init?.timeoutMs ?? DEFAULT_TIMEOUT_MS;

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);

  try {
    return await fetch(url, {
      ...(init || {}),
      signal: controller.signal,
      cache: "no-store",
    });
  } finally {
    clearTimeout(timeout);
  }
}

/**
 * JSON request to openmemory-mcp, returns parsed data + status code
 */
export async function openMemoryJson<T>(
  pathname: string,
  init?: RequestInit & { timeoutMs?: number }
): Promise<{ data: T; status: number }> {
  try {
    const response = await openMemoryRequest(pathname, init);
    const data = (await response.json()) as T;
    return { data, status: response.status };
  } catch (error) {
    throw new Error(
      `OpenMemory request failed: ${error instanceof Error ? error.message : "Unknown error"}`
    );
  }
}
