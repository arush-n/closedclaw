"use client";

import { useCallback, useDeferredValue, useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { FeedbackBanner } from "@/components/ui/feedback-banner";

interface PendingConsent {
  request_id: string;
  memory_id: string;
  memory_text: string;
  sensitivity: number;
  provider: string;
  rule_triggered: string;
  created_at: string;
}

interface ConsentReceipt {
  receipt_id: string;
  memory_id: string;
  provider: string;
  user_decision: "approve" | "approve_redacted" | "deny";
  timestamp: string;
}

const SENSITIVITY_STYLES: Record<number, string> = {
  0: "badge-success",
  1: "badge-primary",
  2: "badge-warning",
  3: "badge-danger",
};

const DECISION_STYLES: Record<string, string> = {
  approve: "badge-success",
  approve_redacted: "badge-warning",
  deny: "badge-danger",
};

export default function ConsentPage() {
  const [pending, setPending] = useState<PendingConsent[]>([]);
  const [receipts, setReceipts] = useState<ConsentReceipt[]>([]);
  const [loading, setLoading] = useState(false);
  const [actionLoadingId, setActionLoadingId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [copiedReceipt, setCopiedReceipt] = useState<string | null>(null);
  const [pendingProviderFilter, setPendingProviderFilter] = useState("ALL");
  const [pendingSensitivityFilter, setPendingSensitivityFilter] = useState("ALL");
  const [historyDecisionFilter, setHistoryDecisionFilter] = useState<"ALL" | "approve" | "approve_redacted" | "deny">("ALL");
  const [historyProviderFilter, setHistoryProviderFilter] = useState("ALL");
  const [historySearch, setHistorySearch] = useState("");
  const [visiblePendingCount, setVisiblePendingCount] = useState(40);
  const [visibleReceiptsCount, setVisibleReceiptsCount] = useState(60);
  const deferredHistorySearch = useDeferredValue(historySearch);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [pendingResp, receiptsResp] = await Promise.all([
        fetch("/api/consent/pending", { cache: "no-store" }),
        fetch("/api/consent/receipts?limit=100", { cache: "no-store" }),
      ]);

      const pendingData = await pendingResp.json();
      const receiptsData = await receiptsResp.json();
      if (!pendingResp.ok || !receiptsResp.ok) {
        throw new Error(
          pendingData?.detail ||
            pendingData?.error ||
            receiptsData?.detail ||
            receiptsData?.error ||
            "Failed to load consent data"
        );
      }
      setPending(Array.isArray(pendingData.pending) ? pendingData.pending : []);
      setReceipts(Array.isArray(receiptsData.receipts) ? receiptsData.receipts : []);
      setLastUpdated(new Date());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load consent data");
      setPending([]);
      setReceipts([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    const timer = setInterval(() => {
      if (document.visibilityState === "visible") {
        load();
      }
    }, 20_000);
    return () => clearInterval(timer);
  }, [load]);

  const decide = async (requestId: string, decision: "approve" | "approve_redacted" | "deny") => {
    setActionLoadingId(requestId);
    setError(null);
    const removed = pending.find((item) => item.request_id === requestId) || null;
    setPending((previous) => previous.filter((item) => item.request_id !== requestId));
    try {
      const response = await fetch(`/api/consent/${requestId}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ decision }),
      });

      if (!response.ok) {
        const data = await response.json();
        throw new Error(data?.detail || data?.error || "Failed to submit decision");
      }

      setSuccess(`Decision submitted: ${decision}`);
      await load();
    } catch (err) {
      if (removed) {
        setPending((previous) => [removed, ...previous]);
      }
      setError(err instanceof Error ? err.message : "Failed to submit decision");
    } finally {
      setActionLoadingId(null);
    }
  };

  const pendingProviders = useMemo(
    () => [...new Set(pending.map((item) => item.provider))].sort(),
    [pending]
  );

  const receiptProviders = useMemo(
    () => [...new Set(receipts.map((item) => item.provider))].sort(),
    [receipts]
  );

  const filteredPending = useMemo(() => {
    return pending.filter((item) => {
      if (pendingProviderFilter !== "ALL" && item.provider !== pendingProviderFilter) return false;
      if (pendingSensitivityFilter !== "ALL" && String(item.sensitivity) !== pendingSensitivityFilter) return false;
      return true;
    });
  }, [pending, pendingProviderFilter, pendingSensitivityFilter]);

  const visiblePending = useMemo(
    () => filteredPending.slice(0, visiblePendingCount),
    [filteredPending, visiblePendingCount]
  );

  const filteredReceipts = useMemo(() => {
    const query = deferredHistorySearch.toLowerCase().trim();
    return receipts.filter((item) => {
      if (historyDecisionFilter !== "ALL" && item.user_decision !== historyDecisionFilter) return false;
      if (historyProviderFilter !== "ALL" && item.provider !== historyProviderFilter) return false;
      if (!query) return true;
      return item.memory_id.toLowerCase().includes(query) || item.receipt_id.toLowerCase().includes(query);
    });
  }, [receipts, historyDecisionFilter, historyProviderFilter, deferredHistorySearch]);

  const visibleReceipts = useMemo(
    () => filteredReceipts.slice(0, visibleReceiptsCount),
    [filteredReceipts, visibleReceiptsCount]
  );

  useEffect(() => {
    setVisiblePendingCount(40);
  }, [pendingProviderFilter, pendingSensitivityFilter, pending.length]);

  useEffect(() => {
    setVisibleReceiptsCount(60);
  }, [historyDecisionFilter, historyProviderFilter, deferredHistorySearch, receipts.length]);

  const summary = useMemo(
    () => ({
      pending: pending.length,
      receipts: receipts.length,
      approved: receipts.filter((item) => item.user_decision !== "deny").length,
      denied: receipts.filter((item) => item.user_decision === "deny").length,
    }),
    [pending.length, receipts]
  );

  const copyReceiptId = async (receiptId: string) => {
    try {
      await navigator.clipboard.writeText(receiptId);
      setCopiedReceipt(receiptId);
      setSuccess("Receipt ID copied");
      window.setTimeout(() => setCopiedReceipt((current) => (current === receiptId ? null : current)), 1200);
    } catch {
      setError("Unable to copy receipt id");
    }
  };

  useEffect(() => {
    if (!success) return;
    const timer = window.setTimeout(() => setSuccess(null), 2400);
    return () => window.clearTimeout(timer);
  }, [success]);

  return (
    <div className="page-container space-y-6 animate-fade-in">
      {/* Page Header */}
      <div className="flex items-center justify-between gap-4">
        <div>
          <h1 className="section-title text-2xl">Consent Management</h1>
          <p className="text-sm text-slate-500 mt-1">Review and manage consent requests for memory access</p>
        </div>
        <div className="flex items-center gap-3">
          {lastUpdated && (
            <span className="text-xs text-slate-500 hidden sm:inline">
              Updated {lastUpdated.toLocaleTimeString()}
            </span>
          )}
          <Button variant="outline" onClick={load} disabled={loading} className="glass-subtle hover:bg-white/[0.06]">
            {loading ? "Refreshing..." : "Refresh"}
          </Button>
        </div>
      </div>

      {/* Feedback */}
      {error && <FeedbackBanner message={error} variant="error" onClose={() => setError(null)} />}
      {success && <FeedbackBanner message={success} variant="success" onClose={() => setSuccess(null)} />}

      {/* Stats Row */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <div className="glass-stat rounded-xl px-4 py-3">
          <div className="text-xs text-slate-500 mb-1">Pending</div>
          <div className="text-xl font-bold text-slate-100">{summary.pending}</div>
        </div>
        <div className="glass-stat rounded-xl px-4 py-3">
          <div className="text-xs text-slate-500 mb-1">Total Receipts</div>
          <div className="text-xl font-bold text-slate-100">{summary.receipts}</div>
        </div>
        <div className="glass-stat rounded-xl px-4 py-3">
          <div className="text-xs text-slate-500 mb-1">Approved</div>
          <div className="text-xl font-bold text-emerald-300">{summary.approved}</div>
        </div>
        <div className="glass-stat rounded-xl px-4 py-3">
          <div className="text-xs text-slate-500 mb-1">Denied</div>
          <div className="text-xl font-bold text-red-300">{summary.denied}</div>
        </div>
      </div>

      {/* Two-Column Layout */}
      <div className="grid lg:grid-cols-2 gap-4">
        {/* Pending Requests */}
        <section className="glass-card rounded-2xl overflow-hidden flex flex-col">
          <div className="px-5 py-4 border-b border-white/[0.06] flex items-center justify-between">
            <div className="flex items-center gap-2">
              <div className="w-2 h-2 rounded-full bg-amber-400 shadow-[0_0_6px_rgba(251,191,36,0.4)]" />
              <h2 className="font-semibold text-slate-100">Pending Requests</h2>
            </div>
            <span className="badge badge-warning text-xs">{filteredPending.length}</span>
          </div>

          {/* Filters */}
          <div className="px-5 py-3 border-b border-white/[0.04] flex flex-wrap items-center gap-2">
            <select
              aria-label="Filter pending by provider"
              className="glass-input rounded-lg px-2.5 py-1.5 text-sm text-slate-200"
              value={pendingProviderFilter}
              onChange={(event) => setPendingProviderFilter(event.target.value)}
            >
              <option value="ALL">All providers</option>
              {pendingProviders.map((provider) => (
                <option key={provider} value={provider}>{provider}</option>
              ))}
            </select>
            <select
              aria-label="Filter pending by sensitivity"
              className="glass-input rounded-lg px-2.5 py-1.5 text-sm text-slate-200"
              value={pendingSensitivityFilter}
              onChange={(event) => setPendingSensitivityFilter(event.target.value)}
            >
              <option value="ALL">All levels</option>
              <option value="0">L0 – Public</option>
              <option value="1">L1 – General</option>
              <option value="2">L2 – Personal</option>
              <option value="3">L3 – Sensitive</option>
            </select>
            {(pendingProviderFilter !== "ALL" || pendingSensitivityFilter !== "ALL") && (
              <button
                className="text-xs text-slate-500 hover:text-violet-300 transition-colors"
                onClick={() => { setPendingProviderFilter("ALL"); setPendingSensitivityFilter("ALL"); }}
              >
                Clear filters
              </button>
            )}
          </div>

          {/* Pending List */}
          <div className="flex-1 max-h-[65vh] overflow-auto">
            {loading && (
              <div className="p-6 text-center">
                <div className="w-6 h-6 border-2 border-violet-500/30 border-t-violet-400 rounded-full animate-spin mx-auto mb-2" />
                <span className="text-sm text-slate-500">Loading requests...</span>
              </div>
            )}
            {!loading && filteredPending.length === 0 && (
              <div className="p-8 text-center">
                <div className="w-10 h-10 rounded-xl bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center mx-auto mb-3">
                  <svg className="w-5 h-5 text-emerald-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" /></svg>
                </div>
                <p className="text-sm text-slate-400">
                  {pending.length === 0 ? "All clear — no pending requests" : "No requests match current filters"}
                </p>
              </div>
            )}
            {visiblePending.map((item) => (
              <div
                key={item.request_id}
                className="px-5 py-4 border-b border-white/[0.04] hover:bg-white/[0.02] transition-all duration-200"
              >
                {/* Meta row */}
                <div className="flex items-center gap-2 mb-2 flex-wrap">
                  <span className="badge badge-neutral text-[11px]">{item.provider}</span>
                  <span className={`badge text-[11px] ${SENSITIVITY_STYLES[item.sensitivity] || 'badge-neutral'}`}>
                    L{item.sensitivity}
                  </span>
                  <span className="badge badge-neutral text-[11px]">{item.rule_triggered}</span>
                  <span className="text-[11px] text-slate-600 ml-auto">
                    {new Date(item.created_at).toLocaleString()}
                  </span>
                </div>

                {/* Memory text */}
                <p className="text-sm text-slate-200 whitespace-pre-wrap leading-relaxed mb-3">
                  {item.memory_text}
                </p>

                {/* Action buttons - aligned right */}
                <div className="flex items-center justify-end gap-2">
                  <Button
                    size="sm"
                    onClick={() => decide(item.request_id, "approve")}
                    disabled={actionLoadingId === item.request_id}
                    className="bg-emerald-500/15 hover:bg-emerald-500/25 text-emerald-300 border border-emerald-500/25 hover:border-emerald-500/40 text-xs h-8"
                  >
                    {actionLoadingId === item.request_id ? "..." : "Approve"}
                  </Button>
                  <Button
                    size="sm"
                    onClick={() => decide(item.request_id, "approve_redacted")}
                    disabled={actionLoadingId === item.request_id}
                    className="bg-amber-500/10 hover:bg-amber-500/20 text-amber-300 border border-amber-500/20 hover:border-amber-500/35 text-xs h-8"
                  >
                    Redacted
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => decide(item.request_id, "deny")}
                    disabled={actionLoadingId === item.request_id}
                    className="bg-red-500/[0.08] hover:bg-red-500/15 text-red-300 border-red-500/20 hover:border-red-500/35 text-xs h-8"
                  >
                    Deny
                  </Button>
                </div>
              </div>
            ))}
            {!loading && visiblePending.length < filteredPending.length && (
              <div className="p-4 border-t border-white/[0.04]">
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => setVisiblePendingCount((count) => count + 40)}
                  className="w-full glass-subtle hover:bg-white/[0.04] text-xs"
                >
                  Load more ({filteredPending.length - visiblePending.length} remaining)
                </Button>
              </div>
            )}
          </div>
        </section>

        {/* Consent History */}
        <section className="glass-card rounded-2xl overflow-hidden flex flex-col">
          <div className="px-5 py-4 border-b border-white/[0.06] flex items-center justify-between">
            <div className="flex items-center gap-2">
              <div className="w-2 h-2 rounded-full bg-violet-400 shadow-[0_0_6px_rgba(139,92,246,0.4)]" />
              <h2 className="font-semibold text-slate-100">Consent History</h2>
            </div>
            <span className="badge badge-neutral text-xs">{filteredReceipts.length}</span>
          </div>

          {/* Filters */}
          <div className="px-5 py-3 border-b border-white/[0.04] flex flex-wrap items-center gap-2">
            <input
              className="glass-input rounded-lg px-2.5 py-1.5 text-sm text-slate-200 min-w-[180px] flex-1"
              placeholder="Search by ID..."
              value={historySearch}
              onChange={(event) => setHistorySearch(event.target.value)}
            />
            <select
              aria-label="Filter consent history by decision"
              className="glass-input rounded-lg px-2.5 py-1.5 text-sm text-slate-200"
              value={historyDecisionFilter}
              onChange={(event) => setHistoryDecisionFilter(event.target.value as "ALL" | "approve" | "approve_redacted" | "deny")}
            >
              <option value="ALL">All decisions</option>
              <option value="approve">Approved</option>
              <option value="approve_redacted">Redacted</option>
              <option value="deny">Denied</option>
            </select>
            <select
              aria-label="Filter consent history by provider"
              className="glass-input rounded-lg px-2.5 py-1.5 text-sm text-slate-200"
              value={historyProviderFilter}
              onChange={(event) => setHistoryProviderFilter(event.target.value)}
            >
              <option value="ALL">All providers</option>
              {receiptProviders.map((provider) => (
                <option key={provider} value={provider}>{provider}</option>
              ))}
            </select>
            {(historySearch || historyDecisionFilter !== "ALL" || historyProviderFilter !== "ALL") && (
              <button
                className="text-xs text-slate-500 hover:text-violet-300 transition-colors"
                onClick={() => { setHistorySearch(""); setHistoryDecisionFilter("ALL"); setHistoryProviderFilter("ALL"); }}
              >
                Clear
              </button>
            )}
          </div>

          {/* History List */}
          <div className="flex-1 max-h-[65vh] overflow-auto">
            {loading && (
              <div className="p-6 text-center">
                <div className="w-6 h-6 border-2 border-violet-500/30 border-t-violet-400 rounded-full animate-spin mx-auto mb-2" />
                <span className="text-sm text-slate-500">Loading history...</span>
              </div>
            )}
            {!loading && filteredReceipts.length === 0 && (
              <div className="p-8 text-center">
                <p className="text-sm text-slate-500">
                  {receipts.length === 0 ? "No consent receipts yet" : "No receipts match filters"}
                </p>
              </div>
            )}
            {visibleReceipts.map((receipt) => (
              <div
                key={receipt.receipt_id}
                className="px-5 py-3.5 border-b border-white/[0.04] hover:bg-white/[0.02] transition-all duration-200 group"
              >
                <div className="flex items-center justify-between gap-3 mb-1.5">
                  <span className={`badge text-[11px] ${DECISION_STYLES[receipt.user_decision] || 'badge-neutral'}`}>
                    {receipt.user_decision === 'approve_redacted' ? 'Redacted' : receipt.user_decision}
                  </span>
                  <span className="text-[11px] text-slate-600">
                    {new Date(receipt.timestamp).toLocaleString()}
                  </span>
                </div>
                <div className="flex items-center justify-between gap-2">
                  <div className="text-xs text-slate-500 truncate">
                    <span className="text-slate-400">{receipt.provider}</span>
                    <span className="mx-1.5 text-slate-700">·</span>
                    <span className="font-mono">{receipt.memory_id.length > 16 ? receipt.memory_id.slice(0, 16) + '…' : receipt.memory_id}</span>
                  </div>
                  <button
                    type="button"
                    className="text-[11px] text-slate-600 hover:text-violet-300 transition-colors opacity-0 group-hover:opacity-100 whitespace-nowrap"
                    onClick={() => copyReceiptId(receipt.receipt_id)}
                  >
                    {copiedReceipt === receipt.receipt_id ? "✓ Copied" : "Copy ID"}
                  </button>
                </div>
              </div>
            ))}
            {!loading && visibleReceipts.length < filteredReceipts.length && (
              <div className="p-4 border-t border-white/[0.04]">
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => setVisibleReceiptsCount((count) => count + 60)}
                  className="w-full glass-subtle hover:bg-white/[0.04] text-xs"
                >
                  Load more ({filteredReceipts.length - visibleReceipts.length} remaining)
                </Button>
              </div>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}
