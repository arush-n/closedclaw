import { NextResponse } from "next/server";
import { closedclawRequest } from "@/app/api/_lib/closedclaw";

export async function GET() {
  try {
    const response = await closedclawRequest("/v1/audit/verify", { method: "GET" });
    const data = await response.json();
    return NextResponse.json(data, { status: response.status });
  } catch (error) {
    return NextResponse.json(
      {
        valid: false,
        message: error instanceof Error ? error.message : "Failed to verify chain",
      },
      { status: 200 }
    );
  }
}
