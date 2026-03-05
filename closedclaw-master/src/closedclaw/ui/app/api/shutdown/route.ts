import { NextRequest, NextResponse } from "next/server";
import { closedclawRequest } from "@/app/api/_lib/closedclaw";

export async function POST(request: NextRequest) {
  try {
    const body = await request.json().catch(() => ({}));
    const { password } = body;

    if (!password) {
      return NextResponse.json(
        { error: "Password is required" },
        { status: 400 }
      );
    }

    const response = await closedclawRequest("/v1/addon/server/shutdown", {
      method: "DELETE",
      body: JSON.stringify({ password }),
      timeoutMs: 10_000,
    });

    const data = await response.json().catch(() => ({}));
    return NextResponse.json(data, { status: response.status });
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Shutdown failed" },
      { status: 500 }
    );
  }
}
