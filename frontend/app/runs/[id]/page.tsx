"use client";

import { AnimatePresence } from "motion/react";
import Link from "next/link";
import { use, useCallback, useEffect, useMemo, useState } from "react";
import { CommitteesTab, CountriesTab, GroupsTab, InfluenceTab, MethodTab, PricingTab, ReasonsTab } from "@/components/run/Details";
import { SocietyTab } from "@/components/run/Society";
import { AskGroup, type GroupPreset } from "@/components/run/AskGroup";
import { KnowledgeGraphTab } from "@/components/run/KnowledgeGraph";
import { TrackButton } from "@/components/run/TrackButton";
import { WhereItWorks } from "@/components/run/WhereItWorks";
import { Overview } from "@/components/run/Overview";
import { PeopleTab } from "@/components/run/People";
import { PersonaDrawer } from "@/components/run/PersonaDrawer";
import { Button, ErrorNote, Notice, Pill, Select, Tabs } from "@/components/ui";
import { api } from "@/lib/api";
import { useMeta } from "@/lib/meta";
import { ago } from "@/lib/format";
import { useRunStream } from "@/lib/useRunStream";

type TabId = "overview" | "ask" | "graph" | "society" | "where" | "countries" | "groups" | "influence" | "reasons" | "pricing" | "committees" | "people" | "method";

const VERDICT: Record<string, { label: string; tone: "yes" | "no" | "neutral" }> = {
  strong: { label: "Strong", tone: "yes" },
  promising: { label: "Promising", tone: "yes" },
  uncertain: { label: "Uncertain", tone: "neutral" },
  weak: { label: "Weak", tone: "no" },
  unlikely: { label: "Unlikely", tone: "no" },
};

export default function RunPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const live = useRunStream(id);
  const { meta, countryName } = useMeta();
  const [tab, setTab] = useState<TabId>("overview");
  const [askPreset, setAskPreset] = useState<GroupPreset | null>(null);
  const [person, setPerson] = useState<string | null>(null);
  const [stopping, setStopping] = useState(false);
  const close = useCallback(() => setPerson(null), []);

  const running = live.status !== "done" && live.status !== "failed" && live.status !== "cancelled";
  const r = live.results;
  const title = live.spec?.title ?? live.run?.title ?? "Simulation";

  useEffect(() => {
    document.title = `${title} | Tellaris`;
  }, [title]);

  const tabs = useMemo(() => {
    const t: { id: TabId; label: string }[] = [{ id: "overview", label: "Overview" }];
    if (r) {
      if (r.splits && Object.keys(r.splits.dimensions).length) t.push({ id: "where", label: "Where it works" });
      if (r.diffusion?.rounds?.length) t.push({ id: "society", label: "Society" });
      if (r.graph?.entities?.length) t.push({ id: "graph", label: "Knowledge graph" });
      t.push({ id: "people", label: "People" }, { id: "countries", label: "Countries" }, { id: "groups", label: "Groups" }, { id: "influence", label: "Outside influence" }, { id: "reasons", label: "Why and why not" });
      if (r.wtp) t.push({ id: "pricing", label: "Pricing" });
      if (r.committees?.n) t.push({ id: "committees", label: "Buying committees" });
      if (live.status === "done") t.push({ id: "ask", label: "Ask a group" });
      t.push({ id: "method", label: "Method" });
    }
    return t;
  }, [r, live.status]);

  const targets = live.spec?.targets ?? [];
  const usedMock = Object.keys(live.usage?.by_model ?? {}).some((m) => m.startsWith("mock/")) || (meta?.mock && running);
  const verdict = live.report ? VERDICT[live.report.verdict] : null;
  const lensId = r?.headline.lens ?? live.spec?.lens ?? null;
  const lensLabel = r?.headline.lens_label ?? meta?.lenses.find((l) => l.id === lensId)?.label;
  const first = live.spec?.outcomes?.[0] ?? "yes";
  const measure = r?.headline.leading
    ? `Share choosing “${first}”`
    : r?.headline.kind === "action"
      ? "Realistic share who say yes"
      : first.toLowerCase() === "yes"
        ? "Share who say yes"
        : `Share who say “${first}”`;
  const [relensing, setRelensing] = useState(false);
  const relens = async (l: string) => {
    const label = meta?.lenses.find((x) => x.id === l)?.label ?? l;
    setRelensing(true);
    try {
      const res = await api.whatif(id, `As ${label.toLowerCase()}`, { lens: l });
      window.location.href = `/runs/${res.id}`;
    } catch {
      setRelensing(false);
    }
  };

  return (
    <div className="mx-auto max-w-[1312px] px-4 py-6 md:px-6">
      <nav aria-label="Breadcrumb" className="mb-2 text-[13px] text-muted">
        <Link href="/runs" className="hover:text-text">
          Simulations
        </Link>
        <span className="px-1.5 text-faint">/</span>
        <span className="text-text">{title}</span>
      </nav>

      <div className="mb-4 flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0 max-w-3xl">
          <div className="flex flex-wrap items-center gap-2.5">
            <h1 className="t-title">{title}</h1>
            {verdict && <Pill tone={verdict.tone}>{verdict.label}</Pill>}
            {lensLabel && <Pill>{lensLabel}</Pill>}
            {r?.diffusion?.feed && r.diffusion.feed.style !== "word_of_mouth" && <Pill>{r.diffusion.feed.style === "viral" ? "Viral feed" : "Ranked feed"}</Pill>}
            {running && (
              <span className="inline-flex items-center gap-1.5 text-[13px] text-muted">
                <span className="live-dot size-1.5 rounded-full bg-live" aria-hidden />
                Live
              </span>
            )}
          </div>
          <p className="mt-1 text-[14px] leading-5 text-muted">
            {live.report?.headline ??
              (running
                ? `Simulating people in ${targets.length ? targets.map(countryName).join(", ") : "the countries that matter"}.`
                : live.status === "failed"
                  ? "This simulation did not finish."
                  : live.status === "cancelled"
                    ? "This simulation was stopped."
                    : `People in ${targets.map(countryName).join(", ")}.`)}
          </p>
          <p className="mt-1 text-[12px] text-faint">
            {targets.map(countryName).join(", ")}
            {live.run && `${targets.length ? ". " : ""}Started ${ago(live.run.created_at).toLowerCase()}.`}
            {live.run?.parent_id && (
              <>
                {" "}
                A changed version of{" "}
                <Link href={`/runs/${live.run.parent_id}`} className="text-text underline-offset-2 hover:underline">
                  the original run
                </Link>
                {r?.comparison && <>, {r.comparison.delta >= 0 ? "+" : "−"}{Math.abs(r.comparison.delta * 100).toFixed(1)} points with the same people</>}
                {r?.comparison?.society && r.comparison.society.parent.feed !== r.comparison.society.this.feed && (
                  <>; after the conversation {r.comparison.society.delta >= 0 ? "+" : "−"}{Math.abs(r.comparison.society.delta * 100).toFixed(1)} points</>
                )}.
              </>
            )}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {!running && live.status === "done" && lensId && meta && (
            <Select
              label="Run again with a different lens"
              value=""
              onChange={(v) => v && relens(v)}
              className="w-auto"
              options={[{ value: "", label: relensing ? "Starting…" : "Try another lens" }, ...meta.lenses.filter((l) => l.id !== lensId).map((l) => ({ value: l.id, label: `As ${l.label.toLowerCase()}` }))]}
            />
          )}
          {running ? (
            <Button
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
              <>
              {live.spec?.outcome_type !== "numeric" && <TrackButton runId={id} horizonMonths={live.spec?.horizon_months} demo={!!usedMock} />}
              <a href={api.exportUrl(id)} className="inline-flex h-8 items-center rounded-md border border-control bg-surface px-3 text-[13px] font-medium hover:bg-raised">
                Download data
              </a>
              </>
            )
          )}
        </div>
      </div>

      {usedMock && (
        <div className="mb-4">
          <Notice>
            This run uses the offline demo model, so the numbers show how Tellaris works but are not predictions.{" "}
            <Link href="/settings" className="font-medium underline">
              Connect a model
            </Link>
          </Notice>
        </div>
      )}
      {(live.status === "failed" || live.status === "cancelled") && (
        <div className="mb-4">
          <ErrorNote
            action={
              <Link href="/" className="text-[13px] font-medium underline">
                Start a new one
              </Link>
            }
          >
            {live.status === "cancelled" ? "Stopped before it finished. Anything already answered is shown below." : <>It failed: {live.error ?? live.run?.error}. Check your models on the Models page.</>}
          </ErrorNote>
        </div>
      )}

      <div className="mb-6">
        <Tabs tabs={tabs} value={tab} onChange={setTab} />
      </div>

      {tab === "overview" && <Overview id={id} live={live} running={running} onSelect={setPerson} onTab={(t) => setTab(t as TabId)} />}
      {r && tab === "society" && <SocietyTab id={id} live={live} r={r} onSelect={setPerson} />}
      {r && tab === "where" && r.splits && (
        <WhereItWorks
          r={r}
          live={live}
          measure={measure}
          onAsk={live.status === "done" ? (g) => {
            setAskPreset(g);
            setTab("ask");
          } : undefined}
        />
      )}
      {r && tab === "ask" && <AskGroup id={id} r={r} preset={askPreset} />}
      {r && tab === "graph" && r.graph && <KnowledgeGraphTab g={r.graph} runId={id} />}
      {r && tab === "countries" && <CountriesTab r={r} live={live} />}
      {r && tab === "groups" && <GroupsTab r={r} />}
      {r && tab === "influence" && <InfluenceTab r={r} live={live} />}
      {r && tab === "reasons" && <ReasonsTab r={r} onSelect={setPerson} />}
      {r && tab === "pricing" && r.wtp && <PricingTab r={r} />}
      {r && tab === "committees" && r.committees?.n ? <CommitteesTab id={id} r={r} /> : null}
      {r && tab === "people" && <PeopleTab id={id} onSelect={setPerson} />}
      {r && tab === "method" && <MethodTab live={live} />}

      <AnimatePresence>{person && <PersonaDrawer key={person} runId={id} pid={person} onClose={close} />}</AnimatePresence>
    </div>
  );
}
