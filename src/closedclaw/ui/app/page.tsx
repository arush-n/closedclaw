"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function HomePage() {
  const router = useRouter();
  
  useEffect(() => {
    router.push("/graph");
  }, [router]);

  return (
    <div className="min-h-screen bg-zinc-950 flex items-center justify-center">
      <div className="text-center">
        <div className="w-12 h-12 border-4 border-zinc-700 border-t-primary rounded-full animate-spin mx-auto mb-4" />
        <p className="text-zinc-400">Loading...</p>
      </div>
    </div>
  );
}
