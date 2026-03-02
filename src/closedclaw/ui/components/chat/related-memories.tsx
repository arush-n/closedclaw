"use client";

import { useState } from "react";
import { ChevronDown, ChevronUp, Sparkles } from "lucide-react";
import { cn } from "@/lib/utils";
import type { RelatedMemory } from "./types";
import { motion, AnimatePresence } from "framer-motion";

interface RelatedMemoriesProps {
  memories: RelatedMemory[];
  isExpanded: boolean;
  onToggle: () => void;
}

export function RelatedMemories({
  memories,
  isExpanded,
  onToggle,
}: RelatedMemoriesProps) {
  if (!memories || memories.length === 0) {
    return null;
  }

  return (
    <div className="mb-3">
      <button
        type="button"
        className="flex items-center gap-2 text-zinc-400 hover:text-zinc-200 transition-colors text-sm font-medium"
        onClick={onToggle}
      >
        <Sparkles className="size-3.5 text-primary" />
        <span>Related memories ({memories.length})</span>
        {isExpanded ? (
          <ChevronUp className="size-3.5" />
        ) : (
          <ChevronDown className="size-3.5" />
        )}
      </button>

      <AnimatePresence>
        {isExpanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden"
          >
            <div className="mt-3 grid grid-cols-1 sm:grid-cols-2 gap-2 max-h-64 overflow-y-auto">
              {memories.map((memory, idx) => (
                <MemoryCard key={memory.id || idx} memory={memory} />
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function MemoryCard({ memory }: { memory: RelatedMemory }) {
  const scorePercent = memory.score ? (memory.score * 100).toFixed(1) : null;

  return (
    <div className="bg-zinc-900/80 rounded-xl border border-zinc-800 overflow-hidden hover:border-zinc-700 transition-colors">
      <div className="p-3">
        <p className="text-xs text-zinc-400 line-clamp-3">{memory.content}</p>
        {memory.created_at && (
          <p className="text-[10px] text-zinc-600 mt-2">
            {new Date(memory.created_at).toLocaleDateString()}
          </p>
        )}
      </div>
      {scorePercent && (
        <div className="px-3 py-2 bg-zinc-950/50 border-t border-zinc-800">
          <span
            className={cn(
              "text-[10px] font-medium inline-block",
              "bg-gradient-to-r from-primary via-purple-400 to-primary bg-clip-text text-transparent"
            )}
          >
            Relevance: {scorePercent}%
          </span>
        </div>
      )}
    </div>
  );
}
