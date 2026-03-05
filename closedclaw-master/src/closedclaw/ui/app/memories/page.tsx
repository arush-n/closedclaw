"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { FeedbackBanner } from "@/components/ui/feedback-banner";
import {
  Brain,
  Search,
  RefreshCw,
  Loader2,
  Trash2,
  Archive,
  Pause,
  ChevronRight,
  Clock,
  Tag,
  AppWindow,
} from "lucide-react";

interface OmMemory {
  id: string;
  memory: string;
  user_id: string;
  app_id?: string | null;
  app_name?: string | null;
  categories: string[];
  metadata?: Record<string, unknown>;
  state?: "active" | "archived" | "paused";
  created_at: string;
  updated_at: string;
}

interface OmMemoryListResponse {
  results: OmMemory[];
  items?: OmMemory[];
  memories?: OmMemory[];
  total: number;
  page?: number;
  size?: number;
}

interface OmStats {
  total_memories: number;
  active: number;
  archived: number;
  paused: number;
}

const USER_ID = "default-user";

export default function MemoriesPage() {
  const [memories, setMemories] = useState<OmMemory[]>([]);
  const [stats, setStats] = useState<OmStats>({
    total_memories: 0,
    active: 0,
    archived: 0,
    paused: 0,
  });
  const [query, setQuery] = useState("");
  const [appFilter, setAppFilter] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("");
  const [fromDate, setFromDate] = useState("");
  const [toDate, setToDate] = useState("");
  const [sort, setSort] = useState("created_at_desc");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);

  const debounceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [apps, setApps] = useState<{ id: string; name: string }[]>([]);
  const [allCategories, setAllCategories] = useState<string[]>([]);

  // Extract unique apps and categories from memories
  useEffect(() => {
    const uniqueApps = Array.from(
      new Map(
        memories
          .filter((m) => m.app_id && m.app_name)
          .map((m) => [m.app_id, { id: m.app_id!, name: m.app_name! }])
      ).values()
    );
    setApps(uniqueApps);

    const uniqueCategories = Array.from(
      new Set(memories.flatMap((m) => m.categories || []))
    ).sort();
    setAllCategories(uniqueCategories);
  }, [memories]);

  const loadMemories = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({
        user_id: USER_ID,
        page_size: "100",
        ...(query && { search_query: query }),
        ...(appFilter && { app_ids: appFilter }),
        ...(categoryFilter && { category_ids: categoryFilter }),
        ...(fromDate && { from_date: fromDate }),
        ...(toDate && { to_date: toDate }),
      });

      const response = await fetch(`/api/openmemory/memories/?${params}`, {
        cache: "no-store",
      });
      if (!response.ok)
        throw new Error(`Failed to load memories (${response.status})`);

      const data = (await response.json()) as OmMemoryListResponse;
      const items =
        data.results ?? data.items ?? data.memories ?? [];
      setMemories(items);

      // Calculate stats
      const statsData: OmStats = {
        total_memories: items.length,
        active: items.filter((m) => m.state !== "archived" && m.state !== "paused").length,
        archived: items.filter((m) => m.state === "archived").length,
        paused: items.filter((m) => m.state === "paused").length,
      };
      setStats(statsData);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to load memories"
      );
    } finally {
      setIsLoading(false);
    }
  }, [query, appFilter, categoryFilter, fromDate, toDate]);

  // Debounced load on filter change
  useEffect(() => {
    if (debounceTimerRef.current) clearTimeout(debounceTimerRef.current);
    debounceTimerRef.current = setTimeout(() => {
      loadMemories();
    }, 300);
    return () => {
      if (debounceTimerRef.current) clearTimeout(debounceTimerRef.current);
    };
  }, [query, appFilter, categoryFilter, fromDate, toDate, loadMemories]);

  const handleArchive = async (id: string) => {
    try {
      const response = await fetch("/api/openmemory/memories/actions/archive", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ memory_ids: [id] }),
      });
      if (!response.ok) throw new Error("Failed to archive");
      setSuccess("Memory archived");
      await loadMemories();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to archive");
    }
  };

  const handlePause = async (id: string) => {
    try {
      const response = await fetch("/api/openmemory/memories/actions/pause", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ memory_ids: [id] }),
      });
      if (!response.ok) throw new Error("Failed to pause");
      setSuccess("Memory paused");
      await loadMemories();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to pause");
    }
  };

  const handleDelete = async (id: string) => {
    try {
      const response = await fetch("/api/openmemory/memories/", {
        method: "DELETE",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ memory_ids: [id] }),
      });
      if (!response.ok) throw new Error("Failed to delete");
      setSuccess("Memory deleted");
      setConfirmDeleteId(null);
      await loadMemories();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete");
    }
  };

  return (
    <div className="page-container space-y-6 animate-fadeIn">
      {error && (
        <FeedbackBanner
          variant="error"
          message={error}
          onDismiss={() => setError(null)}
        />
      )}
      {success && (
        <FeedbackBanner
          variant="success"
          message={success}
          onDismiss={() => setSuccess(null)}
        />
      )}

      {/* Header */}
      <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="p-2.5 rounded-xl bg-violet-500/10 border border-violet-500/20">
            <Brain className="w-5 h-5 text-violet-400" />
          </div>
          <div>
            <h1 className="section-title">Memories</h1>
            <p className="text-sm text-slate-500 mt-0.5">
              {stats.total_memories} total
            </p>
          </div>
        </div>
        <Button variant="outline" onClick={loadMemories} disabled={isLoading}>
          {isLoading ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : (
            <RefreshCw className="w-4 h-4" />
          )}
          {isLoading ? "Loading..." : "Refresh"}
        </Button>
      </div>

      {/* Stats row */}
      <div className="grid grid-cols-4 gap-3">
        {[
          { label: "Total", value: stats.total_memories },
          { label: "Active", value: stats.active },
          { label: "Archived", value: stats.archived },
          { label: "Paused", value: stats.paused },
        ].map((stat) => (
          <div key={stat.label} className="glass-stat rounded-xl p-3">
            <div className="text-xs text-slate-400 uppercase tracking-wide">
              {stat.label}
            </div>
            <div className="text-2xl font-bold text-white mt-1">
              {stat.value}
            </div>
          </div>
        ))}
      </div>

      {/* Filters */}
      <div className="glass-card rounded-xl p-5 space-y-4">
        <div className="flex items-center gap-2 mb-4">
          <Search className="w-4 h-4 text-slate-500" />
          <h2 className="text-sm font-semibold text-slate-200">Filters</h2>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <input
            type="text"
            placeholder="Search memories..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className="glass-input rounded-lg px-3 py-2 text-sm w-full"
          />
          <select
            value={appFilter}
            onChange={(e) => setAppFilter(e.target.value)}
            className="glass-input rounded-lg px-3 py-2 text-sm w-full"
          >
            <option value="">All apps</option>
            {apps.map((app) => (
              <option key={app.id} value={app.id}>
                {app.name}
              </option>
            ))}
          </select>
          <select
            value={categoryFilter}
            onChange={(e) => setCategoryFilter(e.target.value)}
            className="glass-input rounded-lg px-3 py-2 text-sm w-full"
          >
            <option value="">All categories</option>
            {allCategories.map((cat) => (
              <option key={cat} value={cat}>
                {cat}
              </option>
            ))}
          </select>
          <select
            value={sort}
            onChange={(e) => setSort(e.target.value)}
            className="glass-input rounded-lg px-3 py-2 text-sm w-full"
          >
            <option value="created_at_desc">Newest first</option>
            <option value="created_at_asc">Oldest first</option>
          </select>
          <input
            type="date"
            value={fromDate}
            onChange={(e) => setFromDate(e.target.value)}
            className="glass-input rounded-lg px-3 py-2 text-sm w-full"
            placeholder="From date"
          />
          <input
            type="date"
            value={toDate}
            onChange={(e) => setToDate(e.target.value)}
            className="glass-input rounded-lg px-3 py-2 text-sm w-full"
            placeholder="To date"
          />
        </div>
      </div>

      {/* Loading state */}
      {isLoading && memories.length === 0 && (
        <div className="flex items-center justify-center gap-2 py-12 text-slate-400">
          <Loader2 className="w-4 h-4 animate-spin" />
          Loading memories...
        </div>
      )}

      {/* Empty state */}
      {!isLoading && memories.length === 0 && (
        <div className="flex flex-col items-center justify-center py-12 text-center">
          <Brain className="w-12 h-12 text-slate-600 mb-3" />
          <p className="text-slate-400">No memories found</p>
        </div>
      )}

      {/* Memory cards */}
      {memories.length > 0 && (
        <div className="space-y-3">
          {memories.map((memory) => (
            <div
              key={memory.id}
              className="glass-card rounded-xl p-4 space-y-3 hover:bg-white/[0.06] transition-colors"
            >
              <div className="flex items-start justify-between gap-4">
                <Link href={`/memories/${memory.id}`} className="flex-1 group">
                  <p className="text-white font-medium group-hover:text-violet-300 transition-colors line-clamp-2">
                    {memory.memory}
                  </p>
                </Link>
                <Link
                  href={`/memories/${memory.id}`}
                  className="text-slate-500 hover:text-violet-400 transition-colors flex-shrink-0"
                >
                  <ChevronRight className="w-5 h-5" />
                </Link>
              </div>

              <div className="flex flex-wrap gap-2">
                {memory.categories?.map((cat) => (
                  <span
                    key={cat}
                    className="badge badge-primary text-xs"
                  >
                    {cat}
                  </span>
                ))}
                {memory.app_name && (
                  <span className="badge badge-neutral text-xs flex items-center gap-1">
                    <AppWindow className="w-3 h-3" />
                    {memory.app_name}
                  </span>
                )}
              </div>

              <div className="flex items-center justify-between text-xs text-slate-400">
                <div className="flex items-center gap-4">
                  <span className="flex items-center gap-1">
                    <Clock className="w-3 h-3" />
                    {new Date(memory.created_at).toLocaleDateString()}
                  </span>
                  {memory.state && memory.state !== "active" && (
                    <span className={`badge badge-${memory.state === "archived" ? "warning" : "neutral"} text-xs`}>
                      {memory.state}
                    </span>
                  )}
                </div>
              </div>

              <div className="flex items-center gap-2 pt-2 border-t border-white/[0.05]">
                {confirmDeleteId === memory.id ? (
                  <>
                    <Button
                      size="sm"
                      variant="destructive"
                      onClick={() => handleDelete(memory.id)}
                    >
                      Confirm delete
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => setConfirmDeleteId(null)}
                    >
                      Cancel
                    </Button>
                  </>
                ) : (
                  <>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => handleArchive(memory.id)}
                    >
                      <Archive className="w-3 h-3 mr-1" />
                      Archive
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => handlePause(memory.id)}
                    >
                      <Pause className="w-3 h-3 mr-1" />
                      Pause
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => setConfirmDeleteId(memory.id)}
                    >
                      <Trash2 className="w-3 h-3 mr-1" />
                      Delete
                    </Button>
                  </>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
