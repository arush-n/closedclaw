"use client";

import { motion } from "framer-motion";

interface ChatOrbProps {
  size?: number;
  className?: string;
}

function sizeClass(size: number, fallback: string): string {
  if (size >= 180) return "w-[200px] h-[200px]";
  if (size >= 72) return "w-[80px] h-[80px]";
  if (size >= 22) return "w-6 h-6";
  return fallback;
}

export function ChatOrb({ size = 200, className = "" }: ChatOrbProps) {
  const orbSizeClass = sizeClass(size, "w-[200px] h-[200px]");

  return (
    <div className={`flex items-center justify-center ${orbSizeClass} ${className}`}>
      <div className={`rounded-full relative overflow-hidden ${orbSizeClass} shadow-[inset_6px_12px_24px_0_rgba(10,14,20,0.8)]`}>
        <motion.div
          className="absolute inset-0 rounded-full blur-[8px] bg-[conic-gradient(from_0deg,hsl(260,94%,59%)_0%,hsl(280,90%,50%)_25%,hsl(300,85%,45%)_50%,hsl(260,94%,59%)_75%,hsl(240,90%,65%)_100%)]"
          animate={{ rotate: 360 }}
          transition={{
            duration: 12,
            ease: "linear",
            repeat: Infinity,
          }}
        />
        <div className="absolute inset-[3px] rounded-full bg-zinc-950/90 backdrop-blur-sm shadow-[inset_0_2px_20px_rgba(0,0,0,0.5)]" />
        <motion.div
          className="absolute inset-[6px] rounded-full bg-[radial-gradient(circle_at_30%_30%,rgba(147,51,234,0.3)_0%,transparent_50%)]"
          animate={{
            opacity: [0.5, 0.8, 0.5],
            scale: [1, 1.05, 1],
          }}
          transition={{
            duration: 3,
            ease: "easeInOut",
            repeat: Infinity,
          }}
        />
      </div>
    </div>
  );
}

export function ChatOrbSmall({
  size = 24,
  className = "",
}: {
  size?: number;
  className?: string;
}) {
  const orbSizeClass = sizeClass(size, "w-6 h-6");

  return (
    <div className={`flex items-center justify-center ${orbSizeClass} ${className}`}>
      <motion.div
        className={`rounded-full ${orbSizeClass} bg-[radial-gradient(circle_at_40%_40%,hsl(260,94%,65%)_0%,hsl(260,94%,45%)_50%,hsl(260,94%,35%)_100%)] shadow-[0_0_12px_rgba(147,51,234,0.4),inset_0_3px_6px_rgba(255,255,255,0.1)]`}
        animate={{
          scale: [1, 1.1, 1],
          opacity: [0.8, 1, 0.8],
        }}
        transition={{
          duration: 2,
          ease: "easeInOut",
          repeat: Infinity,
        }}
      />
    </div>
  );
}
