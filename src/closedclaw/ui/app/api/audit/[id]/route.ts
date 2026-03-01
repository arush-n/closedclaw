import { NextRequest, NextResponse } from "next/server";
import { closedclawJson } from "@/app/api/_lib/closedclaw";

interface RouteContext {
  params: Promise<{ id: string }>;
}

export async function GET(_request: NextRequest, { params }: RouteContext) {
  try {
    const { id } = await params;
    const { data, status } = await closedclawJson(`/v1/audit/${id}`, { method: "GET" }, { cacheTtlMs: 2_000 });
    return NextResponse.json(data, {
      status,
      headers: { "Cache-Control": "private, max-age=3, stale-while-revalidate=15" },
    });
  } catch (error) {
    return NextResponse.json(
      {
        error: error instanceof Error ? error.message : "Failed to load audit entry",
      },
      {
        status: 500,
        headers: { "Cache-Control": "private, max-age=1" },
      }
    );
  }
}
