"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Card, CardHead, Empty, Pill, Select } from "@/components/ui";
import { useMeta } from "@/lib/meta";
import { cx, pctSmart } from "@/lib/format";
import type { NewsItem, Reach, Results, Timeline, TimelineEventOut } from "@/lib/types";

export const REACH_LABEL: Record<Reach, string> = {
  mass: "Everyone's talking about it",
  broad: "Widely covered",
  niche: "Specialist news",
};

export function fmtDay(iso: string) {
  const d = new Date(`${iso}T00:00:00`);
  return d.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
}

function daysAgo(iso: string, asOf: string) {
  const n = Math.round((new Date(`${asOf}T00:00:00`).getTime() - new Date(`${iso}T00:00:00`).getTime()) / 86400000);
  if (n <= 0) return "today";
  if (n === 1) return "yesterday";
  if (n < 60) return `${n} days ago`;
  const m = Math.round(n / 30);
  return m < 24 ? `${m} months ago` : `${Math.round(n / 365)} years ago`;
}

function addMonths(iso: string, months: number) {
  const d = new Date(`${iso}T00:00:00`);
  const whole = Math.floor(months);
  d.setMonth(d.getMonth() + whole);
  d.setDate(d.getDate() + Math.round((months - whole) * 30));
  return d;
}

function tickLabel(asOf: string, months: number, unit: Timeline["unit"]) {
  const d = addMonths(asOf, months);
  if (unit === "year") return String(d.getFullYear());
  if (unit === "quarter") return `Q${Math.floor(d.getMonth() / 3) + 1} ${String(d.getFullYear()).slice(2)}`;
  return d.toLocaleDateString("en-GB", { month: "short" }) + (d.getMonth() === 0 || months === 0 ? ` ${String(d.getFullYear()).slice(2)}` : "");
}

function host(url: string) {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

/* ---------------------------------------------------------------- timeline chart */

function EventMark({ e, size = 10 }: { e: Pick<TimelineEventOut, "kind">; size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 10 10" aria-hidden className="shrink-0">
      {e.kind === "scheduled" ? <circle cx={5} cy={5} r={4} fill="var(--flow)" /> : <circle cx={5} cy={5} r={3.75} fill="var(--surface)" stroke="var(--flow)" strokeWidth={1.5} />}
    </svg>
  );
}

function TimelineChart({ t, sel, onSel }: { t: Timeline; sel: string | null; onSel: (id: string | null) => void }) {
  const box = useRef<HTMLDivElement>(null);
  const [w, setW] = useState(720);
  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => setW(Math.round(e.contentRect.width)));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  const [hover, setHover] = useState<{ x: number; m: number } | null>(null);

  const H = 260;
  const pad = { l: 40, r: 16, t: 34, b: 30 };
  const iw = Math.max(w - pad.l - pad.r, 100);
  const ih = H - pad.t - pad.b;
  const horizon = t.horizon_months;
  const end = (r: number) => (r === 0 ? 0 : t.periods.find((p) => p.round === r)?.end_month ?? 0);
  const opinion = t.opinion.map((o) => ({ m: end(o.round), v: o.value }));
  const base = t.base?.opinion.map((o) => ({ m: end(o.round), v: o.value })) ?? [];
  const adoption = t.adoption.map((a) => ({ m: a.month, v: a.adoption }));
  const baseAdoption = t.base?.adoption.map((a) => ({ m: a.month, v: a.adoption })) ?? [];
  const maxV = Math.max(0.1, ...opinion.map((p) => p.v), ...base.map((p) => p.v), ...adoption.map((p) => p.v), ...baseAdoption.map((p) => p.v));
  const top = Math.min(1, Math.ceil((maxV * 1.15) / 0.05) * 0.05);
  const x = (m: number) => pad.l + (m / horizon) * iw;
  const y = (v: number) => pad.t + ih - (v / top) * ih;
  const path = (pts: { m: number; v: number }[]) => pts.map((p, i) => `${i ? "L" : "M"}${x(p.m).toFixed(1)},${y(p.v).toFixed(1)}`).join("");
  const unitStep = t.unit === "year" ? 12 : t.unit === "quarter" ? 3 : 1;
  const tickEvery = Math.max(unitStep, Math.ceil(horizon / Math.max(2, Math.floor(iw / 70)) / unitStep) * unitStep);
  const ticks: number[] = [];
  for (let m = 0; m <= horizon + 1e-6; m += tickEvery) ticks.push(m);
  const yTicks = [0, top / 2, top];

  // Nearest values under the pointer, for the readout.
  const at = (pts: { m: number; v: number }[], m: number) => {
    if (!pts.length) return null;
    let best = pts[0];
    for (const p of pts) if (Math.abs(p.m - m) < Math.abs(best.m - m)) best = p;
    return best;
  };
  const hv = hover && {
    op: at(opinion, hover.m),
    ad: at(adoption, hover.m),
    bop: at(base, hover.m),
    bad: at(baseAdoption, hover.m),
  };

  return (
    <div ref={box} className="relative w-full">
      <svg
        width={w}
        height={H}
        className="block w-full touch-pan-y"
        role="img"
        aria-label="Opinion and adoption over the time frame, with events marked"
        onPointerMove={(ev) => {
          const r = (ev.currentTarget as SVGSVGElement).getBoundingClientRect();
          const px = ev.clientX - r.left;
          if (px < pad.l || px > pad.l + iw) return setHover(null);
          setHover({ x: px, m: ((px - pad.l) / iw) * horizon });
        }}
        onPointerLeave={() => setHover(null)}
      >
        {yTicks.map((v) => (
          <g key={v}>
            <line x1={pad.l} x2={pad.l + iw} y1={y(v)} y2={y(v)} stroke="var(--rule)" />
            <text x={pad.l - 6} y={y(v) + 4} textAnchor="end" className="fill-[var(--faint)] text-[11px]">
              {Math.round(v * 100)}%
            </text>
          </g>
        ))}
        {ticks.map((m) => (
          <text key={m} x={x(m)} y={H - 10} textAnchor={m === 0 ? "start" : m >= horizon ? "end" : "middle"} className="fill-[var(--faint)] text-[11px]">
            {m === 0 ? "Today" : tickLabel(t.as_of, m, t.unit)}
          </text>
        ))}
        {t.events.map((e) => (
          <g key={e.id}>
            <line x1={x(e.at_month)} x2={x(e.at_month)} y1={pad.t - 14} y2={pad.t + ih} stroke="var(--flow)" strokeOpacity={sel === e.id ? 0.9 : 0.35} strokeDasharray={e.kind === "assumed" ? "3 3" : undefined} />
          </g>
        ))}
        {baseAdoption.length > 1 && <path d={path(baseAdoption)} fill="none" stroke="var(--text)" strokeOpacity={0.45} strokeWidth={1.5} strokeDasharray="4 4" />}
        {base.length > 1 && <path d={path(base)} fill="none" stroke="var(--yes)" strokeOpacity={0.6} strokeWidth={1.5} strokeDasharray="4 4" />}
        {adoption.length > 1 && <path d={path(adoption)} fill="none" stroke="var(--text)" strokeOpacity={0.8} strokeWidth={2} />}
        {opinion.length > 1 && (
          <>
            <path d={path(opinion)} fill="none" stroke="var(--yes)" strokeWidth={2} />
            {opinion.map((p) => (
              <circle key={p.m} cx={x(p.m)} cy={y(p.v)} r={4} fill="var(--yes)" stroke="var(--surface)" strokeWidth={2} />
            ))}
          </>
        )}
        {hover && <line x1={hover.x} x2={hover.x} y1={pad.t} y2={pad.t + ih} stroke="var(--control)" />}
        {t.events.map((e) => (
          <g
            key={e.id}
            role="button"
            tabIndex={0}
            aria-label={`${e.when}, ${e.name}. ${e.kind === "assumed" ? "Your what-if" : "Real, scheduled"}`}
            className="cursor-pointer outline-none"
            onClick={() => onSel(sel === e.id ? null : e.id)}
            onKeyDown={(ev) => (ev.key === "Enter" || ev.key === " ") && (ev.preventDefault(), onSel(sel === e.id ? null : e.id))}
          >
            <circle cx={x(e.at_month)} cy={pad.t - 18} r={12} fill="transparent" />
            {e.kind === "scheduled" ? (
              <circle cx={x(e.at_month)} cy={pad.t - 18} r={sel === e.id ? 6.5 : 5} fill="var(--flow)" stroke="var(--surface)" strokeWidth={2} />
            ) : (
              <circle cx={x(e.at_month)} cy={pad.t - 18} r={sel === e.id ? 6 : 4.5} fill="var(--surface)" stroke="var(--flow)" strokeWidth={2} />
            )}
          </g>
        ))}
      </svg>
      {hover && hv && (
        <div
          className="pointer-events-none absolute top-8 z-10 w-max max-w-[220px] rounded-md border border-border bg-surface px-2.5 py-2 text-[12px] leading-4"
          style={{ left: Math.min(Math.max(hover.x + 10, 0), w - 200) }}
        >
          <div className="mb-1 font-medium text-text">{hover.m < 0.5 ? "Today" : tickLabel(t.as_of, hover.m, t.unit === "month" ? "month" : t.unit)}</div>
          {hv.op && (
            <div className="flex justify-between gap-3">
              <span className="text-muted">Leaning yes</span>
              <span className="num">
                {pctSmart(hv.op.v)}
                {hv.bop && <span className="text-faint"> / {pctSmart(hv.bop.v)}</span>}
              </span>
            </div>
          )}
          {hv.ad && (
            <div className="flex justify-between gap-3">
              <span className="text-muted">Adopted</span>
              <span className="num">
                {pctSmart(hv.ad.v)}
                {hv.bad && <span className="text-faint"> / {pctSmart(hv.bad.v)}</span>}
              </span>
            </div>
          )}
          {(hv.bop || hv.bad) && <div className="mt-1 text-faint">Second figure: without your what-ifs</div>}
        </div>
      )}
    </div>
  );
}

function Legend({ base, assumed, scheduled }: { base: boolean; assumed: boolean; scheduled: boolean }) {
  const line = (color: string, dashed = false, opacity = 1) => (
    <svg width={18} height={8} aria-hidden>
      <line x1={0} x2={18} y1={4} y2={4} stroke={color} strokeOpacity={opacity} strokeWidth={2} strokeDasharray={dashed ? "4 3" : undefined} />
    </svg>
  );
  return (
    <div className="mb-2 flex flex-wrap gap-x-4 gap-y-1 text-[12px] text-muted">
      <span className="inline-flex items-center gap-1.5">{line("var(--yes)")} Leaning yes</span>
      <span className="inline-flex items-center gap-1.5">{line("var(--text)", false, 0.8)} Adopted (projection)</span>
      {base && <span className="inline-flex items-center gap-1.5">{line("var(--text)", true, 0.5)} Without your what-ifs</span>}
      {scheduled && (
        <span className="inline-flex items-center gap-1.5">
          <EventMark e={{ kind: "scheduled" }} /> Real, scheduled
        </span>
      )}
      {assumed && (
        <span className="inline-flex items-center gap-1.5">
          <EventMark e={{ kind: "assumed" }} /> Your what-if
        </span>
      )}
    </div>
  );
}

function EventRow({ e, active, onSel }: { e: TimelineEventOut; active: boolean; onSel: () => void }) {
  const { countryName } = useMeta();
  return (
    <li className={cx("border-b border-rule last:border-0", active && "bg-raised")}>
      <button onClick={onSel} className="flex w-full items-start gap-3 px-1 py-2.5 text-left" aria-expanded={active}>
        <span className="mt-1">
          <EventMark e={e} />
        </span>
        <span className="min-w-0 flex-1">
          <span className="flex flex-wrap items-baseline gap-x-2 text-[12px] text-faint">
            <span className="text-muted">{e.when}</span>
            <span>{e.label}</span>
            {e.countries.length > 0 && <span>{e.countries.map(countryName).join(", ")}</span>}
          </span>
          <span className="block text-[14px] font-medium leading-5 text-text">{e.name}</span>
          {active && e.description && <span className="mt-0.5 block text-[13px] leading-[18px] text-muted">{e.description}</span>}
          <span className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-[12px] text-muted">
            <Pill tone={e.kind === "assumed" ? "warning" : "neutral"}>{e.kind === "assumed" ? "Your what-if" : "Real, scheduled"}</Pill>
            {e.heard_share != null && <span>Heard by {pctSmart(e.heard_share)} of people talking</span>}
            {e.round == null && <span>After the people stopped talking</span>}
            {e.url && (
              <a href={e.url} target="_blank" rel="noreferrer" className="text-text underline decoration-control underline-offset-2 hover:decoration-text" onClick={(ev) => ev.stopPropagation()}>
                {e.source || host(e.url)}
              </a>
            )}
          </span>
        </span>
      </button>
    </li>
  );
}

/* ---------------------------------------------------------------- news list */

function NewsRow({ n, asOf, isNew }: { n: NewsItem; asOf: string; isNew: boolean }) {
  const { countryName } = useMeta();
  const byC = Object.entries(n.known_by_country ?? {}).sort((a, b) => b[1] - a[1]);
  return (
    <li className="border-b border-rule py-3.5 first:pt-0 last:border-0 last:pb-0">
      <div className="flex flex-wrap items-baseline gap-x-2 text-[12px] text-faint">
        <time dateTime={n.published} className="text-muted">
          {fmtDay(n.published)}
        </time>
        <span>{daysAgo(n.published, asOf)}</span>
        <span>{n.source}</span>
        {isNew && <Pill tone="positive">New since the original run</Pill>}
      </div>
      <h3 className="mt-0.5 text-[15px] font-medium leading-[22px]">
        <a href={n.url} target="_blank" rel="noreferrer" className="hover:underline">
          {n.headline}
        </a>
      </h3>
      {n.summary && <p className="mt-0.5 text-[13px] leading-[18px] text-muted">{n.summary}</p>}
      <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-[12px] text-muted">
        <span>{REACH_LABEL[n.reach]}</span>
        <span>{n.countries.length ? n.countries.map(countryName).join(", ") : "Worldwide"}</span>
        {n.stance !== "neutral" && <span className={n.stance === "helps" ? "text-yes" : "text-no"}>{n.stance === "helps" ? "Helps the case" : "Hurts the case"}</span>}
        {n.upcoming && <span>Takes effect {fmtDay(n.upcoming)}</span>}
        {n.lasting && <span>Still in effect</span>}
      </div>
      {n.known_share != null && (
        <div className="mt-2 grid grid-cols-[minmax(0,160px)_auto] items-center gap-x-3 gap-y-1 text-[12px] sm:grid-cols-[minmax(0,200px)_auto_1fr]">
          <span className="h-1.5 rounded-full bg-raised" role="img" aria-label={`Known by ${pctSmart(n.known_share)} of the people simulated`}>
            <span className="block h-full rounded-full bg-[var(--text)] opacity-70" style={{ width: `${n.known_share * 100}%` }} />
          </span>
          <span className="text-muted">
            Known by <span className="num text-text">{pctSmart(n.known_share)}</span>
          </span>
          {byC.length > 1 && (
            <span className="col-span-2 text-faint sm:col-span-1">
              {byC.map(([c, v]) => `${countryName(c)} ${pctSmart(v)}`).join(", ")}
            </span>
          )}
        </div>
      )}
    </li>
  );
}

/* ---------------------------------------------------------------- tab */

export function NewsTimelineTab({ r }: { r: Results }) {
  const status = r.news_status ?? "none_found";
  const { countryName } = useMeta();
  const t = r.timeline;
  const news = useMemo(() => r.news ?? [], [r.news]);
  const asOf = r.as_of ?? t?.as_of ?? "";
  const [sel, setSel] = useState<string | null>(null);
  const [country, setCountry] = useState("");
  const fresh = new Set(r.comparison?.new_news ?? []);
  const countries = useMemo(() => [...new Set(news.flatMap((n) => n.countries))].sort(), [news]);
  const shown = news.filter((n) => !country || n.countries.length === 0 || n.countries.includes(country));
  const hasChart = !!t && (t.opinion.length > 1 || t.events.length > 0);
  const assumed = t?.events.some((e) => e.kind === "assumed") ?? false;
  const scheduled = t?.events.some((e) => e.kind === "scheduled") ?? false;
  const lastOp = t?.opinion.at(-1)?.value;
  const lastBase = t?.base?.opinion.at(-1)?.value;

  return (
    <div className="grid grid-cols-1 items-start gap-6 lg:grid-cols-5">
      {hasChart && t && (
        <Card className="lg:col-span-5">
          <CardHead title="The timeline">
            From today, {fmtDay(asOf)}, to the end of the {t.horizon_months}-month time frame.
            {t.periods.length > 0 && ` People talked it over in ${t.periods.length} periods; events reach only the people who'd hear of them.`}
          </CardHead>
          {lastOp != null && lastBase != null && (
            <p className="mb-3 text-[14px] text-text">
              With your what-ifs, the share leaning yes ends at <span className="num font-medium">{pctSmart(lastOp)}</span>, against{" "}
              <span className="num font-medium">{pctSmart(lastBase)}</span> with real news only:{" "}
              <span className={cx("num", lastOp - lastBase >= 0 ? "text-yes" : "text-no")}>
                {lastOp - lastBase >= 0 ? "+" : "−"}
                {Math.abs((lastOp - lastBase) * 100).toFixed(1)} points
              </span>
              .
            </p>
          )}
          <Legend base={!!t.base} assumed={assumed} scheduled={scheduled} />
          <TimelineChart t={t} sel={sel} onSel={setSel} />
          {t.events.length > 0 ? (
            <ul className="mt-3 border-t border-rule">
              {t.events.map((e) => (
                <EventRow key={e.id} e={e} active={sel === e.id} onSel={() => setSel(sel === e.id ? null : e.id)} />
              ))}
            </ul>
          ) : (
            <p className="mt-2 text-[13px] text-muted">No scheduled events fall inside the time frame. Add your own under What-if events when you set up a run.</p>
          )}
        </Card>
      )}

      <Card className="lg:col-span-5">
        <CardHead
          title="The world right now"
          aside={
            countries.length > 1 ? (
              <Select label="Country" value={country} onChange={setCountry} options={[{ value: "", label: "All countries" }, ...countries.map((c) => ({ value: c, label: countryName(c) }))]} className="w-44" />
            ) : undefined
          }
        >
          Real news as of {fmtDay(asOf)}, picked for how relevant and recent it is. Each person only knows the stories they&apos;d plausibly have come across.
          {r.comparison?.parent_as_of && ` The original run used news as of ${fmtDay(r.comparison.parent_as_of)}.`}
        </CardHead>
        {shown.length > 0 ? (
          <ul>
            {shown.map((n) => (
              <NewsRow key={n.id} n={n} asOf={asOf} isNew={fresh.has(n.id)} />
            ))}
          </ul>
        ) : (
          <Empty title={status === "no_search" ? "Web search is off" : status === "off" ? "News was switched off for this run" : "No current news found"}>
            {status === "no_search"
              ? "Turn on a search provider in Models so people know what's happening in the world today."
              : status === "off"
                ? "People went on what they already knew. Turn Current news back on in the setup to ground them in the world as it is now."
                : "Nothing recent and relevant came up, so people went on what they already knew."}
          </Empty>
        )}
      </Card>
    </div>
  );
}
