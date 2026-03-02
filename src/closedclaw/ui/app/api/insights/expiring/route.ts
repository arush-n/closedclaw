import { NextRequest, NextResponse } from "next/server";
import { closedclawRequest } from "../../_lib/closedclaw";

/**
 * GET /api/insights/expiring — get memories approaching TTL expiry
 */
export async function GET(request: NextRequest) {
  try {
    const { searchParams } = new URL(request.url);
    const days = searchParams.get("days") || "30";
    const res = await closedclawRequest(`/v1/insights/expiring?days=${days}`);
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
