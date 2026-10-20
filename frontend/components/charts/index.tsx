"use client";

import { useId, useMemo, useState } from "react";
import { cx, pctSmart } from "@/lib/format";

/** Horizontal rows: label, bar with uncertainty whisker, value. Scales to the largest upper bound. */
export function RangeRows({
  rows,
  max,
  emphasis,
}: {
  rows: { key: string; label: string; value: number; ci?: [number, number]; note?: string; n?: number }[];
  max?: number;
  emphasis?: number;
}) {
  const top = max ?? Math.max(0.05, ...rows.map((r) => r.ci?.[1] ?? r.value)) * 1.08;
  const x = (v: number) => `${Math.max(0, Math.min(1, v / top)) * 100}%`;
  return (
    <div className="flex flex-col">
      {rows.map((r) => (
        <div key={r.key} className="grid grid-cols-[minmax(0,1fr)_minmax(0,1.5fr)_64px] items-center gap-3 border-b border-line py-2.5 last:border-0">
          <div className="min-w-0">
            <div className="truncate text-sm font-semibold text-ink">{r.label}</div>
            {(r.note || r.n != null) && <div className="truncate t-tiny text-ink-3">{[r.n != null ? `${r.n} ${r.n === 1 ? "person" : "people"}` : null, r.note].filter(Boolean).join(", ")}</div>}
          </div>
          <div className="relative h-6">
            <div className="absolute inset-y-[11px] left-0 right-0 rounded-full bg-panel-2" />
            {emphasis != null && <div className="absolute inset-y-1 w-px bg-ink-3" style={{ left: x(emphasis) }} title="Overall" />}
            {r.ci && (
              <div className="absolute inset-y-[9px] rounded-full bg-iris/25" style={{ left: x(r.ci[0]), width: `calc(${x(r.ci[1])} - ${x(r.ci[0])})` }} />
            )}
            <div className="absolute inset-y-[9px] left-0 rounded-full bg-iris" style={{ width: x(r.value) }} />
            <div className="absolute top-1/2 size-3 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-panel bg-iris" style={{ left: x(r.value) }} />
          </div>
          <div className="num text-right text-sm font-semibold text-ink">{pctSmart(r.value)}</div>
        </div>
      ))}
    </div>
  );
}

/** Simple share bars (themes, decisions). */
export function ShareBars({ rows, tone = "iris" }: { rows: { label: string; share: number; sub?: string }[]; tone?: "iris" | "yes" | "no" }) {
  const max = Math.max(0.01, ...rows.map((r) => r.share));
  const bg = { iris: "bg-iris", yes: "bg-yes", no: "bg-no" }[tone];
  return (
    <ul className="flex flex-col gap-3">
      {rows.map((r, i) => (
        <li key={`${r.label}-${i}`}>
          <div className="flex items-baseline justify-between gap-3">
            <span className="text-sm font-semibold text-ink">{r.label}</span>
            <span className="num text-sm text-ink-2">{pctSmart(r.share)}</span>
          </div>
          <div className="mt-1.5 h-2 overflow-hidden rounded-full bg-panel-2">
            <div className={cx("h-full rounded-full", bg)} style={{ width: `${(r.share / max) * 100}%` }} />
          </div>
          {r.sub && <p className="mt-1 t-small text-ink-3">“{r.sub}”</p>}
        </li>
      ))}
    </ul>
  );
}

/** Stacked bar for decision mixes. */
export function StackBar({ parts }: { parts: { label: string; value: number; color: string }[] }) {
  const total = parts.reduce((a, p) => a + p.value, 0) || 1;
  return (
    <div>
      <div className="flex h-4 overflow-hidden rounded-full">
        {parts.map((p) => (
          <div key={p.label} style={{ width: `${(p.value / total) * 100}%`, background: p.color }} title={`${p.label}: ${pctSmart(p.value)}`} />
        ))}
      </div>
      <div className="mt-3 flex flex-wrap gap-x-5 gap-y-1">
        {parts.map((p) => (
          <span key={p.label} className="inline-flex items-center gap-2 text-sm text-ink-2">
            <span className="inline-block size-2.5 rounded-full" style={{ background: p.color }} aria-hidden />
            {p.label} <span className="num font-semibold text-ink">{pctSmart(p.value)}</span>
          </span>
        ))}
      </div>
    </div>
  );
}

type Series = { id: string; label: string; color: string; points: { x: number; y: number }[]; dashed?: boolean };

/** Line chart with hover readout. y in 0..1 shown as %. */
export function LineChart({ series, xLabel, height = 220, xFormat = (x: number) => String(x), yMax }: { series: Series[]; xLabel: string; height?: number; xFormat?: (x: number) => string; yMax?: number }) {
  const W = 640;
  const H = height;
  const pad = { l: 44, r: 16, t: 12, b: 34 };
  const gid = useId();
  const all = series.flatMap((s) => s.points);
  const xs = all.map((p) => p.x);
  const x0 = Math.min(...xs);
  const x1 = Math.max(...xs);
  const top = yMax ?? Math.max(0.05, ...all.map((p) => p.y)) * 1.15;
  const sx = (x: number) => pad.l + ((x - x0) / Math.max(1e-9, x1 - x0)) * (W - pad.l - pad.r);
  const sy = (y: number) => H - pad.b - (y / top) * (H - pad.t - pad.b);
  const ticks = useMemo(() => {
    const step = top > 0.6 ? 0.2 : top > 0.3 ? 0.1 : top > 0.12 ? 0.05 : 0.02;
    const out = [];
    for (let v = 0; v <= top + 1e-9; v += step) out.push(v);
    return out;
  }, [top]);
  const xTicks = useMemo(() => {
    const uniq = [...new Set(xs)].sort((a, b) => a - b);
    if (uniq.length <= 8) return uniq;
    const step = Math.ceil(uniq.length / 6);
    return uniq.filter((_, i) => i % step === 0);
  }, [xs]);
  const [hx, setHx] = useState<number | null>(null);

  if (!all.length) return null;
  return (
    <div>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="w-full"
        role="img"
        aria-label={`Chart of ${series.map((s) => s.label).join(", ")} by ${xLabel}`}
        onMouseLeave={() => setHx(null)}
        onMouseMove={(e) => {
          const rect = (e.currentTarget as SVGSVGElement).getBoundingClientRect();
          const px = ((e.clientX - rect.left) / rect.width) * W;
          const xv = x0 + ((px - pad.l) / (W - pad.l - pad.r)) * (x1 - x0);
          const nearest = [...new Set(xs)].reduce((a, b) => (Math.abs(b - xv) < Math.abs(a - xv) ? b : a), xs[0]);
          setHx(nearest);
        }}
      >
        {ticks.map((t) => (
          <g key={t}>
            <line x1={pad.l} x2={W - pad.r} y1={sy(t)} y2={sy(t)} stroke="var(--line)" />
            <text x={pad.l - 8} y={sy(t) + 4} textAnchor="end" fontSize="11" fill="var(--ink-3)">
              {pctSmart(t)}
            </text>
          </g>
        ))}
        {xTicks.map((t) => (
          <text key={t} x={sx(t)} y={H - 12} textAnchor="middle" fontSize="11" fill="var(--ink-3)">
            {xFormat(t)}
          </text>
        ))}
        {series.map((s, i) => {
          const d = s.points.map((p, j) => `${j ? "L" : "M"}${sx(p.x)},${sy(p.y)}`).join(" ");
          const area = `${d} L${sx(s.points[s.points.length - 1].x)},${sy(0)} L${sx(s.points[0].x)},${sy(0)} Z`;
          return (
            <g key={s.id}>
              {i === 0 && (
                <>
                  <defs>
                    <linearGradient id={`${gid}-g`} x1="0" x2="0" y1="0" y2="1">
                      <stop offset="0" stopColor={s.color} stopOpacity="0.18" />
                      <stop offset="1" stopColor={s.color} stopOpacity="0" />
                    </linearGradient>
                  </defs>
                  <path d={area} fill={`url(#${gid}-g)`} />
                </>
              )}
              <path d={d} fill="none" stroke={s.color} strokeWidth={2.2} strokeDasharray={s.dashed ? "5 5" : undefined} strokeLinejoin="round" />
              {s.points.length <= 12 && s.points.map((p) => <circle key={p.x} cx={sx(p.x)} cy={sy(p.y)} r={3} fill="var(--panel)" stroke={s.color} strokeWidth={2} />)}
            </g>
          );
        })}
        {hx != null && <line x1={sx(hx)} x2={sx(hx)} y1={pad.t} y2={H - pad.b} stroke="var(--ink-3)" strokeDasharray="2 3" />}
      </svg>
      <div className="mt-1 flex min-h-6 flex-wrap items-center gap-x-5 gap-y-1 t-small text-ink-2">
        {series.map((s) => {
          const pt = hx != null ? s.points.find((p) => p.x === hx) : s.points[s.points.length - 1];
          return (
            <span key={s.id} className="inline-flex items-center gap-2">
              <span className="inline-block h-0.5 w-4 rounded" style={{ background: s.color }} aria-hidden />
              {s.label}
              {pt && <span className="num font-semibold text-ink">{pctSmart(pt.y)}</span>}
            </span>
          );
        })}
        {hx != null && <span className="text-ink-3">at {xFormat(hx)}</span>}
      </div>
    </div>
  );
}

/** A big answer with its uncertainty band, on a 0-100% track. */
export function AnswerTrack({ value, ci, ifAware }: { value: number; ci: [number, number]; ifAware?: number }) {
  const pos = (v: number) => `${Math.max(0, Math.min(1, v)) * 100}%`;
  return (
    <div className="relative mt-2 h-10" aria-hidden>
      <div className="absolute inset-x-0 top-4 h-2 rounded-full bg-panel-2" />
      <div className="absolute top-3 h-4 rounded-full bg-iris/25" style={{ left: pos(ci[0]), width: `calc(${pos(ci[1])} - ${pos(ci[0])})` }} />
      <div className="absolute top-[9px] size-5 -translate-x-1/2 rounded-full border-[3px] border-panel bg-iris shadow" style={{ left: pos(value) }} />
      {ifAware != null && ifAware !== value && (
        <div className="absolute top-2 h-6 w-0.5 -translate-x-1/2 rounded bg-ink-3" style={{ left: pos(ifAware) }} title="Among people who hear about it" />
      )}
      <div className="absolute inset-x-0 top-7 flex justify-between t-tiny text-ink-3">
        <span>0%</span>
        <span>50%</span>
        <span>100%</span>
      </div>
    </div>
  );
}
