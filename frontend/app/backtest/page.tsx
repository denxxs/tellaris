"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Button, Card, CardHead, ErrorNote, Meter, PageHead, Pill, Slider, Toggle } from "@/components/ui";
import { TrackRecord } from "@/components/track/TrackRecord";
import { api, type BacktestCase, type BacktestJob, type Calibration } from "@/lib/api";
import { useMeta } from "@/lib/meta";
import { ago, cx, pctSmart } from "@/lib/format";

const KIND = { action: "Doing things: buying, signing up", belief: "Opinions and votes" } as const;

export default function AccuracyPage() {
  const { countryName } = useMeta();
  const [cases, setCases] = useState<BacktestCase[]>([]);
  const [picked, setPicked] = useState<string[]>([]);
  const [agents, setAgents] = useState(120);
  const [runs, setRuns] = useState(1);
  const [fit, setFit] = useState(true);
  const [job, setJob] = useState<BacktestJob | null>(null);
  const [history, setHistory] = useState<BacktestJob[]>([]);
  const [cal, setCal] = useState<Record<string, Calibration> | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = () => {
    api.calibration().then(setCal).catch(() => {});
    api.backtests().then(setHistory).catch(() => {});
  };

  useEffect(() => {
    api
      .cases()
      .then((c) => {
        setCases(c);
        setPicked(c.map((x) => x.id));
      })
      .catch((e) => setError(e.message));
    refresh();
  }, []);

  useEffect(() => {
    if (!job || job.status !== "running") return;
    const t = setInterval(async () => {
      const j = await api.backtest(job.id).catch(() => null);
      if (j) {
        setJob(j);
        if (j.status !== "running") refresh();
      }
    }, 1200);
    return () => clearInterval(t);
  }, [job]);

  const start = async () => {
    setError(null);
    try {
      const { id } = await api.startBacktest({ case_ids: picked, agents, runs_per_agent: runs, fit });
      setJob({ id, status: "running", rows: [], done: 0, total: picked.length });
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const shown = job ?? history[0] ?? null;

  return (
    <div className="mx-auto max-w-[1312px] px-4 py-6 md:px-6">
      <PageHead title="Accuracy">
        Score Tellaris against what really happened, and let it learn a correction from the gap.
      </PageHead>
      <div className="mb-6">
        <TrackRecord onCalibrated={refresh} />
      </div>
      <h2 className="t-section mb-1">Past events</h2>
      <p className="mb-4 max-w-[70ch] text-[14px] leading-5 text-muted">A quick check on famous outcomes. Models may already know them, so these scores are optimistic; your track record is the honest test.</p>
      {error && (
        <div className="mb-6">
          <ErrorNote>{error}</ErrorNote>
        </div>
      )}

      <div className="grid grid-cols-1 items-start gap-6 lg:grid-cols-6">
        <Card className="lg:col-span-4">
          <CardHead title="Known outcomes" aside={`${picked.length} of ${cases.length} selected`} />
          <ul>
            {cases.map((c) => (
              <li key={c.id} className="border-b border-rule last:border-0">
                <label className="flex cursor-pointer items-start gap-3 py-2.5">
                  <input
                    type="checkbox"
                    className="mt-0.5 size-4 accent-[var(--text)]"
                    checked={picked.includes(c.id)}
                    onChange={(e) => setPicked(e.target.checked ? [...picked, c.id] : picked.filter((x) => x !== c.id))}
                  />
                  <span className="min-w-0 flex-1">
                    <span className="block text-[14px] leading-5 text-text">{c.prompt.split(". ").slice(1, 2).join(". ") || c.prompt}</span>
                    <span className="block text-[12px] leading-4 text-faint">
                      {c.targets.map(countryName).join(", ")}, {c.as_of}. {c.source}
                    </span>
                  </span>
                  <span className="shrink-0 text-right">
                    <span className="num block text-[14px]">{pctSmart(c.actual)}</span>
                    <span className="block text-[12px] text-faint">{c.kind === "belief" ? "real vote" : "real share"}</span>
                  </span>
                </label>
              </li>
            ))}
          </ul>
        </Card>
        <div className="flex flex-col gap-6 lg:col-span-2">
          <Card>
            <CardHead title="Run a check" />
            <div className="flex flex-col gap-4">
              <div>
                <div className="mb-1 text-[13px] text-muted">People per case</div>
                <Slider label="People per case" value={agents} min={20} max={1000} step={10} onChange={setAgents} />
              </div>
              <div>
                <div className="mb-1 text-[13px] text-muted">Answers per person</div>
                <Slider label="Answers per person" value={runs} min={1} max={4} onChange={setRuns} />
              </div>
              <Toggle checked={fit} onChange={setFit} label="Learn a correction" description="Fit the say-do correction from these results." />
              <Button variant="primary" onClick={start} disabled={!picked.length || job?.status === "running"} busy={job?.status === "running"}>
                Run {picked.length} {picked.length === 1 ? "case" : "cases"}
              </Button>
              {job?.status === "running" && (
                <div>
                  <Meter value={(job.done ?? 0) / Math.max(job.total ?? 1, 1)} />
                  <p className="mt-1 text-[12px] text-faint">
                    {job.done ?? 0} of {job.total} done{job.current ? `, now ${job.current.replace(/_/g, " ")}` : ""}
                  </p>
                </div>
              )}
            </div>
          </Card>
          <Card>
            <CardHead title="Current correction" />
            {cal &&
              Object.values(cal).map((c) => (
                <div key={c.kind} className="flex items-center justify-between gap-3 border-b border-rule py-2.5 first:pt-0 last:border-0 last:pb-0">
                  <div>
                    <div className="text-[14px]">{KIND[c.kind as keyof typeof KIND] ?? c.kind}</div>
                    <div className="text-[12px] text-faint">
                      {c.source === "backtest" ? `Learned from ${c.n_cases} past events` : c.source === "track record" ? `Learned from ${c.n_cases} tracked predictions` : "Default"}, factor {c.a}, shift {c.b}
                    </div>
                  </div>
                  {c.source !== "default" ? (
                    <Button size="sm" variant="ghost" onClick={() => api.resetCalibration(c.kind).then(refresh)}>
                      Reset
                    </Button>
                  ) : (
                    <Pill>Default</Pill>
                  )}
                </div>
              ))}
          </Card>
        </div>

        {shown && shown.rows.length > 0 && (
          <Card className="lg:col-span-6">
            <CardHead title="Results" aside={shown.created_at ? ago(shown.created_at) : job?.status === "running" ? "Running" : undefined} />
            {shown.summary && (
              <dl className="mb-6 grid gap-6 sm:grid-cols-2">
                {Object.entries(shown.summary.by_kind).map(([k, v]) => (
                  <div key={k}>
                    <dt className="text-[14px] font-medium">{KIND[k as keyof typeof KIND] ?? k}</dt>
                    <dd className="mt-2 grid grid-cols-3 gap-3">
                      <div>
                        <div className="text-[12px] text-faint">Raw error</div>
                        <div className="t-kpi">{(v.mae_stated * 100).toFixed(1)}</div>
                      </div>
                      <div>
                        <div className="text-[12px] text-faint">Corrected</div>
                        <div className="t-kpi">{(v.mae_calibrated * 100).toFixed(1)}</div>
                      </div>
                      <div>
                        <div className="text-[12px] text-faint">After learning</div>
                        <div className="t-kpi">{v.mae_refit != null ? (v.mae_refit * 100).toFixed(1) : "–"}</div>
                      </div>
                    </dd>
                    <dd className="mt-1 text-[12px] text-faint">Average distance from the real result, in points, over {v.n} cases.</dd>
                  </div>
                ))}
              </dl>
            )}
            <div className="scroll-thin overflow-x-auto">
              <table className="w-full min-w-[560px] text-[14px]">
                <thead>
                  <tr className="border-b border-border text-left text-[12px] text-faint">
                    <th className="pb-2 font-normal">Case</th>
                    <th className="pb-2 text-right font-normal">Real</th>
                    <th className="pb-2 text-right font-normal">What people said</th>
                    <th className="pb-2 text-right font-normal">Corrected</th>
                    <th className="pb-2 text-right font-normal">Off by</th>
                  </tr>
                </thead>
                <tbody>
                  {shown.rows.map((r) => {
                    const off = r.calibrated == null ? null : r.calibrated - r.actual;
                    return (
                      <tr key={r.case_id} className="border-b border-rule last:border-0">
                        <td className="py-2.5">
                          <Link href={`/runs/${r.run_id}`} className="text-text hover:underline">
                            {r.case_id.replace(/_/g, " ")}
                          </Link>
                          {r.error && <div className="text-[12px] text-negative">{r.error}</div>}
                        </td>
                        <td className="num py-2.5 text-right">{pctSmart(r.actual)}</td>
                        <td className="num py-2.5 text-right text-muted">{pctSmart(r.stated)}</td>
                        <td className="num py-2.5 text-right">{pctSmart(r.calibrated)}</td>
                        <td className={cx("num py-2.5 text-right", off == null ? "text-faint" : Math.abs(off) > 0.15 ? "text-negative" : "text-text")}>
                          {off == null ? "–" : `${off > 0 ? "+" : off < 0 ? "−" : ""}${Math.abs(off * 100).toFixed(1)} pts`}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </Card>
        )}
      </div>
    </div>
  );
}
