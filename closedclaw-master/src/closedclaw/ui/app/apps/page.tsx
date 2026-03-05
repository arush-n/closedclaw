"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { FeedbackBanner } from "@/components/ui/feedback-banner";
import {
  AppWindow,
  RefreshCw,
  Loader2,
  ChevronRight,
  CheckCircle2,
  CircleX,
} from "lucide-react";

interface OmApp {
  id: string;
  name: string;
  description?: string;
  is_active: boolean;
  memory_count: number;
  memories_accessed: number;
  created_at: string;
  updated_at?: string;
}

const USER_ID = "default-user";

interface AppCardProps {
  app: OmApp;
  onToggle: (id: string) => Promise<void>;
  isTogglingId: string | null;
}

function AppCard({ app, onToggle, isTogglingId }: AppCardProps) {
  const [isOptimisticActive, setIsOptimisticActive] = useState(app.is_active);

  const handleToggle = async (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIsOptimisticActive(!isOptimisticActive);
    try {
      await onToggle(app.id);
    } catch {
      setIsOptimisticActive(app.is_active);
    }
  };

  return (
    <Link
      href={`/apps/${app.id}`}
      className="glass-card rounded-xl p-5 space-y-4 hover:bg-white/[0.06] transition-colors group"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <h3 className="font-semibold text-white group-hover:text-violet-300 transition-colors truncate">
            {app.name}
          </h3>
          {app.description && (
            <p className="text-xs text-slate-400 mt-1 truncate">
              {app.description}
            </p>
          )}
        </div>
        <button
          onClick={handleToggle}
          disabled={isTogglingId === app.id}
          className="flex-shrink-0"
        >
          {isTogglingId === app.id ? (
            <Loader2 className="w-5 h-5 text-slate-500 animate-spin" />
          ) : isOptimisticActive ? (
            <CheckCircle2 className="w-5 h-5 text-emerald-400 hover:text-emerald-300 transition-colors" />
          ) : (
            <CircleX className="w-5 h-5 text-slate-500 hover:text-slate-400 transition-colors" />
          )}
        </button>
      </div>

      <div className="grid grid-cols-2 gap-3 pt-2 border-t border-white/[0.05]">
        <div>
          <div className="text-xs text-slate-400">Memories created</div>
          <div className="text-lg font-semibold text-white">
            {app.memory_count}
          </div>
        </div>
        <div>
          <div className="text-xs text-slate-400">Accessed</div>
          <div className="text-lg font-semibold text-white">
            {app.memories_accessed}
          </div>
        </div>
      </div>

      <div className="flex items-center gap-2 text-slate-500 group-hover:text-violet-400 transition-colors text-xs">
        <span>View details</span>
        <ChevronRight className="w-3 h-3" />
      </div>
    </Link>
  );
}

export default function AppsPage() {
  const [apps, setApps] = useState<OmApp[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [isTogglingId, setIsTogglingId] = useState<string | null>(null);

  const loadApps = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const response = await fetch(
        `/api/openmemory/apps/?user_id=${USER_ID}`,
        { cache: "no-store" }
      );
      if (!response.ok) throw new Error(`Failed to load apps (${response.status})`);
      const data = (await response.json()) as { apps: OmApp[] };
      setApps(data.apps || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load apps");
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    loadApps();
  }, [loadApps]);

  const handleToggle = async (id: string) => {
    setIsTogglingId(id);
    try {
      const app = apps.find((a) => a.id === id);
      if (!app) return;

      const response = await fetch(`/api/openmemory/apps/${id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ is_active: !app.is_active }),
      });

      if (!response.ok) throw new Error("Failed to toggle app");
      setSuccess(`App ${app.is_active ? "paused" : "activated"}`);

      // Update local state
      setApps((prev) =>
        prev.map((a) => (a.id === id ? { ...a, is_active: !a.is_active } : a))
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to toggle app");
    } finally {
      setIsTogglingId(null);
    }
  };

  const stats = {
    totalApps: apps.length,
    activeApps: apps.filter((a) => a.is_active).length,
    totalMemories: apps.reduce((sum, a) => sum + a.memory_count, 0),
    totalAccesses: apps.reduce((sum, a) => sum + a.memories_accessed, 0),
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
            <AppWindow className="w-5 h-5 text-violet-400" />
          </div>
          <div>
            <h1 className="section-title">Apps</h1>
            <p className="text-sm text-slate-500 mt-0.5">
              {stats.totalApps} total apps
            </p>
          </div>
        </div>
        <Button variant="outline" onClick={loadApps} disabled={isLoading}>
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
          { label: "Total apps", value: stats.totalApps },
          { label: "Active", value: stats.activeApps },
          { label: "Total memories", value: stats.totalMemories },
          { label: "Total accesses", value: stats.totalAccesses },
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

      {/* Loading state */}
      {isLoading && apps.length === 0 && (
        <div className="flex items-center justify-center gap-2 py-12 text-slate-400">
          <Loader2 className="w-4 h-4 animate-spin" />
          Loading apps...
        </div>
      )}

      {/* Empty state */}
      {!isLoading && apps.length === 0 && (
        <div className="flex flex-col items-center justify-center py-12 text-center">
          <AppWindow className="w-12 h-12 text-slate-600 mb-3" />
          <p className="text-slate-400">No apps found</p>
        </div>
      )}

      {/* Apps grid */}
      {apps.length > 0 && (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {apps.map((app) => (
            <AppCard
              key={app.id}
              app={app}
              onToggle={handleToggle}
              isTogglingId={isTogglingId}
            />
          ))}
        </div>
      )}
    </div>
  );
}
