"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { FeedbackBanner } from "@/components/ui/feedback-banner";
import {
  ArrowLeft,
  AppWindow,
  Loader2,
  Clock,
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

interface OmMemory {
  id: string;
  memory: string;
  categories: string[];
  created_at: string;
}

type TabType = "created" | "accessed";

export default function AppDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const [paramId, setParamId] = useState<string | null>(null);

  useEffect(() => {
    params.then((p) => setParamId(p.id));
  }, [params]);

  const [app, setApp] = useState<OmApp | null>(null);
  const [createdMemories, setCreatedMemories] = useState<OmMemory[]>([]);
  const [accessedMemories, setAccessedMemories] = useState<OmMemory[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<TabType>("created");
  const [togglingActive, setTogglingActive] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    if (!paramId) return;
    setLoading(true);
    try {
      const [appRes, createdRes, accessedRes] = await Promise.allSettled([
        fetch(`/api/openmemory/apps/${paramId}`, { cache: "no-store" }),
        fetch(`/api/openmemory/apps/${paramId}/memories`, {
          cache: "no-store",
        }),
        fetch(`/api/openmemory/apps/${paramId}/accessed`, {
          cache: "no-store",
        }),
      ]);

      if (appRes.status === "fulfilled" && appRes.value.ok) {
        const appData = (await appRes.value.json()) as OmApp;
        setApp(appData);
      }

      if (createdRes.status === "fulfilled" && createdRes.value.ok) {
        const createdData = (await createdRes.value.json()) as OmMemory[];
        setCreatedMemories(Array.isArray(createdData) ? createdData : []);
      }

      if (accessedRes.status === "fulfilled" && accessedRes.value.ok) {
        const accessedData = (await accessedRes.value.json()) as OmMemory[];
        setAccessedMemories(Array.isArray(accessedData) ? accessedData : []);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load app data");
    } finally {
      setLoading(false);
    }
  }, [paramId]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleToggleActive = async () => {
    if (!app) return;
    setTogglingActive(true);
    try {
      const response = await fetch(`/api/openmemory/apps/${app.id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ is_active: !app.is_active }),
      });
      if (!response.ok) throw new Error("Failed to toggle");
      const updated = (await response.json()) as OmApp;
      setApp(updated);
      setSuccess(updated.is_active ? "App activated" : "App paused");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to toggle");
    } finally {
      setTogglingActive(false);
    }
  };

  if (loading) {
    return (
      <div className="page-container flex items-center justify-center py-20">
        <div className="flex flex-col items-center gap-3">
          <Loader2 className="w-6 h-6 animate-spin text-violet-400" />
          <p className="text-slate-400">Loading app...</p>
        </div>
      </div>
    );
  }

  if (!app) {
    return (
      <div className="page-container space-y-6">
        <Link
          href="/apps"
          className="flex items-center gap-2 text-violet-400 hover:text-violet-300 transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          Back to apps
        </Link>
        <div className="text-center py-12">
          <p className="text-slate-400">App not found</p>
        </div>
      </div>
    );
  }

  const tabClass = (active: boolean) =>
    active
      ? "px-4 py-2 text-sm font-medium rounded-lg bg-white/[0.08] text-white border border-white/[0.08]"
      : "px-4 py-2 text-sm font-medium rounded-lg text-slate-400 hover:text-slate-200 hover:bg-white/[0.04]";

  const memoriesToShow =
    activeTab === "created" ? createdMemories : accessedMemories;

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

      {/* Back button */}
      <Link
        href="/apps"
        className="flex items-center gap-2 text-violet-400 hover:text-violet-300 transition-colors mb-2"
      >
        <ArrowLeft className="w-4 h-4" />
        Back to apps
      </Link>

      {/* Header card */}
      <div className="glass-card rounded-xl p-6 space-y-4">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h1 className="section-title">{app.name}</h1>
            {app.description && (
              <p className="text-sm text-slate-400 mt-2">{app.description}</p>
            )}
          </div>
          <div className="flex items-center gap-3">
            <div
              className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-sm font-medium ${
                app.is_active
                  ? "bg-emerald-500/15 text-emerald-300"
                  : "bg-slate-500/15 text-slate-300"
              }`}
            >
              {app.is_active ? (
                <CheckCircle2 className="w-4 h-4" />
              ) : (
                <CircleX className="w-4 h-4" />
              )}
              {app.is_active ? "Active" : "Paused"}
            </div>
            <Button
              onClick={handleToggleActive}
              disabled={togglingActive}
              variant="outline"
            >
              {togglingActive ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <AppWindow className="w-4 h-4 mr-1" />
              )}
              Toggle
            </Button>
          </div>
        </div>

        {/* Stats */}
        <div className="grid grid-cols-3 gap-3 pt-4 border-t border-white/[0.05]">
          <div>
            <div className="text-xs text-slate-400">Memories created</div>
            <div className="text-2xl font-bold text-white mt-1">
              {app.memory_count}
            </div>
          </div>
          <div>
            <div className="text-xs text-slate-400">Memories accessed</div>
            <div className="text-2xl font-bold text-white mt-1">
              {app.memories_accessed}
            </div>
          </div>
          <div>
            <div className="text-xs text-slate-400">Created</div>
            <div className="text-xs text-slate-300 mt-1">
              {new Date(app.created_at).toLocaleDateString()}
            </div>
          </div>
        </div>
      </div>

      {/* Tab bar */}
      <div className="flex items-center gap-2">
        <button
          onClick={() => setActiveTab("created")}
          className={tabClass(activeTab === "created")}
        >
          Created ({createdMemories.length})
        </button>
        <button
          onClick={() => setActiveTab("accessed")}
          className={tabClass(activeTab === "accessed")}
        >
          Accessed ({accessedMemories.length})
        </button>
      </div>

      {/* Tab content */}
      <div className="space-y-3">
        {memoriesToShow.length === 0 ? (
          <div className="flex items-center justify-center py-12 text-center">
            <p className="text-slate-400">
              No {activeTab === "created" ? "created" : "accessed"} memories
            </p>
          </div>
        ) : (
          memoriesToShow.map((memory) => (
            <Link
              key={memory.id}
              href={`/memories/${memory.id}`}
              className="glass-card rounded-xl p-4 hover:bg-white/[0.06] transition-colors group block"
            >
              <div className="flex items-start justify-between gap-3">
                <p className="text-white font-medium group-hover:text-violet-300 transition-colors line-clamp-2 flex-1">
                  {memory.memory}
                </p>
              </div>
              <div className="flex flex-wrap gap-2 mt-2">
                {memory.categories?.map((cat) => (
                  <span
                    key={cat}
                    className="badge badge-primary text-xs"
                  >
                    {cat}
                  </span>
                ))}
              </div>
              <div className="flex items-center gap-2 mt-3 text-xs text-slate-400">
                <Clock className="w-3 h-3" />
                {new Date(memory.created_at).toLocaleDateString()}
              </div>
            </Link>
          ))
        )}
      </div>
    </div>
  );
}
