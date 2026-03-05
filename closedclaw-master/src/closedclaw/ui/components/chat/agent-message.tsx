"use client";

import { useState } from "react";
import { Copy, Check, ThumbsUp, ThumbsDown, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import type { Message } from "./types";
import { RelatedMemories } from "./related-memories";
import { ContextInspector } from "./context-inspector";
import { motion } from "framer-motion";
import ReactMarkdown from "react-markdown";

interface AgentMessageProps {
  message: Message;
  copiedId?: string | null;
  onCopy: (id: string, text: string) => void;
  isStreaming?: boolean;
}

export function AgentMessage({
  message,
  copiedId,
  onCopy,
  isStreaming = false,
}: AgentMessageProps) {
  const [expandedMemories, setExpandedMemories] = useState(false);
  const [feedback, setFeedback] = useState<"like" | "dislike" | null>(null);
  const isCopied = copiedId === message.id;
  const metadata = message.metadata;

  return (
    <div className="flex flex-col gap-2 w-full group">
      {/* Related Memories */}
      {message.relatedMemories && message.relatedMemories.length > 0 && (
        <RelatedMemories
          memories={message.relatedMemories}
          isExpanded={expandedMemories}
          onToggle={() => setExpandedMemories(!expandedMemories)}
        />
      )}

      {/* Message Content */}
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        className="text-sm text-slate-200 prose-chat"
      >
        {isStreaming && !message.content ? (
          <div className="flex items-center gap-2 text-slate-500">
            <Loader2 className="size-4 animate-spin" />
            <span>Thinking...</span>
          </div>
        ) : (
          <ReactMarkdown
            components={{
              p: ({ children }) => <p className="mb-2 last:mb-0">{children}</p>,
              ul: ({ children }) => (
                <ul className="list-disc list-inside mb-2">{children}</ul>
              ),
              ol: ({ children }) => (
                <ol className="list-decimal list-inside mb-2">{children}</ol>
              ),
              code: ({ className, children, ...props }) => {
                const isInline = !className;
                if (isInline) {
                  return (
                    <code className="bg-white/[0.06] px-1.5 py-0.5 rounded text-sm text-primary">
                      {children}
                    </code>
                  );
                }
                return (
                  <code
                    className="block bg-black/30 p-3 rounded-lg text-sm overflow-x-auto mb-2"
                    {...props}
                  >
                    {children}
                  </code>
                );
              },
              pre: ({ children }) => <div className="not-prose">{children}</div>,
              a: ({ href, children }) => (
                <a
                  href={href}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-primary hover:underline"
                >
                  {children}
                </a>
              ),
              blockquote: ({ children }) => (
                <blockquote className="border-l-2 border-primary/50 pl-4 italic text-slate-400 mb-2">
                  {children}
                </blockquote>
              ),
            }}
          >
            {message.content}
          </ReactMarkdown>
        )}
      </motion.div>

      {/* Context Inspector — shows memory details, redaction info, audit link */}
      <ContextInspector
        metadata={metadata}
        memories={message.relatedMemories}
      />

      {/* Actions */}
      <div className="flex items-center gap-1 mt-1 opacity-0 group-hover:opacity-100 transition-opacity">
        <button
          type="button"
          onClick={() => onCopy(message.id, message.content)}
          className="p-1.5 hover:bg-white/[0.06] rounded transition-colors"
          title="Copy message"
        >
          {isCopied ? (
            <Check className="size-3.5 text-green-400" />
          ) : (
            <Copy className="size-3.5 text-slate-500 hover:text-slate-300" />
          )}
        </button>
        <button
          type="button"
          onClick={() => setFeedback(feedback === "like" ? null : "like")}
          className={cn(
            "p-1.5 hover:bg-white/[0.06] rounded transition-colors",
            feedback === "like" && "bg-white/[0.06]"
          )}
          title="Like"
        >
          <ThumbsUp
            className={cn(
              "size-3.5",
              feedback === "like"
                ? "text-green-400 fill-green-400"
                : "text-slate-500 hover:text-slate-300"
            )}
          />
        </button>
        <button
          type="button"
          onClick={() => setFeedback(feedback === "dislike" ? null : "dislike")}
          className={cn(
            "p-1.5 hover:bg-white/[0.06] rounded transition-colors",
            feedback === "dislike" && "bg-white/[0.06]"
          )}
          title="Dislike"
        >
          <ThumbsDown
            className={cn(
              "size-3.5",
              feedback === "dislike"
                ? "text-red-400 fill-red-400"
                : "text-slate-500 hover:text-slate-300"
            )}
          />
        </button>
      </div>
    </div>
  );
}
