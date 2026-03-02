"use client";

import { useRef, useState } from "react";
import { motion } from "framer-motion";
import { Square } from "lucide-react";
import { cn } from "@/lib/utils";
import { ChatOrbSmall } from "./chat-orb";

interface ChatInputProps {
  value: string;
  onChange: (e: React.ChangeEvent<HTMLTextAreaElement>) => void;
  onSend: () => void;
  onStop: () => void;
  onKeyDown?: (e: React.KeyboardEvent) => void;
  isLoading?: boolean;
  statusMessage?: string;
  placeholder?: string;
}

export function SendButton({
  onClick,
  disabled,
}: {
  onClick: () => void;
  disabled: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      title="Send message"
      className={cn(
        "bg-zinc-900 border-zinc-800 border p-2 rounded-lg shrink-0 transition-all",
        disabled
          ? "opacity-50 cursor-not-allowed"
          : "cursor-pointer hover:bg-zinc-800 hover:border-primary/50"
      )}
    >
      <svg
        width="16"
        height="16"
        viewBox="0 0 12 16"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
      >
        <title>Send</title>
        <path
          d="M12 6L10.55 7.4L7 3.85L7 16L5 16L5 3.85L1.45 7.4L-4.37114e-07 6L6 -2.62268e-07L12 6Z"
          fill="currentColor"
          className="text-zinc-200"
        />
      </svg>
    </button>
  );
}

export function StopButton({ onClick }: { onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      title="Stop generation"
      className="bg-zinc-900 border-zinc-800 border p-2 rounded-lg shrink-0 cursor-pointer hover:bg-zinc-800 hover:border-destructive/50 transition-all"
    >
      <Square className="size-4 text-zinc-200 fill-zinc-200" />
    </button>
  );
}

export function ChatInput({
  value,
  onChange,
  onSend,
  onStop,
  onKeyDown,
  isLoading = false,
  statusMessage,
  placeholder = "Chat with your memories...",
}: ChatInputProps) {
  const [isMultiline, setIsMultiline] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const handleChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    onChange(e);
    const textarea = e.target;
    textarea.style.height = "auto";
    const newHeight = Math.min(textarea.scrollHeight, 120);
    textarea.style.height = `${newHeight}px`;
    setIsMultiline(textarea.scrollHeight > 52);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (!isLoading && value.trim()) {
        onSend();
      }
    }
    onKeyDown?.(e);
  };

  return (
    <motion.div
      className="relative z-20"
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
    >
      {/* Status bar */}
      <div className="flex items-center gap-3 px-3 py-2 bg-zinc-900/50 rounded-t-xl border-x border-t border-zinc-800">
        <ChatOrbSmall size={20} className="shrink-0" />
        <p className="text-sm text-zinc-500">
          {statusMessage || "Ready to chat..."}
        </p>
      </div>

      {/* Input area */}
      <div
        className={cn(
          "flex items-end gap-2 bg-zinc-900 rounded-b-xl p-3 border border-zinc-800 focus-within:border-primary/50 transition-all",
          isMultiline && "flex-col items-stretch"
        )}
      >
        <textarea
          ref={textareaRef}
          value={value}
          onChange={handleChange}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          className="bg-transparent w-full p-2 min-h-9 placeholder:text-zinc-600 focus:outline-none resize-none overflow-y-auto text-zinc-200 transition-all"
          rows={1}
          disabled={isLoading}
        />
        <div className={cn("shrink-0", isMultiline && "self-end")}>
          {isLoading ? (
            <StopButton onClick={onStop} />
          ) : (
            <SendButton onClick={onSend} disabled={!value.trim()} />
          )}
        </div>
      </div>
    </motion.div>
  );
}
