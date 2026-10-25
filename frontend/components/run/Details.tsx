"use client";

import { useEffect, useState } from "react";
import { BarRows, Diverging, LineChart, ShareRows, StackBar } from "@/components/charts";
import { Card, CardHead, Pill } from "@/components/ui";
import { WorldMap } from "@/components/world/WorldMap";
import { api } from "@/lib/api";
import { useMeta } from "@/lib/meta";
import { companyLabel, cx, int, money, people, pctSmart, shortJob, signedPts, titleCase } from "@/lib/format";
import type { LiveState } from "@/lib/useRunStream";
import type { Committee, Results } from "@/lib/types";

const rowsOf = (xs: Results["by_segment"], lab = (s: string) => s) =>
  xs.map((s) => ({ key: s.key!, label: lab(s.label!), value: s.value, ci: s.ci, people: s.people }));

/* ---------------------------------------------------------------- Countries */

const DRIVER_LABEL: Record<string, string> = {
  internet_daily: "Uses the internet daily",
  smartphone: "Has a smartphone",
  account: "Has a bank or mobile-money account",
  credit_card: "Has a credit card",
  emergency_hard: "Short of emergency money",
  news_online: "Reads news online",
  age: "Older",
};

export function CountriesTab({ r, live }: { r: Results; live: LiveState }) {
  const { countryName } = useMeta();
  const values = Object.fromEntries(r.by_country.map((c) => [c.key!, c.calibrated]));
  const segs = [...new Set(r.by_country_segment.map((m) => m.key!.split("|").slice(1).join("|")))];
  const countries = r.by_country.map((c) => c.key!);
  const peak = Math.max(0.01, ...r.by_country_segment.map((m) => m.value));
  return (
    <div className="grid grid-cols-1 items-start gap-6 lg:grid-cols-6">
      <Card className="lg:col-span-3">
        <CardHead title="By country" aside="Overall is the tick">
          The bar is the most likely value; the lighter band is the likely range.
        </CardHead>
        <BarRows reference={r.headline.value} rows={r.by_country.map((c) => ({ key: c.key!, label: c.label!, value: c.value, ci: c.ci, people: c.people, sub: c.top_objection?.[0] ? `main objection: ${c.top_objection[0]}` : undefined }))} />
      </Card>
      <Card pad={false} className="lg:col-span-3">
        <div className="px-5 pt-5">
          <CardHead title="Where people lean">Shaded by willingness among people who hear about it.</CardHead>
        </div>
        <div className="px-2 pb-3">
          <WorldMap world={live.world} targets={countries} values={values} showArcs={false} compact label="Countries shaded by willingness" />
        </div>
      </Card>
      {segs.length > 1 && countries.length > 1 && (
        <Card className="lg:col-span-6">
          <CardHead title="Country and group">Each cell is the answer for one group in one country. Darker is higher.</CardHead>
          <div className="scroll-thin overflow-x-auto">
            <table className="w-full min-w-[480px] text-[14px]">
              <thead>
                <tr className="border-b border-border text-[12px] text-faint">
                  <th className="pb-2 text-left font-normal">Group</th>
                  {countries.map((c) => (
                    <th key={c} className="pb-2 text-right font-normal">
                      {countryName(c)}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {segs.map((s) => (
                  <tr key={s} className="border-b border-rule last:border-0">
                    <td className="py-2 pr-4 text-text">{s}</td>
                    {countries.map((c) => {
                      const cell = r.by_country_segment.find((m) => m.key === `${c}|${s}`);
                      return (
                        <td key={c} className="num py-2 text-right">
                          {cell ? (
                            <span className="inline-block min-w-16 rounded px-2 py-0.5" style={{ background: `color-mix(in oklab, var(--yes) ${Math.round((cell.value / peak) * 45)}%, transparent)` }} title={`${cell.n} simulated, ${people(cell.people)} real people`}>
                              {pctSmart(cell.value)}
                            </span>
                          ) : (
                            <span className="text-faint">–</span>
                          )}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}
    </div>
  );
}

/* ---------------------------------------------------------------- Groups */

export function GroupsTab({ r }: { r: Results }) {
  return (
    <div className="grid grid-cols-1 items-start gap-6 lg:grid-cols-6">
      <Card className="lg:col-span-3">
        <CardHead title="By group" aside="Overall is the tick" />
        <BarRows rows={rowsOf(r.by_segment)} reference={r.headline.value} />
      </Card>
      <Card className="lg:col-span-3">
        <CardHead title="By job" />
        <BarRows rows={rowsOf(r.by_occupation, shortJob)} reference={r.headline.value} limit={8} />
      </Card>
      <Card className="lg:col-span-2">
        <CardHead title="By seniority" />
        <BarRows rows={rowsOf(r.by_seniority, titleCase)} reference={r.headline.value} />
      </Card>
      <Card className="lg:col-span-2">
        <CardHead title="By company" />
        <BarRows rows={rowsOf(r.by_company_type, companyLabel)} reference={r.headline.value} limit={6} />
      </Card>
      <Card className="lg:col-span-2">
        <CardHead title="What predicts a yes">How strongly each personal trait moves with the answer. Right of centre pushes towards yes.</CardHead>
        <Diverging rows={r.drivers.map((d) => ({ label: DRIVER_LABEL[d.trait] ?? d.label ?? titleCase(d.trait), value: d.correlation }))} />
      </Card>
    </div>
  );
}

/* ---------------------------------------------------------------- Influence */

export function InfluenceTab({ r, live }: { r: Results; live: LiveState }) {
  const { countryName } = useMeta();
  return (
    <div className="grid grid-cols-1 items-start gap-6 lg:grid-cols-6">
      <Card className="lg:col-span-6">
        <CardHead title="Measured effect of outside forces">
          People who feel each force compared with people who don&apos;t. A negative effect means the force makes a yes less likely.
        </CardHead>
        {r.influence_effects.length === 0 ? (
          <p className="text-[13px] text-muted">No outside force reached enough people to measure.</p>
        ) : (
          <div className="scroll-thin overflow-x-auto">
            <table className="w-full min-w-[680px] text-[14px]">
              <thead>
                <tr className="border-b border-border text-left text-[12px] text-faint">
                  <th className="pb-2 font-normal">Force</th>
                  <th className="pb-2 font-normal">Felt by</th>
                  <th className="pb-2 text-right font-normal">Those who feel it</th>
                  <th className="pb-2 text-right font-normal">Everyone else</th>
                  <th className="pb-2 text-right font-normal">Effect</th>
                  <th className="pb-2 text-right font-normal">Named by people</th>
                </tr>
              </thead>
              <tbody>
                {r.influence_effects.map((e) => (
                  <tr key={`${e.source}-${e.channel}`} className="border-b border-rule align-top last:border-0">
                    <td className="py-2.5 pr-4">
                      <div className="text-text">
                        {e.source_name} <span className="text-muted">through {e.channel.replace("_", " ")}</span>
                      </div>
                      <p className="mt-0.5 max-w-md text-[13px] leading-[18px] text-muted">{e.note}</p>
                    </td>
                    <td className="py-2.5 pr-3 text-[13px] text-muted">
                      <span className="num">{e.exposed_n}</span> in {e.countries.map(countryName).join(", ")}
                    </td>
                    <td className="num py-2.5 text-right">{pctSmart(e.exposed_value)}</td>
                    <td className="num py-2.5 text-right text-muted">{pctSmart(e.others_value)}</td>
                    <td className={cx("num py-2.5 text-right", (e.delta ?? 0) < -0.002 ? "text-negative" : (e.delta ?? 0) > 0.002 ? "text-positive" : "text-muted")}>{signedPts(e.delta)}</td>
                    <td className="num py-2.5 text-right text-muted">{int(e.mentions)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
      <Card pad={false} className="lg:col-span-4">
        <div className="px-5 pt-5">
          <CardHead title="Who shapes your markets">Thicker arrows are stronger. Dashed arrows are indirect.</CardHead>
        </div>
        <div className="px-2 pb-3">
          <WorldMap world={live.world} label="Influence between countries" />
        </div>
      </Card>
      <Card className="lg:col-span-2">
        <CardHead title="Voices from those countries">Asked the same question. Not counted in the answer.</CardHead>
        {r.influencer_voices.length === 0 ? (
          <p className="text-[13px] text-muted">No outside voices in this run.</p>
        ) : (
          <ul className="flex flex-col">
            {r.influencer_voices.map((v) => (
              <li key={v.source} className="border-b border-rule py-2.5 first:pt-0 last:border-0">
                <div className="flex items-baseline justify-between gap-3">
                  <span className="text-[14px] text-text">{countryName(v.source)}</span>
                  <span className="num text-[13px] text-muted">
                    {pctSmart(v.value)}, {v.n} {v.n === 1 ? "person" : "people"}
                  </span>
                </div>
                {v.quotes[0] && (
                  <p className="mt-1 text-[13px] leading-[18px] text-muted">
                    “{v.quotes[0].quote}” <span className="text-faint">{v.quotes[0].name}, {countryName(v.quotes[0].country)}</span>
                  </p>
                )}
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}

/* ---------------------------------------------------------------- Reasons */

export function ReasonsTab({ r, onSelect }: { r: Results; onSelect: (pid: string) => void }) {
  const t = r.themes;
  const { countryName } = useMeta();
  return (
    <div className="grid grid-cols-1 items-start gap-6 lg:grid-cols-6">
      <Card className="lg:col-span-2">
        <CardHead title="Why not" />
        {t?.objections.length ? <ShareRows tone="no" rows={t.objections.map((x) => ({ label: x.theme, share: x.share, example: x.example }))} /> : <p className="text-[13px] text-muted">No objections recorded.</p>}
      </Card>
      <Card className="lg:col-span-2">
        <CardHead title="Why yes" />
        {t?.reasons.length ? <ShareRows rows={t.reasons.map((x) => ({ label: x.theme, share: x.share, example: x.example }))} /> : <p className="text-[13px] text-muted">No reasons recorded.</p>}
      </Card>
      <Card className="lg:col-span-2">
        <CardHead title="What would change minds" />
        {t?.change_mind.length ? <ShareRows tone="text" rows={t.change_mind.map((x) => ({ label: x.theme, share: x.share, example: x.example }))} /> : <p className="text-[13px] text-muted">Nothing recorded.</p>}
      </Card>
      <Card className="lg:col-span-6">
        <CardHead title="Attention">How much attention people would realistically give it.</CardHead>
        <StackBar
          parts={[
            { label: "Ignore", value: r.attention.ignore ?? 0, color: "var(--control)" },
            { label: "Skim", value: r.attention.skim ?? 0, color: "var(--mid)" },
            { label: "Consider", value: r.attention.consider ?? 0, color: "color-mix(in oklab, var(--yes) 55%, var(--surface))" },
            { label: "Evaluate", value: r.attention.evaluate ?? 0, color: "var(--yes)" },
          ]}
        />
      </Card>
      {(["positive", "undecided", "negative"] as const).map((k) => (
        <Card key={k} className="lg:col-span-2">
          <CardHead title={{ positive: "Most keen", undecided: "On the fence", negative: "Least keen" }[k]} />
          <ul className="flex flex-col">
            {r.quotes[k].slice(0, 4).map((q) => (
              <li key={q.persona_id} className="border-b border-rule py-2.5 first:pt-0 last:border-0">
                <button onClick={() => onSelect(q.persona_id)} className="text-left">
                  <p className="text-[14px] leading-5 text-text">“{q.quote}”</p>
                  <p className="mt-0.5 text-[12px] text-faint">
                    {q.name}, {shortJob(q.occupation)}, {countryName(q.country)}
                    {q.p != null && `, ${pctSmart(q.p)}`}
                  </p>
                </button>
              </li>
            ))}
          </ul>
        </Card>
      ))}
    </div>
  );
}

/* ---------------------------------------------------------------- Pricing */

export function PricingTab({ r }: { r: Results }) {
  const w = r.wtp!;
  const { countryName } = useMeta();
  return (
    <div className="grid grid-cols-1 items-start gap-6 lg:grid-cols-6">
      <Card className="lg:col-span-4">
        <CardHead title="How many would pay at each price">The share of people whose maximum price is at or above each point.</CardHead>
        <LineChart
          xLabel="price"
          xFormat={(x) => money(x, w.currency)}
          yMax={1}
          reference={{ x: w.price, label: `Your price, ${money(w.price, w.currency)}` }}
          series={[{ id: "demand", label: "Would pay at least this", color: "var(--yes)", points: w.curve.map((c) => ({ x: c.price, y: c.share })) }]}
        />
      </Card>
      <Card className="lg:col-span-2">
        <dl className="grid grid-cols-2 gap-5">
          <div>
            <dt className="text-[13px] text-muted">Would pay your price</dt>
            <dd className="t-kpi mt-1">{pctSmart(w.share_at_price)}</dd>
          </div>
          <div>
            <dt className="text-[13px] text-muted">Typical maximum</dt>
            <dd className="t-kpi mt-1">{money(w.median, w.currency)}</dd>
          </div>
          <div className="col-span-2">
            <dt className="text-[13px] text-muted">Middle half of people</dt>
            <dd className="num mt-1 text-[16px]">
              {money(w.p25, w.currency)} to {money(w.p75, w.currency)} <span className="text-[13px] text-muted">per {w.period.replace(/-/g, " ")}</span>
            </dd>
          </div>
        </dl>
        <h3 className="mb-1 mt-6 text-[14px] font-medium">Typical maximum by country</h3>
        <ul>
          {w.by_country.map((c) => (
            <li key={c.country} className="flex items-baseline justify-between border-b border-rule py-2 text-[14px] last:border-0">
              <span>{countryName(c.country)}</span>
              <span className="num">
                {money(c.median, w.currency)} <span className="text-[12px] text-faint">from {c.n}</span>
              </span>
            </li>
          ))}
        </ul>
      </Card>
    </div>
  );
}

/* ---------------------------------------------------------------- Committees */

const DECISION_COLOR = { buy: "var(--yes)", pilot: "color-mix(in oklab, var(--yes) 45%, var(--surface))", defer: "var(--mid)", reject: "var(--no)" };
const DECISION_TONE = { buy: "yes", pilot: "yes", defer: "neutral", reject: "no" } as const;

export function CommitteesTab({ id, r }: { id: string; r: Results }) {
  const c = r.committees!;
  const { countryName } = useMeta();
  const [list, setList] = useState<Committee[] | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  useEffect(() => {
    api.committees(id).then(setList).catch(() => setList([]));
  }, [id]);
  return (
    <div className="grid grid-cols-1 items-start gap-6 lg:grid-cols-6">
      <Card className="lg:col-span-6">
        <CardHead title="What the companies decided">
          {c.n} buying groups debated it. Average chance a company pays: <span className="num text-text">{pctSmart(c.purchase_probability)}</span>
          {c.median_cycle_months != null && <>, typical deal {c.median_cycle_months} months</>}.
        </CardHead>
        <div className="grid grid-cols-1 gap-8 lg:grid-cols-3">
          <div>
            <h3 className="mb-3 text-[14px] font-medium">Decisions</h3>
            <StackBar parts={(["buy", "pilot", "defer", "reject"] as const).map((k) => ({ label: titleCase(k), value: c.decisions[k] ?? 0, color: DECISION_COLOR[k] }))} />
          </div>
          <div>
            <h3 className="mb-1 text-[14px] font-medium">By country</h3>
            <BarRows rows={c.by_country.map((x) => ({ key: x.country, label: countryName(x.country), value: x.purchase_probability, sub: `${x.n} companies` }))} />
          </div>
          <div>
            <h3 className="mb-1 text-[14px] font-medium">By company</h3>
            <BarRows rows={c.by_company_type.map((x) => ({ key: x.company_type, label: companyLabel(x.company_type), value: x.purchase_probability, sub: `${x.n} companies` }))} limit={4} />
          </div>
        </div>
      </Card>
      <Card className="lg:col-span-3">
        <CardHead title="Who pushes back">Average stance by role, from against to for.</CardHead>
        <Diverging rows={Object.entries(c.role_stance).sort((a, b) => a[1] - b[1]).map(([role, s]) => ({ label: titleCase(role), value: s }))} />
      </Card>
      <Card className="lg:col-span-3">
        <CardHead title="What blocks deals" />
        <ul>
          {c.top_blockers.slice(0, 4).map((b) => (
            <li key={b.blocker} className="flex justify-between gap-3 border-b border-rule py-2 text-[14px] first:pt-0 last:border-0 last:pb-0">
              <span className="first-letter:uppercase">{b.blocker}</span>
              <span className="num text-muted">{b.count}</span>
            </li>
          ))}
        </ul>
      </Card>
      <Card className="lg:col-span-6">
        <CardHead title="Inside the meetings" aside={list ? `${list.length} companies` : undefined} />
        {!list ? (
          <p className="text-[13px] text-muted">Loading…</p>
        ) : (
          <ul>
            {list.map((cm) => (
              <li key={cm.id} className="border-b border-rule last:border-0">
                <button className="flex w-full flex-wrap items-center justify-between gap-3 py-2.5 text-left" onClick={() => setOpen(open === cm.id ? null : cm.id)} aria-expanded={open === cm.id}>
                  <span className="min-w-0">
                    <span className="text-[14px] text-text">
                      {companyLabel(cm.company_type)} in {countryName(cm.country)}
                    </span>
                    <span className="text-[13px] text-muted">{cm.company_size_text ? `, ${cm.company_size_text}` : ""}, {cm.members.length} people in the room</span>
                  </span>
                  {cm.decision && (
                    <span className="flex items-center gap-2">
                      <Pill tone={DECISION_TONE[cm.decision.decision]}>{titleCase(cm.decision.decision)}</Pill>
                      <span className="num w-12 text-right text-[13px] text-muted">{pctSmart(cm.decision.probability_of_purchase)}</span>
                    </span>
                  )}
                </button>
                {open === cm.id && (
                  <div className="flex flex-col gap-3 pb-4">
                    {cm.transcript.map((t, i) => (
                      <div key={i} className="grid grid-cols-1 gap-1 sm:grid-cols-[180px_minmax(0,1fr)] sm:gap-4">
                        <div className="text-[13px]">
                          <div className="text-text">{t.name}</div>
                          <div className="text-faint">
                            {titleCase(t.role)}, round {t.round + 1}
                          </div>
                        </div>
                        <div className={cx("border-l-2 pl-3 text-[14px] leading-5", t.stance >= 0.2 ? "border-yes" : t.stance <= -0.2 ? "border-no" : "border-control")}>
                          {t.statement}
                          {t.conditions.length > 0 && <div className="mt-1 text-[12px] text-muted">Would agree if: {t.conditions.join("; ")}</div>}
                        </div>
                      </div>
                    ))}
                    {cm.decision && <p className="rounded-lg bg-raised px-3 py-2 text-[13px] text-muted">{cm.decision.summary}</p>}
                  </div>
                )}
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}

/* ---------------------------------------------------------------- Word of mouth */

export function SpreadTab({ r }: { r: Results }) {
  const d = r.diffusion!;
  const { countryName } = useMeta();
  const countries = Object.keys(d.rounds[0]?.by_country ?? {});
  return (
    <div className="grid grid-cols-1 items-start gap-6 lg:grid-cols-6">
      <Card className="lg:col-span-6">
        <CardHead title="Views as people talk">
          {d.agents} people connected by {int(d.edges)} ties over {d.rounds.length - 1} rounds. Social effect: <span className={cx("num", d.social_pull >= 0 ? "text-positive" : "text-negative")}>{signedPts(d.social_pull)}</span>.
        </CardHead>
        <LineChart
          xLabel="round"
          xFormat={(x) => (x === 0 ? "Before" : `Round ${x}`)}
          series={[
            { id: "all", label: "Everyone", color: "var(--yes)", points: d.rounds.map((x) => ({ x: x.round, y: x.calibrated })) },
            ...countries.slice(0, 3).map((c, i) => ({ id: c, label: countryName(c), color: ["var(--text)", "var(--flow)", "var(--no)"][i], dashed: true, points: d.rounds.map((x) => ({ x: x.round, y: x.by_country[c] ?? 0 })) })),
          ]}
        />
        {d.rounds.some((x) => x.news) && <p className="mt-3 text-[13px] text-muted">News that landed: {d.rounds.filter((x) => x.news).map((x) => `round ${x.round}, ${x.news}`).join("; ")}.</p>}
      </Card>
      {d.examples.length > 0 && (
        <Card className="lg:col-span-6">
          <CardHead title="People who changed their mind" />
          <ul className="grid grid-cols-1 gap-x-8 md:grid-cols-2">
            {d.examples.slice(0, 10).map((e) => (
              <li key={`${e.persona_id}-${e.round}`} className="border-b border-rule py-2.5">
                <div className="flex items-baseline justify-between gap-3 text-[14px]">
                  <span>
                    {e.name}, {countryName(e.country)}
                  </span>
                  <span className="num shrink-0">
                    {pctSmart(e.from)} to <span className={e.to > e.from ? "text-positive" : "text-negative"}>{pctSmart(e.to)}</span>
                  </span>
                </div>
                <p className="mt-0.5 text-[13px] leading-[18px] text-muted">{e.why}</p>
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  );
}

/* ---------------------------------------------------------------- Method */

export function MethodTab({ live }: { live: LiveState }) {
  const r = live.results!;
  const spec = live.spec;
  const u = live.usage;
  const cal = r.headline.calibration;
  const { countryName } = useMeta();
  return (
    <div className="grid grid-cols-1 items-start gap-6 lg:grid-cols-6">
      <Card className="lg:col-span-3">
        <CardHead title="How the number is made" />
        <ol className="flex list-decimal flex-col gap-2 pl-5 text-[14px] leading-5 text-muted">
          <li>
            {int(r.headline.agents_total)} simulated people gave {int(r.headline.samples)} answers in their own words, on the Juster probability scale, which predicts real behaviour better than yes or no questions. Each answer is read through Juster&apos;s published probabilities, with no other weighting.
          </li>
          <li>
            Stated intentions are corrected for the gap between saying and doing (factor {cal.a}, shift {cal.b}; {cal.source === "backtest" ? `learned from ${cal.n_cases} past cases` : "defaults until you run the Accuracy checks"}).
          </li>
          {r.headline.kind === "action" &&
            (r.headline.awareness != null ? (
              <li>The answer is for people who hear about it. You set awareness at {pctSmart(r.headline.awareness)}, which gives the totals for the whole audience.</li>
            ) : (
              <li>The answer is for people who hear about it. Tellaris doesn&apos;t guess how many will; totals are given per 1% of the audience who hears, and you can set your own awareness in the setup.</li>
            ))}
          <li>Each person counts for the number of real people they stand for, estimated from World Bank and ILO data for their country and job.</li>
          <li>The range comes from resampling people and model answers 1,000 times.</li>
        </ol>
        <dl className="mt-5 grid grid-cols-3 border-t border-border pt-4">
          {[
            ["What people said", r.headline.stated],
            ["After correction", r.headline.calibrated],
            ["Final answer", r.headline.value],
          ].map(([l, v]) => (
            <div key={l as string}>
              <dt className="text-[13px] text-muted">{l}</dt>
              <dd className="t-kpi mt-1">{pctSmart(v as number)}</dd>
            </div>
          ))}
        </dl>
      </Card>
      <Card className="lg:col-span-3">
        <CardHead title="Model agreement">The same people answered through each model. A big gap means the answer depends on the model.</CardHead>
        <BarRows rows={r.model_agreement.map((m) => ({ key: m.model, label: m.model, value: m.calibrated, sub: `${int(m.n)} answers` }))} />
        {u && (
          <dl className="mt-5 grid grid-cols-3 border-t border-border pt-4">
            <div>
              <dt className="text-[13px] text-muted">Model calls</dt>
              <dd className="t-kpi mt-1">{int(u.calls)}</dd>
            </div>
            <div>
              <dt className="text-[13px] text-muted">Tokens</dt>
              <dd className="t-kpi mt-1">{people(u.prompt_tokens + u.completion_tokens)}</dd>
            </div>
            <div>
              <dt className="text-[13px] text-muted">Cost</dt>
              <dd className="t-kpi mt-1">{money(u.cost_usd)}</dd>
            </div>
          </dl>
        )}
      </Card>
      {live.research && live.research.facts.length > 0 && (
        <Card className="lg:col-span-6">
          <CardHead title="Facts people were given">Found by web search when the run started. Each person only saw the facts that apply to their country.</CardHead>
          <ul className="grid grid-cols-1 gap-x-8 md:grid-cols-2">
            {live.research.facts.map((f, i) => (
              <li key={i} className="border-b border-rule py-2.5 text-[14px] leading-5">
                <p className="text-text">{f.statement}</p>
                <p className="mt-0.5 text-[12px] text-faint">
                  {f.relevance}
                  {f.source_urls.map((url) => {
                    let host = url;
                    try {
                      host = new URL(url).hostname.replace("www.", "");
                    } catch {}
                    return (
                      <a key={url} href={url} target="_blank" rel="noreferrer" className="ml-2 text-text underline-offset-2 hover:underline">
                        {host}
                      </a>
                    );
                  })}
                </p>
              </li>
            ))}
          </ul>
        </Card>
      )}
      {spec && (
        <Card className="lg:col-span-6">
          <CardHead title="Scenario" />
          <dl className="grid grid-cols-1 gap-x-8 gap-y-4 text-[14px] leading-5 md:grid-cols-2">
            <div>
              <dt className="text-[13px] text-muted">Question</dt>
              <dd>{spec.question}</dd>
            </div>
            <div>
              <dt className="text-[13px] text-muted">Asked of each person</dt>
              <dd>{spec.persona_question}</dd>
            </div>
            <div className="md:col-span-2">
              <dt className="text-[13px] text-muted">What people saw</dt>
              <dd>{spec.subject}</dd>
            </div>
            <div>
              <dt className="text-[13px] text-muted">Groups</dt>
              <dd>{spec.segments.map((s) => `${s.name}${s.countries.length ? ` (${s.countries.map(countryName).join(", ")})` : ""}`).join("; ")}</dd>
            </div>
            <div>
              <dt className="text-[13px] text-muted">Outside factors</dt>
              <dd>{spec.forces.map((f) => `${f.name} (${countryName(f.origin)})`).join("; ") || "None"}</dd>
            </div>
            {spec.assumptions.length > 0 && (
              <div className="md:col-span-2">
                <dt className="text-[13px] text-muted">Assumptions</dt>
                <dd>{spec.assumptions.join(" ")}</dd>
              </div>
            )}
          </dl>
        </Card>
      )}
    </div>
  );
}
