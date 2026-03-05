"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { ConsentCenter } from "@/components/consent/consent-center";
import { Power } from "lucide-react";

const links = [
  { href: "/graph", label: "Graph", icon: "◈" },
  { href: "/vault", label: "Vault", icon: "◇" },
  { href: "/memories", label: "Memories", icon: "◫" },
  { href: "/apps", label: "Apps", icon: "◧" },
  { href: "/audit", label: "Audit", icon: "◎" },
  { href: "/policies", label: "Policies", icon: "◆" },
  { href: "/insights", label: "Insights", icon: "◉" },
  { href: "/chat", label: "Chat", icon: "◌" },
  { href: "/swarm", label: "Swarm", icon: "⬡" },
  { href: "/settings", label: "Settings", icon: "⚙" },
];

interface AppShellProps {
  children: React.ReactNode;
}

export function AppShell({ children }: AppShellProps) {
  const pathname = usePathname();
  const [connected, setConnected] = useState(false);
  const [checkedAt, setCheckedAt] = useState<Date | null>(null);
  const failuresRef = useRef(0);

  // Shutdown state
  const [showShutdown, setShowShutdown] = useState(false);
  const [shutdownPassword, setShutdownPassword] = useState("");
  const [shutdownError, setShutdownError] = useState("");
  const [shuttingDown, setShuttingDown] = useState(false);

  const handleShutdown = async () => {
    if (!shutdownPassword.trim()) {
      setShutdownError("Password required");
      return;
    }
    setShuttingDown(true);
    setShutdownError("");
    try {
      const res = await fetch("/api/shutdown", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ password: shutdownPassword }),
      });
      const data = await res.json();
      if (!res.ok) {
        setShutdownError(data.detail || data.error || "Shutdown failed");
        setShuttingDown(false);
        return;
      }
      setConnected(false);
    } catch {
      setShutdownError("Connection lost — server may have shut down");
      setConnected(false);
    }
  };

  useEffect(() => {
    let mounted = true;
    let timer: ReturnType<typeof setTimeout>;
    const BASE_MS = 5_000;
    const MAX_MS = 60_000;

    const refreshStatus = async () => {
      try {
        const response = await fetch("/api/status", { cache: "no-store" });
        const data = await response.json();
        if (mounted) {
          setConnected(Boolean(data.connected));
          setCheckedAt(new Date());
          failuresRef.current = 0;
        }
      } catch {
        if (mounted) {
          setConnected(false);
          setCheckedAt(new Date());
          failuresRef.current++;
        }
      }
      if (mounted) {
        const delay = Math.min(BASE_MS * 2 ** failuresRef.current, MAX_MS);
        timer = setTimeout(refreshStatus, delay);
      }
    };

    refreshStatus();
    return () => {
      mounted = false;
      clearTimeout(timer);
    };
  }, []);

  return (
    <div className="min-h-screen text-slate-100">
      <header className="sticky top-0 z-40 backdrop-blur-xl border-b border-white/[0.06]" style={{ background: 'rgba(10, 12, 20, 0.82)' }}>
        <div className="max-w-7xl mx-auto px-6 py-3 flex items-center justify-between gap-4">
          {/* Logo */}
          <Link href="/graph" className="flex items-center gap-3 group">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-violet-500/20 to-blue-500/20 border border-violet-500/30 flex items-center justify-center text-xs font-bold text-violet-300 group-hover:border-violet-400/50 group-hover:shadow-[0_0_12px_rgba(139,92,246,0.2)] transition-all duration-300">
              CC
            </div>
            <span className="font-semibold tracking-tight text-slate-200 group-hover:text-white transition-colors">
              closedclaw
            </span>
          </Link>

          {/* Navigation */}
          <nav className="flex items-center gap-0.5 glass-subtle rounded-xl px-1 py-1">
            {links.map((item) => {
              const active = pathname === item.href ||
                (item.href.length > 1 && pathname.startsWith(item.href + "/"));
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={`px-3.5 py-1.5 rounded-lg text-sm font-medium transition-all duration-200 ${
                    active
                      ? "bg-white/[0.08] text-white shadow-sm border border-white/[0.08]"
                      : "text-slate-400 hover:text-slate-200 hover:bg-white/[0.04]"
                  }`}
                >
                  {item.label}
                </Link>
              );
            })}
          </nav>

          {/* Status & Consent */}
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2">
              <div className={`w-2 h-2 rounded-full ${connected ? "bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.5)]" : "bg-red-400 shadow-[0_0_8px_rgba(248,113,113,0.5)]"} animate-pulse-glow`} />
              <div className="text-right">
                <div className={`text-xs font-medium ${connected ? "text-emerald-300" : "text-red-300"}`}>
                  {connected ? "Connected" : "Disconnected"}
                </div>
                <div className="text-[10px] text-slate-500">
                  {checkedAt ? checkedAt.toLocaleTimeString() : "checking..."}
                </div>
              </div>
            </div>
            <div className="w-px h-6 bg-white/[0.06]" />
            <ConsentCenter />
            <div className="w-px h-6 bg-white/[0.06]" />
            <button
              onClick={() => { setShowShutdown(true); setShutdownError(""); setShutdownPassword(""); }}
              className="p-1.5 rounded-lg text-slate-400 hover:text-red-400 hover:bg-red-500/10 transition-all duration-200"
              title="Shutdown server"
            >
              <Power className="w-4 h-4" />
            </button>
          </div>
        </div>
      </header>

      {/* Shutdown dialog */}
      {showShutdown && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          <div
            className="absolute inset-0 bg-black/60 backdrop-blur-sm"
            onClick={() => !shuttingDown && setShowShutdown(false)}
          />
          <div className="relative glass-card rounded-2xl p-6 w-full max-w-sm space-y-4 border border-white/[0.08] shadow-2xl">
            <div className="flex items-center gap-3">
              <div className="p-2 rounded-lg bg-red-500/10 border border-red-500/20">
                <Power className="w-5 h-5 text-red-400" />
              </div>
              <div>
                <h3 className="font-semibold text-white">Shutdown Server</h3>
                <p className="text-xs text-slate-400">This will stop all closedclaw services</p>
              </div>
            </div>

            <div className="space-y-2">
              <label className="text-sm text-slate-400">Shutdown password</label>
              <input
                type="password"
                value={shutdownPassword}
                onChange={(e) => setShutdownPassword(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleShutdown()}
                placeholder="Enter shutdown password"
                className="glass-input rounded-lg px-3 py-2 text-sm w-full"
                autoFocus
                disabled={shuttingDown}
              />
              <p className="text-[11px] text-slate-500">
                Check server logs or run: <code className="text-violet-400">docker logs closedclaw-server 2&gt;&amp;1 | grep &quot;SHUTDOWN PASSWORD&quot;</code>
              </p>
            </div>

            {shutdownError && (
              <p className="text-sm text-red-400">{shutdownError}</p>
            )}

            <div className="flex gap-2 pt-2">
              <button
                onClick={handleShutdown}
                disabled={shuttingDown}
                className="flex-1 px-4 py-2 rounded-lg text-sm font-medium bg-red-500/20 text-red-300 border border-red-500/30 hover:bg-red-500/30 transition-colors disabled:opacity-50"
              >
                {shuttingDown ? "Shutting down..." : "Shutdown"}
              </button>
              <button
                onClick={() => setShowShutdown(false)}
                disabled={shuttingDown}
                className="px-4 py-2 rounded-lg text-sm font-medium text-slate-400 hover:text-slate-200 hover:bg-white/[0.04] transition-colors disabled:opacity-50"
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}

      <div className="animate-fade-in">{children}</div>
    </div>
  );
}
