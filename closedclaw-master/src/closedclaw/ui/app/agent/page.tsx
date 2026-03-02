"use client";

import { useState, useCallback, useEffect, useRef } from "react";
import {
  Bot,
  Send,
  Loader2,
  ArrowLeft,
  Wrench,
  ChevronDown,
  ChevronUp,
  AlertCircle,
} from "lucide-react";
import ReactMarkdown from "react-markdown";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface Message {
  role: "user" | "assistant" | "system" | "tool";
  content: string;
  timestamp?: string;
}

interface ToolCallRecord {
  tool: string;
  input: Record<string, unknown>;
  output: string;
}

interface BotStatus {
  available: boolean;
  model?: string;
  reason?: string;
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function ToolCallBadge({ record }: { record: ToolCallRecord }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="rounded-lg glass-card text-xs overflow-hidden">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full flex items-center gap-1.5 px-3 py-2 hover:bg-white/[0.03] transition-colors"
      >
        <Wrench className="w-3 h-3 text-amber-400 shrink-0" />
        <span className="text-amber-300 font-medium">{record.tool}</span>
        <span className="text-slate-500 ml-auto">
          {expanded ? (
            <ChevronUp className="w-3 h-3" />
          ) : (
            <ChevronDown className="w-3 h-3" />
          )}
        </span>
      </button>
      {expanded && (
        <div className="px-3 pb-2.5 space-y-1.5 border-t border-white/[0.05]">
          <div className="pt-2">
            <span className="text-slate-500 text-[10px] block mb-0.5">Input</span>
            <pre className="text-slate-400 whitespace-pre-wrap break-all mt-0.5 p-2 rounded bg-white/[0.02] border border-white/[0.04]">
              {JSON.stringify(record.input, null, 2)}
            </pre>
          </div>
          {record.output && (
            <div>
              <span className="text-slate-500 text-[10px] block mb-0.5">Output</span>
              <pre className="text-slate-400 whitespace-pre-wrap break-all mt-0.5 max-h-40 overflow-y-auto p-2 rounded bg-white/[0.02] border border-white/[0.04]">
                {record.output}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function ChatBubble({
  message,
  toolCalls,
}: {
  message: Message;
  toolCalls?: ToolCallRecord[];
}) {
  const isUser = message.role === "user";
  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-[80%] rounded-2xl px-4 py-3 text-sm ${
          isUser
            ? "bg-violet-500/15 border border-violet-500/25 text-slate-100"
            : "glass-card text-slate-200"
        }`}
      >
        {!isUser && (
          <div className="flex items-center gap-1.5 mb-2 text-xs text-slate-400">
            <Bot className="w-3.5 h-3.5 text-emerald-400" />
            <span className="font-medium">ClawdBot</span>
          </div>
        )}
        <div className="prose-chat">
          <ReactMarkdown>{message.content}</ReactMarkdown>
        </div>
        {toolCalls && toolCalls.length > 0 && (
          <div className="mt-2.5 space-y-1.5">
            {toolCalls.map((tc, i) => (
              <ToolCallBadge key={`${tc.tool}-${i}`} record={tc} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function AgentPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [status, setStatus] = useState<BotStatus | null>(null);
  const [lastToolCalls, setLastToolCalls] = useState<
    Record<number, ToolCallRecord[]>
  >({});
  const [error, setError] = useState("");

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Scroll to bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Check status on mount
  useEffect(() => {
    (async () => {
      try {
        const res = await fetch("/api/clawdbot");
        const data = await res.json();
        setStatus({
          available: !!data.available,
          model: data.model,
          reason: data.reason,
        });
      } catch {
        setStatus({ available: false, reason: "Could not reach backend" });
      }
    })();
  }, []);

  const sendMessage = useCallback(async () => {
    const text = input.trim();
    if (!text || isLoading) return;

    const userMsg: Message = {
      role: "user",
      content: text,
      timestamp: new Date().toISOString(),
    };
    const newMessages = [...messages, userMsg];
    setMessages(newMessages);
    setInput("");
    setIsLoading(true);
    setError("");

    try {
      const res = await fetch("/api/clawdbot", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: text,
          conversation_id: conversationId,
          max_iterations: 5,
        }),
      });
      const data = await res.json();

      if (data.success && data.message) {
        const assistantMsg: Message = {
          role: "assistant",
          content: data.message.content,
          timestamp: data.message.timestamp || new Date().toISOString(),
        };
        const updatedMessages = [...newMessages, assistantMsg];
        setMessages(updatedMessages);

        // Store tool calls keyed by the assistant message index
        if (data.tool_calls && data.tool_calls.length > 0) {
          setLastToolCalls((prev) => ({
            ...prev,
            [updatedMessages.length - 1]: data.tool_calls,
          }));
        }

        if (data.conversation_id) {
          setConversationId(data.conversation_id);
        }
      } else {
        setError(data.error || data.detail || "Unknown error from ClawdBot");
      }
    } catch (err) {
      setError(String(err));
    } finally {
      setIsLoading(false);
      inputRef.current?.focus();
    }
  }, [input, isLoading, messages, conversationId]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  const isAvailable = status?.available !== false;

  return (
    <div className="min-h-screen flex flex-col animate-fadeIn">
      {/* Header */}
      <header className="page-header">
        <div className="max-w-3xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <a
              href="/graph"
              title="Back to graph"
              className="p-1.5 rounded-lg hover:bg-white/[0.06] text-slate-400 hover:text-slate-200 transition-colors"
            >
              <ArrowLeft className="w-4 h-4" />
            </a>
            <div className="flex items-center gap-2.5">
              <div className="p-2 rounded-lg bg-emerald-500/10 border border-emerald-500/20">
                <Bot className="w-4 h-4 text-emerald-400" />
              </div>
              <h1 className="text-lg font-semibold text-slate-100">ClawdBot</h1>
            </div>
          </div>

          <div className="flex items-center gap-2 text-xs">
            {status && (
              <span
                className={`badge ${
                  status.available ? "badge-success" : "badge-danger"
                }`}
              >
                {status.available
                  ? `Online · ${status.model || "local"}`
                  : `Offline${status.reason ? ` · ${status.reason}` : ""}`}
              </span>
            )}
          </div>
        </div>
      </header>

      {/* Chat area */}
      <main className="flex-1 max-w-3xl w-full mx-auto px-6 py-6 flex flex-col">
        {messages.length === 0 && !isLoading ? (
          <div className="flex-1 flex flex-col items-center justify-center gap-5 text-center py-20">
            <div className="p-5 rounded-2xl bg-white/[0.03] border border-white/[0.06]">
              <Bot className="w-12 h-12 text-slate-700" />
            </div>
            <h2 className="text-lg font-medium text-slate-400">
              Chat with ClawdBot
            </h2>
            <p className="text-slate-500 text-sm max-w-md leading-relaxed">
              ClawdBot is an AI agent that can search, analyze, and manage your
              memories autonomously. Ask it anything about your stored knowledge.
            </p>
            {!isAvailable && (
              <div className="flex items-center gap-2 px-4 py-2.5 rounded-xl glass-card border-red-500/20 bg-red-500/[0.03] text-red-300 text-xs">
                <AlertCircle className="w-3.5 h-3.5" />
                {status?.reason || "ClawdBot is not available"}
              </div>
            )}
          </div>
        ) : (
          <div className="flex-1 overflow-y-auto space-y-4 pb-4">
            {messages.map((msg, i) => (
              <ChatBubble
                key={i}
                message={msg}
                toolCalls={lastToolCalls[i]}
              />
            ))}
            {isLoading && (
              <div className="flex justify-start">
                <div className="glass-card rounded-2xl px-4 py-3 flex items-center gap-2.5">
                  <Loader2 className="w-4 h-4 animate-spin text-emerald-400" />
                  <span className="text-xs text-slate-400">
                    ClawdBot is thinking...
                  </span>
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>
        )}

        {error && (
          <div className="mb-3 px-4 py-2.5 rounded-xl glass-card border-red-500/20 bg-red-500/[0.03] text-red-300 text-xs">
            {error}
          </div>
        )}

        {/* Input bar */}
        <div className="sticky bottom-0 pt-3">
          <div className="flex items-center gap-2 glass-card rounded-2xl px-4 py-3">
            <input
              ref={inputRef}
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={
                isAvailable
                  ? "Ask ClawdBot about your memories..."
                  : "ClawdBot is not available"
              }
              disabled={!isAvailable || isLoading}
              className="flex-1 bg-transparent text-sm text-slate-200 placeholder:text-slate-500 focus:outline-none disabled:opacity-50"
            />
            <button
              onClick={sendMessage}
              disabled={!input.trim() || !isAvailable || isLoading}
              title="Send message"
              className="p-2.5 rounded-xl bg-emerald-500/15 hover:bg-emerald-500/25 text-emerald-300 transition-all disabled:opacity-30 disabled:cursor-not-allowed border border-emerald-500/20 hover:scale-105"
            >
              <Send className="w-4 h-4" />
            </button>
          </div>
        </div>
      </main>
    </div>
  );
}
