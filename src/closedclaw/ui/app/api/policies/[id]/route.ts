import { NextRequest, NextResponse } from "next/server";
import { closedclawRequest } from "@/app/api/_lib/closedclaw";

interface RouteContext {
  params: Promise<{ id: string }>;
}

export async function PUT(request: NextRequest, { params }: RouteContext) {
  try {
    const { id } = await params;
    const body = await request.json();
    const response = await closedclawRequest(`/v1/policies/${id}`, {
      method: "PUT",
      body: JSON.stringify(body),
    });
    const data = await response.json();
    return NextResponse.json(data, { status: response.status });
  } catch (error) {
    return NextResponse.json(
      { success: false, message: error instanceof Error ? error.message : "Failed to update policy" },
      { status: 500 }
    );
  }
}

export async function DELETE(_request: NextRequest, { params }: RouteContext) {
  try {
    const { id } = await params;
    const response = await closedclawRequest(`/v1/policies/${id}`, {
      method: "DELETE",
    });
    const data = await response.json();
    return NextResponse.json(data, { status: response.status });
  } catch (error) {
    return NextResponse.json(
      { success: false, message: error instanceof Error ? error.message : "Failed to delete policy" },
      { status: 500 }
    );
  }
}
