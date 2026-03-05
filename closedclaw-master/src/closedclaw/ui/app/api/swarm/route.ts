import { NextRequest, NextResponse } from "next/server";
import { closedclawJson, closedclawRequest } from "@/app/api/_lib/closedclaw";

export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const endpoint = searchParams.get("endpoint") || "status";

  const pathMap: Record<string, string> = {
    status: "/v1/swarm/status",
    agents: "/v1/swarm/agents",
    constitution: "/v1/swarm/constitution",
    amendments: "/v1/swarm/constitution/amendments",
    messages: "/v1/swarm/messages",
    stats: "/v1/swarm/stats",
    pipelines: "/v1/swarm/pipelines",
    tools: "/v1/swarm/tools",
    "tools/history": "/v1/swarm/tools/history",
  };

  const pathname = pathMap[endpoint];
  if (!pathname) {
    return NextResponse.json({ error: `Unknown endpoint: ${endpoint}` }, { status: 400 });
  }

  try {
    const { data, status } = await closedclawJson(pathname, { method: "GET" }, { cacheTtlMs: 2_000 });
    return NextResponse.json(data, {
      status,
      headers: { "Cache-Control": "private, max-age=2, stale-while-revalidate=10" },
    });
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Failed to fetch swarm data" },
      { status: 200 }
    );
  }
}

export async function POST(request: NextRequest) {
  const { searchParams } = new URL(request.url);
  const endpoint = searchParams.get("endpoint") || "tasks";

  const pathMap: Record<string, string> = {
    tasks: "/v1/swarm/tasks",
    verify: "/v1/swarm/verify",
  };

  const pathname = pathMap[endpoint];
  if (!pathname) {
    return NextResponse.json({ error: `Unknown endpoint: ${endpoint}` }, { status: 400 });
  }

  try {
    const body = await request.json().catch(() => ({}));
    const response = await closedclawRequest(pathname, {
      method: "POST",
      body: JSON.stringify(body),
    });
    const data = await response.json();
    return NextResponse.json(data, { status: response.status });
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Failed to submit swarm task" },
      { status: 500 }
    );
  }
}
