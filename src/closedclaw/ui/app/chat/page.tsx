"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { ChatSidebar } from "@/components/chat";
import { MessageSquare, User } from "lucide-react";

export default function ChatPage() {
  const [isOpen, setIsOpen] = useState(false);
  const [userId, setUserId] = useState("default-user");

  return (
    <div className="page-container space-y-6 animate-fadeIn">
      <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="p-2.5 rounded-xl bg-violet-500/10 border border-violet-500/20">
            <MessageSquare className="w-5 h-5 text-violet-400" />
          </div>
          <div>
            <h1 className="section-title">Chat</h1>
            <p className="text-sm text-slate-500 mt-0.5">Privacy-aware memory chat</p>
          </div>
        </div>
        <Button onClick={() => setIsOpen(true)}>
          <MessageSquare className="w-4 h-4" />
          Open Chat
        </Button>
      </div>

      <div className="glass-card rounded-xl p-5 space-y-4">
        <label className="text-sm text-slate-400 flex items-center gap-2">
          <User className="w-4 h-4 text-slate-500" />
          User ID
        </label>
        <input
          value={userId}
          onChange={(event) => setUserId(event.target.value)}
          title="User ID"
          placeholder="default-user"
          className="glass-input rounded-lg px-4 py-2.5 text-sm w-full max-w-md"
        />
        <p className="text-sm text-slate-500 leading-relaxed">
          Chat uses memory retrieval and privacy controls from the backend proxy.
          Conversations are locally processed with full audit trails.
        </p>
      </div>

      <ChatSidebar
        isOpen={isOpen}
        onClose={() => setIsOpen(false)}
        config={{
          userId: userId || "default-user",
          baseUrl: "/api",
        }}
      />
    </div>
  );
}
