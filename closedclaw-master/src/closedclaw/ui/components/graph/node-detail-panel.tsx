"use client";

import { memo, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { X, Copy, Clock, Tag, User, Shield, ShieldAlert, Lock } from "lucide-react";
import type { GraphNode, MemoryData } from "./types";

interface NodeDetailPanelProps {
  node: GraphNode | null;
  onClose: () => void;
}

const SENSITIVITY_LABELS: Record<number, { label: string; color: string }> = {
  0: { label: "Public", color: "text-emerald-400" },
  1: { label: "General", color: "text-blue-400" },
  2: { label: "Personal", color: "text-amber-400" },
  3: { label: "Sensitive", color: "text-red-400" },
};

function isMemorySecure(memory: MemoryData): boolean {
  return (memory.sensitivity !== undefined && memory.sensitivity >= 2) || memory.encrypted === true;
}

export const NodeDetailPanel = memo<NodeDetailPanelProps>(function NodeDetailPanel({
  node,
  onClose,
}) {
  const [copied, setCopied] = useState(false);

  if (!node) return null;

  const memory = node.data as MemoryData;
  const indicatorClass = node.type === "memory" ? "bg-emerald-400" : "bg-slate-300";
  const secure = node.type === "memory" && isMemorySecure(memory);
  const sensitivityInfo = SENSITIVITY_LABELS[memory.sensitivity ?? 1] ?? SENSITIVITY_LABELS[1];

  const handleCopy = async () => {
    if (secure) return;
    try {
      await navigator.clipboard.writeText(memory.memory);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.error("Failed to copy:", err);
    }
  };

  const formatDate = (dateString?: string) => {
    if (!dateString) return "Unknown";
    const date = new Date(dateString);
    return date.toLocaleDateString(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  };

  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0, x: 20 }}
        animate={{ opacity: 1, x: 0 }}
        exit={{ opacity: 0, x: 20 }}
        className="absolute top-4 left-4 z-20 w-80 max-h-[calc(100%-2rem)]"
      >
        <div className="bg-zinc-900/90 backdrop-blur-xl border border-zinc-800 rounded-xl shadow-2xl overflow-hidden">
          {/* Header */}
          <div className="flex items-center justify-between px-4 py-3 border-b border-zinc-800">
            <div className="flex items-center gap-2">
              <div
                className={`w-3 h-3 rounded-full ${indicatorClass}`}
              />
              <span className="text-sm font-medium text-zinc-200">
                {node.type === "memory" ? "Memory" : "User"}
              </span>
              {node.type === "memory" && (
                <span className={`text-xs ${sensitivityInfo.color}`}>
                  {secure ? (
                    <ShieldAlert className="w-3.5 h-3.5 inline-block" />
                  ) : (
                    <Shield className="w-3.5 h-3.5 inline-block" />
                  )}
                </span>
              )}
            </div>
            <button
              onClick={onClose}
              title="Close panel"
              className="p-1 hover:bg-zinc-800 rounded transition-colors"
            >
              <X className="w-4 h-4 text-zinc-400" />
            </button>
          </div>

          {/* Content */}
          <div className="p-4 space-y-4 overflow-y-auto max-h-[400px]">
            {/* Security badge */}
            {node.type === "memory" && memory.sensitivity !== undefined && (
              <div className={`flex items-center gap-2 px-3 py-2 rounded-lg ${
                secure ? "bg-red-950/40 border border-red-900/40" : "bg-emerald-950/30 border border-emerald-900/30"
              }`}>
                {secure ? (
                  <Lock className="w-3.5 h-3.5 text-red-400 shrink-0" />
                ) : (
                  <Shield className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
                )}
                <span className={`text-xs ${secure ? "text-red-300" : "text-emerald-300"}`}>
                  {sensitivityInfo.label}
                  {memory.encrypted && " · Encrypted"}
                </span>
              </div>
            )}

            {/* Memory text - only show if not secure */}
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <h4 className="text-xs font-semibold text-zinc-500 uppercase tracking-wider">
                  Content
                </h4>
                {!secure && (
                  <button
                    onClick={handleCopy}
                    className="p-1 hover:bg-zinc-800 rounded transition-colors"
                    title="Copy to clipboard"
                  >
                    <Copy className="w-3.5 h-3.5 text-zinc-400" />
                  </button>
                )}
              </div>
              {secure ? (
                <div className="flex items-center gap-2 py-3 px-3 bg-zinc-800/50 rounded-lg border border-zinc-700/50">
                  <Lock className="w-4 h-4 text-zinc-500" />
                  <p className="text-sm text-zinc-500 italic">
                    Content hidden — sensitivity level {memory.sensitivity}
                    {memory.encrypted && " (encrypted)"}
                  </p>
                </div>
              ) : (
                <p className="text-sm text-zinc-300 leading-relaxed">
                  {memory.memory}
                </p>
              )}
              {copied && (
                <span className="text-xs text-emerald-400">Copied!</span>
              )}
            </div>

            {/* Group label */}
            {memory.group && (
              <div className="space-y-1">
                <h4 className="text-xs font-semibold text-zinc-500 uppercase tracking-wider">
                  Group
                </h4>
                <span className="inline-block px-2.5 py-1 bg-indigo-500/15 border border-indigo-500/30 rounded-md text-xs text-indigo-300 capitalize">
                  {memory.group}
                </span>
              </div>
            )}

            {/* Metadata */}
            <div className="space-y-2">
              <h4 className="text-xs font-semibold text-zinc-500 uppercase tracking-wider">
                Details
              </h4>
              <div className="space-y-2 text-sm">
                {memory.user_id && (
                  <div className="flex items-center gap-2 text-zinc-400">
                    <User className="w-3.5 h-3.5" />
                    <span className="truncate">{memory.user_id}</span>
                  </div>
                )}
                {memory.created_at && (
                  <div className="flex items-center gap-2 text-zinc-400">
                    <Clock className="w-3.5 h-3.5" />
                    <span>{formatDate(memory.created_at)}</span>
                  </div>
                )}
                {memory.categories && memory.categories.length > 0 && (
                  <div className="flex items-start gap-2 text-zinc-400">
                    <Tag className="w-3.5 h-3.5 mt-0.5" />
                    <div className="flex flex-wrap gap-1">
                      {memory.categories.map((cat, i) => (
                        <span
                          key={i}
                          className="px-2 py-0.5 bg-zinc-800 rounded text-xs text-zinc-300"
                        >
                          {cat}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>

            {/* Score if available */}
            {memory.score !== undefined && (
              <div className="space-y-2">
                <h4 className="text-xs font-semibold text-zinc-500 uppercase tracking-wider">
                  Relevance Score
                </h4>
                <div className="relative h-2 bg-zinc-800 rounded-full overflow-hidden">
                  <motion.div
                    initial={{ width: 0 }}
                    animate={{ width: `${memory.score * 100}%` }}
                    className="absolute inset-y-0 left-0 bg-gradient-to-r from-blue-500 to-cyan-400 rounded-full"
                  />
                </div>
                <span className="text-xs text-zinc-400">
                  {(memory.score * 100).toFixed(1)}%
                </span>
              </div>
            )}

            {/* ID */}
            <div className="pt-2 border-t border-zinc-800">
              <span className="text-xs text-zinc-600 font-mono break-all">
                {memory.id}
              </span>
            </div>
          </div>
        </div>
      </motion.div>
    </AnimatePresence>
  );
});

NodeDetailPanel.displayName = "NodeDetailPanel";
