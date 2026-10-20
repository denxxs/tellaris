"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { API } from "@/lib/api";

/** Tells the user when the server is down or when runs use the offline demo model. */
export function ModeBanner() {
  const [state, setState] = useState<"ok" | "mock" | "down" | null>(null);

  useEffect(() => {
    let alive = true;
    const check = () =>
      fetch(`${API}/api/health`, { cache: "no-store" })
        .then((r) => r.json())
        .then((h) => alive && setState(h.mock ? "mock" : "ok"))
        .catch(() => alive && setState("down"));
    check();
    const t = setInterval(check, 15000);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, []);

  if (state === "down")
    return (
      <div role="status" className="border-b border-no/30 bg-no-soft px-5 py-2.5 text-sm text-ink">
        The simulation server isn&apos;t running. Start it with <code className="rounded bg-panel px-1.5 py-0.5 text-[13px]">cd backend && python -m oracle</code>
      </div>
    );
  if (state === "mock")
    return (
      <div role="status" className="flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-line bg-panel px-5 py-2.5 text-sm text-ink-2">
        <span className="inline-block size-2 rounded-full bg-live" aria-hidden />
        Demo mode: runs use an offline stand-in model, so results show how the product works but aren&apos;t predictions.
        <Link href="/settings" className="font-semibold text-iris-ink underline-offset-4 hover:underline">
          Connect a model
        </Link>
      </div>
    );
  return null;
}
