import { NextRequest, NextResponse } from "next/server";
import { openMemoryRequest } from "@/app/api/_lib/openmemory";

/**
 * Proxy all GET/POST/PUT/DELETE requests to openmemory-mcp
 * Routes like /api/openmemory/memories/?user_id=... → http://localhost:8766/api/v1/memories/?user_id=...
 */

type RouteContext = { params: Promise<{ path: string[] }> };

async function proxyRequest(
  request: NextRequest,
  pathSegments: string[],
  method: string
): Promise<NextResponse> {
  const subpath = pathSegments.join("/");
  const { searchParams } = new URL(request.url);
  const qs = searchParams.toString();
  const pathname = `/api/v1/${subpath}${qs ? `?${qs}` : ""}`;

  try {
    const hasBody = ["POST", "PUT", "PATCH", "DELETE"].includes(method);
    const bodyText = hasBody ? await request.text() : undefined;

    const response = await openMemoryRequest(pathname, {
      method,
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: bodyText || undefined,
    });

    const contentType = response.headers.get("content-type") || "";
    if (contentType.includes("application/json")) {
      const data = await response.json();
      return NextResponse.json(data, { status: response.status });
    }

    // Fallback for non-JSON responses
    const text = await response.text();
    return new NextResponse(text, { status: response.status });
  } catch (error) {
    return NextResponse.json(
      {
        error: error instanceof Error ? error.message : "Proxy error",
      },
      { status: 502 }
    );
  }
}

export async function GET(request: NextRequest, { params }: RouteContext) {
  const { path } = await params;
  return proxyRequest(request, path, "GET");
}

export async function POST(request: NextRequest, { params }: RouteContext) {
  const { path } = await params;
  return proxyRequest(request, path, "POST");
}

export async function PUT(request: NextRequest, { params }: RouteContext) {
  const { path } = await params;
  return proxyRequest(request, path, "PUT");
}

export async function DELETE(request: NextRequest, { params }: RouteContext) {
  const { path } = await params;
  return proxyRequest(request, path, "DELETE");
}

export async function PATCH(request: NextRequest, { params }: RouteContext) {
  const { path } = await params;
  return proxyRequest(request, path, "PATCH");
}
