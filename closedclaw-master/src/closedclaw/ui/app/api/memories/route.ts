import { NextRequest, NextResponse } from "next/server";
import { closedclawRequest, getClosedclawApiUrl, buildClosedclawHeaders } from "@/app/api/_lib/closedclaw";
import { getOpenMemoryUrl } from "@/app/api/_lib/openmemory";

// Types for closedclaw memory response
interface Memory {
  id: string;
  memory: string;
  content?: string;
  text?: string;
  hash?: string;
  user_id?: string;
  agent_id?: string;
  metadata?: Record<string, unknown>;
  categories?: string[];
  tags?: string[];
  created_at?: string;
  updated_at?: string;
  score?: number;
  sensitivity?: number;
  encrypted?: boolean;
}

interface MemoriesResponse {
  memories?: Memory[];
  results?: Memory[];
  data?: Memory[];
}

interface CacheEntry {
  expiresAt: number;
  payload: {
    success: boolean;
    memories: Memory[];
    count: number;
    demo?: boolean;
  };
}

interface CreateMemoryRequest {
  content: string;
  user_id?: string;
  sensitivity?: number;
  tags?: string[];
  source?: string;
  metadata?: Record<string, unknown>;
}

const RESPONSE_CACHE_TTL_MS = 15_000;
const REQUEST_TIMEOUT_MS = 3_000;
const responseCache = new Map<string, CacheEntry>();
let preferredEndpoint = 0;

// Fetch memories from openmemory-mcp as secondary source
async function fetchOpenMemoryMemories(userId: string, limit: number): Promise<Memory[]> {
  try {
    const omUrl = getOpenMemoryUrl();
    const url = `${omUrl}/api/v1/memories/?user_id=${encodeURIComponent(userId)}&page_size=${limit}`;
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
    try {
      const response = await fetch(url, { signal: controller.signal, cache: "no-store" });
      if (response.ok) {
        const data = await response.json();
        const items = data?.results || data?.items || [];
        return normalizeMemories(items);
      }
    } finally {
      clearTimeout(timeout);
    }
  } catch {
    // openmemory unavailable
  }
  return [];
}

// Normalize different API response formats
function normalizeMemoryItem(item: unknown, index: number): Memory | null {
  if (!item || typeof item !== "object") {
    return null;
  }

  const raw = item as Record<string, unknown>;
  const id =
    (typeof raw.id === "string" && raw.id) ||
    (typeof raw.memory_id === "string" && raw.memory_id) ||
    `memory-${index}-${Date.now()}`;

  const content =
    (typeof raw.memory === "string" && raw.memory) ||
    (typeof raw.content === "string" && raw.content) ||
    (typeof raw.text === "string" && raw.text) ||
    "";

  if (!content.trim()) {
    return null;
  }

  const categories = Array.isArray(raw.categories)
    ? raw.categories.filter((value): value is string => typeof value === "string")
    : Array.isArray(raw.tags)
    ? raw.tags.filter((value): value is string => typeof value === "string")
    : [];

  return {
    id,
    memory: content,
    content,
    text: content,
    hash: typeof raw.hash === "string" ? raw.hash : undefined,
    user_id: typeof raw.user_id === "string" ? raw.user_id : undefined,
    agent_id: typeof raw.agent_id === "string" ? raw.agent_id : undefined,
    metadata:
      raw.metadata && typeof raw.metadata === "object"
        ? (raw.metadata as Record<string, unknown>)
        : undefined,
    categories,
    tags: categories,
    created_at: typeof raw.created_at === "string" ? raw.created_at : undefined,
    updated_at: typeof raw.updated_at === "string" ? raw.updated_at : undefined,
    score: typeof raw.score === "number" ? raw.score : undefined,
    sensitivity: typeof raw.sensitivity === "number" ? raw.sensitivity : undefined,
    encrypted: typeof raw.encrypted === "boolean" ? raw.encrypted : undefined,
  };
}

function normalizeMemories(data: unknown): Memory[] {
  if (!data) return [];
  
  // Check if it's already an array
  if (Array.isArray(data)) {
    return data
      .map((item, index) => normalizeMemoryItem(item, index))
      .filter((item): item is Memory => Boolean(item));
  }
  
  const obj = data as MemoriesResponse;
  
  // Try different response formats
  if (obj.memories && Array.isArray(obj.memories)) {
    return obj.memories
      .map((item, index) => normalizeMemoryItem(item, index))
      .filter((item): item is Memory => Boolean(item));
  }
  if (obj.results && Array.isArray(obj.results)) {
    return obj.results
      .map((item, index) => normalizeMemoryItem(item, index))
      .filter((item): item is Memory => Boolean(item));
  }
  if (obj.data && Array.isArray(obj.data)) {
    return obj.data
      .map((item, index) => normalizeMemoryItem(item, index))
      .filter((item): item is Memory => Boolean(item));
  }
  
  return [];
}

export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const userId = searchParams.get("user_id") || undefined;
  const limit = parseInt(searchParams.get("limit") || "100", 10);
  const cacheKey = `${userId || "all"}:${limit}`;

  const cached = responseCache.get(cacheKey);
  if (cached && cached.expiresAt > Date.now()) {
    return NextResponse.json(cached.payload, {
      headers: { "Cache-Control": "private, max-age=10" },
    });
  }
  
  const apiUrl = getClosedclawApiUrl();
  
  const params = new URLSearchParams();
  if (userId) params.append("user_id", userId);
  params.append("limit", limit.toString());

  const baseHeaders = buildClosedclawHeaders(true);
  const requestCandidates = [
    {
      url: `${apiUrl}/v1/memory/all`,
      headers: {
        ...baseHeaders,
        ...(userId ? { "X-User-ID": userId } : {}),
      },
    },
    { url: `${apiUrl}/v1/memories?${params.toString()}`, headers: baseHeaders },
    { url: `${apiUrl}/api/v1/memories?${params.toString()}`, headers: baseHeaders },
    { url: `${apiUrl}/memories?${params.toString()}`, headers: baseHeaders },
    { url: `${apiUrl}/api/memories?${params.toString()}`, headers: baseHeaders },
  ];

  const orderedCandidates = [
    requestCandidates[preferredEndpoint],
    ...requestCandidates.filter((_, idx) => idx !== preferredEndpoint),
  ];
  
  let lastError: Error | null = null;
  
  for (const candidate of orderedCandidates) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);
    try {
      const response = await fetch(candidate.url, {
        method: "GET",
        headers: candidate.headers,
        signal: controller.signal,
      });
      
      if (response.ok) {
        const data = await response.json();
        let memories = normalizeMemories(data).slice(0, limit);

        // If closedclaw server returned no memories, also try openmemory-mcp
        if (memories.length === 0) {
          memories = await fetchOpenMemoryMemories(userId || "default-user", limit);
        }

        preferredEndpoint = requestCandidates.findIndex(
          (item) => item.url === candidate.url
        );

        const payload = {
          success: true,
          memories,
          count: memories.length,
        };

        responseCache.set(cacheKey, {
          expiresAt: Date.now() + RESPONSE_CACHE_TTL_MS,
          payload,
        });

        return NextResponse.json(payload, {
          headers: { "Cache-Control": "private, max-age=10" },
        });
      }
    } catch (error) {
      lastError = error instanceof Error ? error : new Error(String(error));
      continue;
    } finally {
      clearTimeout(timeout);
    }
  }
  
  // If all closedclaw endpoints fail, try openmemory-mcp as last resort
  console.warn("All closedclaw endpoints failed, trying openmemory:", lastError?.message);

  const omMemories = await fetchOpenMemoryMemories(userId || "default-user", limit);

  const payload = {
    success: true,
    memories: omMemories,
    count: omMemories.length,
  };

  responseCache.set(cacheKey, {
    expiresAt: Date.now() + RESPONSE_CACHE_TTL_MS,
    payload,
  });

  return NextResponse.json(payload, {
    headers: { "Cache-Control": "private, max-age=10" },
  });
}

export async function POST(request: NextRequest) {
  try {
    const body = (await request.json()) as CreateMemoryRequest;
    if (!body.content?.trim()) {
      return NextResponse.json(
        { success: false, error: "content is required" },
        { status: 400 }
      );
    }

    const response = await closedclawRequest("/v1/memory", {
      method: "POST",
      timeoutMs: 30_000,
      body: JSON.stringify({
        content: body.content,
        user_id: body.user_id || "default",
        sensitivity: body.sensitivity,
        tags: body.tags || [],
        source: body.source || "manual",
        metadata: body.metadata || {},
      }),
    });

    if (!response.ok) {
      const detail = await response.text();
      return NextResponse.json(
        { success: false, error: detail || "Failed to create memory" },
        { status: response.status }
      );
    }

    const created = await response.json();
    responseCache.clear();

    return NextResponse.json({ success: true, memory: created });
  } catch (error) {
    return NextResponse.json(
      {
        success: false,
        error: error instanceof Error ? error.message : "Failed to create memory",
      },
      { status: 500 }
    );
  }
}
