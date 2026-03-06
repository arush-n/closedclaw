"use client";

import { useState } from "react";
import { Copy, Check, ThumbsUp, ThumbsDown } from "lucide-react";
import { cn } from "@/lib/utils";
import type { Message } from "./types";
import { RelatedMemories } from "./related-memories";
import { ContextInspector } from "./context-inspector";
import { ThinkingSteps } from "./thinking-steps";
import { AnimatePresence } from "framer-motion";
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
    <div className="flex flex-col gap-2.5 w-full group">
      {/* Related Memories */}
      {message.relatedMemories && message.relatedMemories.length > 0 && (
        <RelatedMemories
          memories={message.relatedMemories}
          isExpanded={expandedMemories}
          onToggle={() => setExpandedMemories(!expandedMemories)}
        />
      )}

      {/* Thinking Steps */}
      <AnimatePresence>
        {isStreaming && !message.content && (
          <ThinkingSteps isVisible={true} />
        )}
      </AnimatePresence>

      {/* Message Content */}
      {(message.content || !isStreaming) && (
        <div className="text-sm text-slate-200 prose-chat leading-relaxed">
          <ReactMarkdown
            components={{
              p: ({ children }) => <p className="mb-2 last:mb-0">{children}</p>,
              ul: ({ children }) => (
                <ul className="list-disc list-inside mb-2 space-y-0.5">{children}</ul>
              ),
              ol: ({ children }) => (
                <ol className="list-decimal list-inside mb-2 space-y-0.5">{children}</ol>
              ),
              code: ({ className, children, ...props }) => {
                const isInline = !className;
                if (isInline) {
                  return (
                    <code className="bg-violet-500/10 border border-violet-500/15 px-1.5 py-0.5 rounded text-[13px] text-violet-300">
                      {children}
                    </code>
                  );
                }
                return (
                  <code
                    className="block bg-black/30 border border-white/[0.06] p-3 rounded-lg text-[13px] overflow-x-auto mb-2"
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
                  className="text-violet-400 hover:text-violet-300 underline underline-offset-2 transition-colors"
                >
                  {children}
                </a>
              ),
              blockquote: ({ children }) => (
                <blockquote className="border-l-2 border-violet-500/40 pl-4 italic text-slate-400 mb-2">
                  {children}
                </blockquote>
              ),
            }}
          >
            {message.content}
          </ReactMarkdown>
        </div>
      )}

      {/* Context Inspector */}
      <ContextInspector
        metadata={metadata}
        memories={message.relatedMemories}
      />

      {/* Actions */}
      <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity">
        <button
          type="button"
          onClick={() => onCopy(message.id, message.content)}
          className="p-1.5 hover:bg-white/[0.06] rounded-md transition-colors"
          title="Copy message"
        >
          {isCopied ? (
            <Check className="size-3 text-emerald-400" />
          ) : (
            <Copy className="size-3 text-slate-600 hover:text-slate-400" />
          )}
        </button>
        <button
          type="button"
          onClick={() => setFeedback(feedback === "like" ? null : "like")}
          className={cn(
            "p-1.5 hover:bg-white/[0.06] rounded-md transition-colors",
            feedback === "like" && "bg-white/[0.06]"
          )}
          title="Like"
        >
          <ThumbsUp
            className={cn(
              "size-3",
              feedback === "like"
                ? "text-emerald-400 fill-emerald-400"
                : "text-slate-600 hover:text-slate-400"
            )}
          />
        </button>
        <button
          type="button"
          onClick={() => setFeedback(feedback === "dislike" ? null : "dislike")}
          className={cn(
            "p-1.5 hover:bg-white/[0.06] rounded-md transition-colors",
            feedback === "dislike" && "bg-white/[0.06]"
          )}
          title="Dislike"
        >
          <ThumbsDown
            className={cn(
              "size-3",
              feedback === "dislike"
                ? "text-red-400 fill-red-400"
                : "text-slate-600 hover:text-slate-400"
            )}
          />
        </button>
      </div>
    </div>
  );
}
