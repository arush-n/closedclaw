"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { FeedbackBanner } from "@/components/ui/feedback-banner";
import {
  Zap,
  Shield,
  Eye,
  FileText,
  Brain,
  Scale,
  ClipboardCheck,
  Wrench,
  ToggleLeft,
  ToggleRight,
  RefreshCw,
  ChevronRight,
  MessageSquare,
  Loader2,
  ShieldCheck,
  AlertTriangle,
  Settings2,
  ArrowUpDown,
} from "lucide-react";

/* ── Types ──────────────────────────────────────────────────────────── */

interface AgentInfo {
  agent_id: string;
  total_invocations: number;
  total_llm_calls: number;
  total_tokens: number;
  total_tool_calls: number;
  errors: number;
  reputation: number;
  enabled: boolean;
  tools: string[];
  status?: string;
  last_active?: string;
}

interface SwarmStatus {
  swarm_active: boolean;
  agents: Record<string, AgentInfo>;
  total_messages: number;
  constitution_version: string;
  constitution_principles: number;
  pending_amendments: number;
  pipelines: Record<string, string[]>;
  total_tools: number;
  disabled_agents: string[];
}

interface MessageEntry {
  message_id: string;
  timestamp: string;
  sender: string;
  recipient: string;
  message_type: string;
  payload: Record<string, unknown>;
  signature?: string;
}

type DetailView = "agent" | "constitution" | "messages" | "pipelines" | "tools";

/* ── Agent metadata ─────────────────────────────────────────────────── */

const AGENT_META: Record<string, { role: string; icon: typeof Zap; color: string; usesLlm: boolean }> = {
  accessor:    { role: "Retrieves & serves memories",     icon: Eye,             color: "blue",    usesLlm: false },
  governance:  { role: "Guards memories via firewall",     icon: Shield,          color: "emerald", usesLlm: false },
  sentinel:    { role: "Detects hallucinations & drift",  icon: ShieldCheck,     color: "amber",   usesLlm: true },
  maker:       { role: "Structures info into memories",    icon: Brain,           color: "violet",  usesLlm: true },
  policy:      { role: "Constitution & rule management",   icon: FileText,        color: "cyan",    usesLlm: true },
  arbitrator:  { role: "Resolves inter-agent conflicts",  icon: Scale,           color: "rose",    usesLlm: true },
  auditor:     { role: "Verifies paper trails & crypto",  icon: ClipboardCheck,  color: "orange",  usesLlm: false },
};

const COLOR_MAP: Record<string, string> = {
  blue:    "from-blue-500/20 to-blue-600/10 border-blue-500/30 text-blue-400",
  emerald: "from-emerald-500/20 to-emerald-600/10 border-emerald-500/30 text-emerald-400",
  amber:   "from-amber-500/20 to-amber-600/10 border-amber-500/30 text-amber-400",
  violet:  "from-violet-500/20 to-violet-600/10 border-violet-500/30 text-violet-400",
  cyan:    "from-cyan-500/20 to-cyan-600/10 border-cyan-500/30 text-cyan-400",
  rose:    "from-rose-500/20 to-rose-600/10 border-rose-500/30 text-rose-400",
  orange:  "from-orange-500/20 to-orange-600/10 border-orange-500/30 text-orange-400",
};

/* ── Page ───────────────────────────────────────────────────────────── */

export default function SwarmPage() {
  const [status, setStatus] = useState<SwarmStatus | null>(null);
  const [messages, setMessages] = useState<MessageEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [selectedAgent, setSelectedAgent] = useState<string | null>(null);
  const [detailView, setDetailView] = useState<DetailView>("agent");
  const [verifying, setVerifying] = useState(false);

  /* ── Data loading ────────────────────────────────────────────── */

  const loadStatus = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("/api/swarm?endpoint=status", { cache: "no-store" });
      const data = await res.json();
      if (data.error && !data.swarm_active) {
        setError(data.error || data.detail || "Swarm not available");
        setStatus(null);
      } else {
        setStatus(data);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load swarm status");
    } finally {
      setLoading(false);
    }
  }, []);

  const loadMessages = useCallback(async () => {
    try {
      const res = await fetch("/api/swarm?endpoint=messages", { cache: "no-store" });
      const data = await res.json();
      setMessages(data.messages || []);
    } catch {
      /* non-critical */
    }
  }, []);

  useEffect(() => {
    loadStatus();
    loadMessages();
  }, [loadStatus, loadMessages]);

  /* ── Actions ─────────────────────────────────────────────────── */

  const toggleAgent = async (name: string, enabled: boolean) => {
    try {
      const res = await fetch(`/api/swarm/agents/${name}/enabled`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled }),
      });
      const data = await res.json();
      if (data.success) {
        setSuccess(`${name} ${enabled ? "enabled" : "disabled"}`);
        await loadStatus();
      } else {
        setError(data.error || data.detail || "Toggle failed");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Toggle failed");
    }
  };

  const runVerify = async () => {
    setVerifying(true);
    try {
      const res = await fetch("/api/swarm?endpoint=verify", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: "{}",
      });
      const data = await res.json();
      if (data.status === "completed") {
        setSuccess("Integrity verification passed");
      } else {
        setError(`Verification: ${data.status}`);
      }
      await loadStatus();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Verification failed");
    } finally {
      setVerifying(false);
    }
  };

  /* ── Computed ─────────────────────────────────────────────────── */

  const agents = useMemo(() => status?.agents || {}, [status]);

  const totalStats = useMemo(() => {
    const vals = Object.values(agents);
    return {
      invocations: vals.reduce((s, a) => s + (a.total_invocations || 0), 0),
      llmCalls: vals.reduce((s, a) => s + (a.total_llm_calls || 0), 0),
      tokens: vals.reduce((s, a) => s + (a.total_tokens || 0), 0),
      toolCalls: vals.reduce((s, a) => s + (a.total_tool_calls || 0), 0),
      errors: vals.reduce((s, a) => s + (a.errors || 0), 0),
    };
  }, [agents]);

  const selectedAgentData = selectedAgent ? agents[selectedAgent] : null;
  const selectedMeta = selectedAgent ? AGENT_META[selectedAgent] : null;

  /* ── Render ──────────────────────────────────────────────────── */

  return (
    <div className="page-container animate-fadeIn">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <div className="p-2.5 rounded-xl bg-gradient-to-br from-violet-500/20 to-blue-500/20 border border-violet-500/30">
            <Zap className="w-5 h-5 text-violet-400" />
          </div>
          <div>
            <h1 className="section-title">Agent Swarm</h1>
            <p className="text-xs text-slate-500 mt-0.5">
              {status ? `${Object.keys(agents).length} agents · ${status.total_messages} messages · ${status.total_tools} tools` : "Loading..."}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={loadStatus} disabled={loading}>
            <RefreshCw className={`w-3.5 h-3.5 mr-1.5 ${loading ? "animate-spin" : ""}`} />
            Refresh
          </Button>
          <Button variant="outline" size="sm" onClick={runVerify} disabled={verifying}>
            {verifying ? <Loader2 className="w-3.5 h-3.5 mr-1.5 animate-spin" /> : <ShieldCheck className="w-3.5 h-3.5 mr-1.5" />}
            Verify Integrity
          </Button>
        </div>
      </div>

      {error && <FeedbackBanner variant="error" message={error} onClose={() => setError(null)} />}
      {success && <FeedbackBanner variant="success" message={success} onClose={() => setSuccess(null)} />}

      {/* Stats Bar */}
      {status && (
        <div className="grid grid-cols-2 sm:grid-cols-5 gap-3 mb-6">
          <StatBox label="Invocations" value={totalStats.invocations} />
          <StatBox label="LLM Calls" value={totalStats.llmCalls} />
          <StatBox label="Tokens" value={totalStats.tokens.toLocaleString()} />
          <StatBox label="Tool Calls" value={totalStats.toolCalls} />
          <StatBox label="Errors" value={totalStats.errors} variant={totalStats.errors > 0 ? "warning" : "default"} />
        </div>
      )}

      {/* Main Content */}
      <div className="grid xl:grid-cols-[1.2fr_1fr] gap-6">
        {/* Left: Agent Grid */}
        <section className="space-y-4">
          {/* Tab bar */}
          <div className="flex items-center gap-1 glass-subtle rounded-lg px-1 py-1">
            {(["agent", "pipelines", "messages", "tools"] as DetailView[]).map((view) => (
              <button
                key={view}
                onClick={() => { setDetailView(view); if (view !== "agent") setSelectedAgent(null); }}
                className={`px-3 py-1.5 rounded-md text-xs font-medium transition-all ${
                  detailView === view
                    ? "bg-white/[0.08] text-white border border-white/[0.08]"
                    : "text-slate-400 hover:text-slate-200 hover:bg-white/[0.04]"
                }`}
              >
                {view.charAt(0).toUpperCase() + view.slice(1)}
              </button>
            ))}
          </div>

          {/* Agent cards */}
          {(detailView === "agent" || !detailView) && (
            <div className="grid sm:grid-cols-2 gap-3">
              {Object.entries(AGENT_META).map(([name, meta]) => {
                const agent = agents[name];
                const isSelected = selectedAgent === name;
                const enabled = agent?.enabled !== false;
                const Icon = meta.icon;
                const colors = COLOR_MAP[meta.color] || COLOR_MAP.violet;

                return (
                  <button
                    key={name}
                    onClick={() => { setSelectedAgent(name); setDetailView("agent"); }}
                    className={`glass-card rounded-xl p-4 text-left transition-all duration-200 hover:border-white/[0.12] ${
                      isSelected ? "ring-1 ring-violet-500/40 border-violet-500/30" : ""
                    } ${!enabled ? "opacity-50" : ""}`}
                  >
                    <div className="flex items-start justify-between mb-2">
                      <div className="flex items-center gap-2">
                        <div className={`p-1.5 rounded-lg bg-gradient-to-br ${colors} border`}>
                          <Icon className="w-3.5 h-3.5" />
                        </div>
                        <div>
                          <div className="text-sm font-medium text-slate-200 capitalize">{name}</div>
                          <div className="text-[10px] text-slate-500">{meta.role}</div>
                        </div>
                      </div>
                      <button
                        onClick={(e) => { e.stopPropagation(); toggleAgent(name, !enabled); }}
                        className="text-slate-500 hover:text-slate-300 transition-colors"
                      >
                        {enabled ? <ToggleRight className="w-5 h-5 text-emerald-400" /> : <ToggleLeft className="w-5 h-5" />}
                      </button>
                    </div>

                    {/* Mini stats */}
                    <div className="grid grid-cols-3 gap-2 mt-3">
                      <MiniStat label="Calls" value={agent?.total_invocations || 0} />
                      <MiniStat label="LLM" value={agent?.total_llm_calls || 0} />
                      <MiniStat label="Tools" value={agent?.total_tool_calls || 0} />
                    </div>

                    {/* Reputation bar */}
                    <div className="mt-3">
                      <div className="flex items-center justify-between text-[10px] text-slate-500 mb-1">
                        <span>Reputation</span>
                        <span>{((agent?.reputation || 1) * 100).toFixed(0)}%</span>
                      </div>
                      <div className="h-1 bg-white/[0.06] rounded-full overflow-hidden">
                        <div
                          className="h-full bg-gradient-to-r from-violet-500 to-blue-500 rounded-full transition-all"
                          style={{ width: `${(agent?.reputation || 1) * 100}%` }}
                        />
                      </div>
                    </div>
                  </button>
                );
              })}
            </div>
          )}

          {/* Pipeline view */}
          {detailView === "pipelines" && status?.pipelines && (
            <div className="space-y-3">
              {Object.entries(status.pipelines).map(([taskType, pipeline]) => (
                <div key={taskType} className="glass-card rounded-xl p-4">
                  <div className="text-xs font-medium text-slate-300 mb-2 flex items-center gap-2">
                    <ArrowUpDown className="w-3 h-3 text-violet-400" />
                    {taskType.replace(/_/g, " ").toUpperCase()}
                  </div>
                  <div className="flex items-center gap-1 flex-wrap">
                    {pipeline.map((agentName, i) => {
                      const meta = AGENT_META[agentName];
                      const Icon = meta?.icon || Zap;
                      const disabled = status.disabled_agents?.includes(agentName);
                      return (
                        <div key={i} className="flex items-center gap-1">
                          {i > 0 && <ChevronRight className="w-3 h-3 text-slate-600" />}
                          <span className={`inline-flex items-center gap-1 px-2 py-1 rounded-md text-[11px] font-medium ${
                            disabled
                              ? "bg-white/[0.03] text-slate-600 line-through"
                              : "bg-white/[0.06] text-slate-300"
                          }`}>
                            <Icon className="w-3 h-3" />
                            {agentName}
                          </span>
                        </div>
                      );
                    })}
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Messages view */}
          {detailView === "messages" && (
            <div className="space-y-2 max-h-[600px] overflow-y-auto">
              {messages.length === 0 ? (
                <div className="glass-card rounded-xl p-6 text-center text-sm text-slate-500">
                  No inter-agent messages yet. Run a task to generate activity.
                </div>
              ) : (
                messages.slice(-50).reverse().map((msg) => (
                  <div key={msg.message_id} className="glass-card rounded-lg p-3">
                    <div className="flex items-center justify-between mb-1">
                      <div className="flex items-center gap-2 text-xs">
                        <span className="font-medium text-slate-300">{msg.sender}</span>
                        <ChevronRight className="w-3 h-3 text-slate-600" />
                        <span className="font-medium text-slate-300">{msg.recipient}</span>
                        <span className={`badge ${msg.message_type === "result" ? "badge-success" : msg.message_type === "task" ? "badge-primary" : "badge-neutral"}`}>
                          {msg.message_type}
                        </span>
                      </div>
                      <div className="flex items-center gap-2">
                        {msg.signature && <Shield className="w-3 h-3 text-emerald-500" aria-label="Signed" />}
                        <span className="text-[10px] text-slate-600">
                          {new Date(msg.timestamp).toLocaleTimeString()}
                        </span>
                      </div>
                    </div>
                  </div>
                ))
              )}
            </div>
          )}

          {/* Tools view */}
          {detailView === "tools" && (
            <div className="space-y-3">
              {Object.entries(AGENT_META).map(([name, meta]) => {
                const agent = agents[name];
                const tools = agent?.tools || [];
                const Icon = meta.icon;
                return (
                  <div key={name} className="glass-card rounded-xl p-4">
                    <div className="flex items-center gap-2 mb-2">
                      <Icon className="w-3.5 h-3.5 text-slate-400" />
                      <span className="text-xs font-medium text-slate-300 capitalize">{name}</span>
                      <span className="text-[10px] text-slate-600">({tools.length} tools)</span>
                    </div>
                    <div className="flex flex-wrap gap-1">
                      {tools.map((tool) => (
                        <span key={tool} className="px-2 py-0.5 rounded text-[10px] font-mono bg-white/[0.05] text-slate-400 border border-white/[0.06]">
                          {tool}
                        </span>
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </section>

        {/* Right: Detail Panel */}
        <section className="glass-card rounded-xl p-5 space-y-4 h-fit sticky top-20">
          {detailView === "agent" && selectedAgent && selectedAgentData && selectedMeta ? (
            <>
              {/* Agent header */}
              <div className="flex items-center gap-3">
                <div className={`p-2 rounded-lg bg-gradient-to-br ${COLOR_MAP[selectedMeta.color]} border`}>
                  <selectedMeta.icon className="w-5 h-5" />
                </div>
                <div>
                  <h2 className="text-lg font-semibold text-white capitalize">{selectedAgent}</h2>
                  <p className="text-xs text-slate-500">{selectedMeta.role}</p>
                </div>
              </div>

              {/* Stats grid */}
              <div className="grid grid-cols-2 gap-3">
                <DetailStat label="Invocations" value={selectedAgentData.total_invocations} />
                <DetailStat label="LLM Calls" value={selectedAgentData.total_llm_calls} />
                <DetailStat label="Tokens" value={selectedAgentData.total_tokens.toLocaleString()} />
                <DetailStat label="Tool Calls" value={selectedAgentData.total_tool_calls} />
                <DetailStat label="Errors" value={selectedAgentData.errors} variant={selectedAgentData.errors > 0 ? "warning" : "default"} />
                <DetailStat label="Reputation" value={`${(selectedAgentData.reputation * 100).toFixed(0)}%`} />
              </div>

              {/* Properties */}
              <div className="space-y-2">
                <div className="flex items-center justify-between text-xs">
                  <span className="text-slate-500">Uses LLM</span>
                  <span className={selectedMeta.usesLlm ? "text-amber-400" : "text-emerald-400"}>
                    {selectedMeta.usesLlm ? "Yes (1 call/invocation)" : "No (pure rules)"}
                  </span>
                </div>
                <div className="flex items-center justify-between text-xs">
                  <span className="text-slate-500">Status</span>
                  <span className={selectedAgentData.enabled ? "text-emerald-400" : "text-red-400"}>
                    {selectedAgentData.enabled ? "Enabled" : "Disabled"}
                  </span>
                </div>
                {selectedAgentData.last_active && (
                  <div className="flex items-center justify-between text-xs">
                    <span className="text-slate-500">Last Active</span>
                    <span className="text-slate-400">
                      {new Date(selectedAgentData.last_active).toLocaleString()}
                    </span>
                  </div>
                )}
              </div>

              {/* Tools */}
              <div>
                <h3 className="text-xs font-medium text-slate-400 mb-2 flex items-center gap-1.5">
                  <Wrench className="w-3 h-3" /> Available Tools ({selectedAgentData.tools?.length || 0})
                </h3>
                <div className="flex flex-wrap gap-1">
                  {(selectedAgentData.tools || []).map((tool) => (
                    <span key={tool} className="px-2 py-0.5 rounded text-[10px] font-mono bg-white/[0.05] text-slate-400 border border-white/[0.06]">
                      {tool}
                    </span>
                  ))}
                </div>
              </div>

              {/* Pipelines this agent participates in */}
              {status?.pipelines && (
                <div>
                  <h3 className="text-xs font-medium text-slate-400 mb-2 flex items-center gap-1.5">
                    <Settings2 className="w-3 h-3" /> Pipeline Participation
                  </h3>
                  <div className="space-y-1">
                    {Object.entries(status.pipelines)
                      .filter(([, agents]) => agents.includes(selectedAgent))
                      .map(([taskType, pipeline]) => (
                        <div key={taskType} className="flex items-center gap-2 text-[11px]">
                          <span className="text-slate-500 w-32 truncate">{taskType.replace(/_/g, " ")}</span>
                          <span className="text-slate-600">#{pipeline.indexOf(selectedAgent) + 1}</span>
                        </div>
                      ))}
                  </div>
                </div>
              )}
            </>
          ) : detailView === "agent" ? (
            <div className="text-center py-12 text-sm text-slate-500">
              <Zap className="w-8 h-8 mx-auto mb-3 text-slate-600" />
              <p>Select an agent to view details</p>
            </div>
          ) : detailView === "pipelines" ? (
            <div className="space-y-4">
              <h2 className="text-lg font-semibold text-white flex items-center gap-2">
                <ArrowUpDown className="w-5 h-5 text-violet-400" />
                Pipeline Routing
              </h2>
              <p className="text-xs text-slate-500">
                Pipelines define the order agents execute for each task type.
                Agents run sequentially — each sees the previous agent&apos;s output.
                Disabled agents are skipped.
              </p>
              <div className="space-y-2 text-xs text-slate-400">
                <div className="flex items-center gap-2">
                  <Shield className="w-3 h-3 text-emerald-400" />
                  <span>All messages are Ed25519 signed</span>
                </div>
                <div className="flex items-center gap-2">
                  <AlertTriangle className="w-3 h-3 text-amber-400" />
                  <span>Sentinel only activates for sensitivity &ge; 2</span>
                </div>
                <div className="flex items-center gap-2">
                  <MessageSquare className="w-3 h-3 text-blue-400" />
                  <span>Agents can delegate to each other via tools</span>
                </div>
              </div>
            </div>
          ) : detailView === "messages" ? (
            <div className="space-y-4">
              <h2 className="text-lg font-semibold text-white flex items-center gap-2">
                <MessageSquare className="w-5 h-5 text-violet-400" />
                Message Bus
              </h2>
              <p className="text-xs text-slate-500">
                {status?.total_messages || 0} total messages exchanged between agents.
                Every message is cryptographically signed with Ed25519.
              </p>
              <div className="text-xs text-slate-400 space-y-1">
                <div>Types: task, result, delegation, vote, arbitration</div>
                <div>Bus capacity: 2,000 messages</div>
              </div>
            </div>
          ) : detailView === "tools" ? (
            <div className="space-y-4">
              <h2 className="text-lg font-semibold text-white flex items-center gap-2">
                <Wrench className="w-5 h-5 text-violet-400" />
                Tool Registry
              </h2>
              <p className="text-xs text-slate-500">
                {status?.total_tools || 0} tools registered. Each agent has a configured set of
                tools it can access. Tools are permission-checked before execution.
              </p>
              <div className="space-y-2 text-xs">
                <h3 className="text-slate-400 font-medium">Memory Tools</h3>
                <ToolDesc name="memory_search" desc="Semantic search over the vault" />
                <ToolDesc name="memory_write" desc="Store a new memory" />
                <ToolDesc name="memory_timeline" desc="Chronological memory retrieval" />
                <ToolDesc name="memory_reflect" desc="Synthesize memory summary" />
                <h3 className="text-slate-400 font-medium mt-3">Inter-Agent Tools</h3>
                <ToolDesc name="delegate_to_agent" desc="Delegate a sub-task to another agent" />
                <ToolDesc name="request_vote" desc="Federated consensus voting" />
                <ToolDesc name="check_constitution" desc="Constitution compliance check" />
                <h3 className="text-slate-400 font-medium mt-3">Audit Tools</h3>
                <ToolDesc name="log_decision" desc="Log to audit trail" />
                <ToolDesc name="verify_signature" desc="Verify Ed25519 signature" />
              </div>
            </div>
          ) : null}
        </section>
      </div>
    </div>
  );
}

/* ── Sub-components ─────────────────────────────────────────────────── */

function StatBox({ label, value, variant = "default" }: { label: string; value: string | number; variant?: "default" | "warning" }) {
  return (
    <div className="glass-stat rounded-lg p-3 text-center">
      <div className={`text-lg font-bold ${variant === "warning" ? "text-amber-400" : "text-white"}`}>
        {value}
      </div>
      <div className="text-[10px] text-slate-500 mt-0.5">{label}</div>
    </div>
  );
}

function MiniStat({ label, value }: { label: string; value: number }) {
  return (
    <div className="text-center">
      <div className="text-xs font-semibold text-slate-300">{value}</div>
      <div className="text-[9px] text-slate-600">{label}</div>
    </div>
  );
}

function DetailStat({ label, value, variant = "default" }: { label: string; value: string | number; variant?: "default" | "warning" }) {
  return (
    <div className="bg-white/[0.03] rounded-lg p-3">
      <div className="text-[10px] text-slate-500 mb-1">{label}</div>
      <div className={`text-sm font-semibold ${variant === "warning" ? "text-amber-400" : "text-white"}`}>
        {value}
      </div>
    </div>
  );
}

function ToolDesc({ name, desc }: { name: string; desc: string }) {
  return (
    <div className="flex items-start gap-2">
      <span className="font-mono text-[10px] text-violet-400 bg-violet-500/10 px-1.5 py-0.5 rounded shrink-0">{name}</span>
      <span className="text-slate-500">{desc}</span>
    </div>
  );
}
