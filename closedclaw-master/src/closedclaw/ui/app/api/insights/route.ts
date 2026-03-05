import { NextRequest, NextResponse } from "next/server";
import { closedclawRequest } from "../_lib/closedclaw";

/**
 * GET /api/insights — retrieve latest insight results
 * POST /api/insights — trigger an on-demand insight run
 */

export async function GET(request: NextRequest) {
  try {
    const res = await closedclawRequest("/v1/insights");
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

export async function POST(request: NextRequest) {
  try {
    const body = await request.json().catch(() => ({}));
    const res = await closedclawRequest("/v1/insights/run", {
      method: "POST",
      body: JSON.stringify(body),
      timeoutMs: 180_000,
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
