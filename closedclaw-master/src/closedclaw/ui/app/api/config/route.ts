import { closedclawRequest } from "../_lib/closedclaw";

export async function GET() {
  return closedclawRequest("/v1/config");
}

export async function PUT(request: Request) {
  const body = await request.json();
  return closedclawRequest("/v1/config", {
    method: "PUT",
    body: JSON.stringify(body),
  });
}
