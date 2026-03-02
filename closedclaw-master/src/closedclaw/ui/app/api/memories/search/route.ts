import { NextRequest, NextResponse } from "next/server";
import { closedclawRequest } from "@/app/api/_lib/closedclaw";

interface SearchRequest {
  query: string;
  user_id: string;
  agent_id?: string;
  limit?: number;
}

export async function POST(request: NextRequest) {
  try {
    const body: SearchRequest = await request.json();
    const { query, user_id, agent_id, limit = 10 } = body;

    if (!query || !user_id) {
      return NextResponse.json(
        { error: "Missing required fields: query and user_id" },
        { status: 400 }
      );
    }

    const memories = await searchClosedclawMemories({
      query,
      user_id,
      agent_id,
      limit,
    });

    return NextResponse.json({
      results: memories,
      total: memories.length,
    });
  } catch (error) {
    console.error("Memory search error:", error);
    return NextResponse.json(
      { error: "Failed to search memories", details: error instanceof Error ? error.message : "Unknown error" },
      { status: 500 }
    );
  }
}

async function searchClosedclawMemories({
  query,
  user_id,
  agent_id,
  limit,
}: {
  query: string;
  user_id: string;
  agent_id?: string;
  limit: number;
}): Promise<Array<{ id: string; content: string; score: number; created_at?: string; metadata?: Record<string, unknown> }>> {
  // Try closedclaw native search endpoint first
  try {
    const response = await closedclawRequest(
      `/v1/memory?q=${encodeURIComponent(query)}&limit=${limit}&user_id=${encodeURIComponent(user_id)}`,
      { method: "GET" }
    );

    if (response.ok) {
      const data = await response.json();
      return normalizeMemoryResults(data);
    }
  } catch (err) {
    console.warn("closedclaw search failed, trying compatibility routes:", err);
  }

  // Compatibility route: /api/v1/memories/search
  try {
    const response = await closedclawRequest(
      `/api/v1/memories/search?user_id=${encodeURIComponent(user_id)}&query=${encodeURIComponent(query)}&limit=${limit}`,
      { method: "GET" }
    );

    if (response.ok) {
      const data = await response.json();
      return normalizeMemoryResults(data);
    }
  } catch (err) {
    console.warn("Compatibility search route failed:", err);
  }

  // Compatibility route: /search
  try {
    const response = await closedclawRequest("/search", {
      method: "POST",
      body: JSON.stringify({
        query,
        user_id,
        agent_id,
        limit,
      }),
    });

    if (response.ok) {
      const data = await response.json();
      return normalizeMemoryResults(data);
    }
  } catch (err) {
    console.warn("Direct compatibility search failed:", err);
  }

  // Return empty array if all attempts fail
  console.warn("All memory search methods failed, returning empty results");
  return [];
}

function normalizeMemoryResults(
  data: any
): Array<{ id: string; content: string; score: number; created_at?: string; metadata?: Record<string, unknown> }> {
  // Handle different response formats from closedclaw and compatibility endpoints
  const items = data.results || data.items || data.memories || data || [];

  if (!Array.isArray(items)) {
    return [];
  }

  return items.map((item: any) => ({
    id: item.id || item.memory_id || crypto.randomUUID(),
    content: item.content || item.memory || item.text || item.data || "",
    score: item.score || item.relevance_score || item.similarity || 0,
    created_at: item.created_at || item.createdAt || item.timestamp,
    metadata: item.metadata || item.metadata_ || item.meta || {},
  }));
}

export async function GET(request: NextRequest) {
  const searchParams = request.nextUrl.searchParams;
  const query = searchParams.get("query");
  const user_id = searchParams.get("user_id");
  const agent_id = searchParams.get("agent_id") || undefined;
  const limit = parseInt(searchParams.get("limit") || "10", 10);

  if (!query || !user_id) {
    return NextResponse.json(
      { error: "Missing required parameters: query and user_id" },
      { status: 400 }
    );
  }

  // Reuse POST logic
  const mockRequest = {
    json: async () => ({ query, user_id, agent_id, limit }),
  } as NextRequest;

  return POST(mockRequest);
}
