"use client";

import { memo } from "react";
import { motion } from "framer-motion";
import { ZoomIn, ZoomOut, Maximize, RotateCcw } from "lucide-react";
import type { NavigationControlsProps } from "./types";

export const NavigationControls = memo<NavigationControlsProps>(function NavigationControls({
  onZoomIn,
  onZoomOut,
  onFitToView,
  onResetView,
  zoom,
  minZoom = 0.1,
  maxZoom = 3,
}) {
  const zoomPercent = Math.round(zoom * 100);

  return (
    <div className="absolute bottom-4 left-4 z-20 flex flex-col gap-1">
      <motion.div
        initial={{ opacity: 0, x: -20 }}
        animate={{ opacity: 1, x: 0 }}
        className="bg-slate-950/75 backdrop-blur-xl border border-slate-700/50 rounded-xl overflow-hidden shadow-xl"
      >
        {/* Zoom controls */}
        <div className="flex flex-col">
          <button
            onClick={onZoomIn}
            disabled={zoom >= maxZoom}
            className="p-2 hover:bg-slate-800/40 transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
            title="Zoom in"
          >
            <ZoomIn className="w-3.5 h-3.5 text-slate-300" />
          </button>
          
          <div className="px-2 py-1 text-center text-[10px] text-slate-500 border-y border-slate-700/50">
            {zoomPercent}%
          </div>
          
          <button
            onClick={onZoomOut}
            disabled={zoom <= minZoom}
            className="p-2 hover:bg-slate-800/40 transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
            title="Zoom out"
          >
            <ZoomOut className="w-3.5 h-3.5 text-slate-300" />
          </button>
        </div>

        <div className="border-t border-slate-700/50">
          <button
            onClick={onFitToView}
            className="p-2 w-full hover:bg-slate-800/40 transition-colors"
            title="Fit to view"
          >
            <Maximize className="w-3.5 h-3.5 text-slate-300 mx-auto" />
          </button>
        </div>

        <div className="border-t border-slate-700/50">
          <button
            onClick={onResetView}
            className="p-2 w-full hover:bg-slate-800/40 transition-colors"
            title="Reset view"
          >
            <RotateCcw className="w-3.5 h-3.5 text-slate-300 mx-auto" />
          </button>
        </div>
      </motion.div>
    </div>
  );
});

NavigationControls.displayName = "NavigationControls";
