import { NextRequest, NextResponse } from "next/server";
import { closedclawRequest } from "../../../../_lib/closedclaw";

/**
 * POST /api/insights/expiring/[memoryId]/extend
 * Proxy to backend POST /v1/insights/expiring/{memoryId}/extend
 */
export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ memoryId: string }> }
) {
  try {
    const { memoryId } = await params;
    const body = await request.json().catch(() => ({}));
    const res = await closedclawRequest(
      `/v1/insights/expiring/${memoryId}/extend`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      }
    );
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
      { success: false, error: "Failed to extend memory" },
      { status: 500 }
    );
  }
}
