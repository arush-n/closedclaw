import fs from "node:fs";
import path from "node:path";

const DEFAULT_API_URL = "http://localhost:8765";
const DEFAULT_TIMEOUT_MS = 4_500;
const TOKEN_CACHE_TTL_MS = 10_000;
const MAX_CACHE_ENTRIES = 200;

type JsonCacheEntry = {
  expiresAt: number;
  status: number;
  data: unknown;
};

const GET_JSON_CACHE = new Map<string, JsonCacheEntry>();
const INFLIGHT_JSON = new Map<string, Promise<{ data: unknown; status: number }>>();

let TOKEN_CACHE: { value?: string; expiresAt: number } = {
  value: undefined,
  expiresAt: 0,
};

function buildCacheKey(pathname: string, init?: RequestInit): string {
  const method = (init?.method || "GET").toUpperCase();
  const body = typeof init?.body === "string" ? init.body : "";
  return `${method}:${pathname}:${body}`;
}

export function getClosedclawApiUrl(): string {
  return process.env.CLOSEDCLAW_API_URL || process.env.MEM0_API_URL || DEFAULT_API_URL;
}

export function getClosedclawToken(): string | undefined {
  if (TOKEN_CACHE.expiresAt > Date.now()) {
    return TOKEN_CACHE.value;
  }

  if (process.env.CLOSEDCLAW_API_TOKEN) return process.env.CLOSEDCLAW_API_TOKEN;
  if (process.env.MEM0_API_KEY) return process.env.MEM0_API_KEY;

  try {
    const homeDir = process.env.USERPROFILE || process.env.HOME;
    if (!homeDir) return undefined;
    const tokenPath = path.join(homeDir, ".closedclaw", "token");
    if (!fs.existsSync(tokenPath)) {
      TOKEN_CACHE = { value: undefined, expiresAt: Date.now() + TOKEN_CACHE_TTL_MS };
      return undefined;
    }
    const token = fs.readFileSync(tokenPath, "utf-8").trim() || undefined;
    TOKEN_CACHE = { value: token, expiresAt: Date.now() + TOKEN_CACHE_TTL_MS };
    return token;
  } catch {
    TOKEN_CACHE = { value: undefined, expiresAt: Date.now() + TOKEN_CACHE_TTL_MS };
    return undefined;
  }
}

export function buildClosedclawHeaders(contentType = true): Record<string, string> {
  const headers: Record<string, string> = {};
  if (contentType) {
    headers["Content-Type"] = "application/json";
  }

  const token = getClosedclawToken();
  if (token) {
    headers.Authorization = `Bearer ${token}`;
    headers["X-API-Key"] = token;
  }

  return headers;
}

export async function closedclawRequest(
  pathname: string,
  init?: RequestInit & { timeoutMs?: number }
): Promise<Response> {
  const url = `${getClosedclawApiUrl()}${pathname}`;
  const controller = new AbortController();
  const timeoutMs = init?.timeoutMs ?? DEFAULT_TIMEOUT_MS;
  const timeout = setTimeout(() => controller.abort(), timeoutMs);

  const { timeoutMs: _timeoutMs, signal, ...requestInit } = init || {};

  const mergedSignal = signal || controller.signal;

  try {
    return await fetch(url, {
      ...requestInit,
      headers: {
        ...buildClosedclawHeaders(!(requestInit?.body == null)),
        ...(requestInit?.headers || {}),
      },
      signal: mergedSignal,
      cache: "no-store",
    });
  } finally {
    clearTimeout(timeout);
  }
}

export async function closedclawJson<T>(
  pathname: string,
  init?: (RequestInit & { timeoutMs?: number }) | undefined,
  options?: { cacheTtlMs?: number; useStaleOnError?: boolean }
): Promise<{ data: T; status: number }> {
  const method = (init?.method || "GET").toUpperCase();
  const cacheTtlMs = options?.cacheTtlMs ?? 0;
  const useStaleOnError = options?.useStaleOnError ?? true;
  const cacheKey = buildCacheKey(pathname, init);

  if (method === "GET") {
    for (const [key, value] of GET_JSON_CACHE.entries()) {
      if (value.expiresAt <= Date.now()) {
        GET_JSON_CACHE.delete(key);
      }
    }
  }

  if (method === "GET" && cacheTtlMs > 0) {
    const cached = GET_JSON_CACHE.get(cacheKey);
    if (cached && cached.expiresAt > Date.now()) {
      return { data: cached.data as T, status: cached.status };
    }
  }

  if (method === "GET") {
    const inflight = INFLIGHT_JSON.get(cacheKey);
    if (inflight) {
      const reused = await inflight;
      return { data: reused.data as T, status: reused.status };
    }
  }

  const requestPromise = (async () => {
    try {
      const response = await closedclawRequest(pathname, init);
      const data = (await response.json()) as T;

      if (method === "GET" && cacheTtlMs > 0 && response.ok) {
        if (GET_JSON_CACHE.size >= MAX_CACHE_ENTRIES) {
          const oldestKey = GET_JSON_CACHE.keys().next().value;
          if (oldestKey) {
            GET_JSON_CACHE.delete(oldestKey);
          }
        }
        GET_JSON_CACHE.set(cacheKey, {
          expiresAt: Date.now() + cacheTtlMs,
          status: response.status,
          data,
        });
      }

      return { data, status: response.status };
    } catch (error) {
      if (method === "GET" && useStaleOnError) {
        const cached = GET_JSON_CACHE.get(cacheKey);
        if (cached) {
          return { data: cached.data as T, status: cached.status };
        }
      }
      throw error;
    }
  })();

  if (method === "GET") {
    INFLIGHT_JSON.set(cacheKey, requestPromise as Promise<{ data: unknown; status: number }>);
  }

  try {
    return await requestPromise;
  } finally {
    if (method === "GET") {
      INFLIGHT_JSON.delete(cacheKey);
    }
  }
}
