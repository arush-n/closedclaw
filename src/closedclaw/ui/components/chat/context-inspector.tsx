"use client";

import { useState, memo, useMemo, useCallback } from "react";
import {
  Eye,
  EyeOff,
  Shield,
  ShieldAlert,
  ShieldCheck,
  FileText,
  ChevronDown,
  ChevronUp,
  ExternalLink,
  Lock,
  Eraser,
  Info,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { motion, AnimatePresence } from "framer-motion";
import type { ClosedclawMessageMetadata, RelatedMemory } from "./types";

interface ContextInspectorProps {
  metadata?: ClosedclawMessageMetadata;
  memories?: RelatedMemory[];
  className?: string;
}

const SENSITIVITY_CONFIG = [
  { level: 0, label: "Public", color: "text-green-400", bg: "bg-green-400/10", border: "border-green-400/30", icon: ShieldCheck },
  { level: 1, label: "General", color: "text-blue-400", bg: "bg-blue-400/10", border: "border-blue-400/30", icon: Shield },
  { level: 2, label: "Personal", color: "text-yellow-400", bg: "bg-yellow-400/10", border: "border-yellow-400/30", icon: ShieldAlert },
  { level: 3, label: "Sensitive", color: "text-red-400", bg: "bg-red-400/10", border: "border-red-400/30", icon: ShieldAlert },
];

const SensitivityBadge = memo(function SensitivityBadge({ level }: { level: number }) {
  const config = SENSITIVITY_CONFIG[Math.min(level, 3)];
  const Icon = config.icon;

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-medium border",
        config.bg,
        config.color,
        config.border
      )}
    >
      <Icon className="size-2.5" />
      {config.label}
    </span>
  );
});

const MemoryInspectorCard = memo(function MemoryInspectorCard({ memory }: { memory: RelatedMemory }) {
  const [expanded, setExpanded] = useState(false);
  const sensitivity = (memory.metadata?.sensitivity as number) ?? 0;
  const tags = (memory.metadata?.tags as string[]) ?? [];
  const encrypted = (memory.metadata?.encrypted as boolean) ?? false;
  const source = (memory.metadata?.source as string) ?? "unknown";
  const scorePercent = useMemo(
    () => (memory.score ? (memory.score * 100).toFixed(1) : null),
    [memory.score]
  );
  const toggleExpanded = useCallback(() => setExpanded((v) => !v), []);

  return (
    <div className="bg-zinc-900/60 border border-zinc-800 rounded-lg overflow-hidden hover:border-zinc-700 transition-colors">
      <button
        type="button"
        onClick={toggleExpanded}
        className="w-full text-left p-2.5 flex items-start gap-2"
      >
        <div className="flex-1 min-w-0">
          <p className="text-xs text-zinc-300 line-clamp-2">{memory.content}</p>
          <div className="flex items-center gap-1.5 mt-1.5 flex-wrap">
            <SensitivityBadge level={sensitivity} />
            {encrypted && (
              <span className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[10px] font-medium bg-purple-400/10 text-purple-400 border border-purple-400/30">
                <Lock className="size-2.5" />
                Encrypted
              </span>
            )}
            {scorePercent && (
              <span className="text-[10px] text-zinc-500">
                {scorePercent}% match
              </span>
            )}
          </div>
        </div>
        {expanded ? (
          <ChevronUp className="size-3.5 text-zinc-500 mt-0.5 shrink-0" />
        ) : (
          <ChevronDown className="size-3.5 text-zinc-500 mt-0.5 shrink-0" />
        )}
      </button>

      <AnimatePresence>
        {expanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.15 }}
            className="overflow-hidden"
          >
            <div className="px-2.5 pb-2.5 space-y-1.5 border-t border-zinc-800 pt-2">
              <div className="flex items-center justify-between text-[10px]">
                <span className="text-zinc-500">Source</span>
                <span className="text-zinc-400 capitalize">{source}</span>
              </div>
              {tags.length > 0 && (
                <div className="flex items-center gap-1 flex-wrap">
                  <span className="text-[10px] text-zinc-500">Tags:</span>
                  {tags.map((tag) => (
                    <span
                      key={tag}
                      className="px-1.5 py-0.5 text-[10px] bg-zinc-800 text-zinc-400 rounded"
                    >
                      {tag}
                    </span>
                  ))}
                </div>
              )}
              {memory.created_at && (
                <div className="flex items-center justify-between text-[10px]">
                  <span className="text-zinc-500">Created</span>
                  <span className="text-zinc-400">
                    {new Date(memory.created_at).toLocaleString()}
                  </span>
                </div>
              )}
              <div className="flex items-center justify-between text-[10px]">
                <span className="text-zinc-500">Memory ID</span>
                <span className="text-zinc-500 font-mono truncate max-w-[120px]">
                  {memory.id}
                </span>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
});

export const ContextInspector = memo(function ContextInspector({
  metadata,
  memories,
  className,
}: ContextInspectorProps) {
  const [isOpen, setIsOpen] = useState(false);
  const toggleOpen = useCallback(() => setIsOpen((v) => !v), []);

  const memoriesUsed = useMemo(
    () => metadata?.closedclaw_memories_used ?? memories?.length ?? 0,
    [metadata?.closedclaw_memories_used, memories?.length]
  );
  const redactionsApplied = metadata?.closedclaw_redactions_applied ?? 0;
  const auditId = metadata?.closedclaw_audit_id;

  // Don't render if no metadata and no memories
  if (!metadata && (!memories || memories.length === 0)) {
    return null;
  }

  return (
    <div className={cn("mt-1", className)}>
      <button
        type="button"
        onClick={toggleOpen}
        className={cn(
          "flex items-center gap-1.5 px-2 py-1 rounded-md text-[11px] font-medium transition-colors",
          isOpen
            ? "bg-primary/10 text-primary border border-primary/30"
            : "text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800/50"
        )}
      >
        {isOpen ? (
          <EyeOff className="size-3" />
        ) : (
          <Eye className="size-3" />
        )}
        <span>Context Inspector</span>
        {memoriesUsed > 0 && (
          <span className="px-1 py-0.5 bg-zinc-800 rounded text-[10px] text-zinc-400">
            {memoriesUsed} memories
          </span>
        )}
        {redactionsApplied > 0 && (
          <span className="px-1 py-0.5 bg-orange-400/10 rounded text-[10px] text-orange-400">
            {redactionsApplied} redacted
          </span>
        )}
      </button>

      <AnimatePresence>
        {isOpen && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden"
          >
            <div className="mt-2 rounded-lg border border-zinc-800 bg-zinc-950/80 p-3 space-y-3">
              {/* Stats Row */}
              <div className="grid grid-cols-3 gap-2">
                <div className="flex flex-col items-center p-2 bg-zinc-900/50 rounded-lg">
                  <FileText className="size-3.5 text-blue-400 mb-1" />
                  <span className="text-sm font-semibold text-zinc-200">
                    {memoriesUsed}
                  </span>
                  <span className="text-[10px] text-zinc-500">Memories</span>
                </div>
                <div className="flex flex-col items-center p-2 bg-zinc-900/50 rounded-lg">
                  <Eraser className="size-3.5 text-orange-400 mb-1" />
                  <span className="text-sm font-semibold text-zinc-200">
                    {redactionsApplied}
                  </span>
                  <span className="text-[10px] text-zinc-500">Redactions</span>
                </div>
                <div className="flex flex-col items-center p-2 bg-zinc-900/50 rounded-lg">
                  <Shield className="size-3.5 text-green-400 mb-1" />
                  <span className="text-sm font-semibold text-zinc-200">
                    {auditId ? "✓" : "—"}
                  </span>
                  <span className="text-[10px] text-zinc-500">Audited</span>
                </div>
              </div>

              {/* Audit Link */}
              {auditId && (
                <a
                  href={`/audit?id=${auditId}`}
                  className="flex items-center gap-1.5 text-[11px] text-primary hover:underline"
                >
                  <ExternalLink className="size-3" />
                  View audit entry
                </a>
              )}

              {/* Retrieved Memories */}
              {memories && memories.length > 0 && (
                <div className="space-y-1.5">
                  <div className="flex items-center gap-1.5 text-[11px] text-zinc-400 font-medium">
                    <Info className="size-3" />
                    Retrieved Memories
                  </div>
                  <div className="space-y-1.5 max-h-48 overflow-y-auto pr-1">
                    {memories.map((mem, idx) => (
                      <MemoryInspectorCard key={mem.id || idx} memory={mem} />
                    ))}
                  </div>
                </div>
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
});
