"use client";

import { useEffect, useState } from "react";
import { RunTable } from "@/components/run/RunTable";
import { Empty, ErrorNote, LinkButton, Spinner } from "@/components/ui";
import { api } from "@/lib/api";
import type { RunListItem } from "@/lib/types";

export default function RunsPage() {
  const [runs, setRuns] = useState<RunListItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    const load = () => api.runs().then((r) => alive && setRuns(r)).catch((e) => alive && setError(e.message));
    load();
    const t = setInterval(load, 4000);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, []);

  return (
    <div className="mx-auto max-w-[1000px] px-4 py-8 md:px-8 md:py-12">
      <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
        <h1 className="t-1">Runs</h1>
        <LinkButton href="/" variant="primary">
          New simulation
        </LinkButton>
      </div>
      {error && <ErrorNote>{error}</ErrorNote>}
      {!runs && !error && (
        <div className="flex items-center gap-2 text-sm text-ink-3">
          <Spinner className="size-4" /> Loading
        </div>
      )}
      {runs && runs.length === 0 && (
        <Empty title="No runs yet" action={<LinkButton href="/" variant="primary">Start a simulation</LinkButton>}>
          Describe what you want to predict and Oracle will simulate it. Every run is saved here.
        </Empty>
      )}
      {runs && runs.length > 0 && <RunTable runs={runs} />}
    </div>
  );
}
