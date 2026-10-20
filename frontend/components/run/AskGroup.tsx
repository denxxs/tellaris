"use client";

import { useEffect, useMemo, useState } from "react";
import { Avatar } from "@/components/people/Avatar";
import { Button, Card, CardHead, Empty, ErrorNote, Field, Input, Meter, Pill, Select, Slider, Textarea } from "@/components/ui";
import { api, type Interview, type InterviewKind, type InterviewStats } from "@/lib/api";
import { useMeta } from "@/lib/meta";
import { ago, cx, int, pctSmart, shortJob, stanceFill } from "@/lib/format";
import type { Results } from "@/lib/types";

export type GroupPreset = { keys: Record<string, string>; label: string };

const KINDS: { value: InterviewKind; label: string }[] = [
  { value: "open", label: "Open answer" },
  { value: "choice", label: "Multiple choice" },
  { value: "number", label: "A number" },
  { value: "scale", label: "0 to 10" },
];

const fmt = (v: number | undefined, unit?: string | null) =>
  v == null ? "–" : `${Math.abs(v) >= 100 ? Math.round(v).toLocaleString("en-US") : +v.toFixed(1)}${unit ? ` ${unit}` : ""}`;

function OptionBars({ stats, label }: { stats: InterviewStats; label?: string }) {
  const max = Math.max(0.01, ...(stats.options ?? []).map((o) => o.share));
  const top = Math.max(...(stats.options ?? []).map((o) => o.share));
  return (
    <div>
      {label && <div className="mb-1.5 text-[12px] text-faint">{label}</div>}
      <ul className="flex flex-col gap-1.5">
        {(stats.options ?? []).map((o) => (
          <li key={o.option} className="grid grid-cols-[minmax(0,1fr)_minmax(0,1.5fr)_44px] items-center gap-2 text-[13px]">
            <span className="truncate text-text">{o.option}</span>
            <span className="h-1.5 rounded-full bg-raised">
              <span className={cx("block h-full rounded-full", o.share === top ? "bg-yes" : "bg-text/40")} style={{ width: `${(o.share / max) * 100}%` }} />
            </span>
            <span className="num text-right text-muted">{pctSmart(o.share)}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function Spread({ stats, unit, label }: { stats: InterviewStats; unit?: string | null; label?: string }) {
  return (
    <div>
      {label && <div className="mb-1 text-[12px] text-faint">{label}</div>}
      <div className="flex items-baseline gap-2">
        <span className="t-kpi">{fmt(stats.median)}</span>
        {unit && <span className="text-[13px] text-muted">{unit}</span>}
      </div>
      <div className="text-[12px] text-muted">
        Typical answer. Most between <span className="num text-text">{fmt(stats.p10)}</span> and <span className="num text-text">{fmt(stats.p90)}</span>
      </div>
    </div>
  );
}

function ScaleBars({ stats }: { stats: InterviewStats }) {
  const counts = stats.counts ?? [];
  const max = Math.max(1, ...counts);
  return (
    <div>
      <div className="flex items-baseline gap-2">
        <span className="t-kpi">{fmt(stats.mean)}</span>
        <span className="text-[13px] text-muted">average out of 10</span>
      </div>
      <div className="mt-3 flex h-20 items-end gap-1" role="img" aria-label="How many people gave each score from 0 to 10">
        {counts.map((c, s) => (
          <div key={s} className="flex flex-1 flex-col items-center gap-1">
            <div className={cx("w-full rounded-t-sm", s >= 6 ? "bg-yes" : s <= 4 ? "bg-no" : "bg-text/40")} style={{ height: `${(c / max) * 64}px` }} title={`${c} gave ${s}`} />
            <span className="num text-[10px] text-faint">{s}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function Result({ iv, onDelete }: { iv: Interview; onDelete: () => void }) {
  const { countryName } = useMeta();
  const [showAll, setShowAll] = useState(false);
  const [theme, setTheme] = useState<string | null>(null);
  const all = iv.results?.all;
  const yes = iv.results?.leaning_yes;
  const no = iv.results?.leaning_no;
  const themeIds = new Set(iv.digest?.themes.find((t) => t.label === theme)?.answers ?? []);
  const answers = theme ? iv.answers.filter((a) => themeIds.has(a.n)) : iv.answers;
  const shown = showAll ? answers : answers.slice(0, 6);

  return (
    <Card>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h3 className="text-[16px] font-medium leading-6 text-text">{iv.question}</h3>
          <p className="text-[13px] text-muted">
            {iv.group_label}
            {iv.status !== "running" && `, ${int(iv.done)} ${iv.done === 1 ? "person" : "people"} answered`}
            {iv.pool > iv.asked && ` (picked from ${int(iv.pool)})`}. {ago(iv.created_at)}.
          </p>
        </div>
        <div className="flex items-center gap-2">
          {iv.status === "failed" && <Pill tone="negative">Failed</Pill>}
          <Button size="sm" variant="ghost" onClick={onDelete}>
            Remove
          </Button>
        </div>
      </div>

      {iv.status === "running" && (
        <div className="mt-4">
          <Meter value={iv.asked ? iv.done / iv.asked : 0} />
          <p className="mt-1 text-[12px] text-faint">
            Asking {iv.asked ? `${int(iv.asked)} people` : "people"}… {iv.done ? `${int(iv.done)} answered so far.` : ""}
          </p>
        </div>
      )}
      {iv.status === "failed" && iv.error && (
        <div className="mt-4">
          <ErrorNote>{iv.error}</ErrorNote>
        </div>
      )}

      {iv.status === "done" && (
        <div className="mt-4 flex flex-col gap-6">
          {iv.digest?.summary && <p className="max-w-[70ch] text-[15px] leading-6 text-text">{iv.digest.summary}</p>}

          {all && (
            <div className="grid grid-cols-1 gap-6 md:grid-cols-3">
              <div className="md:col-span-1">
                {iv.kind === "choice" && <OptionBars stats={all} />}
                {iv.kind === "number" && <Spread stats={all} unit={iv.unit} />}
                {iv.kind === "scale" && <ScaleBars stats={all} />}
              </div>
              {(yes || no) && (
                <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 md:col-span-2">
                  {[
                    [yes, "People who leaned yes"],
                    [no, "People who leaned no"],
                  ].map(([s, label]) =>
                    s ? (
                      <div key={label as string}>
                        {iv.kind === "choice" && <OptionBars stats={s as InterviewStats} label={`${label}, ${(s as InterviewStats).n}`} />}
                        {iv.kind === "number" && <Spread stats={s as InterviewStats} unit={iv.unit} label={`${label}, ${(s as InterviewStats).n}`} />}
                        {iv.kind === "scale" && <Spread stats={{ ...(s as InterviewStats), median: (s as InterviewStats).mean }} label={`${label}, ${(s as InterviewStats).n}, average`} />}
                      </div>
                    ) : null,
                  )}
                </div>
              )}
            </div>
          )}

          {iv.digest && iv.digest.themes.length > 0 && (
            <div>
              <h4 className="mb-2 text-[13px] font-medium">Themes</h4>
              <div className="flex flex-wrap gap-1.5">
                {iv.digest.themes.map((t) => (
                  <button
                    key={t.label}
                    type="button"
                    aria-pressed={theme === t.label}
                    onClick={() => setTheme(theme === t.label ? null : t.label)}
                    className={cx(
                      "inline-flex min-h-8 items-center gap-1.5 rounded-md border px-3 text-[13px] transition-colors",
                      theme === t.label ? "border-text bg-text text-surface" : "border-control bg-surface text-text hover:bg-raised",
                    )}
                  >
                    {t.label}
                    <span className={cx("num", theme === t.label ? "text-surface/70" : "text-faint")}>{pctSmart(t.share)}</span>
                  </button>
                ))}
              </div>
            </div>
          )}

          <div>
            <h4 className="mb-2 text-[13px] font-medium">{theme ? `Answers about “${theme}”` : "What they said"}</h4>
            <ul className="flex flex-col">
              {shown.map((a) => (
                <li key={a.persona_id} className="flex items-start gap-3 border-b border-rule py-3 first:pt-0 last:border-0">
                  <a href={`/runs/${iv.run_id}/people/${a.persona_id}`} aria-label={`Open ${a.name}'s profile`}>
                    <Avatar seed={a.persona_id} size={32} ring={stanceFill(a.leaning)} />
                  </a>
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-baseline justify-between gap-x-3">
                      <a href={`/runs/${iv.run_id}/people/${a.persona_id}`} className="text-[14px] font-medium hover:underline">
                        {a.name}
                      </a>
                      <span className="num text-[13px] text-muted">
                        {a.choice ?? (a.number != null ? fmt(a.number, iv.unit) : a.scale != null ? `${a.scale}/10` : "")}
                      </span>
                    </div>
                    <div className="text-[12px] text-faint">
                      {shortJob(a.occupation)}, {a.age}, {countryName(a.country)}
                    </div>
                    <p className="mt-1 text-[14px] leading-5 text-text">{a.answer}</p>
                  </div>
                </li>
              ))}
            </ul>
            {answers.length > 6 && (
              <Button size="sm" variant="ghost" className="mt-2" onClick={() => setShowAll(!showAll)}>
                {showAll ? "Show fewer" : `Show all ${answers.length}`}
              </Button>
            )}
          </div>
        </div>
      )}
    </Card>
  );
}

/** Ask a follow-up question to everyone, or to any group, and get a mini survey back. */
export function AskGroup({ id, r, preset }: { id: string; r: Results; preset?: GroupPreset | null }) {
  const sp = r.splits;
  const dims = useMemo(() => Object.entries(sp?.dimensions ?? {}), [sp]);
  const suggested = useMemo(() => [...(sp?.hot ?? []).slice(0, 3), ...(sp?.cold ?? []).slice(0, 3)].filter((c) => c.keys), [sp]);

  const [group, setGroup] = useState<GroupPreset>(preset ?? { keys: {}, label: "Everyone" });
  const [dim, setDim] = useState<string>("");
  const [question, setQuestion] = useState("");
  const [kind, setKind] = useState<InterviewKind>("open");
  const [options, setOptions] = useState("");
  const [unit, setUnit] = useState("");
  const [limit, setLimit] = useState(40);
  const [list, setList] = useState<Interview[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (preset) setGroup(preset);
  }, [preset]);

  useEffect(() => {
    api.interviews(id).then(setList).catch(() => setList([]));
  }, [id]);

  const running = (list ?? []).filter((x) => x.status === "running").map((x) => x.id).join(",");
  useEffect(() => {
    if (!running) return;
    const t = setInterval(async () => {
      const fresh = await Promise.all(running.split(",").map((iid) => api.interview(iid).catch(() => null)));
      setList((cur) => (cur ?? []).map((x) => fresh.find((f) => f?.id === x.id) ?? x));
    }, 1000);
    return () => clearInterval(t);
  }, [running]);

  const opts = options.split(/\n|,/).map((o) => o.trim()).filter(Boolean);
  const ready = question.trim().length >= 3 && (kind !== "choice" || opts.length >= 2);

  const ask = async () => {
    setBusy(true);
    setError(null);
    try {
      const iv = await api.askGroup(id, { question, kind, options: kind === "choice" ? opts : [], unit: kind === "number" ? unit || null : null, group: group.keys, limit });
      setList([iv, ...(list ?? [])]);
      setQuestion("");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const dimRows = dim ? sp?.dimensions[dim]?.rows ?? [] : [];

  return (
    <div className="grid grid-cols-1 items-start gap-6 lg:grid-cols-12">
      <Card className="lg:col-span-4">
        <CardHead title="Ask a group">Put a follow-up question to the people in this simulation. Each answers in character, from what they decided and remember.</CardHead>
        <div className="flex flex-col gap-5">
          <div>
            <div className="mb-2 text-[14px] font-medium">Who to ask</div>
            <div className="flex flex-wrap items-center gap-2">
              <Pill tone="yes">{group.label}</Pill>
              {Object.keys(group.keys).length > 0 && (
                <Button size="sm" variant="ghost" onClick={() => setGroup({ keys: {}, label: "Everyone" })}>
                  Ask everyone instead
                </Button>
              )}
            </div>
            {dims.length > 0 && (
              <div className="mt-3 grid grid-cols-2 gap-2">
                <Select
                  label="Pick a group by"
                  value={dim}
                  onChange={setDim}
                  options={[{ value: "", label: "Pick a group by…" }, ...dims.map(([k, d]) => ({ value: k, label: d.label }))]}
                />
                <Select
                  label="Group"
                  value=""
                  onChange={(v) => {
                    const row = dimRows.find((x) => x.key === v);
                    if (row) setGroup({ keys: { [dim]: row.key }, label: row.label });
                  }}
                  options={[{ value: "", label: dim ? "Choose…" : "–" }, ...dimRows.map((x) => ({ value: x.key, label: `${x.label} (${x.n})` }))]}
                />
              </div>
            )}
            {suggested.length > 0 && (
              <div className="mt-3">
                <div className="mb-1.5 text-[12px] text-faint">Where it works and where it struggles</div>
                <div className="flex flex-wrap gap-1.5">
                  {suggested.map((c) => (
                    <button
                      key={c.label}
                      type="button"
                      onClick={() => setGroup({ keys: c.keys!, label: c.label })}
                      className="inline-flex min-h-7 items-center rounded-md border border-control bg-surface px-2.5 text-[13px] text-text hover:bg-raised"
                    >
                      {c.label}
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>

          <Field label="Your question">
            {(fid) => <Textarea id={fid} rows={3} value={question} placeholder="e.g. What would make you try it this month?" onChange={(e) => setQuestion(e.target.value)} />}
          </Field>

          <div>
            <div className="mb-2 text-[14px] font-medium">Answer type</div>
            <div className="grid grid-cols-2 gap-1.5" role="radiogroup" aria-label="Answer type">
              {KINDS.map((k) => (
                <button
                  key={k.value}
                  type="button"
                  role="radio"
                  aria-checked={kind === k.value}
                  onClick={() => setKind(k.value)}
                  className={cx(
                    "min-h-9 rounded-md border px-3 text-left text-[14px] transition-colors",
                    kind === k.value ? "border-text bg-text text-surface" : "border-control bg-surface text-text hover:bg-raised",
                  )}
                >
                  {k.label}
                </button>
              ))}
            </div>
          </div>
          {kind === "choice" && (
            <Field label="Options" hint="One per line or separated by commas, up to 8.">
              {(fid) => <Textarea id={fid} rows={3} value={options} placeholder={"Penny\nLedgr\nKosh"} onChange={(e) => setOptions(e.target.value)} />}
            </Field>
          )}
          {kind === "number" && (
            <Field label="Unit" hint="Optional, e.g. USD a month, hours, km.">
              {(fid) => <Input id={fid} value={unit} onChange={(e) => setUnit(e.target.value)} />}
            </Field>
          )}
          <Field label="People to ask" hint={`About ${int(limit + 1)} model calls. Picked at random from the group; the numbers weight each answer by the real people it stands for.`}>
            {(fid) => <Slider id={fid} value={limit} min={5} max={200} step={5} onChange={setLimit} />}
          </Field>
          {error && <ErrorNote>{error}</ErrorNote>}
          <Button variant="primary" onClick={ask} disabled={!ready || busy} busy={busy}>
            Ask {group.label === "Everyone" ? "everyone" : "this group"}
          </Button>
        </div>
      </Card>

      <div className="flex flex-col gap-6 lg:col-span-8">
        {list === null ? null : list.length === 0 ? (
          <Card>
            <Empty title="No questions asked yet">
              Ask anything the simulation didn&apos;t cover: a price, a name, a feature, what would change their mind. Answers come back as a small survey with quotes.
            </Empty>
          </Card>
        ) : (
          list.map((iv) => (
            <Result
              key={iv.id}
              iv={iv}
              onDelete={async () => {
                await api.deleteInterview(iv.id).catch(() => {});
                setList((cur) => (cur ?? []).filter((x) => x.id !== iv.id));
              }}
            />
          ))
        )}
      </div>
    </div>
  );
}
