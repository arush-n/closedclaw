import { NextRequest, NextResponse } from "next/server";
import { closedclawRequest } from "@/app/api/_lib/closedclaw";

export async function GET() {
  try {
    const response = await closedclawRequest("/v1/mcp/servers", { method: "GET" });
    const data = await response.json();
    return NextResponse.json(data, { status: response.status });
  } catch (error) {
    return NextResponse.json(
      {
        error: error instanceof Error ? error.message : "Failed to load MCP servers",
      },
      { status: 500 }
    );
  }
}

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const endpoint = body?.raw ? "/v1/mcp/raw" : "/v1/mcp/call";

    const response = await closedclawRequest(endpoint, {
      method: "POST",
      body: JSON.stringify(body),
    });

    const contentType = response.headers.get("content-type") || "";
    if (contentType.includes("application/json")) {
      const data = await response.json();
      return NextResponse.json(data, { status: response.status });
    }

    const text = await response.text();
    return NextResponse.json({ body: text }, { status: response.status });
  } catch (error) {
    return NextResponse.json(
      {
        error: error instanceof Error ? error.message : "MCP request failed",
      },
      { status: 500 }
    );
  }
}
