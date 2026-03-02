"use client";

import { useState, useCallback, useEffect } from "react";
import {
  Brain,
  TrendingUp,
  AlertTriangle,
  Clock,
  Play,
  Loader2,
  RefreshCw,
  ChevronDown,
  ChevronUp,
  ArrowLeft,
  Tag,
  Shield,
  CalendarClock,
} from "lucide-react";
import ReactMarkdown from "react-markdown";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface TrendItem {
  topic: string;
  count: number;
  tags: string[];
  first_seen?: string;
  last_seen?: string;
  description?: string;
  memory_ids: string[];
}

interface ContradictionAlert {
  alert_id: string;
  memory_a_id: string;
  memory_a_text: string;
  memory_b_id: string;
  memory_b_text: string;
  explanation: string;
  severity: string;
  resolved: boolean;
}

interface ExpiringMemory {
  memory_id: string;
  content: string;
  tags: string[];
  sensitivity: number;
  expires_at: string;
  days_remaining: number;
  created_at?: string;
}

interface InsightResult {
  run_id: string;
  timestamp: string;
  life_summary?: string;
  trends: TrendItem[];
  contradictions: ContradictionAlert[];
  expiring_memories: ExpiringMemory[];
  memories_analyzed: number;
  model_used: string;
  duration_seconds: number;
  errors: string[];
}

// ---------------------------------------------------------------------------
// Sensitivity badge colors
// ---------------------------------------------------------------------------

const SENSITIVITY_COLORS: Record<number, string> = {
  0: "bg-emerald-500/20 text-emerald-300 border-emerald-500/30",
  1: "bg-blue-500/20 text-blue-300 border-blue-500/30",
  2: "bg-amber-500/20 text-amber-300 border-amber-500/30",
  3: "bg-red-500/20 text-red-300 border-red-500/30",
};

const SEVERITY_COLORS: Record<string, string> = {
  low: "bg-blue-500/20 text-blue-300",
  medium: "bg-amber-500/20 text-amber-300",
  high: "bg-red-500/20 text-red-300",
};

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function SectionHeader({
  icon: Icon,
  title,
  count,
  open,
  onToggle,
}: {
  icon: React.ElementType;
  title: string;
  count?: number;
  open: boolean;
  onToggle: () => void;
}) {
  return (
    <button
      onClick={onToggle}
      className="w-full flex items-center justify-between py-3 px-4 rounded-xl glass-card hover:border-violet-500/20 transition-all"
    >
      <div className="flex items-center gap-2.5 text-slate-100 font-medium text-sm">
        <div className="p-1.5 rounded-lg bg-violet-500/10 border border-violet-500/20">
          <Icon className="w-3.5 h-3.5 text-violet-400" />
        </div>
        {title}
        {count !== undefined && (
          <span className="badge badge-neutral text-[10px]">{count}</span>
        )}
      </div>
      {open ? (
        <ChevronUp className="w-4 h-4 text-slate-500" />
      ) : (
        <ChevronDown className="w-4 h-4 text-slate-500" />
      )}
    </button>
  );
}

function LifeSummarySection({ summary }: { summary: string }) {
  return (
    <div className="prose-chat px-5 py-4 glass-card rounded-xl max-h-[28rem] overflow-y-auto">
      <ReactMarkdown>{summary}</ReactMarkdown>
    </div>
  );
}

function TrendCard({ trend }: { trend: TrendItem }) {
  return (
    <div className="glass-card rounded-xl p-4 hover:border-violet-500/20 transition-all group">
      <div className="flex items-center justify-between mb-2">
        <span className="font-medium text-sm text-slate-100 capitalize">
          {trend.topic}
        </span>
        <span className="badge badge-primary text-[10px]">{trend.count}x</span>
      </div>
      {trend.description && (
        <p className="text-xs text-slate-400 mb-2.5 line-clamp-2 leading-relaxed">
          {trend.description}
        </p>
      )}
      {trend.tags.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {trend.tags.map((tag) => (
            <span
              key={tag}
              className="badge badge-neutral text-[10px]"
            >
              <Tag className="w-2.5 h-2.5 mr-0.5" />
              {tag}
            </span>
          ))}
        </div>
      )}
      {(trend.first_seen || trend.last_seen) && (
        <div className="mt-2.5 flex items-center gap-3 text-[10px] text-slate-500">
          {trend.first_seen && (
            <span>First: {new Date(trend.first_seen).toLocaleDateString()}</span>
          )}
          {trend.last_seen && (
            <span>Latest: {new Date(trend.last_seen).toLocaleDateString()}</span>
          )}
        </div>
      )}
    </div>
  );
}

function ContradictionCard({ alert }: { alert: ContradictionAlert }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className="glass-card rounded-xl p-4">
      <div className="flex items-center justify-between mb-2">
        <span
          className={`badge text-[10px] ${
            alert.severity === "high" ? "badge-danger" :
            alert.severity === "medium" ? "badge-warning" : "badge-primary"
          }`}
        >
          {alert.severity}
        </span>
        <button
          onClick={() => setExpanded(!expanded)}
          className="text-xs text-slate-500 hover:text-slate-300 transition-colors px-2 py-0.5 rounded hover:bg-white/[0.05]"
        >
          {expanded ? "Less" : "Details"}
        </button>
      </div>
      <p className="text-xs text-slate-300 mb-2 leading-relaxed">{alert.explanation}</p>
      {expanded && (
        <div className="space-y-2 mt-3 pt-3 border-t border-white/[0.06]">
          <div className="p-3 rounded-lg bg-white/[0.02] border border-white/[0.05]">
            <span className="text-[10px] text-slate-500 block mb-1">Memory A</span>
            <p className="text-xs text-slate-300 line-clamp-3">{alert.memory_a_text}</p>
          </div>
          <div className="p-3 rounded-lg bg-white/[0.02] border border-white/[0.05]">
            <span className="text-[10px] text-slate-500 block mb-1">Memory B</span>
            <p className="text-xs text-slate-300 line-clamp-3">{alert.memory_b_text}</p>
          </div>
        </div>
      )}
    </div>
  );
}

function ExpiringMemoryCard({
  mem,
  onExtend,
}: {
  mem: ExpiringMemory;
  onExtend: (id: string) => void;
}) {
  return (
    <div className="glass-card rounded-xl p-4 flex items-start gap-3 group">
      <div className="flex-1 min-w-0">
        <p className="text-xs text-slate-300 line-clamp-2 mb-2 leading-relaxed">{mem.content}</p>
        <div className="flex items-center gap-2 flex-wrap">
          <span
            className={`badge text-[10px] ${
              SENSITIVITY_COLORS[mem.sensitivity]
                ? (mem.sensitivity === 0 ? "badge-success" : mem.sensitivity === 1 ? "badge-primary" : mem.sensitivity === 2 ? "badge-warning" : "badge-danger")
                : "badge-neutral"
            }`}
          >
            <Shield className="w-2.5 h-2.5 mr-0.5" />L{mem.sensitivity}
          </span>
          <span
            className={`badge text-[10px] ${
              mem.days_remaining <= 7 ? "badge-danger" : "badge-warning"
            }`}
          >
            <CalendarClock className="w-2.5 h-2.5 mr-0.5" />
            {mem.days_remaining}d left
          </span>
          {mem.tags.map((tag) => (
            <span key={tag} className="badge badge-neutral text-[10px]">{tag}</span>
          ))}
        </div>
      </div>
      <button
        onClick={() => onExtend(mem.memory_id)}
        className="px-3 py-1.5 rounded-lg bg-violet-500/10 hover:bg-violet-500/20 border border-violet-500/20 text-violet-300 text-xs font-medium transition-all whitespace-nowrap hover:scale-105"
      >
        +30d
      </button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export default function InsightsPage() {
  const [result, setResult] = useState<InsightResult | null>(null);
  const [status, setStatus] = useState<"idle" | "loading" | "done" | "error">("idle");
  const [errorMsg, setErrorMsg] = useState<string>("");

  // Section toggle state
  const [openSummary, setOpenSummary] = useState(true);
  const [openTrends, setOpenTrends] = useState(true);
  const [openContradictions, setOpenContradictions] = useState(true);
  const [openExpiring, setOpenExpiring] = useState(true);

  // Run options
  const [weeks, setWeeks] = useState(4);
  const [sensitivityMax, setSensitivityMax] = useState(2);

  const runInsights = useCallback(async () => {
    setStatus("loading");
    setErrorMsg("");
    try {
      const res = await fetch("/api/insights", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          weeks,
          sensitivity_max: sensitivityMax,
        }),
      });
      const data = await res.json();
      if (data.success && data.result) {
        setResult(data.result);
        setStatus("done");
      } else if (data.status === "running") {
        setErrorMsg("Analysis already in progress. Please wait.");
        setStatus("idle");
      } else {
        setErrorMsg(data.error || data.message || "Unknown error");
        setStatus("error");
      }
    } catch (err) {
      setErrorMsg(String(err));
      setStatus("error");
    }
  }, [weeks, sensitivityMax]);

  const loadLatest = useCallback(async () => {
    try {
      const res = await fetch("/api/insights");
      const data = await res.json();
      if (data.success && data.result) {
        setResult(data.result);
        setStatus("done");
      }
    } catch {
      // silently fail initial load
    }
  }, []);

  // Load latest on mount
  useEffect(() => {
    loadLatest();
  }, [loadLatest]);

  const handleExtend = async (memoryId: string) => {
    try {
      await fetch(`/api/insights/expiring/${memoryId}/extend`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ days: 30 }),
      });
      // Refresh expiring list
      if (result) {
        setResult({
          ...result,
          expiring_memories: result.expiring_memories.filter(
            (m) => m.memory_id !== memoryId
          ),
        });
      }
    } catch {
      // silent fail
    }
  };

  return (
    <div className="animate-fadeIn">
      {/* Header */}
      <header className="page-header">
        <div className="max-w-4xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <a
              href="/graph"
              title="Back to graph"
              className="p-1.5 rounded-lg hover:bg-white/[0.06] text-slate-400 hover:text-slate-200 transition-colors"
            >
              <ArrowLeft className="w-4 h-4" />
            </a>
            <div className="flex items-center gap-2.5">
              <div className="p-2 rounded-lg bg-violet-500/10 border border-violet-500/20">
                <Brain className="w-4 h-4 text-violet-400" />
              </div>
              <h1 className="text-lg font-semibold text-slate-100">Insights</h1>
            </div>
          </div>

          <div className="flex items-center gap-2">
            {/* Run options */}
            <div className="hidden sm:flex items-center gap-2 mr-2">
              <label className="text-xs text-slate-500">Weeks:</label>
              <select
                value={weeks}
                onChange={(e) => setWeeks(Number(e.target.value))}
                aria-label="Weeks of history"
                className="glass-input rounded-lg text-xs px-2 py-1.5"
              >
                {[1, 2, 4, 8, 12, 26, 52].map((w) => (
                  <option key={w} value={w}>{w}</option>
                ))}
              </select>
              <label className="text-xs text-slate-500 ml-1">Max Level:</label>
              <select
                value={sensitivityMax}
                onChange={(e) => setSensitivityMax(Number(e.target.value))}
                aria-label="Max sensitivity level"
                className="glass-input rounded-lg text-xs px-2 py-1.5"
              >
                {[0, 1, 2, 3].map((l) => (
                  <option key={l} value={l}>L{l}</option>
                ))}
              </select>
            </div>

            <button
              onClick={runInsights}
              disabled={status === "loading"}
              className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-violet-500/15 hover:bg-violet-500/25 text-violet-300 text-xs font-medium transition-all disabled:opacity-50 disabled:cursor-not-allowed border border-violet-500/25 hover:scale-[1.02]"
            >
              {status === "loading" ? (
                <>
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  Running...
                </>
              ) : (
                <>
                  <Play className="w-3.5 h-3.5" />
                  Run Insights
                </>
              )}
            </button>
          </div>
        </div>
      </header>

      {/* Content */}
      <main className="max-w-4xl mx-auto px-6 py-6 space-y-5">
        {/* Status bar */}
        {status === "error" && (
          <div className="glass-card rounded-xl p-4 border-red-500/20 bg-red-500/[0.03]">
            <p className="text-xs text-red-300">{errorMsg}</p>
          </div>
        )}

        {status === "loading" && (
          <div className="flex flex-col items-center justify-center py-24 gap-4">
            <div className="p-4 rounded-2xl bg-violet-500/10 border border-violet-500/20">
              <Loader2 className="w-8 h-8 animate-spin text-violet-400" />
            </div>
            <p className="text-slate-400 text-sm">Analyzing memories with local LLM...</p>
            <p className="text-slate-600 text-xs">
              This may take a minute depending on your hardware.
            </p>
          </div>
        )}

        {status === "idle" && !result && (
          <div className="flex flex-col items-center justify-center py-24 gap-4">
            <div className="p-4 rounded-2xl bg-white/[0.03] border border-white/[0.06]">
              <Brain className="w-10 h-10 text-slate-700" />
            </div>
            <h2 className="text-lg font-medium text-slate-400">No insights yet</h2>
            <p className="text-slate-500 text-sm text-center max-w-md leading-relaxed">
              Click <strong className="text-violet-400">Run Insights</strong> to analyze your memory store. The engine
              will generate a life summary, detect trends, find contradictions, and review
              expiring memories — all locally on your machine.
            </p>
          </div>
        )}

        {result && status !== "loading" && (
          <>
            {/* Run metadata */}
            <div className="glass-stat rounded-xl px-4 py-2.5 flex items-center justify-between text-[11px] text-slate-500">
              <span>
                {result.memories_analyzed} memories analyzed &middot;{" "}
                {result.duration_seconds}s &middot; {result.model_used}
              </span>
              <span>{new Date(result.timestamp).toLocaleString()}</span>
            </div>

            {result.errors.length > 0 && (
              <div className="glass-card rounded-xl p-3 border-amber-500/20 bg-amber-500/[0.03]">
                <p className="text-amber-300 text-xs">Partial errors: {result.errors.join("; ")}</p>
              </div>
            )}

            {/* Life Summary */}
            {result.life_summary && (
              <div className="space-y-2">
                <SectionHeader
                  icon={Brain}
                  title="Life Summary"
                  open={openSummary}
                  onToggle={() => setOpenSummary(!openSummary)}
                />
                {openSummary && (
                  <div className="mt-2">
                    <LifeSummarySection summary={result.life_summary} />
                  </div>
                )}
              </div>
            )}

            {/* Trends */}
            <div className="space-y-2">
              <SectionHeader
                icon={TrendingUp}
                title="Trends"
                count={result.trends.length}
                open={openTrends}
                onToggle={() => setOpenTrends(!openTrends)}
              />
              {openTrends && result.trends.length > 0 && (
                <div className="mt-2 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                  {result.trends.map((trend, i) => (
                    <TrendCard key={`${trend.topic}-${i}`} trend={trend} />
                  ))}
                </div>
              )}
              {openTrends && result.trends.length === 0 && (
                <p className="mt-2 text-xs text-slate-500 pl-4">
                  No trends detected. Add more memories to see patterns emerge.
                </p>
              )}
            </div>

            {/* Contradictions */}
            <div className="space-y-2">
              <SectionHeader
                icon={AlertTriangle}
                title="Contradiction Alerts"
                count={result.contradictions.length}
                open={openContradictions}
                onToggle={() => setOpenContradictions(!openContradictions)}
              />
              {openContradictions && result.contradictions.length > 0 && (
                <div className="mt-2 space-y-3">
                  {result.contradictions.map((alert) => (
                    <ContradictionCard key={alert.alert_id} alert={alert} />
                  ))}
                </div>
              )}
              {openContradictions && result.contradictions.length === 0 && (
                <p className="mt-2 text-xs text-slate-500 pl-4">
                  No contradictions found. Your memories are consistent.
                </p>
              )}
            </div>

            {/* Expiring Memories */}
            <div className="space-y-2">
              <SectionHeader
                icon={Clock}
                title="Expiring Soon"
                count={result.expiring_memories.length}
                open={openExpiring}
                onToggle={() => setOpenExpiring(!openExpiring)}
              />
              {openExpiring && result.expiring_memories.length > 0 && (
                <div className="mt-2 space-y-3">
                  {result.expiring_memories.map((mem) => (
                    <ExpiringMemoryCard
                      key={mem.memory_id}
                      mem={mem}
                      onExtend={handleExtend}
                    />
                  ))}
                </div>
              )}
              {openExpiring && result.expiring_memories.length === 0 && (
                <p className="mt-2 text-xs text-slate-500 pl-4">
                  No memories are expiring soon.
                </p>
              )}
            </div>
          </>
        )}
      </main>
    </div>
  );
}
