import { NextRequest, NextResponse } from "next/server";
import { closedclawRequest } from "../_lib/closedclaw";

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const res = await closedclawRequest("/v1/clawdbot/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!res.ok) {
      const text = await res.text().catch(() => "");
      return NextResponse.json(
        { success: false, error: text || `Backend returned ${res.status}` },
        { status: res.status }
      );
    }
    const data = await res.json();
    return NextResponse.json({ success: true, ...data });
  } catch (err) {
    return NextResponse.json(
      { success: false, error: String(err) },
      { status: 500 }
    );
  }
}

export async function GET() {
  try {
    const res = await closedclawRequest("/v1/clawdbot/status");
    if (!res.ok) {
      const text = await res.text().catch(() => "");
      return NextResponse.json(
        { success: false, error: text || `Backend returned ${res.status}` },
        { status: res.status }
      );
    }
    const data = await res.json();
    return NextResponse.json({ success: true, ...data });
  } catch (err) {
    return NextResponse.json(
      { success: false, error: String(err) },
      { status: 500 }
    );
  }
}
