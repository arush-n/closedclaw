import { NextRequest, NextResponse } from "next/server";
import { closedclawJson, closedclawRequest } from "@/app/api/_lib/closedclaw";

export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  const { path } = await params;
  const subpath = path.join("/");
  const pathname = `/v1/swarm/${subpath}`;

  try {
    const { data, status } = await closedclawJson(pathname, { method: "GET" }, { cacheTtlMs: 2_000 });
    return NextResponse.json(data, { status });
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Request failed" },
      { status: 200 }
    );
  }
}

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  const { path } = await params;
  const subpath = path.join("/");
  const pathname = `/v1/swarm/${subpath}`;

  try {
    const body = await request.json().catch(() => ({}));
    const response = await closedclawRequest(pathname, {
      method: "POST",
      body: JSON.stringify(body),
    });
    const data = await response.json();
    return NextResponse.json(data, { status: response.status });
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Request failed" },
      { status: 500 }
    );
  }
}

export async function PUT(
  request: NextRequest,
  { params }: { params: Promise<{ path: string[] }> }
) {
  const { path } = await params;
  const subpath = path.join("/");
  const pathname = `/v1/swarm/${subpath}`;

  try {
    const body = await request.json().catch(() => ({}));
    const response = await closedclawRequest(pathname, {
      method: "PUT",
      body: JSON.stringify(body),
    });
    const data = await response.json();
    return NextResponse.json(data, { status: response.status });
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Request failed" },
      { status: 500 }
    );
  }
}
