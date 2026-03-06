"use client";

import { Copy, Check } from "lucide-react";
import type { Message } from "./types";

interface UserMessageProps {
  message: Message;
  copiedId?: string | null;
  onCopy: (id: string, text: string) => void;
}

export function UserMessage({ message, copiedId, onCopy }: UserMessageProps) {
  const isCopied = copiedId === message.id;

  return (
    <div className="flex flex-col items-end w-full group">
      <div className="glass-card rounded-2xl rounded-br-md px-4 py-3 max-w-[80%] border-violet-500/20 bg-violet-500/[0.06]">
        <p className="text-sm text-slate-100 whitespace-pre-wrap leading-relaxed">
          {message.content}
        </p>
      </div>
      <button
        type="button"
        onClick={() => onCopy(message.id, message.content)}
        className="p-1.5 hover:bg-white/[0.06] rounded-md transition-all mt-1 opacity-0 group-hover:opacity-100"
        title="Copy message"
      >
        {isCopied ? (
          <Check className="size-3 text-emerald-400" />
        ) : (
          <Copy className="size-3 text-slate-600" />
        )}
      </button>
    </div>
  );
}
