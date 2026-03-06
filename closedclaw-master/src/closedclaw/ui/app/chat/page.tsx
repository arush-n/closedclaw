"use client";

import { useState, useCallback, useRef, useEffect } from "react";
import { MessageSquare, Trash2, Bot, Search, ArrowLeft } from "lucide-react";
import { cn } from "@/lib/utils";
import { ChatInput } from "@/components/chat/chat-input";
import { ChatOrb } from "@/components/chat/chat-orb";
import { UserMessage } from "@/components/chat/user-message";
import { AgentMessage } from "@/components/chat/agent-message";
import { useChatWithClosedclaw } from "@/components/chat/use-chat-with-mem0";

const SUGGESTIONS = [
  "What do I remember most about?",
  "Summarize my recent memories",
  "What patterns do you see in my thoughts?",
  "Connect ideas from my memories",
];

export default function ChatPage() {
  const [userId] = useState("default-user");
  const [useClawdBot, setUseClawdBot] = useState(false);
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const {
    messages,
    input,
    setInput,
    sendMessage,
    stop,
    isLoading,
    error,
    clearMessages,
  } = useChatWithClosedclaw({
    config: { userId, baseUrl: "/api", useClawdBot },
  });

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, scrollToBottom]);

  const handleCopy = useCallback((id: string, text: string) => {
    navigator.clipboard.writeText(text);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  }, []);

  return (
    <div className="animate-fadeIn flex flex-col h-[calc(100vh-57px)]">
      {/* Header */}
      <header className="shrink-0 border-b border-white/[0.06] px-6 py-3" style={{ background: 'rgba(10, 12, 20, 0.6)' }}>
        <div className="max-w-3xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-3">
            <a
              href="/graph"
              title="Back to graph"
              className="p-1.5 rounded-lg hover:bg-white/[0.06] text-slate-400 hover:text-slate-200 transition-colors"
            >
              <ArrowLeft className="w-4 h-4" />
            </a>
            <div className="p-2 rounded-lg bg-violet-500/10 border border-violet-500/20">
              <MessageSquare className="w-4 h-4 text-violet-400" />
            </div>
            <div>
              <h1 className="text-sm font-semibold text-slate-100">
                {useClawdBot ? "ClawdBot" : "Memory Chat"}
              </h1>
              <p className="text-[11px] text-slate-500">Privacy-aware memory retrieval</p>
            </div>
          </div>
          <div className="flex items-center gap-1">
            <button
              onClick={() => setUseClawdBot(!useClawdBot)}
              className={cn(
                "p-2 rounded-lg transition-all text-xs font-medium flex items-center gap-1.5",
                useClawdBot
                  ? "bg-violet-500/15 text-violet-300 border border-violet-500/25"
                  : "text-slate-500 hover:text-slate-300 hover:bg-white/[0.04]"
              )}
              title={useClawdBot ? "Switch to proxy chat" : "Switch to ClawdBot agent"}
            >
              <Bot className="w-3.5 h-3.5" />
              {useClawdBot ? "ClawdBot" : "Proxy"}
            </button>
            {messages.length > 0 && (
              <button
                onClick={clearMessages}
                className="p-2 rounded-lg text-slate-500 hover:text-slate-200 hover:bg-white/[0.04] transition-colors"
                title="Clear chat"
              >
                <Trash2 className="w-3.5 h-3.5" />
              </button>
            )}
          </div>
        </div>
      </header>

      {/* Messages area */}
      <div className="flex-1 overflow-y-auto">
        <div className="max-w-3xl mx-auto px-6">
          {messages.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-24">
              <ChatOrb size={72} className="mb-6 opacity-80" />
              <h2 className="text-lg font-medium text-slate-200 mb-1.5">
                Chat with your memories
              </h2>
              <p className="text-sm text-slate-500 mb-8 text-center max-w-sm">
                Ask questions about your stored memories and get intelligent, privacy-aware answers.
              </p>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 w-full max-w-lg">
                {SUGGESTIONS.map((s) => (
                  <button
                    key={s}
                    onClick={() => setInput(s)}
                    className="glass-card rounded-xl px-4 py-3 text-left flex items-start gap-2.5 hover:border-violet-500/30 group"
                  >
                    <Search className="w-3.5 h-3.5 text-violet-400 mt-0.5 shrink-0" />
                    <span className="text-xs text-slate-400 group-hover:text-slate-200 transition-colors leading-relaxed">
                      {s}
                    </span>
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className="py-6 space-y-5">
              {messages.map((message, index) => (
                <div key={message.id}>
                  {message.role === "user" ? (
                    <UserMessage
                      message={message}
                      copiedId={copiedId}
                      onCopy={handleCopy}
                    />
                  ) : (
                    <AgentMessage
                      message={message}
                      copiedId={copiedId}
                      onCopy={handleCopy}
                      isStreaming={isLoading && index === messages.length - 1}
                    />
                  )}
                </div>
              ))}
              <div ref={messagesEndRef} />
            </div>
          )}
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="shrink-0 max-w-3xl mx-auto w-full px-6">
          <div className="px-4 py-2 rounded-lg bg-red-500/10 border border-red-500/20 mb-2">
            <p className="text-xs text-red-300">{error}</p>
          </div>
        </div>
      )}

      {/* Input */}
      <div className="shrink-0 border-t border-white/[0.06] py-4 px-6" style={{ background: 'rgba(10, 12, 20, 0.6)' }}>
        <div className="max-w-3xl mx-auto">
          <ChatInput
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onSend={sendMessage}
            onStop={stop}
            isLoading={isLoading}
            statusMessage={isLoading ? "Searching memories..." : undefined}
          />
        </div>
      </div>
    </div>
  );
}
