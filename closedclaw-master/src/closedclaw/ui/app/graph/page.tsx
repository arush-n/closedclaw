"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import { useRouter } from "next/navigation";
import { MemoryGraph, MemoryData } from "@/components/graph";
import { Sidebar } from "@/components/graph/sidebar";
import { ChatSidebar, ChatFloatingButton } from "@/components/chat";
import { Button } from "@/components/ui/button";
import {
  Settings,
  RefreshCw,
  List,
  Grid3X3,
  MessageSquare,
  Send,
  Clock,
  X,
} from "lucide-react";

type ViewMode = "graph" | "list";

export default function GraphPage() {
  const router = useRouter();
  const [memories, setMemories] = useState<MemoryData[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);
  const [viewMode, setViewMode] = useState<ViewMode>("graph");
  const [isChatOpen, setIsChatOpen] = useState(false);
  const [userId, setUserId] = useState("default");
  const [showSettings, setShowSettings] = useState(false);
  const [showAddMemoryModal, setShowAddMemoryModal] = useState(false);
  const [newMemoryText, setNewMemoryText] = useState("");
  const [newMemoryTags, setNewMemoryTags] = useState("");
  const [newMemorySensitivity, setNewMemorySensitivity] = useState(1);
  const [isSavingMemory, setIsSavingMemory] = useState(false);
  const [selectedMemory, setSelectedMemory] = useState<MemoryData | null>(null);
  const [chatQuery, setChatQuery] = useState("");
  const [activeGroup, setActiveGroup] = useState<string | null>(null);
  const [availableGroups, setAvailableGroups] = useState<Record<string, number>>({});
  const inputRef = useRef<HTMLInputElement>(null);

  // Progressive memory loading — small initial batch, then rest in background
  const fetchMemories = useCallback(async () => {
    setIsLoading(true);
    setError(null);

    const INITIAL_BATCH = 50;
    const FULL_LIMIT = 200;

    try {
      const params = new URLSearchParams({ limit: String(INITIAL_BATCH) });
      if (userId) params.append("user_id", userId);

      const response = await fetch(`/api/memories?${params.toString()}`);
      const data = await response.json();

      if (!data.success) {
        throw new Error(data.error || "Failed to fetch memories");
      }

      setMemories(data.memories);
      setIsLoading(false);

      // Load remaining in background if there might be more
      if (data.memories.length >= INITIAL_BATCH) {
        const fullParams = new URLSearchParams({ limit: String(FULL_LIMIT) });
        if (userId) fullParams.append("user_id", userId);

        fetch(`/api/memories?${fullParams.toString()}`)
          .then((r) => r.json())
          .then((fullData) => {
            if (fullData.success && fullData.memories.length > INITIAL_BATCH) {
              setMemories(fullData.memories);
            }
          })
          .catch(() => {});
      }
    } catch (err) {
      setError(err instanceof Error ? err : new Error(String(err)));
      setIsLoading(false);
    }
  }, [userId]);

  // Initial fetch
  useEffect(() => {
    fetchMemories();
  }, [fetchMemories]);

  const handleMemoryClick = (memory: MemoryData) => {
    setSelectedMemory(memory);
  };

  const handleGroupsChange = useCallback((groups: Record<string, number>) => {
    setAvailableGroups(groups);
  }, []);

  const handleAddMemory = useCallback(async () => {
    if (!newMemoryText.trim() || isSavingMemory) {
      return;
    }

    setIsSavingMemory(true);
    try {
      const tags = newMemoryTags
        .split(",")
        .map((tag) => tag.trim())
        .filter(Boolean);

      const response = await fetch("/api/memories", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          content: newMemoryText.trim(),
          user_id: userId || "default",
          sensitivity: newMemorySensitivity,
          tags,
          source: "manual",
        }),
      });

      const result = await response.json();
      if (!result.success) {
        throw new Error(result.error || "Failed to add memory");
      }

      setShowAddMemoryModal(false);
      setNewMemoryText("");
      setNewMemoryTags("");
      setNewMemorySensitivity(1);
      await fetchMemories();
    } catch (err) {
      setError(err instanceof Error ? err : new Error(String(err)));
    } finally {
      setIsSavingMemory(false);
    }
  }, [
    newMemoryText,
    newMemoryTags,
    newMemorySensitivity,
    userId,
    isSavingMemory,
    fetchMemories,
  ]);

  return (
    <div className="h-[calc(100vh-52px)] w-full bg-zinc-950 flex flex-col overflow-hidden">
      <main className="flex-1 relative overflow-hidden">
        <div className="absolute top-3 right-4 z-20 flex items-center gap-2">
          <div className="flex items-center bg-slate-900/70 border border-slate-700/50 rounded-lg p-0.5 backdrop-blur-md">
            <button
              onClick={() => setViewMode("graph")}
              className={`px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
                viewMode === "graph"
                  ? "bg-indigo-500/20 text-indigo-200"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              <Grid3X3 className="w-3.5 h-3.5 inline-block mr-1" />
              Graph
            </button>
            <button
              onClick={() => setViewMode("list")}
              className={`px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${
                viewMode === "list"
                  ? "bg-indigo-500/20 text-indigo-200"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              <List className="w-3.5 h-3.5 inline-block mr-1" />
              List
            </button>
          </div>

          <Button
            variant="ghost"
            size="icon"
            onClick={fetchMemories}
            disabled={isLoading}
            className="h-9 w-9 text-slate-300 hover:text-slate-100 bg-slate-900/60 border border-slate-700/50"
            title="Refresh"
          >
            <RefreshCw className={`w-4 h-4 ${isLoading ? "animate-spin" : ""}`} />
          </Button>

          <Button
            variant="ghost"
            size="icon"
            onClick={() => setShowSettings(!showSettings)}
            className="h-9 w-9 text-slate-300 hover:text-slate-100 bg-slate-900/60 border border-slate-700/50"
          >
            <Settings className="w-4 h-4" />
          </Button>

          <Button
            onClick={() => setIsChatOpen(true)}
            className="h-9 bg-slate-900/80 hover:bg-slate-900 text-slate-100 border border-slate-700/50"
          >
            <MessageSquare className="w-4 h-4 mr-1.5" />
            Chat
          </Button>
        </div>

        {showSettings && (
          <div className="absolute top-14 right-4 z-20 bg-slate-950/85 border border-slate-700/50 rounded-xl p-3 flex items-center gap-4 backdrop-blur-md">
            <div className="flex items-center gap-2">
              <label className="text-xs text-slate-400">User ID</label>
              <input
                type="text"
                value={userId}
                onChange={(e) => setUserId(e.target.value)}
                placeholder="Filter by user..."
                className="px-2.5 py-1.5 bg-slate-900 border border-slate-700 rounded-md text-xs text-slate-200 placeholder:text-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/40 w-44"
              />
            </div>
            <div className="text-xs text-slate-500">{memories.length} memories</div>
          </div>
        )}

        {viewMode === "graph" ? (
          <>
            <MemoryGraph
              memories={memories}
              isLoading={isLoading}
              error={error}
              onMemoryClick={handleMemoryClick}
              showLegend={true}
              showControls={true}
              activeGroup={activeGroup}
              onGroupsChange={handleGroupsChange}
            />
            
            {/* Group Filter Pills */}
            {Object.keys(availableGroups).length > 0 && (
              <div className="absolute top-3 left-1/2 -translate-x-1/2 z-20 flex items-center gap-1.5 px-3 py-1.5 bg-slate-950/80 backdrop-blur-xl border border-slate-700/40 rounded-xl">
                <button
                  onClick={() => setActiveGroup(null)}
                  className={`px-2.5 py-1 rounded-md text-xs font-medium transition-colors ${
                    activeGroup === null
                      ? "bg-indigo-500/25 text-indigo-200 border border-indigo-500/40"
                      : "text-slate-400 hover:text-slate-200 border border-transparent"
                  }`}
                >
                  All
                </button>
                {Object.entries(availableGroups)
                  .sort((a, b) => b[1] - a[1])
                  .map(([group, count]) => (
                    <button
                      key={group}
                      onClick={() => setActiveGroup(activeGroup === group ? null : group)}
                      className={`px-2.5 py-1 rounded-md text-xs font-medium transition-colors ${
                        activeGroup === group
                          ? "bg-indigo-500/25 text-indigo-200 border border-indigo-500/40"
                          : "text-slate-400 hover:text-slate-200 border border-transparent"
                      }`}
                    >
                      {group}
                      <span className="ml-1 text-[10px] text-slate-500">{count}</span>
                    </button>
                  ))}
              </div>
            )}

            {/* Left Sidebar */}
            <Sidebar
              onAddMemory={() => setShowAddMemoryModal(true)}
              onViewVault={() => router.push("/vault")}
              onViewProfile={() => router.push("/profile")}
              onViewInsights={() => router.push("/insights")}
              onViewAgent={() => router.push("/agent")}
              onOpenSettings={() => setShowSettings(true)}
            />
          </>
        ) : (
          <div className="h-full overflow-auto p-16 pt-20">
            <div className="grid gap-3 max-w-4xl mx-auto">
              {memories.map((memory) => (
                <div
                  key={memory.id}
                  onClick={() => setSelectedMemory(memory)}
                  className={`p-4 bg-zinc-900/50 border border-zinc-800 rounded-xl hover:border-zinc-700 transition-colors cursor-pointer ${
                    selectedMemory?.id === memory.id ? "border-primary" : ""
                  }`}
                >
                  <p className="text-zinc-200 mb-2">{memory.memory}</p>
                  <div className="flex items-center gap-3 text-xs text-zinc-500">
                    {memory.user_id && <span>User: {memory.user_id}</span>}
                    {memory.created_at && (
                      <span>
                        {new Date(memory.created_at).toLocaleDateString()}
                      </span>
                    )}
                    {memory.categories?.map((cat) => (
                      <span
                        key={cat}
                        className="px-2 py-0.5 bg-zinc-800 rounded text-zinc-400"
                      >
                        {cat}
                      </span>
                    ))}
                  </div>
                </div>
              ))}
              {memories.length === 0 && !isLoading && (
                <div className="text-center py-12 text-zinc-500">
                  No memories found
                </div>
              )}
            </div>
          </div>
        )}

        {showAddMemoryModal && (
          <div className="absolute inset-0 z-40 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4">
            <div className="w-full max-w-xl rounded-xl border border-slate-700/60 bg-slate-950/95 p-5">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-lg font-semibold text-slate-100">Add Memory</h3>
                <button
                  onClick={() => setShowAddMemoryModal(false)}
                  className="p-1.5 text-slate-400 hover:text-slate-200"
                  title="Close"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>

              <div className="space-y-3">
                <textarea
                  value={newMemoryText}
                  onChange={(e) => setNewMemoryText(e.target.value)}
                  placeholder="What memory do you want to store?"
                  className="w-full min-h-28 rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-200 placeholder:text-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/40"
                />

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <input
                    type="text"
                    value={newMemoryTags}
                    onChange={(e) => setNewMemoryTags(e.target.value)}
                    placeholder="Tags (comma separated)"
                    className="rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-200 placeholder:text-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500/40"
                  />

                  <select
                    aria-label="Select memory sensitivity"
                    value={newMemorySensitivity}
                    onChange={(e) => setNewMemorySensitivity(Number(e.target.value))}
                    className="rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-200 focus:outline-none focus:ring-2 focus:ring-indigo-500/40"
                  >
                    <option value={0}>Sensitivity 0 - Public</option>
                    <option value={1}>Sensitivity 1 - General</option>
                    <option value={2}>Sensitivity 2 - Personal</option>
                    <option value={3}>Sensitivity 3 - Sensitive</option>
                  </select>
                </div>
              </div>

              <div className="mt-5 flex items-center justify-end gap-2">
                <Button
                  variant="ghost"
                  onClick={() => setShowAddMemoryModal(false)}
                  className="text-slate-300"
                >
                  Cancel
                </Button>
                <Button
                  onClick={handleAddMemory}
                  disabled={isSavingMemory || !newMemoryText.trim()}
                  className="bg-indigo-600 hover:bg-indigo-500 text-white"
                >
                  {isSavingMemory ? "Saving..." : "Save Memory"}
                </Button>
              </div>
            </div>
          </div>
        )}
      </main>

      {/* Chat Sidebar */}
      <ChatSidebar
        isOpen={isChatOpen}
        onClose={() => setIsChatOpen(false)}
        config={{
          userId: userId || "default-user",
          baseUrl: "/api",
        }}
        initialMessage={chatQuery}
      />

      {/* Bottom Chat Input Bar */}
      {!isChatOpen && viewMode === "graph" && (
        <div className="absolute bottom-6 left-1/2 -translate-x-1/2 z-20 w-full max-w-lg px-4">
          <div className="bg-slate-950/85 backdrop-blur-xl border border-slate-700/50 rounded-2xl shadow-2xl overflow-hidden">
            <div className="flex items-center gap-2 p-2">
              <button
                className="p-2 text-slate-500 hover:text-slate-300 transition-colors"
                title="Recent searches"
              >
                <Clock className="w-5 h-5" />
              </button>
              <input
                ref={inputRef}
                type="text"
                value={chatQuery}
                onChange={(e) => setChatQuery(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && chatQuery.trim()) {
                    setIsChatOpen(true);
                  }
                }}
                placeholder="Ask your closedclaw"
                className="flex-1 bg-transparent text-slate-200 placeholder:text-slate-500 focus:outline-none text-sm py-2"
              />
              <button
                onClick={() => {
                  if (chatQuery.trim()) {
                    setIsChatOpen(true);
                  }
                }}
                disabled={!chatQuery.trim()}
                className="p-2 text-slate-500 hover:text-indigo-300 disabled:opacity-50 transition-colors"
                title="Send"
              >
                <Send className="w-5 h-5" />
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Chat Floating Button (when chat is closed) */}
      {!isChatOpen && viewMode !== "graph" && (
        <ChatFloatingButton onClick={() => setIsChatOpen(true)} isOpen={isChatOpen} />
      )}
    </div>
  );
}
