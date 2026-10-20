"use client";

import Link from "next/link";
import { use, useEffect, useMemo, useState } from "react";
import { Answer, Counters, StageList, Ticker } from "@/components/run/Live";
import { ResultTabs } from "@/components/run/ResultTabs";
import { Button, Chip, ErrorNote, Meter } from "@/components/ui";
import { WorldMap, type MapAgent } from "@/components/world/WorldMap";
import { api } from "@/lib/api";
import { cx } from "@/lib/format";
import type { Meta } from "@/lib/types";
import { useRunStream } from "@/lib/useRunStream";

export default function RunPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const live = useRunStream(id);
  const [meta, setMeta] = useState<Meta | null>(null);
  const [stopping, setStopping] = useState(false);

  useEffect(() => {
    api.meta().then(setMeta).catch(() => {});
  }, []);

  const agents: MapAgent[] = useMemo(
    () =>
      live.order.map((pid) => {
        const p = live.personas[pid];
        const s = live.scores[pid];
        return { id: pid, country: p.country, voice: p.voice, p: s?.length ? s.reduce((a, b) => a + b, 0) / s.length : null };
      }),
    [live.order, live.personas, live.scores],
  );

  const running = live.status === "live" || live.status === "connecting" || live.run?.status === "running" || live.run?.status === "queued";
  const isRunning = running && live.status !== "done" && live.status !== "failed" && live.status !== "cancelled";
  const title = live.spec?.title ?? live.run?.title ?? "Simulation";
  // The stage in progress, or the next one waiting to start.
  const stageLabel = (() => {
    const order = meta?.stages ?? [];
    const active = order.find((s) => live.stages[s.id]?.status === "start");
    if (active) return active.label;
    const next = order.find((s) => !live.stages[s.id]);
    return next?.label;
  })();
  const cname = useMemo(() => Object.fromEntries((meta?.countries ?? []).map((c) => [c.iso3, c.name])), [meta]);

  useEffect(() => {
    document.title = `${title} | Oracle`;
  }, [title]);

  return (
    <div className="mx-auto max-w-[1320px] px-4 py-6 md:px-8 md:py-8">
      <header className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <Link href="/runs" className="t-small font-semibold text-ink-3 hover:text-ink">
            All runs
          </Link>
          <h1 className="t-1 mt-1">{title}</h1>
          <div className="mt-2 flex flex-wrap items-center gap-1.5">
            {(live.spec?.targets ?? []).map((t) => (
              <Chip key={t} tone="iris">
                {cname[t] ?? t}
              </Chip>
            ))}
            {live.run?.parent_id && (
              <Link href={`/runs/${live.run.parent_id}`} className="ml-1 t-small font-semibold text-iris-ink hover:underline">
                Compared with the original
              </Link>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2">
          {isRunning ? (
            <Button
              variant="secondary"
              busy={stopping}
              onClick={async () => {
                setStopping(true);
                await api.cancel(id).catch(() => {});
              }}
            >
              Stop
            </Button>
          ) : (
            live.status === "done" && (
              <a href={api.exportUrl(id)} className="inline-flex h-10 items-center rounded-[10px] border border-line-strong bg-panel px-4 text-sm font-semibold text-ink hover:border-ink-3">
                Download data
              </a>
            )
          )}
        </div>
      </header>

      {(live.status === "failed" || live.status === "cancelled") && (
        <div className="mb-6">
          <ErrorNote>
            {live.status === "cancelled" ? "This run was stopped." : <>This run failed: {live.error ?? live.run?.error}</>}
            {live.status === "failed" && (
              <span className="block t-small text-ink-2">
                Check the models in <Link href="/settings" className="font-semibold text-iris-ink underline">Models</Link>, then run it again from the home page.
              </span>
            )}
          </ErrorNote>
        </div>
      )}

      {live.results && (
        <section className="mb-8 rounded-3xl border border-line bg-panel p-6 md:p-8">
          <Answer live={live} />
        </section>
      )}

      <section className={cx("grid items-start gap-6", isRunning ? "lg:grid-cols-[minmax(0,1fr)_340px]" : "")}>
        <div className="overflow-hidden rounded-3xl border border-line bg-panel">
          {isRunning && (
            <div className="flex flex-wrap items-center gap-x-4 gap-y-2 border-b border-line px-5 py-3">
              <span className="inline-flex items-center gap-2 text-sm font-semibold text-ink">
                <span className="live-dot inline-block size-2 rounded-full bg-live" aria-hidden />
                {stageLabel ?? "Starting"}
              </span>
              <Meter value={live.progress} className="min-w-[120px] flex-1" />
              <span className="num t-small text-ink-3">{Math.round(live.progress * 100)}%</span>
            </div>
          )}
          <WorldMap world={live.world} targets={live.spec?.targets ?? []} agents={agents} />
          <div className="flex flex-wrap items-center gap-x-5 gap-y-1 border-t border-line px-5 py-3 t-small text-ink-2">
            <span className="inline-flex items-center gap-1.5">
              <span className="inline-block size-2.5 rounded-full bg-yes" aria-hidden /> Leaning yes
            </span>
            <span className="inline-flex items-center gap-1.5">
              <span className="inline-block size-2.5 rounded-full bg-mid" aria-hidden /> Unsure
            </span>
            <span className="inline-flex items-center gap-1.5">
              <span className="inline-block size-2.5 rounded-full bg-no" aria-hidden /> Leaning no
            </span>
            <span className="inline-flex items-center gap-1.5">
              <span className="inline-block size-2.5 rounded-full border border-iris" aria-hidden /> Outside voice
            </span>
            <span className="ml-auto">{agents.length.toLocaleString()} people</span>
          </div>
        </div>
        {isRunning && (
          <aside className="flex flex-col gap-6">
            <StageList live={live} meta={meta} />
            <Counters live={live} />
            <Ticker live={live} />
          </aside>
        )}
      </section>

      {live.results && (
        <div className="mt-10">
          <ResultTabs id={id} live={live} meta={meta} />
        </div>
      )}
    </div>
  );
}
