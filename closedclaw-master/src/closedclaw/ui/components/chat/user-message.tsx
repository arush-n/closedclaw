"use client";

import { Copy, Check } from "lucide-react";
import { cn } from "@/lib/utils";
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
      <div className="bg-primary/20 rounded-2xl rounded-br-md p-3 px-4 max-w-[85%] border border-primary/30">
        <p className="text-sm text-slate-100 whitespace-pre-wrap">
          {message.content}
        </p>
      </div>
      <button
        type="button"
        onClick={() => onCopy(message.id, message.content)}
        className="p-1.5 hover:bg-white/[0.06] rounded transition-all mt-1 opacity-0 group-hover:opacity-100"
        title="Copy message"
      >
        {isCopied ? (
          <Check className="size-3.5 text-green-400" />
        ) : (
          <Copy className="size-3.5 text-slate-500" />
        )}
      </button>
    </div>
  );
}
