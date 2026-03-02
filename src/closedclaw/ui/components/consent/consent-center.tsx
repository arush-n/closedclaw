"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Bell, ShieldCheck, X } from "lucide-react";
import { Button } from "@/components/ui/button";

interface PendingConsent {
  request_id: string;
  memory_id: string;
  memory_text: string;
  sensitivity: number;
  provider: string;
  rule_triggered: string;
  created_at: string;
}

interface ConsentReceiptsResponse {
  receipts: Array<{
    receipt_id: string;
    memory_id: string;
    provider: string;
    user_decision: "approve" | "approve_redacted" | "deny";
    timestamp: string;
  }>;
}

function getWsBaseUrl(): string {
  const env =
    process.env.NEXT_PUBLIC_CLOSEDCLAW_API_URL ||
    process.env.NEXT_PUBLIC_MEM0_API_URL ||
    "http://localhost:8765";
  if (env.startsWith("https://")) return env.replace("https://", "wss://");
  return env.replace("http://", "ws://");
}

function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("closedclaw-token") || null;
}

export function ConsentCenter() {
  const [pending, setPending] = useState<PendingConsent[]>([]);
  const [receipts, setReceipts] = useState<ConsentReceiptsResponse["receipts"]>([]);
  const [isOpen, setIsOpen] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copiedReceipt, setCopiedReceipt] = useState<string | null>(null);

  const nextPending = useMemo(() => pending[0], [pending]);

  const copyReceiptId = useCallback((id: string) => {
    navigator.clipboard.writeText(id).then(() => {
      setCopiedReceipt(id);
      setTimeout(() => setCopiedReceipt(null), 2000);
    });
  }, []);

  const loadPending = useCallback(async () => {
    try {
      const response = await fetch("/api/consent/pending", { cache: "no-store" });
      const data = await response.json();
      setPending(Array.isArray(data.pending) ? data.pending : []);
    } catch {
      setPending([]);
    }
  }, []);

  const loadReceipts = useCallback(async () => {
    try {
      const response = await fetch("/api/consent/receipts?limit=20", { cache: "no-store" });
      const data: ConsentReceiptsResponse = await response.json();
      setReceipts(Array.isArray(data.receipts) ? data.receipts : []);
    } catch {
      setReceipts([]);
    }
  }, []);

  useEffect(() => {
    loadPending();
  }, [loadPending]);

  useEffect(() => {
    if (!isOpen) return;
    loadReceipts();
  }, [isOpen, loadReceipts]);

  useEffect(() => {
    const token = getToken();
    if (!token) {
      return;
    }

    const ws = new WebSocket(`${getWsBaseUrl()}/ws/consent?token=${encodeURIComponent(token)}`);
    ws.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data);
        if (payload.event === "consent_required") {
          loadPending();
          setIsOpen(true);
        }
      } catch {
        // no-op
      }
    };

    return () => {
      ws.close();
    };
  }, [loadPending]);

  const submitDecision = useCallback(
    async (decision: "approve" | "approve_redacted" | "deny") => {
      if (!nextPending) return;
      setIsSubmitting(true);
      setError(null);

      try {
        const response = await fetch(`/api/consent/${nextPending.request_id}`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ decision }),
        });

        if (!response.ok) {
          const data = await response.json();
          throw new Error(data?.detail || data?.error || "Unable to submit decision");
        }

        await Promise.all([loadPending(), loadReceipts()]);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to submit decision");
      } finally {
        setIsSubmitting(false);
      }
    },
    [loadPending, loadReceipts, nextPending]
  );

  return (
    <>
      <Button
        variant="ghost"
        size="sm"
        onClick={() => setIsOpen(true)}
        className="relative text-slate-300 hover:text-white hover:bg-white/[0.06] rounded-lg transition-all duration-200"
      >
        <Bell className="w-4 h-4 mr-2" />
        Consent
        {pending.length > 0 && (
          <span className="ml-2 inline-flex h-5 min-w-5 items-center justify-center rounded-full bg-red-500/80 px-1.5 text-[10px] font-bold text-white shadow-[0_0_8px_rgba(239,68,68,0.4)]">
            {pending.length}
          </span>
        )}
      </Button>

      {isOpen && (
        <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-md flex items-center justify-center p-4">
          <div className="w-full max-w-3xl glass-card rounded-2xl p-6 animate-fade-in">
            <div className="flex items-center justify-between mb-5">
              <div className="flex items-center gap-3">
                <div className="w-9 h-9 rounded-xl bg-violet-500/15 border border-violet-500/25 flex items-center justify-center">
                  <ShieldCheck className="w-4.5 h-4.5 text-violet-400" />
                </div>
                <h2 className="text-lg font-semibold text-slate-100">Consent Notifications</h2>
              </div>
              <button
                onClick={() => setIsOpen(false)}
                className="p-2 rounded-lg hover:bg-white/[0.06] text-slate-400 hover:text-white transition-all duration-200"
                aria-label="Close consent modal"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {nextPending ? (
              <div className="space-y-4">
                <div className="rounded-xl glass-subtle p-4">
                  <div className="flex items-center gap-3 text-sm text-slate-400 mb-3 flex-wrap">
                    <span className="badge badge-neutral">
                      <ShieldCheck className="w-3 h-3 mr-1.5" />
                      {nextPending.rule_triggered}
                    </span>
                    <span className="badge badge-primary">{nextPending.provider}</span>
                    <span className="badge badge-warning">L{nextPending.sensitivity}</span>
                  </div>
                  <p className="text-sm text-slate-200 whitespace-pre-wrap leading-relaxed">{nextPending.memory_text}</p>
                </div>

                {error && <div className="text-sm text-red-400 glass-subtle rounded-lg px-3 py-2 border-red-500/20">{error}</div>}

                <div className="flex flex-wrap gap-2">
                  <Button disabled={isSubmitting} onClick={() => submitDecision("approve")} className="bg-emerald-500/15 hover:bg-emerald-500/25 text-emerald-300 border border-emerald-500/25 hover:border-emerald-500/40">Approve</Button>
                  <Button
                    disabled={isSubmitting}
                    variant="secondary"
                    onClick={() => submitDecision("approve_redacted")}
                    className="bg-amber-500/15 hover:bg-amber-500/25 text-amber-300 border border-amber-500/25 hover:border-amber-500/40"
                  >
                    Approve Redacted
                  </Button>
                  <Button
                    disabled={isSubmitting}
                    variant="outline"
                    onClick={() => submitDecision("deny")}
                    className="bg-red-500/10 hover:bg-red-500/20 text-red-300 border-red-500/25 hover:border-red-500/40"
                  >
                    Deny
                  </Button>
                </div>
              </div>
            ) : (
              <div className="rounded-xl glass-subtle p-6 text-center">
                <ShieldCheck className="w-8 h-8 text-emerald-400/50 mx-auto mb-2" />
                <p className="text-sm text-slate-400">No pending consent requests.</p>
              </div>
            )}

            <div className="mt-6 pt-5 border-t border-white/[0.06]">
              <h3 className="text-sm font-medium text-slate-300 mb-3 flex items-center gap-2">
                <span className="w-1.5 h-1.5 rounded-full bg-violet-400" />
                Recent Decisions
              </h3>
              <div className="max-h-48 overflow-auto rounded-xl glass-subtle">
                {receipts.length === 0 ? (
                  <div className="p-4 text-sm text-slate-500 text-center">No receipts yet.</div>
                ) : (
                  receipts.map((receipt) => (
                    <div
                      key={receipt.receipt_id}
                      className="p-3.5 border-b border-white/[0.04] last:border-b-0 text-sm hover:bg-white/[0.02] transition-colors"
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className={`badge text-xs ${receipt.user_decision === 'deny' ? 'badge-danger' : receipt.user_decision === 'approve_redacted' ? 'badge-warning' : 'badge-success'}`}>
                          {receipt.user_decision}
                        </span>
                        <span className="text-xs text-slate-500">{new Date(receipt.timestamp).toLocaleString()}</span>
                      </div>
                      <div className="text-xs text-slate-500 mt-1.5 flex items-center justify-between">
                        <span>{receipt.provider} · {receipt.memory_id.slice(0, 12)}…</span>
                        <button
                          type="button"
                          className="text-xs text-slate-500 hover:text-violet-300 transition-colors"
                          onClick={() => copyReceiptId(receipt.receipt_id)}
                        >
                          {copiedReceipt === receipt.receipt_id ? "✓ Copied" : "Copy ID"}
                        </button>
                      </div>
                    </div>
                  ))
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
