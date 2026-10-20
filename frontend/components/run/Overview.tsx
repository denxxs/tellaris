"use client";

import { AnimatePresence, motion } from "motion/react";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { BarRows, RangeTrack, ShareRows } from "@/components/charts";
import { Button, Card, CardHead, Empty, Meter, Skeleton } from "@/components/ui";
import { WorldMap, type MapAgent } from "@/components/world/WorldMap";
import { api } from "@/lib/api";
import { useMeta } from "@/lib/meta";
import { cx, int, people, pctSmart, shortJob, stanceText } from "@/lib/format";
import type { LiveState } from "@/lib/useRunStream";
import { Crowd } from "./Crowd";

const STAGES = [
  { id: "scenario", label: "Understand the question" },
  { id: "research", label: "Research the real world" },
  { id: "world", label: "Map outside influence" },
  { id: "population", label: "Build the population" },
  { id: "reactions", label: "Each person decides" },
  { id: "committees", label: "Buying committees" },
  { id: "diffusion", label: "Word of mouth" },
  { id: "report", label: "Write the analysis" },
];

export function useAgents(live: LiveState): MapAgent[] {
  return useMemo(
    () =>
      live.order.map((pid) => {
        const p = live.personas[pid];
        const s = live.scores[pid];
        return { id: pid, country: p.country, voice: p.voice, p: s?.length ? s.reduce((a, b) => a + b, 0) / s.length : null };
      }),
    [live.order, live.personas, live.scores],
  );
}

/** The KPI strip: one container split by dividers. The answer figure leads. */
function AnswerStrip({ live, running }: { live: LiveState; running: boolean }) {
  const h = live.results?.headline;
  const answers = Object.values(live.scores).reduce((a, s) => a + s.length, 0);
  const raw = useMemo(() => {
    const v = Object.entries(live.scores)
      .filter(([id]) => !live.personas[id]?.voice)
      .map(([, s]) => s.reduce((a, b) => a + b, 0) / s.length);
    return v.length ? v.reduce((a, b) => a + b, 0) / v.length : null;
  }, [live.scores, live.personas]);

  const cells = [
    {
      label: h ? h.kind === "action" ? "Among those who hear about it" : "Before correction" : "Leaning yes so far",
      value: h ? pctSmart(h.kind === "action" ? h.if_aware : h.stated) : raw == null ? "–" : pctSmart(raw),
      sub: h ? (h.kind === "action" ? `${pctSmart(h.reach)} expected to hear about it` : "What people said") : "Raw, before any correction",
    },
    { label: "People represented", value: h?.people ? people(h.people) : "–", sub: h?.people ? "Estimated real headcount" : "Known when people are built" },
    { label: h?.kind === "belief" ? "Expected to agree" : "Expected to say yes", value: h?.adopters != null ? people(h.adopters) : "–", sub: h?.adopters != null ? "Answer × people represented" : "Known at the end" },
    { label: "Simulated", value: int(live.order.length), sub: `${int(answers)} answers` },
  ];

  return (
    <Card pad={false} className="grid lg:grid-cols-[minmax(0,1.6fr)_repeat(4,minmax(0,1fr))]">
      <div className="border-b border-border p-5 lg:border-b-0 lg:border-r">
        <div className="text-[14px] font-medium text-text">{h ? h.label : "Answer"}</div>
        {h ? (
          <>
            <div className="t-answer mt-1">{pctSmart(h.value)}</div>
            <div className="mt-1 text-[13px] text-muted">
              Likely between <span className="num text-text">{pctSmart(h.ci[0])}</span> and <span className="num text-text">{pctSmart(h.ci[1])}</span>
            </div>
            <div className="mt-2">
              <RangeTrack value={h.value} ci={h.ci} aware={h.kind === "action" ? h.if_aware : undefined} />
            </div>
          </>
        ) : (
          <>
            <Skeleton className="mt-2 h-9 w-28" />
            <div className="mt-2 text-[13px] text-muted">{running ? "Calculated when everyone has answered" : "No answer was produced"}</div>
          </>
        )}
      </div>
      <dl className="grid grid-cols-2 lg:col-span-4 lg:grid-cols-4">
        {cells.map((c, i) => (
          <div key={c.label} className={cx("p-5", i % 2 === 0 && "border-r border-border", i < 2 && "border-b border-border lg:border-b-0", "lg:border-r lg:last:border-r-0")}>
            <dt className="text-[13px] text-muted">{c.label}</dt>
            <dd className="t-kpi mt-1">{c.value}</dd>
            <dd className="mt-1 text-[12px] leading-4 text-faint">{c.sub}</dd>
          </div>
        ))}
      </dl>
    </Card>
  );
}

function Progress({ live }: { live: LiveState }) {
  const current = STAGES.find((s) => live.stages[s.id]?.status === "start") ?? STAGES.find((s) => !live.stages[s.id]);
  return (
    <div>
      <div className="mb-2 flex items-baseline justify-between text-[13px]">
        <span className="text-text">{current?.label ?? "Finishing"}</span>
        <span className="num text-muted">{Math.round(live.progress * 100)}%</span>
      </div>
      <Meter value={live.progress} />
      <ol className="mt-4 flex flex-col gap-1.5">
        {STAGES.map((s) => {
          const st = live.stages[s.id]?.status ?? "pending";
          const now = st === "start";
          return (
            <li key={s.id} className={cx("flex items-center gap-2.5 text-[13px]", st === "pending" || st === "skipped" ? "text-faint" : "text-text")}>
              <span className={cx("grid size-4 place-items-center rounded-full", st === "done" ? "bg-text text-surface" : now ? "bg-live" : "border border-control")} aria-hidden>
                {st === "done" && (
                  <svg viewBox="0 0 12 12" className="size-2.5">
                    <path d="M2.5 6.3l2.2 2.2 4.8-5" stroke="currentColor" strokeWidth="1.8" fill="none" strokeLinecap="round" />
                  </svg>
                )}
              </span>
              {s.label}
              {st === "skipped" && <span className="text-faint">, not needed</span>}
            </li>
          );
        })}
      </ol>
    </div>
  );
}

function Ticker({ live }: { live: LiveState }) {
  const { countryName } = useMeta();
  return (
    <ul className="flex flex-col gap-2" aria-live="polite">
      <AnimatePresence initial={false}>
        {live.ticker.slice(0, 4).map((t) => {
          const p = live.personas[t.id];
          return (
            <motion.li key={`${t.id}-${t.run}`} layout initial={{ opacity: 0, y: -6 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} transition={{ duration: 0.25 }} className="border-b border-rule pb-2 last:border-0">
              <div className="flex items-baseline justify-between gap-2 text-[13px]">
                <span className="truncate text-text">{p?.name || "Someone"}</span>
                <span className={cx("num shrink-0", stanceText(t.p))}>{pctSmart(t.p)}</span>
              </div>
              <div className="truncate text-[12px] text-faint">{p ? `${shortJob(p.occupation)}, ${countryName(p.country)}` : ""}</div>
              <p className="mt-0.5 line-clamp-2 text-[13px] leading-[18px] text-muted">“{t.quote}”</p>
            </motion.li>
          );
        })}
      </AnimatePresence>
      {live.ticker.length === 0 && <li className="text-[13px] text-muted">Answers appear here as people decide.</li>}
    </ul>
  );
}

export function Overview({ id, live, running, onSelect }: { id: string; live: LiveState; running: boolean; onSelect: (pid: string) => void }) {
  const router = useRouter();
  const agents = useAgents(live);
  const r = live.results;
  const rep = live.report;
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const voices = agents.filter((a) => a.voice).length;

  const whatif = async (label: string, changes: Record<string, unknown>) => {
    setBusy(label);
    setErr(null);
    try {
      const res = await api.whatif(id, label, changes);
      router.push(`/runs/${res.id}`);
    } catch (e) {
      setErr((e as Error).message);
      setBusy(null);
    }
  };

  return (
    <div className="flex flex-col gap-6">
      <AnswerStrip live={live} running={running} />

      <div className="grid items-start gap-6 lg:grid-cols-6">
        <Card pad={false} className="lg:col-span-4">
          <div className="px-5 pt-5">
            <CardHead title="The world of this simulation" aside={`${int(agents.length - voices)} people${voices ? `, ${voices} outside voices` : ""}`}>
              Each dot is one simulated person, coloured by their answer. Arrows are outside countries and blocs pressing on your markets.
            </CardHead>
          </div>
          <div className="px-2 pb-3">
            <WorldMap world={live.world} targets={live.spec?.targets ?? []} agents={agents} label="Simulated people on a world map, coloured by their answers" />
          </div>
        </Card>

        <div className="flex flex-col gap-6 lg:col-span-2">
          {running ? (
            <Card>
              <CardHead title="Progress" />
              <Progress live={live} />
              <div className="mt-6">
                <h3 className="mb-2 text-[14px] font-medium">Latest answers</h3>
                <Ticker live={live} />
              </div>
            </Card>
          ) : r ? (
            <>
              <Card>
                <CardHead title="By country" aside="Overall is the tick" />
                <BarRows reference={r.headline.value} rows={r.by_country.map((c) => ({ key: c.key!, label: c.label!, value: c.value, ci: c.ci, people: c.people }))} limit={5} />
              </Card>
              <Card>
                <CardHead title="By group" />
                <BarRows reference={r.headline.value} rows={r.by_segment.map((x) => ({ key: x.key!, label: x.label!, value: x.value, ci: x.ci, people: x.people }))} limit={3} />
              </Card>
            </>
          ) : (
            <Card>
              <Empty title="No results">This run stopped before anyone answered.</Empty>
            </Card>
          )}
        </div>
      </div>

      <Card>
        <CardHead title="The crowd" aside={`${int(live.order.length)} people`}>
          Every simulated person as one square, grouped by who they are.
        </CardHead>
        <Crowd order={live.order} personas={live.personas} scores={live.scores} done={!running} onSelect={onSelect} />
      </Card>

      {r && (
        <div className="grid items-start gap-6 lg:grid-cols-6">
          <Card className="lg:col-span-3">
            <CardHead title="What to do next">{rep ? undefined : "Writing the analysis…"}</CardHead>
            {rep ? (
              <ol className="flex flex-col">
                {rep.recommendations.map((x, i) => (
                  <li key={i} className="flex gap-3 border-b border-rule py-3 first:pt-0 last:border-0 last:pb-0">
                    <span className={cx("mt-0.5 grid size-5 shrink-0 place-items-center rounded-full text-[11px] font-medium", x.priority === "high" ? "bg-text text-surface" : "bg-raised text-muted")}>{i + 1}</span>
                    <div>
                      <div className="text-[14px] font-medium text-text">{x.action}</div>
                      <p className="mt-0.5 text-[13px] leading-[18px] text-muted">{x.why}</p>
                      <p className="mt-0.5 text-[12px] text-faint">Expected: {x.expected_impact}</p>
                    </div>
                  </li>
                ))}
              </ol>
            ) : (
              <div className="flex flex-col gap-3">
                {[0, 1, 2].map((i) => (
                  <Skeleton key={i} className="h-10" />
                ))}
              </div>
            )}
          </Card>
          <Card className="lg:col-span-3">
            <CardHead title="Test a change">Re-runs the same people with one thing changed, so the difference is the real effect.</CardHead>
            {rep?.levers.length ? (
              <ul className="flex flex-col">
                {rep.levers.map((l) => (
                  <li key={l.label} className="flex items-center justify-between gap-4 border-b border-rule py-2.5 first:pt-0 last:border-0 last:pb-0">
                    <div className="min-w-0">
                      <div className="text-[14px] text-text">{l.label}</div>
                      <p className="text-[13px] leading-[18px] text-muted">{l.description}</p>
                    </div>
                    <Button size="sm" onClick={() => whatif(l.label, l.changes)} busy={busy === l.label} disabled={!!busy}>
                      Simulate
                    </Button>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-[13px] text-muted">{rep ? "No changes suggested for this question." : "Suggestions appear with the analysis."}</p>
            )}
            {err && <p className="mt-3 text-[13px] text-negative">{err}</p>}
          </Card>
          {r.themes?.objections.length ? (
            <Card className="lg:col-span-3">
              <CardHead title="Why people say no" />
              <ShareRows tone="no" rows={r.themes.objections.slice(0, 4).map((t) => ({ label: t.theme, share: t.share }))} />
            </Card>
          ) : null}
          {r.themes?.change_mind.length ? (
            <Card className="lg:col-span-3">
              <CardHead title="What would change their mind" />
              <ShareRows tone="text" rows={r.themes.change_mind.slice(0, 4).map((t) => ({ label: t.theme, share: t.share }))} />
            </Card>
          ) : null}
        </div>
      )}
    </div>
  );
}
