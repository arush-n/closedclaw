"use client";

import { memo, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { ChevronDown, ChevronUp } from "lucide-react";
import type { LegendProps, GraphStats } from "./types";

export const Legend = memo<LegendProps>(function Legend({
  stats,
  isExpanded: externalIsExpanded,
  onToggle,
  isLoading = false,
}) {
  const [internalIsExpanded, setInternalIsExpanded] = useState(true);
  const isExpanded = externalIsExpanded ?? internalIsExpanded;

  const handleToggle = () => {
    if (onToggle) {
      onToggle();
    } else {
      setInternalIsExpanded((prev) => !prev);
    }
  };

  const categoryEntries = Object.entries(stats.categories || {}).slice(0, 4);

  return (
    <div className="absolute top-14 right-4 z-10 min-w-[230px] max-w-[270px]">
      <motion.div
        layout
        className="bg-[#060c18]/85 backdrop-blur-xl border border-slate-700/40 rounded-xl overflow-hidden shadow-2xl"
      >
        {/* Header */}
        <button
          onClick={handleToggle}
          className="w-full flex items-center justify-between px-4 py-3 hover:bg-slate-800/30 transition-colors"
        >
          <span className="text-xs font-semibold tracking-wide text-slate-200 uppercase">Legend</span>
          {isExpanded ? (
            <ChevronUp className="w-4 h-4 text-zinc-400" />
          ) : (
            <ChevronDown className="w-4 h-4 text-zinc-400" />
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
              <div className="px-4 pb-4 space-y-5">
                {/* Statistics */}
                {!isLoading && (
                  <div className="space-y-2.5 pt-1">
                    <h4 className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider">
                      Statistics
                    </h4>
                    <div className="space-y-1.5 text-xs">
                      <div className="flex items-center gap-2.5">
                        <span className="h-2 w-2 rounded-full bg-slate-200/90" />
                        <span className="text-slate-200">{stats.totalMemories} memories</span>
                      </div>
                      <div className="flex items-center gap-2.5">
                        <span className="h-2 w-2 rounded-full bg-emerald-300/90" />
                        <span className="text-slate-200">{stats.totalUsers} users</span>
                      </div>
                      <div className="flex items-center gap-2.5">
                        <span className="h-2 w-2 rounded-full bg-indigo-300/90" />
                        <span className="text-slate-200">{stats.totalConnections} connections</span>
                      </div>
                    </div>
                  </div>
                )}

                {/* Node Types */}
                <div className="space-y-2.5 pt-1">
                  <h4 className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider">
                    Nodes
                  </h4>
                  <div className="space-y-1.5 text-xs">
                    <div className="flex items-center gap-2.5">
                      <div className="w-2.5 h-2.5 rounded-full bg-[rgba(241,245,249,0.95)]" />
                      <span className="text-slate-200">Document</span>
                    </div>
                    <div className="flex items-center gap-2.5">
                      <div className="w-3 h-3 rounded-full bg-[rgba(16,185,129,0.92)]" />
                      <span className="text-slate-200">Memory (latest)</span>
                    </div>
                    <div className="flex items-center gap-2.5">
                      <div className="w-2.5 h-2.5 rounded-full bg-[rgba(148,163,184,0.8)]" />
                      <span className="text-slate-200">Memory (older)</span>
                    </div>
                  </div>
                </div>

                {/* Status */}
                <div className="space-y-2.5 pt-1">
                  <h4 className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider">
                    Status
                  </h4>
                  <div className="space-y-1.5 text-xs">
                    <div className="flex items-center gap-2.5">
                      <div className="w-2.5 h-2.5 rounded-full bg-[rgba(248,113,113,0.95)]" />
                      <span className="text-slate-200">Forgotten</span>
                    </div>
                    <div className="flex items-center gap-2.5">
                      <div className="w-2.5 h-2.5 rounded-full bg-[rgba(250,204,21,0.95)]" />
                      <span className="text-slate-200">Expiring soon</span>
                    </div>
                    <div className="flex items-center gap-2.5">
                      <div className="w-2.5 h-2.5 rounded-full bg-[rgba(16,185,129,0.95)]" />
                      <span className="text-slate-200">New memory</span>
                    </div>
                  </div>
                </div>

                {/* Connections */}
                <div className="space-y-2.5 pt-1">
                  <h4 className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider">
                    Connections
                  </h4>
                  <div className="space-y-1.5 text-xs">
                    <div className="flex items-center gap-2.5">
                      <div className="w-6 h-px bg-[rgba(226,232,240,0.65)]" />
                      <span className="text-slate-200">Doc → Memory</span>
                    </div>
                    <div className="flex items-center gap-2.5">
                      <div className="w-6 h-px bg-[rgba(148,163,184,0.48)]" />
                      <span className="text-slate-200">Doc similarity</span>
                    </div>
                    <div className="flex items-center gap-2.5">
                      <div className="w-6 h-px bg-[rgba(129,140,248,0.55)]" />
                      <span className="text-slate-200">Version chain</span>
                    </div>
                  </div>
                </div>

                {/* Groups */}
                {Object.keys(stats.groups || {}).length > 0 && (
                  <div className="space-y-2.5 pt-1">
                    <h4 className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider">
                      Groups
                    </h4>
                    <div className="space-y-1.5 text-xs">
                      {Object.entries(stats.groups)
                        .sort((a, b) => b[1] - a[1])
                        .slice(0, 8)
                        .map(([group, count]) => (
                          <div key={group} className="flex items-center justify-between gap-2.5">
                            <span className="text-slate-300 truncate">{group}</span>
                            <span className="text-slate-500 text-[10px]">{count}</span>
                          </div>
                        ))}
                    </div>
                  </div>
                )}

                {/* Categories (if any) */}
                {categoryEntries.length > 0 && (
                  <div className="space-y-2.5 pt-1">
                    <h4 className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider">
                      Categories
                    </h4>
                    <div className="space-y-1.5 text-xs">
                      {categoryEntries.map(([category, count]) => (
                        <div key={category} className="flex items-center justify-between gap-2.5">
                          <span className="text-slate-300 truncate capitalize">{category}</span>
                          <span className="text-slate-500 text-[10px]">{count}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </motion.div>
    </div>
  );
});

Legend.displayName = "Legend";
