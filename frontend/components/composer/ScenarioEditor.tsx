"use client";

import { useMemo } from "react";
import type { Force, Meta, RunConfig, Segment, Spec } from "@/lib/types";
import { Button, Chip, Field, Input, Select, Slider, Textarea, Toggle } from "@/components/ui";
import { CountryPicker } from "./CountryPicker";
import { pct, titleCase } from "@/lib/format";

type Props = {
  meta: Meta | null;
  spec: Spec;
  onSpec: (s: Spec) => void;
  config: RunConfig;
  onConfig: (c: RunConfig) => void;
};

const newSegment = (): Segment => ({
  name: "New group", description: "", occupations: [], custom_occupation: null, company_types: [], countries: [], weight: 1, is_buyer: true,
});
const newForce = (): Force => ({
  name: "New outside factor", origin: "global", affects: [], sectors: ["all"], channel: "regulation", direction: "mixed", strength: 0.5, description: "",
});

export function ScenarioEditor({ meta, spec, onSpec, config, onConfig }: Props) {
  const set = <K extends keyof Spec>(k: K, v: Spec[K]) => onSpec({ ...spec, [k]: v });
  const occTitle = useMemo(() => Object.fromEntries((meta?.occupations ?? []).map((o) => [o.id, o.title.split(" (")[0]])), [meta]);
  const countryName = useMemo(() => Object.fromEntries((meta?.countries ?? []).map((c) => [c.iso3, c.name])), [meta]);
  const originOptions = useMemo(
    () => [
      { value: "global", label: "Global" },
      ...(meta?.blocs ?? []).map((b) => ({ value: b.id, label: b.name })),
      ...(meta?.countries ?? []).map((c) => ({ value: c.iso3, label: c.name })),
    ],
    [meta],
  );
  const segs = spec.segments;
  const setSeg = (i: number, patch: Partial<Segment>) => set("segments", segs.map((s, j) => (j === i ? { ...s, ...patch } : s)));
  const setForce = (i: number, patch: Partial<Force>) => set("forces", spec.forces.map((f, j) => (j === i ? { ...f, ...patch } : f)));
  const toggleMode = (m: string, on: boolean) => {
    const modes = new Set(spec.modes);
    if (on) modes.add(m);
    else modes.delete(m);
    modes.add("reaction");
    onSpec({ ...spec, modes: [...modes], b2b: m === "committee" ? on : spec.b2b });
  };

  return (
    <div className="flex flex-col gap-8">
      {/* The question */}
      <div className="grid gap-5 md:grid-cols-2">
        <Field label="Title">{(id) => <Input id={id} value={spec.title} onChange={(e) => set("title", e.target.value)} />}</Field>
        <Field label="Time frame" hint="How far ahead people should think">
          {(id) => (
            <Slider id={id} value={spec.horizon_months} min={1} max={60} onChange={(v) => set("horizon_months", v)} format={(v) => `${v} mo`} />
          )}
        </Field>
        <Field label="What we're predicting" className="md:col-span-2">
          {(id) => <Input id={id} value={spec.question} onChange={(e) => set("question", e.target.value)} />}
        </Field>
        <Field label="What each person is asked" hint="About their own behaviour, not society's" className="md:col-span-2">
          {(id) => <Input id={id} value={spec.persona_question} onChange={(e) => set("persona_question", e.target.value)} />}
        </Field>
        <Field label="What people see" hint="Describe it the way a real person would first hear about it" className="md:col-span-2">
          {(id) => <Textarea id={id} rows={4} value={spec.subject} onChange={(e) => set("subject", e.target.value)} />}
        </Field>
        <Field label="Outcomes" hint={spec.outcome_type === "binary" ? "The first one is what the headline number measures" : "Options people choose between"}>
          {() => (
            <div className="flex flex-wrap gap-1.5">
              {spec.outcomes.map((o, i) => (
                <Chip key={i} tone={i === 0 ? "yes" : "neutral"}>
                  {o}
                </Chip>
              ))}
            </div>
          )}
        </Field>
        <Field label="Price" hint="Leave empty if there's no price">
          {(id) => (
            <div className="flex gap-2">
              <Input
                id={id}
                type="number"
                min={0}
                step="any"
                placeholder="None"
                value={spec.price?.amount ?? ""}
                onChange={(e) =>
                  set("price", e.target.value === "" ? null : { amount: Number(e.target.value), currency: spec.price?.currency ?? "USD", period: spec.price?.period ?? "month" })
                }
              />
              <Select
                className="w-44"
                value={spec.price?.period ?? "month"}
                onChange={(v) => spec.price && set("price", { ...spec.price, period: v })}
                options={[
                  { value: "month", label: "per month" },
                  { value: "per-seat-month", label: "per seat / month" },
                  { value: "year", label: "per year" },
                  { value: "one-time", label: "one-time" },
                  { value: "usage", label: "usage-based" },
                ]}
              />
            </div>
          )}
        </Field>
      </div>

      {/* Where */}
      <div>
        <h3 className="t-3">Target countries</h3>
        <p className="mb-3 t-small text-ink-2">Countries that influence these are found automatically.</p>
        <div className="rounded-xl border border-line-strong bg-panel px-3 py-2">
          <CountryPicker meta={meta} value={spec.targets} onChange={(v) => onSpec({ ...spec, targets: v, target_weights: {} })} />
        </div>
      </div>

      {/* Who */}
      <div>
        <div className="mb-3 flex items-end justify-between gap-3">
          <div>
            <h3 className="t-3">Who gets simulated</h3>
            <p className="t-small text-ink-2">Groups of people, their jobs, and where they live.</p>
          </div>
          <Button size="sm" onClick={() => set("segments", [...segs, newSegment()])}>
            Add group
          </Button>
        </div>
        <div className="flex flex-col divide-y divide-line rounded-xl border border-line">
          {segs.map((s, i) => (
            <div key={i} className="grid gap-4 p-4 lg:grid-cols-[1.1fr_1.6fr_1fr]">
              <div className="flex flex-col gap-2">
                <Input aria-label="Group name" value={s.name} onChange={(e) => setSeg(i, { name: e.target.value })} className="font-semibold" />
                <Toggle checked={s.is_buyer} onChange={(v) => setSeg(i, { is_buyer: v })} label="Counts toward the answer" />
              </div>
              <div className="flex flex-col gap-2">
                <div className="flex flex-wrap gap-1.5">
                  {s.occupations.map((o) => (
                    <Chip key={o} onRemove={() => setSeg(i, { occupations: s.occupations.filter((x) => x !== o) })}>
                      {occTitle[o] ?? o}
                    </Chip>
                  ))}
                  {s.custom_occupation && <Chip onRemove={() => setSeg(i, { custom_occupation: null })}>{s.custom_occupation}</Chip>}
                  {!s.occupations.length && !s.custom_occupation && <span className="t-small text-ink-3">Representative mix of all jobs</span>}
                </div>
                <Select
                  value=""
                  onChange={(v) => v && setSeg(i, { occupations: [...new Set([...s.occupations, v])] })}
                  options={[{ value: "", label: "Add a job…" }, ...(meta?.occupations ?? []).filter((o) => !s.occupations.includes(o.id)).map((o) => ({ value: o.id, label: o.title }))]}
                />
                <div className="flex flex-wrap items-center gap-1.5 t-small text-ink-2">
                  Lives in
                  {s.countries.length ? (
                    s.countries.map((c) => (
                      <Chip key={c} onRemove={() => setSeg(i, { countries: s.countries.filter((x) => x !== c) })}>
                        {countryName[c] ?? c}
                      </Chip>
                    ))
                  ) : (
                    <span className="text-ink">every target country</span>
                  )}
                  <select
                    aria-label="Limit to a country"
                    value=""
                    onChange={(e) => e.target.value && setSeg(i, { countries: [...new Set([...s.countries, e.target.value])] })}
                    className="h-7 rounded-full border border-line-strong bg-panel px-2 text-[13px] text-ink-2"
                  >
                    <option value="">Limit to…</option>
                    {spec.targets.filter((t) => !s.countries.includes(t)).map((t) => (
                      <option key={t} value={t}>
                        {countryName[t] ?? t}
                      </option>
                    ))}
                  </select>
                </div>
              </div>
              <div className="flex flex-col gap-2">
                <span className="t-tiny text-ink-3">Share of agents</span>
                <Slider value={s.weight} min={0.1} max={3} step={0.1} onChange={(v) => setSeg(i, { weight: v })} format={(v) => `×${v.toFixed(1)}`} />
                <Button size="sm" variant="danger" className="self-start" onClick={() => set("segments", segs.filter((_, j) => j !== i))} disabled={segs.length <= 1}>
                  Remove group
                </Button>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Outside forces */}
      <div>
        <div className="mb-3 flex items-end justify-between gap-3">
          <div>
            <h3 className="t-3">Outside factors</h3>
            <p className="t-small text-ink-2">Regulation, competitors or economic pressure that people will feel.</p>
          </div>
          <Button size="sm" onClick={() => set("forces", [...spec.forces, newForce()])}>
            Add factor
          </Button>
        </div>
        {spec.forces.length === 0 ? (
          <p className="t-small text-ink-3">None added. The influence map still applies.</p>
        ) : (
          <div className="flex flex-col divide-y divide-line rounded-xl border border-line">
            {spec.forces.map((f, i) => (
              <div key={i} className="grid gap-3 p-4 md:grid-cols-[1.3fr_1fr_1fr]">
                <div className="flex flex-col gap-2">
                  <Input aria-label="Factor name" value={f.name} onChange={(e) => setForce(i, { name: e.target.value })} className="font-semibold" />
                  <Textarea aria-label="Factor description" rows={2} value={f.description} onChange={(e) => setForce(i, { description: e.target.value })} />
                </div>
                <div className="flex flex-col gap-2">
                  <Select value={f.origin} onChange={(v) => setForce(i, { origin: v })} options={originOptions} />
                  <Select
                    value={f.direction}
                    onChange={(v) => setForce(i, { direction: v as Force["direction"] })}
                    options={[
                      { value: "helps", label: "Helps the outcome" },
                      { value: "hurts", label: "Hurts the outcome" },
                      { value: "mixed", label: "Mixed effect" },
                    ]}
                  />
                </div>
                <div className="flex flex-col gap-2">
                  <span className="t-tiny text-ink-3">Strength</span>
                  <Slider value={f.strength} min={0} max={1} step={0.05} onChange={(v) => setForce(i, { strength: v })} format={(v) => pct(v)} />
                  <Button size="sm" variant="danger" className="self-start" onClick={() => set("forces", spec.forces.filter((_, j) => j !== i))}>
                    Remove
                  </Button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* How */}
      <div className="grid gap-6 md:grid-cols-2">
        <div className="flex flex-col gap-4">
          <h3 className="t-3">How to simulate</h3>
          <Toggle checked={spec.modes.includes("committee")} onChange={(v) => toggleMode("committee", v)} label="Buying committees (B2B deals)" />
          <Toggle checked={spec.modes.includes("diffusion")} onChange={(v) => toggleMode("diffusion", v)} label="Word of mouth between people" />
          <Toggle checked={config.research} onChange={(v) => onConfig({ ...config, research: v })} label="Search the web for current facts" />
          <Field label="Awareness" hint="Share of the audience who would realistically hear about it">
            {(id) => <Slider id={id} value={spec.assumed_reach} min={0.02} max={1} step={0.01} onChange={(v) => set("assumed_reach", v)} format={(v) => pct(v)} />}
          </Field>
        </div>
        <div className="flex flex-col gap-4">
          <h3 className="t-3">Size</h3>
          <Field label="People" hint="More people, tighter ranges, more model calls">
            {(id) => <Slider id={id} value={config.agents} min={20} max={3000} step={10} onChange={(v) => onConfig({ ...config, agents: v })} />}
          </Field>
          <Field label="Answers per person" hint="Repeated across your models to cancel out bias">
            {(id) => <Slider id={id} value={config.runs_per_agent} min={1} max={6} onChange={(v) => onConfig({ ...config, runs_per_agent: v })} />}
          </Field>
          <Field label="People from influencing countries" hint="Heard separately, not counted in the answer">
            {(id) => <Slider id={id} value={config.influencer_voices} min={0} max={80} onChange={(v) => onConfig({ ...config, influencer_voices: v })} />}
          </Field>
          {spec.modes.includes("committee") && (
            <Field label="Buying committees">{(id) => <Slider id={id} value={config.committees} min={2} max={60} onChange={(v) => onConfig({ ...config, committees: v })} />}</Field>
          )}
          {spec.modes.includes("diffusion") && (
            <Field label="Word-of-mouth rounds">
              {(id) => <Slider id={id} value={config.diffusion_rounds} min={1} max={6} onChange={(v) => onConfig({ ...config, diffusion_rounds: v })} />}
            </Field>
          )}
        </div>
      </div>

      {spec.key_uncertainties.length > 0 && (
        <div>
          <h3 className="t-3 mb-2">Open questions the simulation will test</h3>
          <ul className="list-disc space-y-1 pl-5 text-sm text-ink-2">
            {spec.key_uncertainties.map((u) => (
              <li key={u}>{u}</li>
            ))}
          </ul>
        </div>
      )}
      <p className="t-tiny text-ink-3">Question type: {titleCase(spec.subject_kind)}. Sectors: {spec.sectors.map(titleCase).join(", ") || "general"}.</p>
    </div>
  );
}
