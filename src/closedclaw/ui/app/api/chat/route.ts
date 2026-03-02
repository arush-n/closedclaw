import { NextRequest, NextResponse } from "next/server";
import { closedclawRequest } from "@/app/api/_lib/closedclaw";

interface ChatRequest {
  message: string;
  user_id: string;
  memories?: Array<{ id: string; content: string; score: number }>;
  history?: Array<{ role: string; content: string }>;
}

let discoveredModelCache: { value?: string; expiresAt: number } = {
  value: undefined,
  expiresAt: 0,
};

async function discoverBackendModel(): Promise<string | undefined> {
  if (discoveredModelCache.expiresAt > Date.now()) {
    return discoveredModelCache.value;
  }

  try {
    const modelsResponse = await closedclawRequest("/v1/models", {
      method: "GET",
      timeoutMs: 2000,
    });

    if (!modelsResponse.ok) {
      discoveredModelCache = {
        value: undefined,
        expiresAt: Date.now() + 10_000,
      };
      return undefined;
    }

    const payload = (await modelsResponse.json()) as {
      data?: Array<{ id?: string }>;
      models?: Array<{ id?: string; name?: string }>;
    };

    const firstId =
      payload?.data?.find((entry) => typeof entry?.id === "string")?.id ||
      payload?.models?.find(
        (entry) => typeof entry?.id === "string" || typeof entry?.name === "string"
      )?.id ||
      payload?.models?.find((entry) => typeof entry?.name === "string")?.name;

    discoveredModelCache = {
      value: firstId,
      expiresAt: Date.now() + 60_000,
    };

    return firstId;
  } catch {
    discoveredModelCache = {
      value: undefined,
      expiresAt: Date.now() + 10_000,
    };
    return undefined;
  }
}

function buildModelCandidates(discoveredModel?: string): string[] {
  const candidates = [
    process.env.CLOSEDCLAW_UI_MODEL,
    process.env.CLOSEDCLAW_DEFAULT_MODEL,
    process.env.OLLAMA_MODEL,
    discoveredModel,
    "llama3.2",
    "llama3.1",
    "qwen2.5:7b",
    "mistral",
  ];

  const unique = new Set<string>();
  for (const candidate of candidates) {
    const trimmed = candidate?.trim();
    if (trimmed) {
      unique.add(trimmed);
    }
  }
  return Array.from(unique);
}

export async function POST(request: NextRequest) {
  try {
    const body: ChatRequest = await request.json();
    const { message, user_id, memories = [], history = [] } = body;

    if (!message || !user_id) {
      return NextResponse.json(
        { error: "Missing required fields: message and user_id" },
        { status: 400 }
      );
    }

    const buildMessages = () => [
      ...history.slice(-6).map((entry) => ({
        role: entry.role,
        content: entry.content,
      })),
      { role: "user", content: message },
    ];

    const discoveredModel = await discoverBackendModel();
    const modelCandidates = buildModelCandidates(discoveredModel);

    const requestWithModel = async (model: string) =>
      closedclawRequest("/v1/chat/completions", {
        method: "POST",
        timeoutMs: 60_000,
        headers: {
          "x-closedclaw-user-id": user_id,
        },
        body: JSON.stringify({
          model,
          messages: buildMessages(),
          stream: false,
        }),
      });

    if (modelCandidates.length === 0) {
      return NextResponse.json(
        { error: "No chat model configured. Set CLOSEDCLAW_UI_MODEL or configure backend models." },
        { status: 500 }
      );
    }

    let proxyResponse: Response | null = null;
    let lastDetail = "";

    for (const model of modelCandidates) {
      const attempt = await requestWithModel(model);
      if (attempt.ok) {
        proxyResponse = attempt;
        break;
      }

      const detailText = await attempt.text();
      lastDetail = detailText || `Chat request failed with ${attempt.status}`;

      const isModelError =
        attempt.status === 400 ||
        attempt.status === 404 ||
        attempt.status === 422 ||
        /model|upstream provider|not found/i.test(lastDetail);

      if (!isModelError) {
        proxyResponse = new Response(lastDetail, { status: attempt.status });
        break;
      }
    }

    if (!proxyResponse || !proxyResponse.ok) {
      const detail = proxyResponse ? await proxyResponse.text() : lastDetail;
      return NextResponse.json(
        { error: detail || "Chat request failed" },
        { status: proxyResponse?.status || 502 }
      );
    }

    const proxyData = await proxyResponse.json();
    const chatResponse =
      proxyData?.choices?.[0]?.message?.content ||
      "I couldn't generate a response.";

    return NextResponse.json({
      response: chatResponse,
      memories: memories,
      metadata: {
        closedclaw_memories_used: proxyData?.closedclaw_memories_used,
        closedclaw_redactions_applied: proxyData?.closedclaw_redactions_applied,
        closedclaw_audit_id: proxyData?.closedclaw_audit_id,
      },
    });
  } catch (error) {
    console.error("Chat API error:", error);
    return NextResponse.json(
      { error: "Internal server error" },
      { status: 500 }
    );
  }
}
