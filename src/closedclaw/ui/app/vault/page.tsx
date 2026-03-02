"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Search, Database, RefreshCw, Shield, Tag, Clock, User, Loader2 } from "lucide-react";

interface MemoryItem {
  id: string;
  memory: string;
  user_id?: string;
  sensitivity?: number;
  tags?: string[];
  created_at?: string;
}

const SENSITIVITY_BADGE: Record<number, string> = {
  0: "badge badge-success",
  1: "badge badge-primary",
  2: "badge badge-warning",
  3: "badge badge-danger",
};

export default function VaultPage() {
  const [memories, setMemories] = useState<MemoryItem[]>([]);
  const [query, setQuery] = useState("");
  const [sensitivityFilter, setSensitivityFilter] = useState<string>("all");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadMemories = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const response = await fetch("/api/memories?limit=300", { cache: "no-store" });
      if (!response.ok) throw new Error(`Failed to load memories (${response.status})`);
      const data = await response.json();
      setMemories(Array.isArray(data.memories) ? data.memories : []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load memories");
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    loadMemories();
  }, [loadMemories]);

  const filtered = useMemo(() => {
    return memories.filter((memory) => {
      const text = (memory.memory || "").toLowerCase();
      const matchesQuery = !query.trim() || text.includes(query.toLowerCase());

      const sensitivity = memory.sensitivity ?? 0;
      const matchesSensitivity =
        sensitivityFilter === "all" || sensitivity === Number(sensitivityFilter);

      return matchesQuery && matchesSensitivity;
    });
  }, [memories, query, sensitivityFilter]);

  return (
    <div className="page-container space-y-6 animate-fadeIn">
      {/* Header */}
      <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="p-2.5 rounded-xl bg-violet-500/10 border border-violet-500/20">
            <Database className="w-5 h-5 text-violet-400" />
          </div>
          <div>
            <h1 className="section-title">Memory Vault</h1>
            <p className="text-sm text-slate-500 mt-0.5">{memories.length} memories stored</p>
          </div>
        </div>
        <Button variant="outline" onClick={loadMemories} disabled={isLoading}>
          {isLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />}
          {isLoading ? "Refreshing..." : "Refresh"}
        </Button>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {[
          { label: "Total", value: memories.length, color: "text-slate-200" },
          { label: "Low Risk", value: memories.filter(m => (m.sensitivity ?? 0) <= 1).length, color: "text-emerald-400" },
          { label: "Medium Risk", value: memories.filter(m => (m.sensitivity ?? 0) === 2).length, color: "text-amber-400" },
          { label: "High Risk", value: memories.filter(m => (m.sensitivity ?? 0) >= 3).length, color: "text-red-400" },
        ].map((stat) => (
          <div key={stat.label} className="glass-stat rounded-xl p-4">
            <div className="text-xs text-slate-500 mb-1">{stat.label}</div>
            <div className={`text-xl font-bold ${stat.color}`}>{stat.value}</div>
          </div>
        ))}
      </div>

      {/* Filters */}
      <div className="glass-card rounded-xl p-4">
        <div className="flex flex-wrap items-center gap-3">
          <div className="relative flex-1 min-w-[260px]">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search memories..."
              className="glass-input rounded-lg pl-10 pr-4 py-2.5 text-sm w-full"
            />
          </div>
          <select
            aria-label="Filter by sensitivity"
            value={sensitivityFilter}
            onChange={(event) => setSensitivityFilter(event.target.value)}
            className="glass-input rounded-lg px-3 py-2.5 text-sm"
          >
            <option value="all">All sensitivities</option>
            <option value="0">Level 0 — Public</option>
            <option value="1">Level 1 — Internal</option>
            <option value="2">Level 2 — Sensitive</option>
            <option value="3">Level 3 — Critical</option>
          </select>
          {(query || sensitivityFilter !== "all") && (
            <span className="text-xs text-slate-500">
              {filtered.length} of {memories.length} shown
            </span>
          )}
        </div>
      </div>

      {/* Memory List */}
      <div className="space-y-3">
        {error && (
          <div className="glass-card rounded-xl p-4 border-red-500/30 bg-red-500/5">
            <p className="text-sm text-red-400">{error}</p>
          </div>
        )}

        {isLoading && (
          <div className="flex flex-col items-center justify-center py-16 gap-3">
            <Loader2 className="w-8 h-8 animate-spin text-violet-400" />
            <p className="text-sm text-slate-500">Loading memories...</p>
          </div>
        )}

        {!isLoading && !error && filtered.length === 0 && (
          <div className="glass-card rounded-xl p-8 text-center">
            <Database className="w-10 h-10 text-slate-700 mx-auto mb-3" />
            <p className="text-sm text-slate-500">No memories found.</p>
          </div>
        )}

        {!isLoading && filtered.map((memory) => (
          <article
            key={memory.id}
            className="group glass-card rounded-xl p-5 hover:border-violet-500/20"
          >
            <p className="text-sm text-slate-200 whitespace-pre-wrap leading-relaxed">{memory.memory}</p>
            <div className="mt-3 pt-3 border-t border-white/[0.05] flex flex-wrap items-center gap-2 text-xs">
              <span className={SENSITIVITY_BADGE[memory.sensitivity ?? 0] || "badge badge-neutral"}>
                <Shield className="w-3 h-3 mr-1" />
                L{memory.sensitivity ?? 0}
              </span>
              {memory.user_id && (
                <span className="badge badge-neutral">
                  <User className="w-3 h-3 mr-1" />
                  {memory.user_id}
                </span>
              )}
              {memory.created_at && (
                <span className="flex items-center gap-1 text-slate-500">
                  <Clock className="w-3 h-3" />
                  {new Date(memory.created_at).toLocaleString()}
                </span>
              )}
              <div className="flex-1" />
              {(memory.tags || []).map((tag) => (
                <span key={`${memory.id}-${tag}`} className="badge badge-neutral">
                  <Tag className="w-3 h-3 mr-1" />
                  {tag}
                </span>
              ))}
            </div>
          </article>
        ))}
      </div>
    </div>
  );
}
