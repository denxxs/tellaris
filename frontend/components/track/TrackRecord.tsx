"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Button, Card, CardHead, Empty, Input, Pill } from "@/components/ui";
import { api, type Prediction, type TrackSummary } from "@/lib/api";
import { useMeta } from "@/lib/meta";
import { cx, pctSmart } from "@/lib/format";

const KIND = { action: "Doing things", belief: "Opinions and votes" } as const;
const day = (iso: string) => new Date(`${iso}T00:00:00`).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
const pts = (v: number) => `${v > 0 ? "+" : v < 0 ? "−" : ""}${Math.abs(v * 100).toFixed(1)} pts`;
const today = () => new Date().toISOString().slice(0, 10);

/** Predicted against what really happened. On the diagonal is a perfect call. */
function CallsChart({ points }: { points: NonNullable<TrackSummary["points"]> }) {
  const size = 240;
  const pad = 40;
  const end = 16;
  const x = (v: number) => pad + v * (size - pad - end);
  const y = (v: number) => size - pad + 12 - v * (size - pad - end);
  return (
    <figure>
      <svg viewBox={`0 0 ${size} ${size}`} className="w-full max-w-[260px]" role="img" aria-label="Predicted against real results">
        {[0, 0.5, 1].map((t) => (
          <g key={t}>
            <line x1={x(0)} x2={x(1)} y1={y(t)} y2={y(t)} stroke="var(--rule)" />
            <text x={pad - 6} y={y(t) + 4} textAnchor="end" className="fill-[var(--faint)] text-[10px]">
              {t * 100}%
            </text>
            <text x={x(t)} y={y(0) + 16} textAnchor="middle" className="fill-[var(--faint)] text-[10px]">
              {t * 100}%
            </text>
          </g>
        ))}
        <line x1={x(0)} y1={y(0)} x2={x(1)} y2={y(1)} stroke="var(--muted)" strokeDasharray="3 3" />
        {points.map((p) => (
          <circle key={p.id} cx={x(p.predicted)} cy={y(p.actual)} r={4.5} fill="var(--yes)" fillOpacity={0.85}>
            <title>{`${p.title}: predicted ${pctSmart(p.predicted)}, real ${pctSmart(p.actual)}`}</title>
          </circle>
        ))}
      </svg>
      <figcaption className="mt-1 text-[12px] text-faint">Across: predicted. Up: what really happened. On the dashed line is a perfect call.</figcaption>
    </figure>
  );
}

function ResolveForm({ p, onDone }: { p: Prediction; onDone: () => void }) {
  const [value, setValue] = useState("");
  const [source, setSource] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const n = Number(value);
  const ok = value !== "" && n >= 0 && n <= 100;
  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      await api.resolvePrediction(p.id, { actual: n / 100, source });
      onDone();
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  };
  return (
    <div className="mt-3 flex flex-wrap items-center gap-2">
      <div className="flex items-center gap-1.5 text-[13px] text-muted">
        <Input type="number" min={0} max={100} step="any" aria-label={`Real ${p.measure.toLowerCase()}`} placeholder="Real %" value={value} onChange={(e) => setValue(e.target.value)} className="w-24" />%
      </div>
      <Input aria-label="Source of the real result" placeholder="Source, e.g. a link to the results" value={source} onChange={(e) => setSource(e.target.value)} className="min-w-0 flex-1 basis-56" />
      <Button size="sm" variant="primary" onClick={save} disabled={!ok} busy={busy}>
        Score it
      </Button>
      {error && <p className="w-full text-[13px] text-negative">{error}</p>}
    </div>
  );
}

function Row({ p, onChange }: { p: Prediction; onChange: () => void }) {
  const { countryName } = useMeta();
  const [resolving, setResolving] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const due = p.status === "open" && p.resolves_on <= today();
  const off = p.error ?? null;
  return (
    <li className="border-b border-rule py-3.5 first:pt-0 last:border-0 last:pb-0">
      <div className="flex flex-wrap items-start justify-between gap-x-6 gap-y-2">
        <div className="min-w-0 flex-1 basis-72">
          <div className="flex flex-wrap items-center gap-2">
            <Link href={`/runs/${p.run_id}`} className="text-[14px] font-medium text-text hover:underline">
              {p.title}
            </Link>
            {p.status === "resolved" ? <Pill tone={p.within_range ? "positive" : "neutral"}>{p.within_range ? "Inside likely range" : "Scored"}</Pill> : due ? <Pill tone="warning">Result due</Pill> : <Pill>Open</Pill>}
          </div>
          <div className="mt-0.5 text-[13px] leading-[18px] text-muted">
            {p.measure}
            {p.targets.length ? ` in ${p.targets.slice(0, 4).map(countryName).join(", ")}${p.targets.length > 4 ? ` and ${p.targets.length - 4} more` : ""}` : ""}
          </div>
          <div className="mt-0.5 text-[12px] text-faint">
            Predicted {day(p.made_on)}, result {p.status === "resolved" ? "entered" : "due"} {p.status === "resolved" && p.resolved_at ? new Date(p.resolved_at * 1000).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" }) : day(p.resolves_on)}
            {p.note ? `. ${p.note}` : ""}
            {p.source ? (
              <>
                {". "}
                {/^https?:\/\//.test(p.source) ? (
                  <a href={p.source} target="_blank" rel="noreferrer" className="underline-offset-2 hover:underline">
                    Source
                  </a>
                ) : (
                  p.source
                )}
              </>
            ) : null}
          </div>
        </div>
        <div className="flex shrink-0 items-start gap-6 text-right">
          <div>
            <div className="text-[12px] text-faint">Predicted</div>
            <div className="num text-[16px]">{pctSmart(p.predicted)}</div>
            {p.ci && <div className="num text-[12px] text-faint">{pctSmart(p.ci[0])} to {pctSmart(p.ci[1])}</div>}
          </div>
          <div>
            <div className="text-[12px] text-faint">Real</div>
            <div className="num text-[16px]">{p.actual != null ? pctSmart(p.actual) : "–"}</div>
            {off != null && <div className={cx("num text-[12px]", Math.abs(off) > 0.1 ? "text-negative" : "text-muted")}>{pts(off)}</div>}
          </div>
        </div>
      </div>
      <div className="mt-2 flex flex-wrap gap-2">
        {p.status === "open" && !resolving && (
          <Button size="sm" variant={due ? "primary" : "secondary"} onClick={() => setResolving(true)}>
            Enter the real result
          </Button>
        )}
        {p.status === "open" && !resolving && (
          <Button
            size="sm"
            busy={refreshing}
            disabled={refreshing}
            title="Run the same people again with today's news, and see what moved"
            onClick={async () => {
              setRefreshing(true);
              try {
                const res = await api.whatif(p.run_id, "Refreshed with today's news", {});
                window.location.href = `/runs/${res.id}`;
              } catch {
                setRefreshing(false);
              }
            }}
          >
            Refresh with today&apos;s news
          </Button>
        )}
        <Button
          size="sm"
          variant="ghost"
          onClick={async () => {
            await api.deletePrediction(p.id).catch(() => {});
            onChange();
          }}
        >
          Remove
        </Button>
      </div>
      {resolving && p.status === "open" && <ResolveForm p={p} onDone={onChange} />}
    </li>
  );
}

/** Predictions made before the outcome was known, scored when it is: the honest accuracy test. */
export function TrackRecord({ onCalibrated }: { onCalibrated: () => void }) {
  const [data, setData] = useState<{ predictions: Prediction[]; summary: TrackSummary } | null>(null);
  const [fitNote, setFitNote] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const load = () => api.trackRecord().then(setData).catch((e) => setError(e.message));
  useEffect(() => {
    load();
  }, []);

  if (!data) return error ? <Card id="track"><p className="text-[13px] text-negative">{error}</p></Card> : null;
  const s = data.summary;
  const learn = async (kind: string) => {
    setFitNote(null);
    try {
      const r = await api.fitFromTrack(kind);
      setFitNote(`Learned from ${r.n} predictions. Average error on them goes from ${(r.mae_before * 100).toFixed(1)} to ${(r.mae_after * 100).toFixed(1)} points. New runs use it.`);
      onCalibrated();
    } catch (e) {
      setFitNote((e as Error).message);
    }
  };

  return (
    <Card id="track" className="scroll-mt-4">
      <CardHead title="Track record" aside={s.due ? `${s.due} ${s.due === 1 ? "result" : "results"} due` : undefined}>
        Predictions saved before the real answer was known, scored once it is. This is the test models can&apos;t have memorised.
      </CardHead>
      {!data.predictions.length ? (
        <Empty title="Nothing tracked yet">
          Open a finished simulation about something that hasn&apos;t happened yet and choose Track this prediction. When the result is out, enter it here.
        </Empty>
      ) : (
        <div className="flex flex-col gap-6">
          <dl className="grid grid-cols-2 gap-x-6 gap-y-4 border-b border-rule pb-5 sm:grid-cols-4">
            <div>
              <dt className="text-[12px] text-faint">Tracked</dt>
              <dd className="t-kpi">{s.total}</dd>
            </div>
            <div>
              <dt className="text-[12px] text-faint">Scored</dt>
              <dd className="t-kpi">{s.resolved}</dd>
            </div>
            <div>
              <dt className="text-[12px] text-faint">Average error</dt>
              <dd className="t-kpi">{s.mae != null ? `${(s.mae * 100).toFixed(1)} pts` : "–"}</dd>
            </div>
            <div>
              <dt className="text-[12px] text-faint">Inside the likely range</dt>
              <dd className="t-kpi">{s.within_range != null ? pctSmart(s.within_range) : "–"}</dd>
            </div>
          </dl>

          <div className="grid grid-cols-1 items-start gap-8 lg:grid-cols-[minmax(0,1fr)_260px]">
            <ul>
              {data.predictions.map((p) => (
                <Row key={p.id} p={p} onChange={load} />
              ))}
            </ul>
            {s.points && s.points.length > 0 && (
              <div className="flex flex-col gap-5">
                <CallsChart points={s.points} />
                {Object.entries(s.by_kind).map(([kind, v]) => (
                  <div key={kind} className="border-t border-rule pt-4">
                    <div className="text-[14px] font-medium">{KIND[kind as keyof typeof KIND] ?? kind}</div>
                    <div className="mt-0.5 text-[12px] text-faint">
                      {v.n} scored, off by {(v.mae * 100).toFixed(1)} points on average.
                    </div>
                    <Button size="sm" className="mt-2" disabled={!v.can_fit} onClick={() => learn(kind)}>
                      {v.can_fit ? "Learn the correction from these" : `Learn the correction at 3 scored`}
                    </Button>
                  </div>
                ))}
                {fitNote && <p className="text-[13px] leading-[18px] text-muted">{fitNote}</p>}
              </div>
            )}
          </div>
        </div>
      )}
    </Card>
  );
}
