"use client";

import { useState, useCallback, useRef, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { MessageSquare, X, Trash2, Search, Sparkles, Bot } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { ChatInput } from "./chat-input";
import { ChatOrb } from "./chat-orb";
import { UserMessage } from "./user-message";
import { AgentMessage } from "./agent-message";
import { useChatWithClosedclaw } from "./use-chat-with-mem0";
import type { ClosedclawConfig } from "./types";

const DEFAULT_SUGGESTIONS = [
  "What do I remember most about?",
  "Summarize my recent memories",
  "What patterns do you see in my thoughts?",
  "Connect ideas from my memories",
];

interface ChatSidebarProps {
  isOpen: boolean;
  onClose: () => void;
  config: ClosedclawConfig;
  suggestions?: string[];
  initialMessage?: string;
}

function ChatEmptyState({
  onSuggestionClick,
  suggestions = DEFAULT_SUGGESTIONS,
}: {
  onSuggestionClick: (suggestion: string) => void;
  suggestions?: string[];
}) {
  return (
    <div className="flex flex-col items-center justify-center h-full py-8">
      <ChatOrb size={80} className="mb-6" />
      <h3 className="text-lg font-medium text-zinc-200 mb-2">
        Chat with your memories
      </h3>
      <p className="text-sm text-zinc-500 mb-6 text-center max-w-[280px]">
        Ask questions about your stored memories and get intelligent answers.
      </p>
      <div className="flex flex-col gap-2 w-full max-w-[320px]">
        {suggestions.map((suggestion) => (
          <Button
            key={suggestion}
            variant="outline"
            className="w-full justify-start gap-2 h-auto py-2 px-3 text-left border-zinc-800 bg-zinc-900/50 hover:bg-zinc-800 hover:border-primary/50 transition-all"
            onClick={() => onSuggestionClick(suggestion)}
          >
            <Search className="size-4 text-primary shrink-0" />
            <span className="text-xs text-zinc-400 truncate">{suggestion}</span>
          </Button>
        ))}
      </div>
    </div>
  );
}

export function ChatSidebar({
  isOpen,
  onClose,
  config,
  suggestions = DEFAULT_SUGGESTIONS,
  initialMessage = "",
}: ChatSidebarProps) {
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [useClawdBot, setUseClawdBot] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const hasSetInitialMessage = useRef(false);

  const chatConfig = { ...config, useClawdBot };

  const {
    messages,
    input,
    setInput,
    sendMessage,
    stop,
    isLoading,
    error,
    clearMessages,
  } = useChatWithClosedclaw({ config: chatConfig });

  // Set initial message when chat opens
  useEffect(() => {
    if (isOpen && initialMessage && !hasSetInitialMessage.current) {
      setInput(initialMessage);
      hasSetInitialMessage.current = true;
    }
    if (!isOpen) {
      hasSetInitialMessage.current = false;
    }
  }, [isOpen, initialMessage, setInput]);

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

  const handleSuggestionClick = useCallback(
    (suggestion: string) => {
      setInput(suggestion);
    },
    [setInput]
  );

  return (
    <AnimatePresence>
      {isOpen && (
        <>
          {/* Backdrop */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 bg-black/50 z-40 lg:hidden"
            onClick={onClose}
          />

          {/* Sidebar */}
          <motion.div
            initial={{ x: "100%", opacity: 0 }}
            animate={{ x: 0, opacity: 1 }}
            exit={{ x: "100%", opacity: 0 }}
            transition={{ type: "spring", damping: 25, stiffness: 200 }}
            className={cn(
              "fixed right-0 top-0 h-full z-50",
              "w-full sm:w-[420px] lg:w-[480px]",
              "bg-zinc-950 border-l border-zinc-800",
              "flex flex-col"
            )}
          >
            {/* Header */}
            <div className="flex items-center justify-between px-4 py-3 border-b border-zinc-800">
              <div className="flex items-center gap-2">
                <Sparkles className="size-5 text-primary" />
                <h2 className="font-semibold text-zinc-100">
                  {useClawdBot ? "ClawdBot" : "Memory Chat"}
                </h2>
              </div>
              <div className="flex items-center gap-1">
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={() => setUseClawdBot(!useClawdBot)}
                  className={cn(
                    "size-8",
                    useClawdBot
                      ? "text-primary bg-primary/10"
                      : "text-zinc-500 hover:text-zinc-200"
                  )}
                  title={useClawdBot ? "Switch to proxy chat" : "Switch to ClawdBot agent"}
                >
                  <Bot className="size-4" />
                </Button>
                {messages.length > 0 && (
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={clearMessages}
                    className="size-8 text-zinc-500 hover:text-zinc-200"
                    title="Clear chat"
                  >
                    <Trash2 className="size-4" />
                  </Button>
                )}
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={onClose}
                  className="size-8 text-zinc-500 hover:text-zinc-200"
                >
                  <X className="size-4" />
                </Button>
              </div>
            </div>

            {/* Messages Area */}
            <ScrollArea className="flex-1 px-4">
              {messages.length === 0 ? (
                <ChatEmptyState
                  onSuggestionClick={handleSuggestionClick}
                  suggestions={suggestions}
                />
              ) : (
                <div className="py-4 space-y-4">
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
                          isStreaming={
                            isLoading && index === messages.length - 1
                          }
                        />
                      )}
                    </div>
                  ))}
                  <div ref={messagesEndRef} />
                </div>
              )}
            </ScrollArea>

            {/* Error Display */}
            {error && (
              <div className="px-4 py-2 bg-destructive/10 border-t border-destructive/20">
                <p className="text-xs text-destructive">{error}</p>
              </div>
            )}

            {/* Input Area */}
            <div className="p-4 border-t border-zinc-800">
              <ChatInput
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onSend={sendMessage}
                onStop={stop}
                isLoading={isLoading}
                statusMessage={
                  isLoading ? "Searching memories..." : undefined
                }
              />
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}

// Floating chat button component
export function ChatFloatingButton({
  onClick,
  isOpen,
}: {
  onClick: () => void;
  isOpen: boolean;
}) {
  return (
    <motion.button
      onClick={onClick}
      className={cn(
        "fixed bottom-6 right-6 z-30",
        "size-14 rounded-full",
        "bg-primary hover:bg-primary/90",
        "flex items-center justify-center",
        "shadow-lg shadow-primary/25",
        "transition-colors"
      )}
      whileHover={{ scale: 1.05 }}
      whileTap={{ scale: 0.95 }}
      animate={{ rotate: isOpen ? 180 : 0 }}
    >
      {isOpen ? (
        <X className="size-6 text-white" />
      ) : (
        <MessageSquare className="size-6 text-white" />
      )}
    </motion.button>
  );
}
