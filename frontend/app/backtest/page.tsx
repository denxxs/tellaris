"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Button, ErrorNote, Meter, Panel, SectionHead, Slider, Toggle } from "@/components/ui";
import { api, type BacktestCase, type BacktestJob, type Calibration } from "@/lib/api";
import { ago, cx, pctSmart } from "@/lib/format";

export default function BacktestPage() {
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
    <div className="mx-auto max-w-[1100px] px-4 py-8 md:px-8 md:py-12">
      <h1 className="t-1">Accuracy</h1>
      <p className="mt-2 max-w-[70ch] text-[15px] text-ink-2">
        Run Oracle on questions whose real answers are known, see how far off it is, and let it learn a correction from the gap. Models may already know
        these famous outcomes, so treat scores here as optimistic. The honest test is adding your own cases that happened after your models were trained.
      </p>
      {error && <div className="mt-4"><ErrorNote>{error}</ErrorNote></div>}

      <div className="mt-8 grid gap-6 lg:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)]">
        <Panel>
          <SectionHead title="Known outcomes" />
          <ul className="flex flex-col divide-y divide-line">
            {cases.map((c) => (
              <li key={c.id} className="flex items-start gap-3 py-3">
                <input
                  type="checkbox"
                  className="mt-1 size-4 accent-[var(--iris)]"
                  checked={picked.includes(c.id)}
                  onChange={(e) => setPicked(e.target.checked ? [...picked, c.id] : picked.filter((x) => x !== c.id))}
                  aria-label={`Include ${c.id}`}
                />
                <div className="min-w-0 flex-1">
                  <p className="text-sm text-ink">{c.prompt.split(". ").slice(0, 2).join(". ")}.</p>
                  <p className="mt-0.5 t-tiny text-ink-3">{c.source}</p>
                </div>
                <div className="text-right">
                  <div className="num font-display text-lg font-bold">{pctSmart(c.actual)}</div>
                  <div className="t-tiny text-ink-3">{c.kind === "belief" ? "vote" : "adoption"}</div>
                </div>
              </li>
            ))}
          </ul>
        </Panel>
        <div className="flex flex-col gap-6">
          <Panel>
            <SectionHead title="Run a backtest" />
            <div className="flex flex-col gap-4">
              <div>
                <div className="mb-1 t-small font-semibold">People per case</div>
                <Slider value={agents} min={20} max={1000} step={10} onChange={setAgents} />
              </div>
              <div>
                <div className="mb-1 t-small font-semibold">Answers per person</div>
                <Slider value={runs} min={1} max={4} onChange={setRuns} />
              </div>
              <Toggle checked={fit} onChange={setFit} label="Learn a correction from the results" />
              <Button variant="primary" onClick={start} disabled={!picked.length || job?.status === "running"} busy={job?.status === "running"}>
                Run {picked.length} {picked.length === 1 ? "case" : "cases"}
              </Button>
              {job?.status === "running" && (
                <div>
                  <Meter value={(job.done ?? 0) / Math.max(job.total ?? 1, 1)} />
                  <p className="mt-1 t-tiny text-ink-3">
                    {job.done ?? 0} of {job.total} done{job.current ? `, now running ${job.current}` : ""}
                  </p>
                </div>
              )}
            </div>
          </Panel>
          <Panel>
            <SectionHead title="Current correction" />
            {cal &&
              Object.values(cal).map((c) => (
                <div key={c.kind} className="flex items-center justify-between border-b border-line py-2.5 last:border-0">
                  <div>
                    <div className="text-sm font-semibold text-ink">{c.kind === "action" ? "Doing things (buying, signing up)" : "Opinions and votes"}</div>
                    <div className="t-tiny text-ink-3">
                      {c.source === "backtest" ? `Learned from ${c.n_cases} cases` : "Default"}, factor {c.a}, shift {c.b}
                    </div>
                  </div>
                  {c.source === "backtest" && (
                    <Button size="sm" variant="ghost" onClick={() => api.resetCalibration(c.kind).then(refresh)}>
                      Reset
                    </Button>
                  )}
                </div>
              ))}
          </Panel>
        </div>
      </div>

      {shown && shown.rows.length > 0 && (
        <Panel className="mt-6">
          <SectionHead title="Results" aside={shown.created_at ? <span className="t-small text-ink-3">{ago(shown.created_at)}</span> : undefined} />
          {shown.summary && (
            <div className="mb-6 grid gap-4 sm:grid-cols-2">
              {Object.entries(shown.summary.by_kind).map(([k, v]) => (
                <div key={k} className="rounded-xl bg-panel-2 px-4 py-3">
                  <div className="t-3">{k === "action" ? "Doing things" : "Opinions and votes"}</div>
                  <dl className="mt-2 grid grid-cols-3 gap-3">
                    <div>
                      <dt className="t-tiny text-ink-3">Raw error</dt>
                      <dd className="num text-xl font-bold">{(v.mae_stated * 100).toFixed(1)} pts</dd>
                    </div>
                    <div>
                      <dt className="t-tiny text-ink-3">Corrected</dt>
                      <dd className="num text-xl font-bold">{(v.mae_calibrated * 100).toFixed(1)} pts</dd>
                    </div>
                    {v.mae_refit != null && (
                      <div>
                        <dt className="t-tiny text-ink-3">After learning</dt>
                        <dd className="num text-xl font-bold text-yes">{(v.mae_refit * 100).toFixed(1)} pts</dd>
                      </div>
                    )}
                  </dl>
                  <p className="mt-1 t-tiny text-ink-3">Average distance from the real result over {v.n} cases.</p>
                </div>
              ))}
            </div>
          )}
          <div className="scroll-thin overflow-x-auto">
            <table className="w-full min-w-[560px] text-sm">
              <thead>
                <tr className="text-left text-ink-3">
                  <th className="pb-2 font-semibold">Case</th>
                  <th className="pb-2 text-right font-semibold">Real</th>
                  <th className="pb-2 text-right font-semibold">Raw</th>
                  <th className="pb-2 text-right font-semibold">Corrected</th>
                  <th className="pb-2 text-right font-semibold">Off by</th>
                </tr>
              </thead>
              <tbody>
                {shown.rows.map((r) => {
                  const off = r.calibrated == null ? null : r.calibrated - r.actual;
                  return (
                    <tr key={r.case_id} className="border-t border-line">
                      <td className="py-2.5">
                        <Link href={`/runs/${r.run_id}`} className="font-semibold text-ink hover:text-iris-ink">
                          {r.case_id.replace(/_/g, " ")}
                        </Link>
                        {r.error && <div className="t-tiny text-no">{r.error}</div>}
                      </td>
                      <td className="num py-2.5 text-right">{pctSmart(r.actual)}</td>
                      <td className="num py-2.5 text-right text-ink-2">{pctSmart(r.stated)}</td>
                      <td className="num py-2.5 text-right">{pctSmart(r.calibrated)}</td>
                      <td className={cx("num py-2.5 text-right font-semibold", off == null ? "text-ink-3" : Math.abs(off) < 0.05 ? "text-yes" : Math.abs(off) > 0.15 ? "text-no" : "text-ink")}>
                        {off == null ? "–" : `${off > 0 ? "+" : ""}${(off * 100).toFixed(1)}`}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </Panel>
      )}
    </div>
  );
}
