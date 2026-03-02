"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { ConsentCenter } from "@/components/consent/consent-center";

const links = [
  { href: "/graph", label: "Graph", icon: "◈" },
  { href: "/vault", label: "Vault", icon: "◇" },
  { href: "/audit", label: "Audit", icon: "◎" },
  { href: "/policies", label: "Policies", icon: "◆" },
  { href: "/insights", label: "Insights", icon: "◉" },
  { href: "/chat", label: "Chat", icon: "◌" },
];

interface AppShellProps {
  children: React.ReactNode;
}

export function AppShell({ children }: AppShellProps) {
  const pathname = usePathname();
  const [connected, setConnected] = useState(false);
  const [checkedAt, setCheckedAt] = useState<Date | null>(null);

  useEffect(() => {
    let mounted = true;

    const refreshStatus = async () => {
      try {
        const response = await fetch("/api/status", { cache: "no-store" });
        const data = await response.json();
        if (mounted) {
          setConnected(Boolean(data.connected));
          setCheckedAt(new Date());
        }
      } catch {
        if (mounted) {
          setConnected(false);
          setCheckedAt(new Date());
        }
      }
    };

    refreshStatus();
    const interval = window.setInterval(refreshStatus, 5000);

    return () => {
      mounted = false;
      window.clearInterval(interval);
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
              const active = pathname === item.href;
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
          </div>
        </div>
      </header>

      <div className="animate-fade-in">{children}</div>
    </div>
  );
}
