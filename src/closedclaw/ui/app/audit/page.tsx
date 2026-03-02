"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { FeedbackBanner } from "@/components/ui/feedback-banner";
import { ShieldCheck, ShieldAlert, Search, Download, RefreshCw, FileText, Copy, CheckCircle2, AlertTriangle, Loader2 } from "lucide-react";

interface AuditEntry {
  entry_id: string;
  timestamp: string;
  request_id: string;
  provider: string;
  model: string;
  memories_retrieved: number;
  memories_used: number;
  redactions_applied: number;
  blocked_memories: number;
  consent_required: boolean;
  context_tokens: number;
  total_tokens?: number;
}

interface VerifyResponse {
  valid: boolean;
  message: string;
  entries_checked: number;
}

interface AuditEntryDetail extends AuditEntry {
  memory_ids?: string[];
  consent_receipt_id?: string;
  query_summary?: string;
  prev_hash?: string;
  entry_hash?: string;
}

export default function AuditPage() {
  const [entries, setEntries] = useState<AuditEntry[]>([]);
  const [selected, setSelected] = useState<AuditEntryDetail | null>(null);
  const [verify, setVerify] = useState<VerifyResponse | null>(null);
  const [provider, setProvider] = useState("");
  const [consentOnly, setConsentOnly] = useState(false);
  const [requestQuery, setRequestQuery] = useState("");
  const [fromDate, setFromDate] = useState("");
  const [toDate, setToDate] = useState("");
  const [pageSize, setPageSize] = useState("100");
  const [isLoading, setIsLoading] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [copiedField, setCopiedField] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [visibleEntriesCount, setVisibleEntriesCount] = useState(80);
  const searchInputRef = useRef<HTMLInputElement>(null);
  const listAbortRef = useRef<AbortController | null>(null);
  const detailAbortRef = useRef<AbortController | null>(null);

  const loadAuditEntries = useCallback(async () => {
    listAbortRef.current?.abort();
    const controller = new AbortController();
    listAbortRef.current = controller;

    setIsLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({ limit: pageSize });
      if (provider) params.append("provider", provider);
      if (consentOnly) params.append("has_consent", "true");
      if (fromDate) params.append("from_time", new Date(fromDate).toISOString());
      if (toDate) {
        const inclusiveEnd = new Date(toDate);
        inclusiveEnd.setHours(23, 59, 59, 999);
        params.append("to_time", inclusiveEnd.toISOString());
      }

      const response = await fetch(`/api/audit?${params.toString()}`, {
        cache: "no-store",
        signal: controller.signal,
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data?.detail || data?.error || "Failed to load audit entries");
      }
      setEntries(Array.isArray(data.entries) ? data.entries : []);
      setSelected(null);
      setLastUpdated(new Date());
    } catch (err) {
      if (err instanceof Error && err.name === "AbortError") {
        return;
      }
      setError(err instanceof Error ? err.message : "Failed to load audit entries");
      setEntries([]);
    } finally {
      setIsLoading(false);
    }
  }, [provider, consentOnly, fromDate, toDate, pageSize]);

  const loadVerifyStatus = useCallback(async () => {
    try {
      const response = await fetch("/api/audit/verify", { cache: "no-store" });
      const data = await response.json();
      setVerify(data);
    } catch {
      setVerify({ valid: false, message: "Unable to verify chain", entries_checked: 0 });
    }
  }, []);

  const loadAuditDetail = useCallback(async (entry: AuditEntry) => {
    detailAbortRef.current?.abort();
    const controller = new AbortController();
    detailAbortRef.current = controller;

    setDetailLoading(true);
    try {
      const response = await fetch(`/api/audit/${entry.entry_id}`, {
        cache: "no-store",
        signal: controller.signal,
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data?.detail || data?.error || "Failed to load audit detail");
      }
      setSelected(data);
    } catch (err) {
      if (err instanceof Error && err.name === "AbortError") {
        return;
      }
      setSelected(entry);
    } finally {
      setDetailLoading(false);
    }
  }, []);

  useEffect(() => {
    const debounce = setTimeout(() => {
      loadAuditEntries();
    }, 180);
    return () => clearTimeout(debounce);
  }, [loadAuditEntries]);

  useEffect(() => {
    loadVerifyStatus();
  }, [loadVerifyStatus]);

  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if (event.key === "/" && !(event.target instanceof HTMLInputElement || event.target instanceof HTMLTextAreaElement)) {
        event.preventDefault();
        searchInputRef.current?.focus();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  const sortedProviders = useMemo(
    () => [...new Set(entries.map((entry) => entry.provider))].sort(),
    [entries]
  );

  const filteredEntries = useMemo(() => {
    if (!requestQuery.trim()) return entries;
    const query = requestQuery.toLowerCase();
    return entries.filter(
      (entry) =>
        entry.request_id.toLowerCase().includes(query) ||
        entry.entry_id.toLowerCase().includes(query) ||
        entry.model.toLowerCase().includes(query)
    );
  }, [entries, requestQuery]);

  const visibleEntries = useMemo(
    () => filteredEntries.slice(0, visibleEntriesCount),
    [filteredEntries, visibleEntriesCount]
  );

  useEffect(() => {
    setVisibleEntriesCount(80);
  }, [provider, consentOnly, requestQuery, fromDate, toDate, pageSize]);

  const stats = useMemo(() => {
    return {
      total: filteredEntries.length,
      consentRequired: filteredEntries.filter((item) => item.consent_required).length,
      blockedTotal: filteredEntries.reduce((sum, item) => sum + item.blocked_memories, 0),
      redactionsTotal: filteredEntries.reduce((sum, item) => sum + item.redactions_applied, 0),
    };
  }, [filteredEntries]);

  const exportBundle = async () => {
    const params = new URLSearchParams();
    if (fromDate) params.append("from_time", new Date(fromDate).toISOString());
    if (toDate) {
      const inclusiveEnd = new Date(toDate);
      inclusiveEnd.setHours(23, 59, 59, 999);
      params.append("to_time", inclusiveEnd.toISOString());
    }

    const response = await fetch(`/api/audit/export?${params.toString()}`, { cache: "no-store" });
    const data = await response.json();
    if (!response.ok) {
      setError(data?.error || "Failed to export audit bundle");
      return;
    }
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `closedclaw-audit-export-${Date.now()}.json`;
    anchor.click();
    URL.revokeObjectURL(url);
    setNotice("Audit bundle exported");
  };

  const copyText = async (value: string, field: string) => {
    try {
      await navigator.clipboard.writeText(value);
      setCopiedField(field);
      setNotice("Copied to clipboard");
      window.setTimeout(() => setCopiedField((current) => (current === field ? null : current)), 1200);
    } catch {
      setError("Unable to copy to clipboard");
    }
  };

  useEffect(() => {
    if (!notice) return;
    const timer = window.setTimeout(() => setNotice(null), 2200);
    return () => window.clearTimeout(timer);
  }, [notice]);

  return (
    <div className="page-container space-y-6 animate-fadeIn">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="p-2.5 rounded-xl bg-violet-500/10 border border-violet-500/20">
            <FileText className="w-5 h-5 text-violet-400" />
          </div>
          <div>
            <h1 className="section-title">Audit Log</h1>
            {lastUpdated && (
              <p className="text-xs text-slate-500 mt-0.5">Updated {lastUpdated.toLocaleTimeString()}</p>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" onClick={loadAuditEntries} disabled={isLoading}>
            <RefreshCw className={`w-4 h-4 ${isLoading ? "animate-spin" : ""}`} />
            Refresh
          </Button>
          <Button onClick={exportBundle}>
            <Download className="w-4 h-4" />
            Export
          </Button>
        </div>
      </div>

      {/* Chain Integrity */}
      <div
        className={`glass-card rounded-xl p-4 flex items-start gap-3 ${
          verify?.valid
            ? "border-emerald-500/20 bg-emerald-500/[0.03]"
            : "border-red-500/20 bg-red-500/[0.03]"
        }`}
      >
        {verify?.valid ? (
          <ShieldCheck className="w-5 h-5 text-emerald-400 mt-0.5 shrink-0" />
        ) : (
          <ShieldAlert className="w-5 h-5 text-red-400 mt-0.5 shrink-0" />
        )}
        <div>
          <div className="font-medium text-sm">
            Chain Integrity: {verify?.valid ? "Verified" : "Issue Detected"}
          </div>
          <div className="text-xs text-slate-500 mt-0.5">{verify?.message || "Checking chain status..."}</div>
        </div>
      </div>

      {/* Filters */}
      <div className="glass-card rounded-xl p-4">
        <div className="flex flex-wrap items-center gap-2">
          <div className="relative flex-1 min-w-[220px]">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
            <input
              ref={searchInputRef}
              className="glass-input rounded-lg pl-10 pr-4 py-2 text-sm w-full"
              placeholder="Search request/model/entry id ( / )"
              value={requestQuery}
              onChange={(event) => setRequestQuery(event.target.value)}
            />
          </div>
          {requestQuery && (
            <Button variant="outline" size="sm" onClick={() => setRequestQuery("")}>Clear</Button>
          )}
          <select
            aria-label="Filter audit entries by provider"
            className="glass-input rounded-lg px-3 py-2 text-sm"
            value={provider}
            onChange={(event) => setProvider(event.target.value)}
          >
            <option value="">All providers</option>
            {sortedProviders.map((item) => (
              <option key={item} value={item}>{item}</option>
            ))}
          </select>

          <label className="text-sm text-slate-400 flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={consentOnly}
              onChange={(event) => setConsentOnly(event.target.checked)}
              className="rounded border-slate-600"
            />
            Consent only
          </label>

          <input
            type="date"
            aria-label="Filter from date"
            className="glass-input rounded-lg px-3 py-2 text-sm"
            value={fromDate}
            onChange={(event) => setFromDate(event.target.value)}
          />
          <input
            type="date"
            aria-label="Filter to date"
            className="glass-input rounded-lg px-3 py-2 text-sm"
            value={toDate}
            onChange={(event) => setToDate(event.target.value)}
          />
          <select
            aria-label="Audit page size"
            className="glass-input rounded-lg px-3 py-2 text-sm"
            value={pageSize}
            onChange={(event) => setPageSize(event.target.value)}
          >
            <option value="50">50 rows</option>
            <option value="100">100 rows</option>
            <option value="200">200 rows</option>
          </select>
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              setProvider("");
              setConsentOnly(false);
              setRequestQuery("");
              setFromDate("");
              setToDate("");
              setPageSize("100");
            }}
          >
            Clear All
          </Button>
        </div>
      </div>

      {error && <FeedbackBanner message={error} variant="error" onClose={() => setError(null)} />}
      {notice && <FeedbackBanner message={notice} variant="success" onClose={() => setNotice(null)} />}

      {/* Stats */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {[
          { label: "Entries", value: stats.total, color: "text-slate-200" },
          { label: "Consent Required", value: stats.consentRequired, color: "text-amber-400" },
          { label: "Blocked Memories", value: stats.blockedTotal, color: "text-red-400" },
          { label: "Redactions", value: stats.redactionsTotal, color: "text-violet-400" },
        ].map((stat) => (
          <div key={stat.label} className="glass-stat rounded-xl p-4">
            <div className="text-xs text-slate-500 mb-1">{stat.label}</div>
            <div className={`text-xl font-bold ${stat.color}`}>{stat.value}</div>
          </div>
        ))}
      </div>

      {/* Entry List & Detail */}
      <div className="grid lg:grid-cols-[1.2fr_1fr] gap-4">
        {/* Entries */}
        <div className="glass-card rounded-xl overflow-hidden">
          <div className="px-4 py-2.5 text-xs text-slate-500 border-b border-white/[0.06] flex items-center gap-2">
            <FileText className="w-3.5 h-3.5" />
            Showing {visibleEntries.length} of {filteredEntries.length} entries
          </div>
          <div className="max-h-[64vh] overflow-auto">
            {isLoading && (
              <div className="flex items-center gap-3 p-6 justify-center">
                <Loader2 className="w-5 h-5 animate-spin text-violet-400" />
                <span className="text-slate-500 text-sm">Loading audit entries...</span>
              </div>
            )}
            {!isLoading && filteredEntries.length === 0 && (
              <div className="p-8 text-center">
                <FileText className="w-8 h-8 text-slate-700 mx-auto mb-2" />
                <p className="text-sm text-slate-500">
                  {entries.length === 0
                    ? "No audit entries found yet. Run a proxy request to generate activity."
                    : "No entries match current filters."}
                </p>
              </div>
            )}
            {visibleEntries.map((entry) => (
              <button
                key={entry.entry_id}
                onClick={() => loadAuditDetail(entry)}
                className={`w-full text-left p-4 border-b border-white/[0.05] transition-all duration-200 hover:bg-white/[0.03] ${
                  selected?.entry_id === entry.entry_id
                    ? "bg-violet-500/[0.05] border-l-2 border-l-violet-500/50"
                    : ""
                }`}
              >
                <div className="flex items-center justify-between gap-2">
                  <div className="font-medium text-sm text-slate-200">{entry.provider} / {entry.model}</div>
                  <div className="text-[11px] text-slate-500">{new Date(entry.timestamp).toLocaleString()}</div>
                </div>
                <div className="text-xs text-slate-500 mt-1 font-mono truncate">req: {entry.request_id}</div>
                <div className="mt-2 flex flex-wrap gap-1.5">
                  <span className="badge badge-neutral text-[10px]">mem: {entry.memories_used}</span>
                  {entry.redactions_applied > 0 && (
                    <span className="badge badge-warning text-[10px]">redact: {entry.redactions_applied}</span>
                  )}
                  {entry.blocked_memories > 0 && (
                    <span className="badge badge-danger text-[10px]">blocked: {entry.blocked_memories}</span>
                  )}
                  {entry.consent_required && (
                    <span className="badge badge-warning text-[10px]">
                      <AlertTriangle className="w-2.5 h-2.5 mr-0.5" />
                      consent
                    </span>
                  )}
                </div>
              </button>
            ))}
            {!isLoading && visibleEntries.length < filteredEntries.length && (
              <div className="p-3 border-t border-white/[0.05]">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setVisibleEntriesCount((count) => count + 80)}
                >
                  Load 80 more ({filteredEntries.length - visibleEntries.length} remaining)
                </Button>
              </div>
            )}
          </div>
        </div>

        {/* Detail Panel */}
        <div className="glass-card rounded-xl p-5">
          <div className="flex items-center gap-2 mb-4">
            <div className="w-1.5 h-1.5 rounded-full bg-violet-400" />
            <h2 className="text-sm font-semibold text-slate-200">Entry Detail</h2>
          </div>
          {detailLoading && (
            <div className="flex items-center gap-2 mb-3">
              <Loader2 className="w-4 h-4 animate-spin text-violet-400" />
              <span className="text-sm text-slate-500">Loading details...</span>
            </div>
          )}
          {!selected ? (
            <div className="flex flex-col items-center justify-center py-12 gap-3">
              <FileText className="w-8 h-8 text-slate-700" />
              <p className="text-sm text-slate-500">Select an entry to inspect details.</p>
            </div>
          ) : (
            <dl className="space-y-3 text-sm">
              {[
                { label: "Entry ID", value: selected.entry_id, copyKey: "entry", mono: true },
                { label: "Provider", value: selected.provider },
                { label: "Model", value: selected.model },
                { label: "Memories Retrieved", value: selected.memories_retrieved },
                { label: "Memories Used", value: selected.memories_used },
                { label: "Context Tokens", value: selected.context_tokens },
                { label: "Total Tokens", value: selected.total_tokens ?? "—" },
                { label: "Memory IDs", value: selected.memory_ids?.length ?? 0 },
                { label: "Consent Receipt", value: selected.consent_receipt_id || "—", mono: true },
              ].map((item) => (
                <div key={item.label} className="flex items-start justify-between gap-3 py-1.5 border-b border-white/[0.04]">
                  <dt className="text-slate-500 shrink-0">{item.label}</dt>
                  <dd className={`text-slate-200 text-right break-all flex items-center gap-2 justify-end ${item.mono ? "font-mono text-xs" : ""}`}>
                    <span className="truncate max-w-[200px]">{String(item.value)}</span>
                    {item.copyKey && (
                      <button
                        onClick={() => copyText(String(item.value), item.copyKey!)}
                        className="p-1 rounded hover:bg-white/[0.06] transition-colors shrink-0"
                        title="Copy"
                      >
                        {copiedField === item.copyKey ? (
                          <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                        ) : (
                          <Copy className="w-3.5 h-3.5 text-slate-500" />
                        )}
                      </button>
                    )}
                  </dd>
                </div>
              ))}
              {selected.query_summary && (
                <div className="pt-2">
                  <dt className="text-slate-500 mb-1.5 text-xs uppercase tracking-wide">Summary</dt>
                  <dd className="text-slate-300 text-sm bg-white/[0.02] rounded-lg p-3 border border-white/[0.05]">
                    {selected.query_summary}
                  </dd>
                </div>
              )}
            </dl>
          )}
        </div>
      </div>
    </div>
  );
}
