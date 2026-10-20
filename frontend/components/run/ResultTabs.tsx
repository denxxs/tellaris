"use client";

import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { LineChart, RangeRows, ShareBars, StackBar } from "@/components/charts";
import { Chip, Empty, Panel, SectionHead, Tabs } from "@/components/ui";
import { WorldMap } from "@/components/world/WorldMap";
import { api } from "@/lib/api";
import { companyLabel, cx, money, pctSmart, signedPts, titleCase } from "@/lib/format";
import type { LiveState } from "@/lib/useRunStream";
import type { Committee, Meta, Quote, Results, Report } from "@/lib/types";
import { PeopleTab } from "./People";

type TabId = "overview" | "countries" | "groups" | "influence" | "objections" | "pricing" | "committees" | "spread" | "people" | "method";

export function ResultTabs({ id, live, meta }: { id: string; live: LiveState; meta: Meta | null }) {
  const r = live.results!;
  const [tab, setTab] = useState<TabId>("overview");
  const tabs = useMemo(() => {
    const t: { id: TabId; label: string }[] = [
      { id: "overview", label: "Summary" },
      { id: "countries", label: "Countries" },
      { id: "groups", label: "Groups" },
      { id: "influence", label: "Outside influence" },
      { id: "objections", label: "Why and why not" },
    ];
    if (r.wtp) t.push({ id: "pricing", label: "Pricing" });
    if (r.committees?.n) t.push({ id: "committees", label: "Buying committees" });
    if (r.diffusion?.rounds?.length) t.push({ id: "spread", label: "Word of mouth" });
    t.push({ id: "people", label: "People" }, { id: "method", label: "Method" });
    return t;
  }, [r]);

  return (
    <div>
      <div className="sticky top-0 z-20 -mx-4 mb-6 border-b border-line bg-fog/90 px-4 py-2 backdrop-blur md:-mx-8 md:px-8">
        <Tabs tabs={tabs} value={tab} onChange={setTab} />
      </div>
      {tab === "overview" && <Overview id={id} r={r} report={live.report} />}
      {tab === "countries" && <Countries r={r} live={live} meta={meta} />}
      {tab === "groups" && <Groups r={r} />}
      {tab === "influence" && <Influence r={r} live={live} />}
      {tab === "objections" && <Objections r={r} />}
      {tab === "pricing" && <Pricing r={r} />}
      {tab === "committees" && <Committees id={id} r={r} />}
      {tab === "spread" && <Spread r={r} />}
      {tab === "people" && <PeopleTab id={id} />}
      {tab === "method" && <Method live={live} />}
    </div>
  );
}

/* ---------------------------------------------------------------- Summary */

function Overview({ id, r, report }: { id: string; r: Results; report: Report | null }) {
  const router = useRouter();
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  if (!report)
    return (
      <Empty title="Writing the analysis">The numbers are in. The written summary appears here in a moment.</Empty>
    );
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
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)]">
      <div className="flex flex-col gap-6">
        <Panel>
          <h2 className="t-2 mb-3">What&apos;s going on</h2>
          <p className="max-w-[68ch] text-[16px] leading-relaxed text-ink">{report.summary}</p>
        </Panel>
        <Panel>
          <SectionHead title="What to do next" />
          <ol className="flex flex-col divide-y divide-line">
            {report.recommendations.map((rec, i) => (
              <li key={i} className="grid grid-cols-[28px_minmax(0,1fr)] gap-3 py-3.5 first:pt-0 last:pb-0">
                <span className={cx("mt-0.5 grid size-6 place-items-center rounded-full text-[11px] font-bold", rec.priority === "high" ? "bg-iris text-white" : "bg-panel-2 text-ink-2")}>{i + 1}</span>
                <div>
                  <div className="font-semibold text-ink">{rec.action}</div>
                  <p className="mt-0.5 text-sm text-ink-2">{rec.why}</p>
                  <p className="mt-1 t-small text-ink-3">Expected: {rec.expected_impact}</p>
                </div>
              </li>
            ))}
          </ol>
        </Panel>
        {report.drivers.length > 0 && (
          <Panel>
            <SectionHead title="What drives the answer" />
            <ul className="grid gap-4 sm:grid-cols-2">
              {report.drivers.map((d, i) => (
                <li key={i} className="flex gap-3">
                  <span className={cx("mt-1.5 size-2.5 shrink-0 rounded-full", d.effect === "positive" ? "bg-yes" : d.effect === "negative" ? "bg-no" : "bg-mid")} aria-hidden />
                  <div>
                    <div className="font-semibold text-ink">{d.factor}</div>
                    <p className="text-sm text-ink-2">{d.evidence}</p>
                  </div>
                </li>
              ))}
            </ul>
          </Panel>
        )}
      </div>
      <div className="flex flex-col gap-6">
        {report.levers.length > 0 && (
          <Panel className="border-iris/40">
            <h2 className="t-2">Test a change</h2>
            <p className="mb-4 mt-1 text-sm text-ink-2">Re-runs the same people with one thing changed, so you see the real effect.</p>
            <div className="flex flex-col gap-2">
              {report.levers.map((l) => (
                <button
                  key={l.label}
                  disabled={!!busy}
                  onClick={() => whatif(l.label, l.changes)}
                  className="group rounded-xl border border-line bg-panel-2 px-4 py-3 text-left transition-colors hover:border-iris disabled:opacity-60"
                >
                  <div className="flex items-center justify-between gap-3">
                    <span className="font-semibold text-ink group-hover:text-iris-ink">{l.label}</span>
                    {busy === l.label ? <span className="t-small text-ink-3">Starting…</span> : <span className="t-small font-semibold text-iris-ink">Simulate</span>}
                  </div>
                  <p className="mt-0.5 t-small text-ink-2">{l.description}</p>
                </button>
              ))}
            </div>
            {err && <p className="mt-3 t-small text-no">{err}</p>}
          </Panel>
        )}
        {report.risks.length > 0 && (
          <Panel>
            <h2 className="t-2 mb-3">Risks</h2>
            <ul className="flex flex-col gap-2">
              {report.risks.map((x) => (
                <li key={x} className="flex gap-2.5 text-sm text-ink-2">
                  <span className="mt-2 size-1.5 shrink-0 rounded-full bg-no" aria-hidden />
                  {x}
                </li>
              ))}
            </ul>
          </Panel>
        )}
        <Panel>
          <h2 className="t-2 mb-2">How much to trust this</h2>
          <p className="text-sm text-ink-2">{report.confidence_note}</p>
        </Panel>
        <QuotePair q={r.quotes} />
      </div>
    </div>
  );
}

function QuotePair({ q }: { q: Results["quotes"] }) {
  const pick = [q.positive[0], q.negative[0]].filter(Boolean) as Quote[];
  if (!pick.length) return null;
  return (
    <div className="flex flex-col gap-3">
      {pick.map((x) => (
        <figure key={x.persona_id} className={cx("rounded-2xl border-l-4 bg-panel px-5 py-4", (x.p ?? 0) >= 0.5 ? "border-yes" : "border-no")}>
          <blockquote className="text-[15px] leading-relaxed text-ink">“{x.quote}”</blockquote>
          <figcaption className="mt-2 t-small text-ink-3">
            {x.name}, {x.occupation.split("(")[0].trim()} in {x.country}
          </figcaption>
        </figure>
      ))}
    </div>
  );
}

/* ---------------------------------------------------------------- Countries */

function Countries({ r, live, meta }: { r: Results; live: LiveState; meta: Meta | null }) {
  const values = Object.fromEntries(r.by_country.map((c) => [c.key!, c.value / Math.max(r.headline.reach, 0.01)]));
  const matrix = r.by_country_segment;
  const segs = [...new Set(matrix.map((m) => m.key!.split("|").slice(1).join("|")))];
  const countries = r.by_country.map((c) => c.key!);
  const cname = Object.fromEntries((meta?.countries ?? []).map((c) => [c.iso3, c.name]));
  return (
    <div className="flex flex-col gap-6">
      <Panel>
        <SectionHead title="By country">Each bar shows the most likely value; the lighter band is the likely range. The thin line is the overall answer.</SectionHead>
        <RangeRows
          emphasis={r.headline.value}
          rows={r.by_country.map((c) => ({ key: c.key!, label: c.label!, value: c.value, ci: c.ci, n: c.n, note: c.top_objection?.[0] ? `top objection: ${c.top_objection[0]}` : undefined }))}
        />
      </Panel>
      <div className="grid gap-6 lg:grid-cols-2">
        <Panel pad={false} className="overflow-hidden">
          <div className="px-5 pt-5">
            <h2 className="t-2">Where people lean</h2>
            <p className="mt-1 text-sm text-ink-2">Shaded by willingness among those who hear about it.</p>
          </div>
          <WorldMap world={live.world} targets={countries} values={values} showArcs={false} compact />
        </Panel>
        {segs.length > 1 && (
          <Panel>
            <h2 className="t-2 mb-4">Country and group</h2>
            <div className="scroll-thin overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr>
                    <th className="pb-2 text-left font-semibold text-ink-3">Group</th>
                    {countries.map((c) => (
                      <th key={c} className="pb-2 text-right font-semibold text-ink-3">
                        {cname[c] ?? c}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {segs.map((s) => (
                    <tr key={s} className="border-t border-line">
                      <td className="py-2.5 pr-3 font-semibold text-ink">{s}</td>
                      {countries.map((c) => {
                        const cell = matrix.find((m) => m.key === `${c}|${s}`);
                        return (
                          <td key={c} className="num py-2.5 text-right">
                            {cell ? (
                              <span title={`${cell.n} people`} className="inline-block min-w-14 rounded-md px-2 py-0.5" style={{ background: `color-mix(in oklab, var(--iris) ${Math.round(Math.min(1, cell.value / Math.max(r.headline.value * 2.5, 0.01)) * 55)}%, transparent)` }}>
                                {pctSmart(cell.value)}
                              </span>
                            ) : (
                              <span className="text-ink-3">–</span>
                            )}
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>
        )}
      </div>
    </div>
  );
}

/* ---------------------------------------------------------------- Groups */

function Groups({ r }: { r: Results }) {
  const toRows = (xs: Results["by_segment"], lab = (s: string) => s) => xs.map((s) => ({ key: s.key!, label: lab(s.label!), value: s.value, ci: s.ci, n: s.n }));
  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <Panel className="lg:col-span-2">
        <SectionHead title="By group" />
        <RangeRows rows={toRows(r.by_segment)} emphasis={r.headline.value} />
      </Panel>
      <Panel>
        <SectionHead title="By job" />
        <RangeRows rows={toRows(r.by_occupation, (s) => s.split("(")[0].trim())} emphasis={r.headline.value} />
      </Panel>
      <div className="flex flex-col gap-6">
        <Panel>
          <SectionHead title="By seniority" />
          <RangeRows rows={toRows(r.by_seniority, titleCase)} emphasis={r.headline.value} />
        </Panel>
        <Panel>
          <SectionHead title="By company type" />
          <RangeRows rows={toRows(r.by_company_type, companyLabel)} emphasis={r.headline.value} />
        </Panel>
        {r.drivers.length > 0 && (
          <Panel>
            <SectionHead title="Which traits predict a yes">Correlation between each personal trait and willingness. Above zero pushes towards yes.</SectionHead>
            <ul className="flex flex-col gap-2">
              {r.drivers.map((d) => (
                <li key={d.trait} className="grid grid-cols-[140px_minmax(0,1fr)_48px] items-center gap-3 text-sm">
                  <span className="text-ink">{titleCase(d.trait)}</span>
                  <div className="relative h-2 rounded-full bg-panel-2">
                    <div className="absolute inset-y-0 left-1/2 w-px bg-line-strong" />
                    <div
                      className={cx("absolute inset-y-0 rounded-full", d.correlation >= 0 ? "bg-yes" : "bg-no")}
                      style={d.correlation >= 0 ? { left: "50%", width: `${d.correlation * 50}%` } : { right: "50%", width: `${-d.correlation * 50}%` }}
                    />
                  </div>
                  <span className="num text-right text-ink-2">{d.correlation > 0 ? "+" : ""}{d.correlation.toFixed(2)}</span>
                </li>
              ))}
            </ul>
          </Panel>
        )}
      </div>
    </div>
  );
}

/* ---------------------------------------------------------------- Influence */

function Influence({ r, live }: { r: Results; live: LiveState }) {
  const effects = r.influence_effects;
  return (
    <div className="flex flex-col gap-6">
      <Panel pad={false} className="overflow-hidden">
        <div className="px-5 pt-5 md:px-6">
          <h2 className="t-2">Who shapes your markets</h2>
          <p className="mt-1 max-w-2xl text-sm text-ink-2">
            Arrows show outside countries and blocs that affect your target countries. Thicker means stronger. Dashed means an indirect effect.
          </p>
        </div>
        <WorldMap world={live.world} />
      </Panel>
      <Panel>
        <SectionHead title="Measured effect on the answer">
          People who feel each outside force compared with people who don&apos;t. A negative number means the force makes a yes less likely.
        </SectionHead>
        {effects.length === 0 ? (
          <p className="text-sm text-ink-3">No outside force reached enough people to measure.</p>
        ) : (
          <div className="scroll-thin overflow-x-auto">
            <table className="w-full min-w-[640px] text-sm">
              <thead>
                <tr className="text-left text-ink-3">
                  <th className="pb-2 font-semibold">Force</th>
                  <th className="pb-2 font-semibold">Felt by</th>
                  <th className="pb-2 text-right font-semibold">Exposed</th>
                  <th className="pb-2 text-right font-semibold">Others</th>
                  <th className="pb-2 text-right font-semibold">Effect</th>
                  <th className="pb-2 text-right font-semibold">Named by people</th>
                </tr>
              </thead>
              <tbody>
                {effects.map((e) => (
                  <tr key={`${e.source}-${e.channel}`} className="border-t border-line align-top">
                    <td className="py-3 pr-4">
                      <div className="font-semibold text-ink">
                        {e.source_name} <span className="font-normal text-ink-3">through {e.channel.replace("_", " ")}</span>
                      </div>
                      <p className="mt-0.5 max-w-md t-small text-ink-2">{e.note}</p>
                    </td>
                    <td className="num py-3 pr-3 text-ink-2">
                      {e.exposed_n} in {e.countries.join(", ")}
                    </td>
                    <td className="num py-3 text-right">{pctSmart(e.exposed_value)}</td>
                    <td className="num py-3 text-right text-ink-2">{pctSmart(e.others_value)}</td>
                    <td className={cx("num py-3 text-right font-semibold", (e.delta ?? 0) < -0.002 ? "text-no" : (e.delta ?? 0) > 0.002 ? "text-yes" : "text-ink-2")}>
                      {signedPts(e.delta)}
                    </td>
                    <td className="num py-3 text-right text-ink-2">{e.mentions}×</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
      {r.influencer_voices.length > 0 && (
        <Panel>
          <SectionHead title="Voices from influencing countries">People from the countries that shape your markets, asked the same question. Not counted in the answer.</SectionHead>
          <div className="grid gap-5 md:grid-cols-2">
            {r.influencer_voices.map((v) => (
              <div key={v.source}>
                <div className="flex items-baseline justify-between">
                  <span className="t-3">{v.source}</span>
                  <span className="num text-sm text-ink-2">
                    {pctSmart(v.value)} from {v.n} {v.n === 1 ? "person" : "people"}
                  </span>
                </div>
                <ul className="mt-2 flex flex-col gap-2">
                  {v.quotes.map((q) => (
                    <li key={q.persona_id} className="rounded-xl bg-panel-2 px-3.5 py-2.5">
                      <p className="text-sm text-ink">“{q.quote}”</p>
                      <p className="mt-1 t-tiny text-ink-3">
                        {q.name}, {q.occupation.split("(")[0].trim()} in {q.country}
                      </p>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        </Panel>
      )}
    </div>
  );
}

/* ---------------------------------------------------------------- Objections */

function Objections({ r }: { r: Results }) {
  const t = r.themes;
  return (
    <div className="flex flex-col gap-6">
      <div className="grid gap-6 lg:grid-cols-3">
        <Panel>
          <SectionHead title="Why not" />
          {t?.objections.length ? <ShareBars tone="no" rows={t.objections.map((x) => ({ label: x.theme, share: x.share, sub: x.example }))} /> : <p className="text-sm text-ink-3">No objections recorded.</p>}
        </Panel>
        <Panel>
          <SectionHead title="Why yes" />
          {t?.reasons.length ? <ShareBars tone="yes" rows={t.reasons.map((x) => ({ label: x.theme, share: x.share, sub: x.example }))} /> : <p className="text-sm text-ink-3">No reasons recorded.</p>}
        </Panel>
        <Panel>
          <SectionHead title="What would change minds" />
          {t?.change_mind.length ? <ShareBars rows={t.change_mind.map((x) => ({ label: x.theme, share: x.share, sub: x.example }))} /> : <p className="text-sm text-ink-3">Nothing recorded.</p>}
        </Panel>
      </div>
      <Panel>
        <SectionHead title="Attention">How much attention people would realistically give this.</SectionHead>
        <StackBar
          parts={[
            { label: "Ignore", value: r.attention.ignore ?? 0, color: "var(--line-strong)" },
            { label: "Skim", value: r.attention.skim ?? 0, color: "var(--mid)" },
            { label: "Consider", value: r.attention.consider ?? 0, color: "color-mix(in oklab, var(--iris) 60%, var(--panel))" },
            { label: "Evaluate", value: r.attention.evaluate ?? 0, color: "var(--iris)" },
          ]}
        />
      </Panel>
      <div className="grid gap-6 lg:grid-cols-3">
        {(["positive", "undecided", "negative"] as const).map((k) => (
          <Panel key={k}>
            <h2 className="t-2 mb-3">{{ positive: "Most keen", undecided: "On the fence", negative: "Least keen" }[k]}</h2>
            <ul className="flex flex-col gap-3">
              {r.quotes[k].slice(0, 4).map((q) => (
                <li key={q.persona_id}>
                  <p className="text-sm text-ink">“{q.quote}”</p>
                  <p className="mt-0.5 t-tiny text-ink-3">
                    {q.name}, {q.occupation.split("(")[0].trim()} in {q.country}
                    {q.p != null && `, ${pctSmart(q.p)}`}
                  </p>
                </li>
              ))}
            </ul>
          </Panel>
        ))}
      </div>
    </div>
  );
}

/* ---------------------------------------------------------------- Pricing */

function Pricing({ r }: { r: Results }) {
  const w = r.wtp!;
  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
      <Panel>
        <SectionHead title="How many would pay at each price">Share of people whose maximum price is at or above each point. Your price is marked.</SectionHead>
        <LineChart
          xLabel="price"
          xFormat={(x) => money(x, w.currency)}
          yMax={1}
          series={[{ id: "demand", label: "Would pay at least this", color: "var(--iris)", points: w.curve.map((c) => ({ x: c.price, y: c.share })) }]}
        />
      </Panel>
      <div className="flex flex-col gap-6">
        <Panel>
          <dl className="grid grid-cols-2 gap-5">
            <div>
              <dt className="t-tiny text-ink-3">Your price</dt>
              <dd className="t-number mt-1 text-3xl">{money(w.price, w.currency)}</dd>
              <dd className="t-tiny text-ink-3">per {w.period.replace(/-/g, " ")}</dd>
            </div>
            <div>
              <dt className="t-tiny text-ink-3">Would pay it</dt>
              <dd className="t-number mt-1 text-3xl">{pctSmart(w.share_at_price)}</dd>
            </div>
            <div>
              <dt className="t-tiny text-ink-3">Typical max price</dt>
              <dd className="t-number mt-1 text-3xl">{money(w.median, w.currency)}</dd>
            </div>
            <div>
              <dt className="t-tiny text-ink-3">Middle half</dt>
              <dd className="num mt-1 text-lg font-semibold">
                {money(w.p25, w.currency)} to {money(w.p75, w.currency)}
              </dd>
            </div>
          </dl>
        </Panel>
        <Panel>
          <h2 className="t-2 mb-3">Typical max price by country</h2>
          <ul className="flex flex-col divide-y divide-line">
            {w.by_country.map((c) => (
              <li key={c.country} className="flex items-baseline justify-between py-2 text-sm">
                <span className="font-semibold text-ink">{c.country}</span>
                <span className="num text-ink-2">
                  {money(c.median, w.currency)} <span className="text-ink-3">from {c.n}</span>
                </span>
              </li>
            ))}
          </ul>
        </Panel>
      </div>
    </div>
  );
}

/* ---------------------------------------------------------------- Committees */

const DECISION_COLOR = { buy: "var(--yes)", pilot: "color-mix(in oklab, var(--yes) 45%, var(--panel))", defer: "var(--mid)", reject: "var(--no)" };

function Committees({ id, r }: { id: string; r: Results }) {
  const c = r.committees!;
  const [list, setList] = useState<Committee[] | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  useEffect(() => {
    api.committees(id).then(setList).catch(() => setList([]));
  }, [id]);
  return (
    <div className="flex flex-col gap-6">
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
        <Panel>
          <SectionHead title="What the companies decided">
            {c.n} simulated buying groups argued it out. Average chance a company pays: <b className="num text-ink">{pctSmart(c.purchase_probability)}</b>
            {c.median_cycle_months != null && <>, typical deal takes {c.median_cycle_months} months</>}.
          </SectionHead>
          <StackBar parts={(["buy", "pilot", "defer", "reject"] as const).map((k) => ({ label: titleCase(k), value: c.decisions[k] ?? 0, color: DECISION_COLOR[k] }))} />
          <div className="mt-6 grid gap-6 sm:grid-cols-2">
            <div>
              <h3 className="t-3 mb-2">By country</h3>
              <RangeRows rows={c.by_country.map((x) => ({ key: x.country, label: x.country, value: x.purchase_probability, n: x.n }))} />
            </div>
            <div>
              <h3 className="t-3 mb-2">By company type</h3>
              <RangeRows rows={c.by_company_type.map((x) => ({ key: x.company_type, label: companyLabel(x.company_type), value: x.purchase_probability, n: x.n }))} />
            </div>
          </div>
        </Panel>
        <div className="flex flex-col gap-6">
          <Panel>
            <h2 className="t-2 mb-3">Who pushes back</h2>
            <ul className="flex flex-col gap-2.5">
              {Object.entries(c.role_stance)
                .sort((a, b) => a[1] - b[1])
                .map(([role, s]) => (
                  <li key={role} className="grid grid-cols-[130px_minmax(0,1fr)_44px] items-center gap-3 text-sm">
                    <span className="text-ink">{titleCase(role)}</span>
                    <div className="relative h-2 rounded-full bg-panel-2">
                      <div className="absolute inset-y-0 left-1/2 w-px bg-line-strong" />
                      <div className={cx("absolute inset-y-0 rounded-full", s >= 0 ? "bg-yes" : "bg-no")} style={s >= 0 ? { left: "50%", width: `${s * 50}%` } : { right: "50%", width: `${-s * 50}%` }} />
                    </div>
                    <span className="num text-right text-ink-2">{s > 0 ? "+" : ""}{s.toFixed(2)}</span>
                  </li>
                ))}
            </ul>
          </Panel>
          <Panel>
            <h2 className="t-2 mb-3">Deal blockers</h2>
            <ul className="flex flex-col gap-1.5">
              {c.top_blockers.map((b) => (
                <li key={b.blocker} className="flex justify-between gap-3 text-sm">
                  <span className="text-ink first-letter:uppercase">{b.blocker}</span>
                  <span className="num text-ink-3">{b.count}</span>
                </li>
              ))}
            </ul>
          </Panel>
        </div>
      </div>
      <Panel>
        <SectionHead title="Inside the meetings" />
        {!list ? (
          <p className="text-sm text-ink-3">Loading…</p>
        ) : (
          <ul className="flex flex-col divide-y divide-line">
            {list.map((cm) => (
              <li key={cm.id} className="py-3">
                <button className="flex w-full flex-wrap items-center justify-between gap-3 text-left" onClick={() => setOpen(open === cm.id ? null : cm.id)} aria-expanded={open === cm.id}>
                  <span>
                    <span className="font-semibold text-ink">
                      {companyLabel(cm.company_type)} in {cm.country}
                    </span>
                    <span className="t-small text-ink-3"> with {cm.company_size.toLocaleString()} people, {cm.members.length} in the room</span>
                  </span>
                  {cm.decision && (
                    <span className="inline-flex items-center gap-2 text-sm">
                      <span className="inline-block size-2.5 rounded-full" style={{ background: DECISION_COLOR[cm.decision.decision] }} aria-hidden />
                      <span className="font-semibold">{titleCase(cm.decision.decision)}</span>
                      <span className="num text-ink-3">{pctSmart(cm.decision.probability_of_purchase)}</span>
                    </span>
                  )}
                </button>
                {open === cm.id && (
                  <div className="mt-3 flex flex-col gap-3">
                    {cm.transcript.map((t, i) => (
                      <div key={i} className="grid grid-cols-[minmax(0,160px)_minmax(0,1fr)] gap-3">
                        <div className="t-small">
                          <div className="font-semibold text-ink">{t.name}</div>
                          <div className="text-ink-3">
                            {titleCase(t.role)}, round {t.round + 1}
                          </div>
                        </div>
                        <div className={cx("rounded-xl px-3.5 py-2.5 text-sm", t.stance >= 0.2 ? "bg-yes-soft" : t.stance <= -0.2 ? "bg-no-soft" : "bg-panel-2")}>
                          {t.statement}
                          {t.conditions.length > 0 && <div className="mt-1 t-tiny text-ink-2">Would agree if: {t.conditions.join("; ")}</div>}
                        </div>
                      </div>
                    ))}
                    {cm.decision && <p className="rounded-xl border border-line px-3.5 py-2.5 text-sm text-ink-2">{cm.decision.summary}</p>}
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
      </Panel>
    </div>
  );
}

/* ---------------------------------------------------------------- Spread */

function Spread({ r }: { r: Results }) {
  const d = r.diffusion!;
  const countries = Object.keys(d.rounds[0]?.by_country ?? {});
  const palette = ["var(--iris)", "var(--yes)", "var(--no)", "var(--live)", "var(--ink-2)"];
  return (
    <div className="flex flex-col gap-6">
      <div className="grid gap-6 lg:grid-cols-2">
        <Panel>
          <SectionHead title="Views as people talk">
            {d.agents} people in a network of {d.edges} connections, over {d.rounds.length - 1} rounds of conversation.
          </SectionHead>
          <LineChart
            xLabel="round"
            xFormat={(x) => (x === 0 ? "Start" : `Round ${x}`)}
            series={[
              { id: "all", label: "Everyone", color: "var(--iris)", points: d.rounds.map((x) => ({ x: x.round, y: x.calibrated })) },
              ...countries.map((c, i) => ({ id: c, label: c, color: palette[(i + 1) % palette.length], dashed: true, points: d.rounds.map((x) => ({ x: x.round, y: x.by_country[c] ?? 0 })) })),
            ]}
          />
          <p className="mt-3 text-sm text-ink-2">
            Net social effect: <b className={cx("num", d.social_pull >= 0 ? "text-yes" : "text-no")}>{signedPts(d.social_pull)}</b>
            {d.rounds.some((x) => x.news) && <> News that landed: {d.rounds.filter((x) => x.news).map((x) => x.news).join("; ")}</>}
          </p>
        </Panel>
        <Panel>
          <SectionHead title="Projected adoption over time">
            Bass diffusion model fitted to the simulation: {pctSmart(d.bass.p)} start on their own each month, social pull {d.bass.q.toFixed(2)}.
          </SectionHead>
          <LineChart xLabel="month" xFormat={(x) => `M${x}`} series={[{ id: "bass", label: "Cumulative adoption", color: "var(--yes)", points: d.bass.curve.map((c) => ({ x: c.month, y: c.adoption })) }]} />
        </Panel>
      </div>
      {d.examples.length > 0 && (
        <Panel>
          <SectionHead title="People who changed their mind" />
          <ul className="grid gap-3 md:grid-cols-2">
            {d.examples.slice(0, 10).map((e) => (
              <li key={`${e.persona_id}-${e.round}`} className="rounded-xl bg-panel-2 px-4 py-3">
                <div className="flex items-baseline justify-between gap-3">
                  <span className="text-sm font-semibold text-ink">
                    {e.name}, {e.country}
                  </span>
                  <span className="num text-sm">
                    {pctSmart(e.from)} to <b className={e.to > e.from ? "text-yes" : "text-no"}>{pctSmart(e.to)}</b>
                  </span>
                </div>
                <p className="mt-1 text-sm text-ink-2">{e.why}</p>
              </li>
            ))}
          </ul>
        </Panel>
      )}
    </div>
  );
}

/* ---------------------------------------------------------------- Method */

function Method({ live }: { live: LiveState }) {
  const r = live.results!;
  const spec = live.spec;
  const u = live.usage;
  const cal = r.headline.calibration;
  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <Panel>
        <SectionHead title="How the number is made" />
        <ol className="flex list-decimal flex-col gap-2 pl-5 text-sm text-ink-2">
          <li>
            {r.headline.agents_total} simulated people gave {r.headline.samples} answers in their own words, using a probability scale (the Juster scale) that predicts real behaviour better than yes/no questions.
          </li>
          <li>
            Stated intentions are corrected for the gap between saying and doing (log-odds factor {cal.a}, shift {cal.b}, {cal.source === "backtest" ? `fitted on ${cal.n_cases} past cases` : "default values until you run backtests"}).
          </li>
          {r.headline.kind === "action" && <li>The result is multiplied by awareness: {pctSmart(r.headline.reach)} of the audience hears about it within the time frame.</li>}
          <li>Each person counts in proportion to how many real people they represent in their country and group.</li>
          <li>The range comes from resampling people and model answers 1,000 times.</li>
        </ol>
        <dl className="mt-5 grid grid-cols-3 gap-4 border-t border-line pt-4">
          <div>
            <dt className="t-tiny text-ink-3">Raw stated</dt>
            <dd className="num text-xl font-bold">{pctSmart(r.headline.stated)}</dd>
          </div>
          <div>
            <dt className="t-tiny text-ink-3">After correction</dt>
            <dd className="num text-xl font-bold">{pctSmart(r.headline.calibrated)}</dd>
          </div>
          <div>
            <dt className="t-tiny text-ink-3">Final</dt>
            <dd className="num text-xl font-bold">{pctSmart(r.headline.value)}</dd>
          </div>
        </dl>
      </Panel>
      <Panel>
        <SectionHead title="Model agreement">The same people answered through each model. Big gaps mean the answer depends on the model.</SectionHead>
        <RangeRows rows={r.model_agreement.map((m) => ({ key: m.model, label: m.model, value: m.calibrated, n: m.n }))} />
        {u && (
          <dl className="mt-5 grid grid-cols-3 gap-4 border-t border-line pt-4">
            <div>
              <dt className="t-tiny text-ink-3">Model calls</dt>
              <dd className="num text-xl font-bold">{u.calls.toLocaleString()}</dd>
            </div>
            <div>
              <dt className="t-tiny text-ink-3">Tokens</dt>
              <dd className="num text-xl font-bold">{(u.prompt_tokens + u.completion_tokens).toLocaleString()}</dd>
            </div>
            <div>
              <dt className="t-tiny text-ink-3">Cost</dt>
              <dd className="num text-xl font-bold">{money(u.cost_usd)}</dd>
            </div>
          </dl>
        )}
      </Panel>
      {live.research && live.research.facts.length > 0 && (
        <Panel className="lg:col-span-2">
          <SectionHead title="Facts people were given">Found by web search when the run started. Agents only saw facts relevant to their country.</SectionHead>
          <ul className="grid gap-4 md:grid-cols-2">
            {live.research.facts.map((f, i) => (
              <li key={i} className="text-sm">
                <p className="text-ink">{f.statement}</p>
                <p className="mt-0.5 t-small text-ink-3">
                  {f.relevance}
                  {f.source_urls.map((u) => (
                    <a key={u} href={u} target="_blank" rel="noreferrer" className="ml-2 font-semibold text-iris-ink hover:underline">
                      {new URL(u).hostname.replace("www.", "")}
                    </a>
                  ))}
                </p>
              </li>
            ))}
          </ul>
        </Panel>
      )}
      {spec && (
        <Panel className="lg:col-span-2">
          <SectionHead title="Scenario" />
          <dl className="grid gap-4 text-sm md:grid-cols-2">
            <div>
              <dt className="font-semibold text-ink">Question</dt>
              <dd className="text-ink-2">{spec.question}</dd>
            </div>
            <div>
              <dt className="font-semibold text-ink">Asked of each person</dt>
              <dd className="text-ink-2">{spec.persona_question}</dd>
            </div>
            <div className="md:col-span-2">
              <dt className="font-semibold text-ink">What people saw</dt>
              <dd className="text-ink-2">{spec.subject}</dd>
            </div>
            <div>
              <dt className="font-semibold text-ink">Groups</dt>
              <dd className="mt-1 flex flex-wrap gap-1.5">
                {spec.segments.map((s) => (
                  <Chip key={s.name}>
                    {s.name}
                    {s.countries.length > 0 && ` (${s.countries.join(", ")})`}
                  </Chip>
                ))}
              </dd>
            </div>
            <div>
              <dt className="font-semibold text-ink">Outside factors</dt>
              <dd className="text-ink-2">{spec.forces.map((f) => `${f.name} (${f.origin})`).join("; ") || "None"}</dd>
            </div>
            {spec.assumptions.length > 0 && (
              <div className="md:col-span-2">
                <dt className="font-semibold text-ink">Assumptions</dt>
                <dd className="text-ink-2">{spec.assumptions.join(" ")}</dd>
              </div>
            )}
          </dl>
        </Panel>
      )}
    </div>
  );
}
