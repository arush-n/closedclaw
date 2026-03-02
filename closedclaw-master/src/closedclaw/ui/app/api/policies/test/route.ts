import { NextRequest, NextResponse } from "next/server";
import { closedclawRequest } from "@/app/api/_lib/closedclaw";

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const response = await closedclawRequest("/v1/policies/test", {
      method: "POST",
      body: JSON.stringify(body),
    });
    const data = await response.json();
    return NextResponse.json(data, { status: response.status });
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Policy test failed" },
      { status: 500 }
    );
  }
}
