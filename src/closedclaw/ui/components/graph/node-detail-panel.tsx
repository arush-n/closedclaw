"use client";

import { memo, useCallback, useEffect, useRef, useState } from "react";
import { X } from "lucide-react";
import type { GraphNode, MemoryData } from "./types";

interface NodeDetailPanelProps {
  node: GraphNode;
  index: number;
  onClose: () => void;
}

export const NodeDetailPanel = memo<NodeDetailPanelProps>(function NodeDetailPanel({
  node,
  index,
  onClose,
}) {
  const isDragging = useRef(false);
  const dragStart = useRef({ x: 0, y: 0 });
  const posStart = useRef({ x: 0, y: 0 });

  // Stagger panels so they don't stack on top of each other
  const [position, setPosition] = useState(() => ({
    x: 16 + index * 24,
    y: 56 + index * 40,
  }));

  const handleMouseDown = useCallback(
    (e: React.MouseEvent) => {
      isDragging.current = true;
      dragStart.current = { x: e.clientX, y: e.clientY };
      posStart.current = { x: position.x, y: position.y };
      e.preventDefault();
    },
    [position]
  );

  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      if (!isDragging.current) return;
      setPosition({
        x: posStart.current.x + (e.clientX - dragStart.current.x),
        y: posStart.current.y + (e.clientY - dragStart.current.y),
      });
    };
    const handleMouseUp = () => {
      isDragging.current = false;
    };
    window.addEventListener("mousemove", handleMouseMove);
    window.addEventListener("mouseup", handleMouseUp);
    return () => {
      window.removeEventListener("mousemove", handleMouseMove);
      window.removeEventListener("mouseup", handleMouseUp);
    };
  }, []);

  const memory = node.data as MemoryData;

  return (
    <div
      className="absolute z-30 w-72"
      style={{ left: position.x, top: position.y }}
    >
      <div className="bg-zinc-900/90 backdrop-blur-xl border border-zinc-700/60 rounded-lg shadow-2xl p-3">
        {/* Draggable header */}
        <div
          className="flex items-start justify-between gap-2 mb-1.5 cursor-grab active:cursor-grabbing select-none"
          onMouseDown={handleMouseDown}
        >
          <span className="text-[10px] font-medium uppercase tracking-wider text-zinc-500">
            {node.type === "memory" ? "Memory" : "User"}
          </span>
          <button
            onClick={onClose}
            title="Close"
            className="p-0.5 hover:bg-zinc-800 rounded transition-colors -mt-0.5"
            onMouseDown={(e) => e.stopPropagation()}
          >
            <X className="w-3.5 h-3.5 text-zinc-500" />
          </button>
        </div>
        <p className="text-sm text-zinc-200 leading-relaxed">{memory.memory}</p>
        {memory.categories && memory.categories.length > 0 && (
          <div className="flex flex-wrap gap-1 mt-2">
            {memory.categories.map((cat, i) => (
              <span
                key={i}
                className="px-1.5 py-0.5 bg-zinc-800 rounded text-[10px] text-zinc-400"
              >
                {cat}
              </span>
            ))}
          </div>
        )}
        {memory.created_at && (
          <p className="text-[10px] text-zinc-600 mt-2">
            {new Date(memory.created_at).toLocaleDateString(undefined, {
              month: "short",
              day: "numeric",
              year: "numeric",
            })}
          </p>
        )}
      </div>
    </div>
  );
});

NodeDetailPanel.displayName = "NodeDetailPanel";
