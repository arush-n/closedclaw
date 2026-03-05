"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { FeedbackBanner } from "@/components/ui/feedback-banner";
import {
  ArrowLeft,
  Brain,
  Loader2,
  Trash2,
  Edit2,
  Save,
  X,
  GitBranch,
  History,
  AppWindow,
  Calendar,
  Tag,
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

interface OmRelatedMemory {
  id: string;
  memory: string;
  score: number;
  categories: string[];
  created_at: string;
}

interface OmAccessLogEntry {
  id: string;
  memory_id: string;
  app_id: string;
  app_name?: string;
  accessed_at: string;
}

export default function MemoryDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const router = useRouter();
  const [paramId, setParamId] = useState<string | null>(null);

  useEffect(() => {
    params.then((p) => setParamId(p.id));
  }, [params]);

  const [memory, setMemory] = useState<OmMemory | null>(null);
  const [related, setRelated] = useState<OmRelatedMemory[]>([]);
  const [accessLog, setAccessLog] = useState<OmAccessLogEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [isEditing, setIsEditing] = useState(false);
  const [editText, setEditText] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);

  const loadData = useCallback(async () => {
    if (!paramId) return;
    setLoading(true);
    try {
      const [memRes, relRes, logRes] = await Promise.allSettled([
        fetch(`/api/openmemory/memories/${paramId}`, { cache: "no-store" }),
        fetch(`/api/openmemory/memories/${paramId}/related`, {
          cache: "no-store",
        }),
        fetch(`/api/openmemory/memories/${paramId}/access-log`, {
          cache: "no-store",
        }),
      ]);

      if (memRes.status === "fulfilled" && memRes.value.ok) {
        const memData = (await memRes.value.json()) as OmMemory;
        setMemory(memData);
        setEditText(memData.memory);
      } else if (memRes.status === "fulfilled") {
        setError(`Failed to load memory (${memRes.value.status})`);
      }

      if (relRes.status === "fulfilled" && relRes.value.ok) {
        const relData = (await relRes.value.json()) as OmRelatedMemory[];
        setRelated(Array.isArray(relData) ? relData : []);
      }

      if (logRes.status === "fulfilled" && logRes.value.ok) {
        const logData = (await logRes.value.json()) as OmAccessLogEntry[];
        setAccessLog(Array.isArray(logData) ? logData : []);
      }
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to load memory"
      );
    } finally {
      setLoading(false);
    }
  }, [paramId]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleSaveEdit = async () => {
    if (!memory || editText === memory.memory) {
      setIsEditing(false);
      return;
    }
    setSaving(true);
    try {
      const response = await fetch(`/api/openmemory/memories/${memory.id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ memory: editText }),
      });
      if (!response.ok) throw new Error("Failed to save");
      const updated = (await response.json()) as OmMemory;
      setMemory(updated);
      setIsEditing(false);
      setSuccess("Memory updated");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save");
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!memory) return;
    setSaving(true);
    try {
      const response = await fetch("/api/openmemory/memories/", {
        method: "DELETE",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ memory_ids: [memory.id] }),
      });
      if (!response.ok) throw new Error("Failed to delete");
      setSuccess("Memory deleted");
      setTimeout(() => router.push("/memories"), 500);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete");
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="page-container flex items-center justify-center py-20">
        <div className="flex flex-col items-center gap-3">
          <Loader2 className="w-6 h-6 animate-spin text-violet-400" />
          <p className="text-slate-400">Loading memory...</p>
        </div>
      </div>
    );
  }

  if (!memory) {
    return (
      <div className="page-container space-y-6">
        <Link
          href="/memories"
          className="flex items-center gap-2 text-violet-400 hover:text-violet-300 transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          Back to memories
        </Link>
        <div className="text-center py-12">
          <p className="text-slate-400">Memory not found</p>
        </div>
      </div>
    );
  }

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
        href="/memories"
        className="flex items-center gap-2 text-violet-400 hover:text-violet-300 transition-colors mb-2"
      >
        <ArrowLeft className="w-4 h-4" />
        Back to memories
      </Link>

      {/* Header with delete button */}
      <div className="flex items-center justify-between gap-4">
        <h1 className="section-title">Memory Detail</h1>
        {!isEditing && (
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              onClick={() => setIsEditing(true)}
              disabled={saving}
            >
              <Edit2 className="w-4 h-4 mr-1" />
              Edit
            </Button>
            {confirmDelete ? (
              <>
                <Button
                  variant="destructive"
                  onClick={handleDelete}
                  disabled={saving}
                >
                  {saving ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : (
                    <Trash2 className="w-4 h-4 mr-1" />
                  )}
                  Confirm
                </Button>
                <Button
                  variant="outline"
                  onClick={() => setConfirmDelete(false)}
                  disabled={saving}
                >
                  Cancel
                </Button>
              </>
            ) : (
              <Button
                variant="destructive"
                onClick={() => setConfirmDelete(true)}
                disabled={saving}
              >
                <Trash2 className="w-4 h-4 mr-1" />
                Delete
              </Button>
            )}
          </div>
        )}
      </div>

      {/* Main content card */}
      <div className="glass-card rounded-xl p-6 space-y-6">
        {/* Memory text (editable) */}
        <div className="space-y-2">
          {isEditing ? (
            <>
              <label className="text-sm font-semibold text-slate-300">
                Memory text
              </label>
              <textarea
                value={editText}
                onChange={(e) => setEditText(e.target.value)}
                className="glass-input rounded-lg px-4 py-3 text-sm w-full resize-none h-32"
                placeholder="Edit memory text..."
              />
              <div className="flex gap-2 pt-2">
                <Button
                  onClick={handleSaveEdit}
                  disabled={saving}
                >
                  {saving ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : (
                    <Save className="w-4 h-4 mr-1" />
                  )}
                  Save
                </Button>
                <Button
                  variant="outline"
                  onClick={() => {
                    setIsEditing(false);
                    setEditText(memory.memory);
                  }}
                  disabled={saving}
                >
                  <X className="w-4 h-4 mr-1" />
                  Cancel
                </Button>
              </div>
            </>
          ) : (
            <p className="text-white text-base leading-relaxed whitespace-pre-wrap">
              {memory.memory}
            </p>
          )}
        </div>

        {/* Metadata */}
        <div className="pt-4 border-t border-white/[0.05] space-y-3">
          <div className="text-xs text-slate-500 uppercase tracking-wide">
            Metadata
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {/* Categories */}
            <div>
              <div className="text-xs text-slate-400 mb-2 flex items-center gap-1">
                <Tag className="w-3 h-3" />
                Categories
              </div>
              <div className="flex flex-wrap gap-2">
                {memory.categories && memory.categories.length > 0 ? (
                  memory.categories.map((cat) => (
                    <span
                      key={cat}
                      className="badge badge-primary text-xs"
                    >
                      {cat}
                    </span>
                  ))
                ) : (
                  <span className="text-xs text-slate-500">None</span>
                )}
              </div>
            </div>

            {/* App */}
            {memory.app_name && (
              <div>
                <div className="text-xs text-slate-400 mb-2 flex items-center gap-1">
                  <AppWindow className="w-3 h-3" />
                  Source app
                </div>
                <span className="badge badge-neutral text-xs">
                  {memory.app_name}
                </span>
              </div>
            )}

            {/* State */}
            {memory.state && memory.state !== "active" && (
              <div>
                <div className="text-xs text-slate-400 mb-2">State</div>
                <span
                  className={`badge badge-${memory.state === "archived" ? "warning" : "neutral"} text-xs`}
                >
                  {memory.state}
                </span>
              </div>
            )}

            {/* Created at */}
            <div>
              <div className="text-xs text-slate-400 mb-2 flex items-center gap-1">
                <Calendar className="w-3 h-3" />
                Created
              </div>
              <div className="text-xs text-slate-300">
                {new Date(memory.created_at).toLocaleString()}
              </div>
            </div>

            {/* Updated at */}
            {memory.updated_at && memory.updated_at !== memory.created_at && (
              <div>
                <div className="text-xs text-slate-400 mb-2">Updated</div>
                <div className="text-xs text-slate-300">
                  {new Date(memory.updated_at).toLocaleString()}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Related memories */}
      {related && related.length > 0 && (
        <div className="glass-card rounded-xl p-6 space-y-4">
          <div className="flex items-center gap-2">
            <GitBranch className="w-5 h-5 text-violet-400" />
            <h2 className="text-sm font-semibold text-slate-200">
              Related Memories
            </h2>
          </div>
          <div className="space-y-2">
            {related.map((rel) => (
              <Link
                key={rel.id}
                href={`/memories/${rel.id}`}
                className="block glass-subtle rounded-lg p-3 hover:bg-white/[0.08] transition-colors group"
              >
                <div className="flex items-start justify-between gap-2">
                  <p className="text-sm text-slate-300 group-hover:text-white transition-colors line-clamp-2 flex-1">
                    {rel.memory}
                  </p>
                  <span className="text-xs text-violet-400 font-semibold flex-shrink-0">
                    {Math.round(rel.score * 100)}%
                  </span>
                </div>
                {rel.categories && rel.categories.length > 0 && (
                  <div className="flex flex-wrap gap-1 mt-2">
                    {rel.categories.map((cat) => (
                      <span
                        key={cat}
                        className="badge badge-primary text-xs"
                      >
                        {cat}
                      </span>
                    ))}
                  </div>
                )}
              </Link>
            ))}
          </div>
        </div>
      )}

      {/* Access log */}
      {accessLog && accessLog.length > 0 && (
        <div className="glass-card rounded-xl p-6 space-y-4">
          <div className="flex items-center gap-2">
            <History className="w-5 h-5 text-violet-400" />
            <h2 className="text-sm font-semibold text-slate-200">
              Access History
            </h2>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-white/[0.05]">
                  <th className="text-left px-3 py-2 text-xs text-slate-400 font-semibold">
                    App
                  </th>
                  <th className="text-left px-3 py-2 text-xs text-slate-400 font-semibold">
                    Accessed at
                  </th>
                </tr>
              </thead>
              <tbody>
                {accessLog.map((entry) => (
                  <tr
                    key={entry.id}
                    className="border-b border-white/[0.05] hover:bg-white/[0.02]"
                  >
                    <td className="px-3 py-2 text-slate-300">
                      {entry.app_name || entry.app_id}
                    </td>
                    <td className="px-3 py-2 text-slate-400">
                      {new Date(entry.accessed_at).toLocaleString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
