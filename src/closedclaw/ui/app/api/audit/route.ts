import { NextRequest, NextResponse } from "next/server";
import { closedclawJson } from "@/app/api/_lib/closedclaw";

export async function GET(request: NextRequest) {
  const query = request.nextUrl.searchParams.toString();
  const pathname = query ? `/v1/audit?${query}` : "/v1/audit";

  try {
    const { data, status } = await closedclawJson(pathname, { method: "GET" }, { cacheTtlMs: 2_000 });
    return NextResponse.json(data, {
      status,
      headers: { "Cache-Control": "private, max-age=3, stale-while-revalidate=15" },
    });
  } catch (error) {
    return NextResponse.json(
      {
        entries: [],
        total: 0,
        offset: 0,
        limit: 100,
        error: error instanceof Error ? error.message : "Failed to load audit entries",
      },
      {
        status: 200,
        headers: { "Cache-Control": "private, max-age=3, stale-while-revalidate=15" },
      }
    );
  }
}
