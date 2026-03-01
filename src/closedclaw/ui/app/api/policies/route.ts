import { NextRequest, NextResponse } from "next/server";
import { closedclawJson, closedclawRequest } from "@/app/api/_lib/closedclaw";

export async function GET() {
  try {
    const { data, status } = await closedclawJson("/v1/policies", { method: "GET" }, { cacheTtlMs: 3_000 });
    return NextResponse.json(data, {
      status,
      headers: { "Cache-Control": "private, max-age=3, stale-while-revalidate=15" },
    });
  } catch (error) {
    return NextResponse.json(
      { rules: [], total: 0, error: error instanceof Error ? error.message : "Failed to list policies" },
      {
        status: 200,
        headers: { "Cache-Control": "private, max-age=3, stale-while-revalidate=15" },
      }
    );
  }
}

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const response = await closedclawRequest("/v1/policies", {
      method: "POST",
      body: JSON.stringify(body),
    });
    const data = await response.json();
    return NextResponse.json(data, { status: response.status });
  } catch (error) {
    return NextResponse.json(
      { success: false, message: error instanceof Error ? error.message : "Failed to create policy" },
      { status: 500 }
    );
  }
}
