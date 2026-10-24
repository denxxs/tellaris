"use client";

import { AnimatePresence, motion } from "motion/react";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { BarRows, RangeTrack, ShareRows } from "@/components/charts";
import { Button, Card, CardHead, Empty, Meter, Skeleton } from "@/components/ui";
import { WorldMap, type MapAgent } from "@/components/world/WorldMap";
import { api } from "@/lib/api";
import { useMeta } from "@/lib/meta";
import { cx, int, money, people, pctSmart, shortJob, stanceText } from "@/lib/format";
import type { LiveState } from "@/lib/useRunStream";
import { Crowd } from "./Crowd";
import { SocietyFeed } from "./Society";

const STAGES = [
  { id: "scenario", label: "Understand the question" },
  { id: "research", label: "Research the real world" },
  { id: "news", label: "Read the news" },
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

function fmtNum(v: number | null | undefined) {
  if (v == null || Number.isNaN(v)) return "–";
  const a = Math.abs(v);
  return a >= 1000 ? Math.round(v).toLocaleString("en-US") : a >= 10 ? v.toFixed(0) : v.toFixed(1);
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

  const outcomes = live.results?.outcomes;
  const options = Array.isArray(outcomes) ? [...outcomes].sort((a, b) => b.share - a.share) : null;
  const numeric = outcomes && !Array.isArray(outcomes) ? outcomes : null;
  const first = live.spec?.outcomes?.[0] ?? "yes";
  const countries = live.spec?.targets.length ?? 0;

  const cells = h?.leading && options
    ? [
        { label: "Runner-up", value: options[1] ? pctSmart(options[1].share) : "–", sub: options[1] ? options[1].option : "Only one option" },
        { label: "People represented", value: h.people ? people(h.people) : "–", sub: "Estimated real headcount" },
        { label: "Countries", value: int(countries), sub: live.spec?.scope === "global" ? "Global sample" : "Simulated" },
        { label: "Simulated", value: int(live.order.length), sub: `${int(answers)} answers` },
      ]
    : numeric
      ? [
          { label: "Average", value: fmtNum(numeric.mean), sub: numeric.unit ?? "Mean of all answers" },
          { label: "People represented", value: h?.people ? people(h.people) : "–", sub: "Estimated real headcount" },
          { label: "Countries", value: int(countries), sub: "Simulated" },
          { label: "Simulated", value: int(live.order.length), sub: `${int(answers)} answers` },
        ]
      : [
    h?.with_awareness && h.awareness != null
      ? { label: "Whole audience", value: pctSmart(h.with_awareness.value), sub: `If ${pctSmart(h.awareness)} hear about it, your estimate` }
      : {
          label: h ? "Before correction" : "Leaning yes so far",
          value: h ? pctSmart(h.stated) : raw == null ? "–" : pctSmart(raw),
          sub: h ? "What people said, before the say/do correction" : "Raw, before any correction",
        },
    { label: "People represented", value: h?.people ? people(h.people) : "–", sub: h?.people ? "Estimated real headcount" : "Known when people are built" },
    h?.adopters != null
      ? {
          label: h.kind === "belief" ? (first.toLowerCase() === "yes" ? "Expected to say yes" : `Expected to say “${first}”`) : "Expected customers",
          value: people(h.adopters),
          sub: h.awareness != null ? `If ${pctSmart(h.awareness)} hear about it` : "Answer × people represented",
        }
      : h?.per_point_adopters != null
        ? { label: "Per 1% who hear about it", value: people(h.per_point_adopters), sub: "people would do it" }
        : { label: "Expected to say yes", value: "–", sub: "Known at the end" },
    h?.revenue && h.revenue.monthly != null
      ? {
          label: "Implied monthly revenue",
          value: money(h.revenue.monthly, h.revenue.currency),
          sub: h.revenue.monthly_ci ? `${money(h.revenue.monthly_ci[0], h.revenue.currency)} to ${money(h.revenue.monthly_ci[1], h.revenue.currency)} at list price` : "At list price",
        }
      : h?.revenue && h.revenue.per_point_monthly != null
        ? { label: "Revenue per 1% who hear", value: money(h.revenue.per_point_monthly, h.revenue.currency), sub: "a month, at list price" }
        : { label: "Simulated", value: int(live.order.length), sub: `${int(answers)} answers` },
  ];

  return (
    <Card pad={false} className="grid grid-cols-1 lg:grid-cols-[minmax(0,1.6fr)_repeat(4,minmax(0,1fr))]">
      <div className="border-b border-border p-5 lg:border-b-0 lg:border-r">
        <div className="text-[14px] font-medium text-text">{h ? (h.leading && options ? "Most chosen" : h.label) : "Answer"}</div>
        {h && h.leading && options ? (
          <>
            <div className="mt-1 flex items-baseline gap-3">
              <span className="t-answer">{pctSmart(h.leading.share)}</span>
              <span className="truncate text-[16px] text-text">{h.leading.option}</span>
            </div>
            <div className="mt-1 text-[13px] text-muted">
              Likely between <span className="num text-text">{pctSmart(h.leading.ci[0])}</span> and <span className="num text-text">{pctSmart(h.leading.ci[1])}</span>
            </div>
            <ul className="mt-3 flex flex-col gap-1.5">
              {options.map((o) => (
                <li key={o.option} className="grid grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)_44px] items-center gap-2 text-[13px]">
                  <span className="truncate text-text">{o.option}</span>
                  <span className="h-1.5 rounded-full bg-raised">
                    <span className={cx("block h-full rounded-full", o.option === h.leading!.option ? "bg-yes" : "bg-text/40")} style={{ width: `${o.share * 100}%` }} />
                  </span>
                  <span className="num text-right text-muted">{pctSmart(o.share)}</span>
                </li>
              ))}
            </ul>
          </>
        ) : h && numeric ? (
          <>
            <div className="mt-1 flex items-baseline gap-2">
              <span className="t-answer">{fmtNum(numeric.median)}</span>
              {numeric.unit && <span className="text-[14px] text-muted">{numeric.unit}</span>}
            </div>
            <div className="mt-1 text-[13px] text-muted">
              Most answers between <span className="num text-text">{fmtNum(numeric.p10)}</span> and <span className="num text-text">{fmtNum(numeric.p90)}</span>
            </div>
          </>
        ) : h ? (
          <>
            <div className="t-answer mt-1">{pctSmart(h.value)}</div>
            <div className="mt-1 text-[13px] text-muted">
              Likely between <span className="num text-text">{pctSmart(h.ci[0])}</span> and <span className="num text-text">{pctSmart(h.ci[1])}</span>
            </div>
            <div className="mt-2">
              <RangeTrack value={h.value} ci={h.ci} />
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

export function Overview({ id, live, running, onSelect, onTab }: { id: string; live: LiveState; running: boolean; onSelect: (pid: string) => void; onTab: (tab: string) => void }) {
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

      <div className="grid grid-cols-1 items-start gap-6 lg:grid-cols-6">
        <Card pad={false} className="lg:col-span-4">
          <div className="px-5 pt-5">
            <CardHead title="The world of this simulation" aside={`${int(agents.length - voices)} people${voices ? `, ${voices} outside voices` : ""}`}>
              Each dot is one simulated person, coloured by their answer. Arrows are the countries and blocs your markets are most tied to through trade, friendships and people living abroad.
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
                <h3 className="mb-2 text-[14px] font-medium">{live.feed.length ? "Latest in the conversation" : "Latest answers"}</h3>
                {live.feed.length ? <SocietyFeed id={id} live={live} r={null} onSelect={onSelect} compact /> : <Ticker live={live} />}
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

      {r?.diffusion?.society && (
        <Card>
          <CardHead
            title="What people are saying"
            aside={
              <button onClick={() => onTab("society")} className="font-medium text-text hover:underline">
                Open the conversation
              </button>
            }
          >
            {r.diffusion.society.posts} posts, {r.diffusion.society.replies} replies, {r.diffusion.society.shifts} people changed their mind.
          </CardHead>
          <div className="grid grid-cols-1 gap-x-8 md:grid-cols-2">
            {r.diffusion.society.hot_threads.slice(0, 4).map((t) => (
              <button key={t.id} onClick={() => onTab("society")} className="border-b border-rule py-2.5 text-left">
                <span className="block text-[13px] text-muted">{t.author_name}</span>
                <span className="line-clamp-2 block text-[14px] leading-5 text-text">“{t.text}”</span>
                <span className="mt-0.5 block text-[12px] text-faint">
                  {t.replies} {t.replies === 1 ? "reply" : "replies"}, {t.agrees} agree, {t.disagrees} disagree
                </span>
              </button>
            ))}
          </div>
        </Card>
      )}

      <Card>
        <CardHead title="The crowd" aside={`${int(live.order.length)} people`}>
          Every simulated person as one square, grouped by who they are.
        </CardHead>
        <Crowd order={live.order} personas={live.personas} scores={live.scores} done={!running} onSelect={onSelect} />
      </Card>

      {r && (
        <div className="grid grid-cols-1 items-start gap-6 lg:grid-cols-6">
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
