import { NextRequest, NextResponse } from "next/server";
import { closedclawRequest } from "@/app/api/_lib/closedclaw";

export async function PUT(request: NextRequest) {
  try {
    const body = await request.json().catch(() => ({}));
    const { current_password, new_password } = body;

    if (!new_password || new_password.length < 8) {
      return NextResponse.json(
        { error: "New password must be at least 8 characters" },
        { status: 400 }
      );
    }

    const response = await closedclawRequest("/v1/server/password", {
      method: "PUT",
      body: JSON.stringify({ current_password: current_password || "", new_password }),
      timeoutMs: 10_000,
    });

    const data = await response.json().catch(() => ({}));
    return NextResponse.json(data, { status: response.status });
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Password update failed" },
      { status: 500 }
    );
  }
}
