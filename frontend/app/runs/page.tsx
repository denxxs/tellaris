"use client";

import { useEffect, useMemo, useState } from "react";
import { RunTable } from "@/components/run/RunTable";
import { Card, Empty, ErrorNote, Input, LinkButton, PageHead, Skeleton } from "@/components/ui";
import { api } from "@/lib/api";
import type { RunListItem } from "@/lib/types";

export default function RunsPage() {
  const [runs, setRuns] = useState<RunListItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [q, setQ] = useState("");

  useEffect(() => {
    let alive = true;
    const load = () =>
      api
        .runs()
        .then((r) => {
          if (!alive) return;
          setRuns(r);
          setError(null);
        })
        .catch((e) => alive && setError(e.message));
    load();
    const t = setInterval(load, 4000);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, []);

  const shown = useMemo(() => {
    const t = q.trim().toLowerCase();
    return (runs ?? []).filter((r) => !t || `${r.title} ${r.prompt} ${r.targets.join(" ")}`.toLowerCase().includes(t));
  }, [runs, q]);
  const running = (runs ?? []).filter((r) => r.status === "running" || r.status === "queued").length;

  return (
    <div className="mx-auto max-w-[1312px] px-4 py-6 md:px-6">
      <PageHead
        title="Simulations"
        actions={
          <LinkButton href="/" variant="primary">
            New simulation
          </LinkButton>
        }
      >
        {runs ? `${runs.length} saved${running ? `, ${running} running now` : ""}.` : "Loading your simulations."}
      </PageHead>
      {error && (
        <div className="mb-4">
          <ErrorNote>{error}</ErrorNote>
        </div>
      )}
      <Card>
        <div className="mb-4 max-w-sm">
          <Input placeholder="Filter by title, question or country code" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Filter simulations" />
        </div>
        {!runs && !error ? (
          <div className="flex flex-col gap-3">
            {[0, 1, 2, 3].map((i) => (
              <Skeleton key={i} className="h-6" />
            ))}
          </div>
        ) : runs && runs.length === 0 ? (
          <Empty title="No simulations yet" action={<LinkButton href="/" variant="primary">Start one</LinkButton>}>
            Describe what you want to predict and Tellaris simulates it. Every run is saved here.
          </Empty>
        ) : shown.length === 0 ? (
          <p className="text-[13px] text-muted">No simulation matches “{q}”.</p>
        ) : (
          <RunTable runs={shown} onDeleted={(id) => setRuns((rs) => (rs ?? []).filter((r) => r.id !== id))} />
        )}
      </Card>
    </div>
  );
}
