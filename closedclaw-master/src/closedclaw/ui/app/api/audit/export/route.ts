import { NextRequest, NextResponse } from "next/server";
import { closedclawRequest } from "@/app/api/_lib/closedclaw";

export async function GET(request: NextRequest) {
  const query = request.nextUrl.searchParams.toString();
  const pathname = query ? `/v1/audit/export?${query}` : "/v1/audit/export";

  try {
    const response = await closedclawRequest(pathname, { method: "GET" });
    const data = await response.json();
    return NextResponse.json(data, { status: response.status });
  } catch (error) {
    return NextResponse.json(
      {
        error: error instanceof Error ? error.message : "Failed to export audit bundle",
      },
      { status: 500 }
    );
  }
}
