import { NextResponse } from "next/server";

export async function GET() {
  try {
    const apiUrl =
      process.env.CLOSEDCLAW_API_URL ||
      process.env.MEM0_API_URL ||
      "http://localhost:8765";
    const response = await fetch(`${apiUrl}/health`, {
      method: "GET",
      cache: "no-store",
    });

    return NextResponse.json({
      connected: response.ok,
      status: response.ok ? "connected" : "disconnected",
    });
  } catch {
    return NextResponse.json({
      connected: false,
      status: "disconnected",
    });
  }
}
