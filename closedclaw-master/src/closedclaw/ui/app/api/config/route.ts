import { NextResponse } from "next/server";
import { closedclawRequest } from "../_lib/closedclaw";

export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const response = await closedclawRequest("/v1/config");
    const data = await response.json();
    return NextResponse.json(data, { status: response.status });
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Failed to load config" },
      { status: 502 }
    );
  }
}

export async function PUT(request: Request) {
  try {
    const body = await request.json();
    const response = await closedclawRequest("/v1/config", {
      method: "PUT",
      body: JSON.stringify(body),
    });
    const data = await response.json();
    return NextResponse.json(data, { status: response.status });
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Failed to save config" },
      { status: 502 }
    );
  }
}
