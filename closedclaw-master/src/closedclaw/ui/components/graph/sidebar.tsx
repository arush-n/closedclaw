"use client";

import { memo } from "react";
import { motion } from "framer-motion";
import {
  Plus,
  FileText,
  User,
  Settings,
  Brain,
  Bot,
} from "lucide-react";

interface SidebarProps {
  onAddMemory?: () => void;
  onViewVault?: () => void;
  onViewProfile?: () => void;
  onViewInsights?: () => void;
  onViewAgent?: () => void;
  onOpenSettings?: () => void;
  activeView?: string;
}

export const Sidebar = memo<SidebarProps>(function Sidebar({
  onAddMemory,
  onViewVault,
  onViewProfile,
  onViewInsights,
  onViewAgent,
  onOpenSettings,
  activeView,
}) {
  const items = [
    {
      id: "add",
      icon: Plus,
      label: "Add Memory",
      onClick: onAddMemory,
    },
    {
      id: "documents",
      icon: FileText,
      label: "Vault",
      onClick: onViewVault,
    },
    {
      id: "profile",
      icon: User,
      label: "Profile",
      onClick: onViewProfile,
    },
    {
      id: "insights",
      icon: Brain,
      label: "Insights",
      onClick: onViewInsights,
    },
    {
      id: "agent",
      icon: Bot,
      label: "ClawdBot",
      onClick: onViewAgent,
    },
  ];

  return (
    <motion.div
      initial={{ opacity: 0, x: -20 }}
      animate={{ opacity: 1, x: 0 }}
      className="absolute left-4 top-3 z-20"
    >
      <div className="flex flex-col py-1 gap-1.5">
          {items.map((item) => {
            const Icon = item.icon;
            const isActive = activeView === item.id;

            return (
              <button
                key={item.id}
                onClick={item.onClick}
                disabled={!item.onClick}
                className={`relative p-3 transition-colors group ${
                  isActive
                    ? "text-slate-100 bg-slate-800/40 rounded-lg"
                    : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/25 rounded-lg"
                } ${!item.onClick ? "opacity-50 cursor-not-allowed" : ""}`}
                title={item.label}
              >
                <Icon className="w-5 h-5" />
                
                {/* Tooltip */}
                <div className="absolute left-full ml-2 px-2 py-1 bg-slate-900/90 border border-slate-700/40 text-slate-200 text-xs rounded whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none">
                  {item.label}
                </div>

                {/* Active indicator */}
                {isActive && (
                  <motion.div
                    layoutId="sidebar-indicator"
                    className="absolute left-0 top-1/2 -translate-y-1/2 w-0.5 h-5 bg-slate-200 rounded-r"
                  />
                )}
              </button>
            );
          })}
        

        {/* Settings button at bottom */}
        <div className="pt-1.5 mt-1.5 border-t border-slate-700/40">
          <button
            onClick={onOpenSettings}
            className="w-full p-3 text-slate-400 hover:text-slate-200 hover:bg-slate-800/25 rounded-lg transition-colors"
            title="Settings"
          >
            <Settings className="w-5 h-5" />
          </button>
        </div>
      </div>
    </motion.div>
  );
});

Sidebar.displayName = "Sidebar";
