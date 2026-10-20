"use client";

import Link from "next/link";
import { useState } from "react";
import { Pill } from "@/components/ui";
import { api } from "@/lib/api";
import { useMeta } from "@/lib/meta";
import { ago, cx, people, pctSmart } from "@/lib/format";
import type { RunListItem } from "@/lib/types";

export function StatusPill({ status, progress }: { status: string; progress: number }) {
  if (status === "running" || status === "queued")
    return (
      <span className="inline-flex items-center gap-1.5 text-[13px] text-muted">
        <span className="live-dot size-1.5 rounded-full bg-live" aria-hidden />
        Running, <span className="num">{Math.round(progress * 100)}%</span>
      </span>
    );
  if (status === "failed") return <Pill tone="negative">Failed</Pill>;
  if (status === "cancelled") return <Pill>Stopped</Pill>;
  return <Pill tone="positive">Done</Pill>;
}

/** Simulations as rules and alignment: identity on the left, the answer right-aligned. */
export function RunTable({ runs, onDeleted, compact }: { runs: RunListItem[]; onDeleted?: (id: string) => void; compact?: boolean }) {
  const { countryName } = useMeta();
  const [confirm, setConfirm] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  return (
    <div className="overflow-hidden">
      <table className="w-full text-[14px]">
        <thead>
          <tr className="border-b border-border text-left text-[12px] text-faint">
            <th className="pb-2 font-normal">Simulation</th>
            <th className="hidden pb-2 font-normal md:table-cell">Countries</th>
            <th className="hidden pb-2 text-right font-normal sm:table-cell">People represented</th>
            <th className="pb-2 text-right font-normal">Answer</th>
            {!compact && <th className="hidden pb-2 pl-6 font-normal lg:table-cell">Status</th>}
            <th className="hidden pb-2 text-right font-normal sm:table-cell">Created</th>
            {onDeleted && <th className="w-24 pb-2" aria-label="Actions" />}
          </tr>
        </thead>
        <tbody>
          {runs.map((r) => (
            <tr key={r.id} className="group border-b border-rule last:border-0">
              <td className="max-w-0 py-2.5 pr-4">
                <Link href={`/runs/${r.id}`} className="block">
                  <span className="block truncate text-text group-hover:underline">{r.title}</span>
                  <span className="block truncate text-[12px] leading-4 text-faint md:hidden">{r.targets.map(countryName).join(", ")}</span>
                </Link>
              </td>
              <td className="hidden max-w-[220px] truncate py-2.5 pr-4 text-[13px] text-muted md:table-cell">{r.targets.map(countryName).join(", ") || "–"}</td>
              <td className="num hidden py-2.5 text-right text-muted sm:table-cell">{r.headline?.people ? people(r.headline.people) : "–"}</td>
              <td className="num py-2.5 text-right">{r.status === "done" && r.headline ? pctSmart(r.headline.value) : compact ? <StatusPill status={r.status} progress={r.progress} /> : "–"}</td>
              {!compact && (
                <td className="hidden py-2.5 pl-6 lg:table-cell">
                  <StatusPill status={r.status} progress={r.progress} />
                </td>
              )}
              <td className="hidden whitespace-nowrap py-2.5 pl-4 text-right text-[13px] text-muted sm:table-cell">{ago(r.created_at)}</td>
              {onDeleted && (
                <td className="py-2.5 pl-3 text-right">
                  {confirm === r.id ? (
                    <span className="inline-flex gap-1">
                      <button
                        className="rounded px-1.5 py-0.5 text-[13px] font-medium text-negative hover:bg-[var(--pill-negative-bg)]"
                        disabled={busy === r.id}
                        onClick={async () => {
                          setBusy(r.id);
                          await api.deleteRun(r.id).catch(() => {});
                          setBusy(null);
                          setConfirm(null);
                          onDeleted(r.id);
                        }}
                      >
                        Delete
                      </button>
                      <button className="rounded px-1.5 py-0.5 text-[13px] text-muted hover:bg-active" onClick={() => setConfirm(null)}>
                        Keep
                      </button>
                    </span>
                  ) : (
                    <button
                      className={cx("rounded px-1.5 py-0.5 text-[13px] text-muted opacity-0 hover:bg-active hover:text-text focus:opacity-100 group-hover:opacity-100")}
                      onClick={() => setConfirm(r.id)}
                      aria-label={`Delete ${r.title}`}
                    >
                      Delete
                    </button>
                  )}
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
