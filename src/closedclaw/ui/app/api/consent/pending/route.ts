import { NextResponse } from "next/server";
import { closedclawJson } from "@/app/api/_lib/closedclaw";

export async function GET() {
  try {
    const { data, status } = await closedclawJson("/v1/consent/pending", { method: "GET" }, { cacheTtlMs: 2_000 });
    return NextResponse.json(data, {
      status,
      headers: { "Cache-Control": "private, max-age=2, stale-while-revalidate=10" },
    });
  } catch (error) {
    return NextResponse.json(
      {
        pending: [],
        count: 0,
        error: error instanceof Error ? error.message : "Failed to load pending consent requests",
      },
      {
        status: 200,
        headers: { "Cache-Control": "private, max-age=2, stale-while-revalidate=10" },
      }
    );
  }
}
