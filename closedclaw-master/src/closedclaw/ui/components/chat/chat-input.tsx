"use client";

import { useRef, useState } from "react";
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
        "glass-card p-2.5 rounded-lg shrink-0 transition-all border-white/[0.08]",
        disabled
          ? "opacity-40 cursor-not-allowed"
          : "cursor-pointer hover:border-violet-500/30"
      )}
    >
      <svg
        width="14"
        height="14"
        viewBox="0 0 12 16"
        fill="none"
        xmlns="http://www.w3.org/2000/svg"
      >
        <title>Send</title>
        <path
          d="M12 6L10.55 7.4L7 3.85L7 16L5 16L5 3.85L1.45 7.4L-4.37114e-07 6L6 -2.62268e-07L12 6Z"
          fill="currentColor"
          className="text-slate-300"
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
      className="glass-card p-2.5 rounded-lg shrink-0 cursor-pointer hover:border-red-500/30 transition-all border-white/[0.08]"
    >
      <Square className="size-3.5 text-slate-300 fill-slate-300" />
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
    <div className="relative z-20">
      {/* Status bar */}
      <div className="flex items-center gap-3 px-3 py-2 rounded-t-xl border-x border-t border-white/[0.08] bg-white/[0.02]">
        <ChatOrbSmall size={18} className="shrink-0" />
        <p className="text-xs text-slate-500">
          {statusMessage || "Ready to chat..."}
        </p>
      </div>

      {/* Input area */}
      <div
        className={cn(
          "flex items-end gap-2 glass-card rounded-b-xl rounded-t-none p-3 border-t-0 focus-within:border-violet-500/30 transition-all",
          isMultiline && "flex-col items-stretch"
        )}
      >
        <textarea
          ref={textareaRef}
          value={value}
          onChange={handleChange}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          className="bg-transparent w-full p-2 min-h-9 placeholder:text-slate-600 focus:outline-none resize-none overflow-y-auto text-sm text-slate-200 transition-all"
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
    </div>
  );
}
