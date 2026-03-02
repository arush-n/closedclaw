import { NextRequest, NextResponse } from "next/server";
import { closedclawRequest } from "../../_lib/closedclaw";

/**
 * GET /api/insights/trends — get trend data
 */
export async function GET(request: NextRequest) {
  try {
    const res = await closedclawRequest("/v1/insights/trends");
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
