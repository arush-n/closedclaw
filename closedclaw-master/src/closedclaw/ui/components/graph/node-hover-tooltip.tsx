"use client";

import { memo } from "react";
import type { GraphNode, MemoryData } from "./types";

interface NodeHoverTooltipProps {
  node: GraphNode | null;
  x: number;
  y: number;
  containerWidth: number;
  containerHeight: number;
}

function isSecure(memory: MemoryData): boolean {
  return (memory.sensitivity !== undefined && memory.sensitivity >= 2) || memory.encrypted === true;
}

const SENSITIVITY_LABELS: Record<number, string> = {
  0: "Public",
  1: "General",
  2: "Personal",
  3: "Sensitive",
};

function timeAgo(dateString?: string): string {
  if (!dateString) return "";
  const ms = Date.now() - new Date(dateString).getTime();
  const mins = Math.floor(ms / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days}d ago`;
  const months = Math.floor(days / 30);
  return `${months}mo ago`;
}

export const NodeHoverTooltip = memo<NodeHoverTooltipProps>(function NodeHoverTooltip({
  node,
  x,
  y,
  containerWidth,
}) {
  if (!node) return null;

  const memory = node.data;
  const secure = node.type === "memory" && isSecure(memory);

  // Position tooltip: offset from cursor, flip if near edges
  const tooltipWidth = 240;
  const offsetX = 14;
  const offsetY = -10;
  let left = x + offsetX;
  if (left + tooltipWidth > containerWidth - 16) {
    left = x - tooltipWidth - offsetX;
  }
  const top = y + offsetY;

  const preview = secure
    ? "Content hidden (sensitive)"
    : memory.memory.length > 120
    ? memory.memory.slice(0, 120) + "..."
    : memory.memory;

  return (
    <div
      className="absolute z-30 pointer-events-none"
      style={{ left, top, width: tooltipWidth }}
    >
      <div className="bg-zinc-900/95 backdrop-blur-md border border-zinc-700/60 rounded-lg shadow-xl px-3 py-2.5 space-y-1.5">
        {/* Memory preview */}
        <p className={`text-xs leading-relaxed ${secure ? "text-zinc-500 italic" : "text-zinc-200"}`}>
          {preview}
        </p>

        {/* Meta row */}
        <div className="flex items-center gap-2 text-[10px] text-zinc-500">
          {memory.group && (
            <span className="px-1.5 py-0.5 bg-indigo-500/15 border border-indigo-500/25 rounded text-indigo-300">
              {memory.group}
            </span>
          )}
          {memory.sensitivity !== undefined && (
            <span className={secure ? "text-red-400" : "text-emerald-400"}>
              {SENSITIVITY_LABELS[memory.sensitivity] ?? "Unknown"}
            </span>
          )}
          {memory.created_at && (
            <span className="ml-auto">{timeAgo(memory.created_at)}</span>
          )}
        </div>

        {/* User */}
        {node.type === "user" && (
          <p className="text-xs text-zinc-300">{memory.user_id}</p>
        )}
      </div>
    </div>
  );
});

NodeHoverTooltip.displayName = "NodeHoverTooltip";
