"use client";

import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Brain, Shield, Eye, Sparkles, CheckCircle2 } from "lucide-react";

interface Step {
  id: string;
  label: string;
  detail: string;
  icon: React.ElementType;
  durationMs: number;
}

const PIPELINE_STEPS: Step[] = [
  {
    id: "retrieve",
    label: "Searching memories",
    detail: "Semantic search across your memory vault",
    icon: Brain,
    durationMs: 1200,
  },
  {
    id: "privacy",
    label: "Applying privacy filters",
    detail: "Checking sensitivity levels and access policies",
    icon: Shield,
    durationMs: 900,
  },
  {
    id: "audit",
    label: "Verifying permissions",
    detail: "Governance firewall and consent check",
    icon: Eye,
    durationMs: 700,
  },
  {
    id: "generate",
    label: "Generating response",
    detail: "Building context-aware answer",
    icon: Sparkles,
    durationMs: 999_999, // stays active until response arrives
  },
];

interface ThinkingStepsProps {
  isVisible: boolean;
}

export function ThinkingSteps({ isVisible }: ThinkingStepsProps) {
  const [completedIds, setCompletedIds] = useState<Set<string>>(new Set());
  const [activeIndex, setActiveIndex] = useState(0);

  // Advance through steps based on their durations
  useEffect(() => {
    if (!isVisible) {
      setCompletedIds(new Set());
      setActiveIndex(0);
      return;
    }

    let elapsed = 0;
    const timers: ReturnType<typeof setTimeout>[] = [];

    PIPELINE_STEPS.forEach((step, idx) => {
      if (idx === PIPELINE_STEPS.length - 1) return; // last step stays active
      const delay = elapsed + step.durationMs;
      elapsed = delay;
      timers.push(
        setTimeout(() => {
          setCompletedIds((prev) => new Set([...prev, step.id]));
          setActiveIndex(idx + 1);
        }, delay)
      );
    });

    return () => timers.forEach(clearTimeout);
  }, [isVisible]);

  if (!isVisible) return null;

  return (
    <motion.div
      initial={{ opacity: 0, height: 0 }}
      animate={{ opacity: 1, height: "auto" }}
      exit={{ opacity: 0, height: 0 }}
      transition={{ duration: 0.2 }}
      className="mb-3 overflow-hidden"
    >
      <div className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-3 space-y-1">
        <p className="text-[11px] font-medium text-slate-500 uppercase tracking-wider mb-2 px-1">
          Agent pipeline
        </p>
        {PIPELINE_STEPS.map((step, idx) => {
          const Icon = step.icon;
          const isDone = completedIds.has(step.id);
          const isActive = activeIndex === idx && !isDone;

          return (
            <motion.div
              key={step.id}
              initial={{ opacity: 0, x: -8 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: idx * 0.08, duration: 0.2 }}
              className={`flex items-center gap-2.5 rounded-lg px-2.5 py-1.5 transition-colors ${
                isActive
                  ? "bg-violet-500/10 border border-violet-500/20"
                  : isDone
                  ? "opacity-50"
                  : "opacity-30"
              }`}
            >
              {/* Icon */}
              <div className="shrink-0 relative">
                {isDone ? (
                  <CheckCircle2 className="size-3.5 text-green-400" />
                ) : isActive ? (
                  <>
                    <Icon className="size-3.5 text-violet-400" />
                    {/* Pulsing ring */}
                    <span className="absolute inset-0 animate-ping rounded-full bg-violet-400/30" />
                  </>
                ) : (
                  <Icon className="size-3.5 text-slate-600" />
                )}
              </div>

              {/* Text */}
              <div className="min-w-0 flex-1">
                <span
                  className={`text-xs font-medium ${
                    isActive
                      ? "text-violet-300"
                      : isDone
                      ? "text-slate-400"
                      : "text-slate-600"
                  }`}
                >
                  {step.label}
                </span>
                <AnimatePresence>
                  {isActive && (
                    <motion.p
                      initial={{ opacity: 0, height: 0 }}
                      animate={{ opacity: 1, height: "auto" }}
                      exit={{ opacity: 0, height: 0 }}
                      className="text-[11px] text-slate-500 mt-0.5"
                    >
                      {step.detail}
                    </motion.p>
                  )}
                </AnimatePresence>
              </div>

              {/* Active typing dots */}
              {isActive && (
                <div className="flex gap-0.5 shrink-0">
                  {[0, 1, 2].map((i) => (
                    <span
                      key={i}
                      className="size-1 rounded-full bg-violet-400 animate-bounce"
                      style={{ animationDelay: `${i * 150}ms` }}
                    />
                  ))}
                </div>
              )}
            </motion.div>
          );
        })}
      </div>
    </motion.div>
  );
}
