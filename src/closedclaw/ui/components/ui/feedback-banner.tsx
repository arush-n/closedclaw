"use client";

import { cn } from "@/lib/utils";
import { CheckCircle2, AlertCircle, Info, X } from "lucide-react";

interface FeedbackBannerProps {
  message: string;
  variant?: "success" | "error" | "info";
  onClose?: () => void;
}

const ICON_MAP = {
  success: CheckCircle2,
  error: AlertCircle,
  info: Info,
};

export function FeedbackBanner({ message, variant = "info", onClose }: FeedbackBannerProps) {
  const Icon = ICON_MAP[variant];
  const sharedClassName = cn(
    "rounded-xl border px-4 py-3 text-sm flex items-center justify-between gap-3 animate-fadeIn backdrop-blur-md",
    variant === "success" && "border-emerald-500/20 bg-emerald-500/[0.06] text-emerald-300",
    variant === "error" && "border-red-500/20 bg-red-500/[0.06] text-red-300",
    variant === "info" && "border-white/[0.08] bg-white/[0.03] text-slate-200"
  );

  return (
    <div className={sharedClassName} role={variant === "error" ? "alert" : "status"}>
      <div className="flex items-center gap-2.5">
        <Icon className="w-4 h-4 shrink-0" />
        <span>{message}</span>
      </div>
      {onClose && (
        <button
          type="button"
          onClick={onClose}
          className="p-1 rounded-lg hover:bg-white/[0.08] text-slate-400 hover:text-slate-200 transition-colors"
        >
          <X className="w-3.5 h-3.5" />
        </button>
      )}
    </div>
  );
}
