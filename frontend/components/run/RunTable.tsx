"use client";

import Link from "next/link";
import { ago, pctSmart } from "@/lib/format";
import type { RunListItem } from "@/lib/types";

export function RunTable({ runs }: { runs: RunListItem[] }) {
  return (
    <div className="overflow-hidden rounded-2xl border border-line bg-panel">
      <table className="w-full text-sm">
        <thead className="sr-only">
          <tr>
            <th>Run</th>
            <th>Answer</th>
            <th>When</th>
          </tr>
        </thead>
        <tbody>
          {runs.map((r) => (
            <tr key={r.id} className="border-b border-line last:border-0 hover:bg-panel-2">
              <td className="max-w-0 py-3 pl-5 pr-3">
                <Link href={`/runs/${r.id}`} className="block">
                  <span className="block truncate font-semibold text-ink">{r.title}</span>
                  <span className="block truncate t-small text-ink-3">{r.targets.join(", ") || "Choosing countries"}</span>
                </Link>
              </td>
              <td className="w-40 px-3 text-right">
                {r.status === "done" && r.headline ? (
                  <span className="num font-display text-lg font-bold">{pctSmart(r.headline.value)}</span>
                ) : (
                  <StatusLabel status={r.status} progress={r.progress} />
                )}
              </td>
              <td className="hidden w-32 pr-5 text-right t-small text-ink-3 sm:table-cell">{ago(r.created_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function StatusLabel({ status, progress }: { status: string; progress: number }) {
  if (status === "running" || status === "queued")
    return (
      <span className="inline-flex items-center gap-2 t-small font-semibold text-ink-2">
        <span className="live-dot inline-block size-2 rounded-full bg-live" aria-hidden />
        {Math.round(progress * 100)}%
      </span>
    );
  if (status === "failed") return <span className="t-small font-semibold text-no">Failed</span>;
  if (status === "cancelled") return <span className="t-small text-ink-3">Stopped</span>;
  return <span className="t-small text-ink-3">{status}</span>;
}
