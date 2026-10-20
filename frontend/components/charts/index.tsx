"use client";

import { useEffect, useMemo, useRef, useState } from "react";

/** Width of an element, so charts draw at their real size and text stays legible. */
function useWidth<T extends HTMLElement>(fallback = 640) {
  const ref = useRef<T>(null);
  const [w, setW] = useState(fallback);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => setW(Math.max(260, Math.round(e.contentRect.width))));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return [ref, w] as const;
}
import { cx, people as fmtPeople, pctSmart } from "@/lib/format";

/* ------------------------------------------------------------------
   Ranked rows: label (+ subline) on the left, value on the right, a 6px
   bar under the label in the one data hue, the likely range as a lighter
   band, and an optional 1px tick for the overall answer.
------------------------------------------------------------------- */
export function BarRows({
  rows,
  reference,
  max,
  limit,
}: {
  rows: { key: string; label: string; sub?: string; value: number; ci?: [number, number]; people?: number }[];
  reference?: number;
  max?: number;
  limit?: number;
}) {
  const [all, setAll] = useState(false);
  const top = max ?? Math.max(0.02, ...rows.map((r) => r.ci?.[1] ?? r.value)) * 1.05;
  const x = (v: number) => `${Math.max(0, Math.min(1, v / top)) * 100}%`;
  const shown = limit && !all ? rows.slice(0, limit) : rows;
  return (
    <div>
      <ul className="flex flex-col">
        {shown.map((r) => (
          <li key={r.key} className="border-b border-rule py-2.5 last:border-0">
            <div className="flex items-baseline justify-between gap-4">
              <div className="min-w-0">
                <span className="block truncate text-[14px] text-text">{r.label}</span>
                {(r.sub || r.people != null) && (
                  <span className="block truncate text-[12px] leading-4 text-faint">{[r.people != null ? `${fmtPeople(r.people)} people` : null, r.sub].filter(Boolean).join(", ")}</span>
                )}
              </div>
              <span className="num shrink-0 text-[14px] text-text">{pctSmart(r.value)}</span>
            </div>
            <div className="relative mt-1.5 h-1.5 rounded-full bg-raised">
              {r.ci && <div className="absolute inset-y-0 rounded-full bg-yes/25" style={{ left: x(r.ci[0]), width: `calc(${x(r.ci[1])} - ${x(r.ci[0])})` }} />}
              <div className="absolute inset-y-0 left-0 rounded-full bg-yes" style={{ width: x(r.value) }} />
              {reference != null && <div className="absolute -inset-y-1 w-px bg-text/50" style={{ left: x(reference) }} title={`Overall ${pctSmart(reference)}`} />}
            </div>
          </li>
        ))}
      </ul>
      {limit && rows.length > limit && (
        <button onClick={() => setAll(!all)} className="mt-2 text-[13px] font-medium text-muted hover:text-text">
          {all ? "Show fewer" : `View all ${rows.length}`}
        </button>
      )}
    </div>
  );
}

/** Share rows for themes: label, share, a thin bar, and a verbatim example. */
export function ShareRows({ rows, tone = "yes" }: { rows: { label: string; share: number; example?: string }[]; tone?: "yes" | "no" | "text" }) {
  const max = Math.max(0.01, ...rows.map((r) => r.share));
  const bg = { yes: "bg-yes", no: "bg-no", text: "bg-text" }[tone];
  return (
    <ul className="flex flex-col">
      {rows.map((r, i) => (
        <li key={`${r.label}-${i}`} className="border-b border-rule py-2.5 last:border-0">
          <div className="flex items-baseline justify-between gap-4">
            <span className="text-[14px] text-text">{r.label}</span>
            <span className="num shrink-0 text-[14px] text-muted">{pctSmart(r.share)}</span>
          </div>
          <div className="mt-1.5 h-1 rounded-full bg-raised">
            <div className={cx("h-full rounded-full", bg)} style={{ width: `${(r.share / max) * 100}%` }} />
          </div>
          {r.example && <p className="mt-1.5 text-[13px] leading-[18px] text-muted">“{r.example}”</p>}
        </li>
      ))}
    </ul>
  );
}

/** A 100% stacked bar with 2px seams; the legend is a small table of the same marks. */
export function StackBar({ parts }: { parts: { label: string; value: number; color: string }[] }) {
  const total = parts.reduce((a, p) => a + p.value, 0) || 1;
  return (
    <div>
      <div className="flex h-3 gap-0.5 overflow-hidden rounded">
        {parts
          .filter((p) => p.value > 0)
          .map((p) => (
            <div key={p.label} style={{ width: `${(p.value / total) * 100}%`, background: p.color }} title={`${p.label}: ${pctSmart(p.value / total)}`} />
          ))}
      </div>
      <dl className="mt-3 grid grid-cols-2 gap-x-6 gap-y-1.5 sm:grid-cols-4">
        {parts.map((p) => (
          <div key={p.label} className="flex items-center justify-between gap-2 text-[13px]">
            <dt className="inline-flex items-center gap-2 text-muted">
              <span className="inline-block size-2 rounded-full" style={{ background: p.color }} aria-hidden />
              {p.label}
            </dt>
            <dd className="num text-text">{pctSmart(p.value / total)}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

type Series = { id: string; label: string; color: string; points: { x: number; y: number }[]; dashed?: boolean };

/** Line chart: straight segments, faint gridlines, round ticks above the max, hover readout. */
export function LineChart({
  series,
  xLabel,
  height = 200,
  xFormat = (x: number) => String(x),
  yMax,
  reference,
}: {
  series: Series[];
  xLabel: string;
  height?: number;
  xFormat?: (x: number) => string;
  yMax?: number;
  reference?: { x: number; label: string };
}) {
  const [box, W] = useWidth<HTMLDivElement>();
  const H = height;
  const pad = { l: 40, r: 12, t: reference ? 22 : 10, b: 28 };
  const all = useMemo(() => series.flatMap((s) => s.points), [series]);
  const xs = useMemo(() => [...new Set(all.map((p) => p.x))].sort((a, b) => a - b), [all]);
  const [hx, setHx] = useState<number | null>(null);
  if (!all.length) return null;
  const x0 = xs[0];
  const x1 = xs[xs.length - 1];
  const rawTop = Math.max(0.005, ...all.map((p) => p.y));
  const step = yMax ? yMax / 4 : rawTop > 0.6 ? 0.25 : rawTop > 0.3 ? 0.1 : rawTop > 0.12 ? 0.05 : rawTop > 0.05 ? 0.02 : 0.01;
  const top = yMax ?? Math.floor(rawTop / step + 1) * step;
  const ticks: number[] = [];
  for (let v = 0; v <= top + 1e-9; v += step) ticks.push(Math.round(v * 10000) / 10000);
  while (ticks.length > 6) ticks.splice(1, 1);
  const sx = (x: number) => pad.l + ((x - x0) / Math.max(1e-9, x1 - x0)) * (W - pad.l - pad.r);
  const sy = (y: number) => H - pad.b - (y / top) * (H - pad.t - pad.b);
  const maxTicks = Math.max(3, Math.floor(W / 90));
  const xTicks = xs.length <= maxTicks ? xs : xs.filter((_, i) => i % Math.ceil(xs.length / maxTicks) === 0);

  return (
    <div ref={box}>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="block w-full"
        height={H}
        role="img"
        aria-label={`${series.map((s) => s.label).join(", ")} by ${xLabel}`}
        onMouseLeave={() => setHx(null)}
        onMouseMove={(e) => {
          const rect = e.currentTarget.getBoundingClientRect();
          const px = ((e.clientX - rect.left) / rect.width) * W;
          const xv = x0 + ((px - pad.l) / (W - pad.l - pad.r)) * (x1 - x0);
          setHx(xs.reduce((a, b) => (Math.abs(b - xv) < Math.abs(a - xv) ? b : a), xs[0]));
        }}
      >
        {ticks.map((t) => (
          <g key={t}>
            <line x1={pad.l} x2={W - pad.r} y1={sy(t)} y2={sy(t)} stroke="var(--grid)" strokeWidth={t === 0 ? 1.5 : 1} />
            <text x={pad.l - 8} y={sy(t) + 4} textAnchor="end" fontSize="11" fill="var(--faint)">
              {pctSmart(t)}
            </text>
          </g>
        ))}
        {xTicks.map((t, i) => (
          <text key={t} x={sx(t)} y={H - 8} textAnchor={i === 0 ? "start" : i === xTicks.length - 1 && xTicks.length > 1 ? "end" : "middle"} fontSize="11" fill="var(--faint)">
            {xFormat(t)}
          </text>
        ))}
        {reference && (
          <g>
            <line x1={sx(reference.x)} x2={sx(reference.x)} y1={pad.t - 4} y2={H - pad.b} stroke="var(--text)" strokeOpacity="0.5" strokeDasharray="3 3" />
            <text x={Math.min(sx(reference.x) + 5, W - 120)} y={12} fontSize="11" fill="var(--muted)">
              {reference.label}
            </text>
          </g>
        )}
        {series.map((s) => (
          <path
            key={s.id}
            d={s.points.map((p, j) => `${j ? "L" : "M"}${sx(p.x)},${sy(p.y)}`).join(" ")}
            fill="none"
            stroke={s.color}
            strokeWidth={2}
            strokeDasharray={s.dashed ? "4 4" : undefined}
            strokeLinejoin="round"
          />
        ))}
        {hx != null && (
          <g>
            <line x1={sx(hx)} x2={sx(hx)} y1={pad.t} y2={H - pad.b} stroke="var(--control)" />
            {series.map((s) => {
              const p = s.points.find((q) => q.x === hx);
              return p ? <circle key={s.id} cx={sx(p.x)} cy={sy(p.y)} r={4} fill="var(--surface)" stroke={s.color} strokeWidth={2} /> : null;
            })}
          </g>
        )}
      </svg>
      {(series.length > 1 || hx != null) && (
        <div className="mt-1 flex min-h-5 flex-wrap items-center gap-x-4 gap-y-1 text-[12px] text-muted">
          {series.map((s) => {
            const p = hx != null ? s.points.find((q) => q.x === hx) : s.points[s.points.length - 1];
            return (
              <span key={s.id} className="inline-flex items-center gap-1.5">
                <svg width="14" height="6" aria-hidden>
                  <line x1="0" x2="14" y1="3" y2="3" stroke={s.color} strokeWidth="2" strokeDasharray={s.dashed ? "3 2" : undefined} />
                </svg>
                {s.label}
                {p && <span className="num text-text">{pctSmart(p.y)}</span>}
              </span>
            );
          })}
          {hx != null && <span className="text-faint">at {xFormat(hx)}</span>}
        </div>
      )}
    </div>
  );
}

/** The answer on a 0-100% track with its likely range, and a tick for "if they hear about it". */
export function RangeTrack({ value, ci, aware }: { value: number; ci: [number, number]; aware?: number }) {
  const pos = (v: number) => `${Math.max(0, Math.min(1, v)) * 100}%`;
  return (
    <div className="relative h-9" aria-hidden>
      <div className="absolute inset-x-0 top-2 h-1.5 rounded-full bg-raised" />
      <div className="absolute top-2 h-1.5 rounded-full bg-yes/30" style={{ left: pos(ci[0]), width: `max(2px, calc(${pos(ci[1])} - ${pos(ci[0])}))` }} />
      <div className="absolute top-[3px] size-4 -translate-x-1/2 rounded-full border-[3px] border-surface bg-yes" style={{ left: pos(value) }} />
      {aware != null && Math.abs(aware - value) > 0.005 && <div className="absolute top-0.5 h-5 w-px -translate-x-1/2 bg-text/60" style={{ left: pos(aware) }} />}
      <div className="absolute inset-x-0 top-6 flex justify-between text-[11px] text-faint">
        <span>0%</span>
        <span>50%</span>
        <span>100%</span>
      </div>
    </div>
  );
}

/** Diverging bars around zero, for correlations and stances (-1..1). */
export function Diverging({ rows }: { rows: { label: string; value: number }[] }) {
  return (
    <ul className="flex flex-col gap-2.5">
      {rows.map((d) => (
        <li key={d.label} className="grid grid-cols-[minmax(0,150px)_minmax(0,1fr)_48px] items-center gap-3 text-[13px]">
          <span className="truncate text-text">{d.label}</span>
          <div className="relative h-1.5 rounded-full bg-raised">
            <div className="absolute -inset-y-1 left-1/2 w-px bg-control" />
            <div
              className={cx("absolute inset-y-0 rounded-full", d.value >= 0 ? "bg-yes" : "bg-no")}
              style={d.value >= 0 ? { left: "50%", width: `${Math.min(1, d.value) * 50}%` } : { right: "50%", width: `${Math.min(1, -d.value) * 50}%` }}
            />
          </div>
          <span className="num text-right text-muted">
            {d.value > 0 ? "+" : d.value < 0 ? "−" : ""}
            {Math.abs(d.value).toFixed(2)}
          </span>
        </li>
      ))}
    </ul>
  );
}
