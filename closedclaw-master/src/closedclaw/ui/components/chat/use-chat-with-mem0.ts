"use client";

import { useState, useCallback, useRef, useEffect } from "react";
import type {
  Message,
  RelatedMemory,
  ClosedclawConfig,
  ClosedclawMessageMetadata,
} from "./types";
import { generateId } from "@/lib/utils";

interface UseChatWithClosedclawOptions {
  config: ClosedclawConfig;
  onError?: (error: Error) => void;
}

interface UseChatWithClosedclawReturn {
  messages: Message[];
  input: string;
  setInput: (input: string) => void;
  sendMessage: () => Promise<void>;
  stop: () => void;
  isLoading: boolean;
  error: string | null;
  clearMessages: () => void;
}

export function useChatWithClosedclaw({
  config,
  onError,
}: UseChatWithClosedclawOptions): UseChatWithClosedclawReturn {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const messagesRef = useRef<Message[]>([]);

  useEffect(() => {
    messagesRef.current = messages;
  }, [messages]);

  const searchMemories = useCallback(
    async (query: string): Promise<RelatedMemory[]> => {
      try {
        const response = await fetch("/api/memories/search", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            query,
            user_id: config.userId,
            agent_id: config.agentId,
            limit: 5,
          }),
        });

        if (!response.ok) {
          console.warn("Memory search failed:", response.statusText);
          return [];
        }

        const data = await response.json();
        return data.results || [];
      } catch (err) {
        console.warn("Memory search error:", err);
        return [];
      }
    },
    [config.userId, config.agentId]
  );

  const generateResponse = useCallback(
    async (
      userMessage: string,
      memories: RelatedMemory[],
      history: Message[]
    ): Promise<{ response: string; metadata?: ClosedclawMessageMetadata }> => {
      // ClawdBot agent mode — routes through /api/clawdbot
      if (config.useClawdBot) {
        const response = await fetch("/api/clawdbot", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            message: userMessage,
            user_id: config.userId,
            conversation_id: `chat-${config.userId}`,
          }),
          signal: abortControllerRef.current?.signal,
        });

        if (!response.ok) {
          throw new Error(`ClawdBot request failed: ${response.statusText}`);
        }

        const data = await response.json();
        // ClawdBot API returns {message: {role, content}, tool_calls, iterations, ...}
        const content =
          typeof data.message === "object"
            ? data.message?.content ?? ""
            : data.message ?? data.response ?? "";
        return {
          response: content,
          metadata: {
            closedclaw_memories_used: data.tool_calls?.length ?? 0,
            closedclaw_redactions_applied: 0,
            closedclaw_audit_id: data.conversation_id,
          },
        };
      }

      // Standard proxy mode — routes through /api/chat
      const response = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: userMessage,
          user_id: config.userId,
          memories,
          history: history.slice(-10).map((m) => ({
            role: m.role,
            content: m.content,
          })),
        }),
        signal: abortControllerRef.current?.signal,
      });

      if (!response.ok) {
        throw new Error(`Chat request failed: ${response.statusText}`);
      }

      const data = await response.json();
      return {
        response: data.response,
        metadata: data.metadata,
      };
    },
    [config.userId, config.useClawdBot]
  );

  const sendMessage = useCallback(async () => {
    if (!input.trim() || isLoading) return;

    const messageText = input.trim();
    const userMessage: Message = {
      id: generateId(),
      role: "user",
      content: messageText,
      timestamp: new Date(),
    };

    // Create placeholder for assistant message
    const assistantMessageId = generateId();
    const assistantMessage: Message = {
      id: assistantMessageId,
      role: "assistant",
      content: "",
      timestamp: new Date(),
      relatedMemories: [],
    };

    setMessages((prev) => [...prev, userMessage, assistantMessage]);
    setInput("");
    setIsLoading(true);
    setError(null);

    abortControllerRef.current = new AbortController();

    try {
      const shouldPrefetch = Boolean(config.prefetchMemories);
      const memories = shouldPrefetch
        ? await searchMemories(userMessage.content)
        : [];

      // Update assistant message with memories
      setMessages((prev) =>
        prev.map((msg) =>
          msg.id === assistantMessageId
            ? { ...msg, relatedMemories: memories }
            : msg
        )
      );

      // Generate response
      const currentMessages = [...messagesRef.current, userMessage];
      const generated = await generateResponse(
        userMessage.content,
        memories,
        currentMessages
      );

      // Update assistant message with response
      setMessages((prev) =>
        prev.map((msg) =>
          msg.id === assistantMessageId
            ? {
                ...msg,
                content: generated.response,
                metadata: generated.metadata,
              }
            : msg
        )
      );
    } catch (err) {
      if (err instanceof Error && err.name === "AbortError") {
        // Request was cancelled
        setMessages((prev) =>
          prev.filter((msg) => msg.id !== assistantMessageId)
        );
      } else {
        const errorMessage =
          err instanceof Error ? err.message : "An error occurred";
        setError(errorMessage);
        onError?.(err instanceof Error ? err : new Error(errorMessage));

        setMessages((prev) =>
          prev.map((msg) =>
            msg.id === assistantMessageId
              ? {
                  ...msg,
                  content:
                    "Sorry, I encountered an error while processing your request. Please try again.",
                }
              : msg
          )
        );
      }
    } finally {
      setIsLoading(false);
      abortControllerRef.current = null;
    }
  }, [
    input,
    isLoading,
    config.prefetchMemories,
    searchMemories,
    generateResponse,
    onError,
  ]);

  const stop = useCallback(() => {
    abortControllerRef.current?.abort();
    setIsLoading(false);
  }, []);

  const clearMessages = useCallback(() => {
    setMessages([]);
    setError(null);
  }, []);

  return {
    messages,
    input,
    setInput,
    sendMessage,
    stop,
    isLoading,
    error,
    clearMessages,
  };
}

export const useChatWithMem0 = useChatWithClosedclaw;
