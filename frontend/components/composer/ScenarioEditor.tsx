"use client";

import { useEffect, useMemo, useState } from "react";
import { Button, Chip, Field, Input, Segmented, Select, Slider, Textarea, Toggle } from "@/components/ui";
import { api } from "@/lib/api";
import { useMeta } from "@/lib/meta";
import { int, pct, people, shortJob, titleCase } from "@/lib/format";
import type { Force, LensId, RunConfig, Segment, Spec } from "@/lib/types";
import { CountryPicker } from "./CountryPicker";

type Props = {
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

/** A settings-style row: what it is on the left, the controls in a panel on the right. */
function Section({ title, children, aside, summary }: { title: string; children: React.ReactNode; aside?: React.ReactNode; summary?: React.ReactNode }) {
  return (
    <section className="grid grid-cols-1 gap-4 border-b border-border py-8 first:pt-0 last:border-0 lg:grid-cols-[minmax(0,300px)_minmax(0,1fr)] lg:gap-10">
      <div>
        <h2 className="t-section">{title}</h2>
        {aside && <p className="mt-1 text-[14px] leading-5 text-muted">{aside}</p>}
        {summary && <div className="mt-3 text-[13px] leading-[18px] text-muted">{summary}</div>}
      </div>
      <div className="flex min-w-0 flex-col gap-5 rounded-2xl bg-raised p-4 md:p-5">{children}</div>
    </section>
  );
}

/** Rough count of model calls for the cost line. */
export function estimateCalls(spec: Spec, c: RunConfig) {
  const agents = c.agents + c.influencer_voices;
  let calls = 2 + Math.ceil(agents / 8) + agents * c.runs_per_agent + 2;
  if (spec.modes.includes("committee")) calls += c.committees * (spec.committee_roles.length * c.committee_rounds + 1);
  if (spec.modes.includes("diffusion")) calls += Math.min(c.diffusion_agent_cap, c.agents) * c.diffusion_rounds;
  if (c.research) calls += 1;
  return calls;
}

export function ScenarioEditor({ spec, onSpec, config, onConfig }: Props) {
  const { meta, countryName } = useMeta();
  const set = <K extends keyof Spec>(k: K, v: Spec[K]) => onSpec({ ...spec, [k]: v });
  const [heads, setHeads] = useState<Record<string, number>>({});
  const [estimated, setEstimated] = useState<Record<string, boolean>>({});

  // How many real people each group stands for (debounced).
  useEffect(() => {
    const t = setTimeout(() => {
      api
        .headcount(spec)
        .then((r) => {
          setHeads(Object.fromEntries(r.segments.map((s) => [s.name, s.total])));
          setEstimated(Object.fromEntries(r.segments.map((s) => [s.name, !!s.estimated])));
        })
        .catch(() => {});
    }, 300);
    return () => clearTimeout(t);
  }, [spec]);

  const originOptions = useMemo(
    () => [
      { value: "global", label: "Global" },
      ...(meta?.blocs ?? []).map((b) => ({ value: b.id, label: b.name })),
      ...(meta?.countries ?? []).map((c) => ({ value: c.iso3, label: c.name })),
    ],
    [meta],
  );
  const occTitle = useMemo(() => Object.fromEntries((meta?.occupations ?? []).map((o) => [o.id, shortJob(o.title)])), [meta]);
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
  const totalHeads = Object.values(heads).reduce((a, b) => a + b, 0);
  const lens = meta?.lenses.find((l) => l.id === spec.lens);
  const setLens = (id: LensId) => {
    // Buying committees belong to the business lens only.
    const modes = new Set(spec.modes.filter((m) => m !== "committee"));
    if (id === "b2b") modes.add("committee");
    onSpec({ ...spec, lens: id, b2b: id === "b2b", modes: [...modes] });
  };
  const global = spec.scope === "global";
  const ageNum = (v: string) => (v === "" ? null : Math.max(0, Math.min(100, Math.round(Number(v)))));

  return (
    <div>
      <Section title="The question" aside="What Tellaris predicts, and what each simulated person is asked about their own behaviour.">
        {meta && (
          <Field label="Reading this as" hint={lens?.description ?? "How people are asked, and how answers turn into the headline."}>
            {() => (
              <div className="scroll-thin max-w-full overflow-x-auto">
                <div className="w-max">
                  <Segmented
                    label="Lens"
                    value={(spec.lens ?? "consumer") as LensId}
                    onChange={setLens}
                    options={meta.lenses.map((l) => ({ value: l.id, label: l.label }))}
                  />
                </div>
              </div>
            )}
          </Field>
        )}
        <Field label="Title">{(id) => <Input id={id} value={spec.title} onChange={(e) => set("title", e.target.value)} />}</Field>
        <Field label="What we're predicting">{(id) => <Input id={id} value={spec.question} onChange={(e) => set("question", e.target.value)} />}</Field>
        <Field label="Asked of each person" hint="About their own choice, never about what society will do.">
          {(id) => <Input id={id} value={spec.persona_question} onChange={(e) => set("persona_question", e.target.value)} />}
        </Field>
        <div className="grid grid-cols-1 gap-5 md:grid-cols-2">
          <Field label="Possible answers" hint="The first one is what the headline measures.">
            {() => (
              <div className="flex flex-wrap gap-1.5">
                {spec.outcomes.map((o, i) => (
                  <Chip key={i} active={i === 0}>
                    {o}
                  </Chip>
                ))}
              </div>
            )}
          </Field>
          <Field label="Time frame">{(id) => <Slider id={id} value={spec.horizon_months} min={1} max={60} onChange={(v) => set("horizon_months", v)} format={(v) => `${v} months`} />}</Field>
        </div>
      </Section>

      <Section title="What people see" aside="Describe it the way a person would first come across it. People only judge what is written here and the facts Tellaris finds.">
        <Field label="Description">{(id) => <Textarea id={id} rows={4} value={spec.subject} onChange={(e) => set("subject", e.target.value)} />}</Field>
        <div className="grid grid-cols-1 gap-5 md:grid-cols-2">
          <Field label="Price" hint="Leave empty when there is no price.">
            {(id) => (
              <div className="flex gap-2">
                <Input
                  id={id}
                  type="number"
                  min={0}
                  step="any"
                  placeholder="No price"
                  value={spec.price?.amount ?? ""}
                  onChange={(e) =>
                    set("price", e.target.value === "" ? null : { amount: Number(e.target.value), currency: spec.price?.currency ?? "USD", period: spec.price?.period ?? "month" })
                  }
                  className="w-32"
                />
                <Select
                  label="Price period"
                  value={spec.price?.period ?? "month"}
                  onChange={(v) => spec.price && set("price", { ...spec.price, period: v })}
                  options={[
                    { value: "month", label: "per month" },
                    { value: "per-seat-month", label: "per seat per month" },
                    { value: "year", label: "per year" },
                    { value: "one-time", label: "one-time" },
                    { value: "usage", label: "usage-based" },
                  ]}
                />
              </div>
            )}
          </Field>
          <Field label="Alternatives people know" hint={spec.competitors.length ? undefined : "Web research adds competitors it finds."}>
            {() => (
              <div className="flex flex-wrap gap-1.5">
                {spec.competitors.length ? spec.competitors.map((c) => <Chip key={c} onRemove={() => set("competitors", spec.competitors.filter((x) => x !== c))}>{c}</Chip>) : <span className="text-[13px] text-faint">None yet</span>}
              </div>
            )}
          </Field>
        </div>
      </Section>

      <Section
        title="Where"
        aside="Target countries. The countries and blocs that influence them are found automatically and shown on the map."
        summary={
          global
            ? `A global sample of ${spec.targets.length} countries, chosen to cover most of the world's adults.`
            : spec.targets.length
              ? `${spec.targets.length} ${spec.targets.length === 1 ? "country" : "countries"} selected.`
              : "Pick at least one country."
        }
      >
        {global && (
          <Toggle
            checked
            onChange={(v) => !v && onSpec({ ...spec, scope: "countries" })}
            label="Whole world"
            description="Results are split by country, region and demographic so you can see where it works and where it doesn't. Turn off to edit the countries freely."
          />
        )}
        <Field label="Target countries">{(id) => <CountryPicker id={id} value={spec.targets} onChange={(v) => onSpec({ ...spec, targets: v, target_weights: {} })} />}</Field>
        <Field label="How groups add up" hint={config.weighting === "population" ? "Each person counts for the real number of people they stand for. Large groups weigh more, as they do in the real world." : "Each group counts the same, whatever its real size. Useful for comparing groups."}>
          {() => (
            <Segmented
              label="How groups add up"
              value={config.weighting}
              onChange={(v) => onConfig({ ...config, weighting: v })}
              options={[
                { value: "population", label: "By real population" },
                { value: "equal", label: "Each group equally" },
              ]}
            />
          )}
        </Field>
      </Section>

      <Section
        title="Who"
        aside="Groups of people, their jobs and where they live. Tellaris sizes each group from real population data, so there's nothing to balance by hand."
        summary={totalHeads > 0 ? <>These groups stand for about <span className="num text-text">{people(totalHeads)}</span> real people.</> : undefined}
      >
        {segs.map((s, i) => (
          <div key={i} className="flex flex-col gap-3 border-b border-border pb-5 last:border-0 last:pb-0">
            <div className="flex flex-wrap items-center gap-3">
              <Input aria-label="Group name" value={s.name} onChange={(e) => setSeg(i, { name: e.target.value })} className="max-w-xs font-medium" />
              <span className="num text-[13px] text-muted">
                {heads[s.name] != null ? `${estimated[s.name] ? "About " : ""}${people(heads[s.name])} people` : ""}
                {estimated[s.name] && <span className="ml-1.5 text-faint">estimated from the trait share</span>}
              </span>
              <Button size="sm" variant="ghost" className="ml-auto" onClick={() => set("segments", segs.filter((_, j) => j !== i))} disabled={segs.length <= 1}>
                Remove
              </Button>
            </div>
            <div className="flex flex-wrap items-center gap-1.5">
              {s.occupations.map((o) => (
                <Chip key={o} onRemove={() => setSeg(i, { occupations: s.occupations.filter((x) => x !== o) })}>
                  {occTitle[o] ?? o}
                </Chip>
              ))}
              {s.custom_occupation && <Chip onRemove={() => setSeg(i, { custom_occupation: null })}>{s.custom_occupation}</Chip>}
              {!s.occupations.length && !s.custom_occupation && <span className="text-[13px] text-muted">A representative mix of all adults</span>}
              <select
                aria-label={`Add a job to ${s.name}`}
                value=""
                onChange={(e) => e.target.value && setSeg(i, { occupations: [...new Set([...s.occupations, e.target.value])] })}
                className="h-6 rounded border border-control bg-surface px-1.5 text-[13px] text-muted"
              >
                <option value="">Add a job</option>
                {(meta?.occupations ?? []).filter((o) => !s.occupations.includes(o.id)).map((o) => (
                  <option key={o.id} value={o.id}>
                    {shortJob(o.title)}
                  </option>
                ))}
              </select>
            </div>
            <div className="flex flex-wrap items-center gap-1.5 text-[13px] text-muted">
              Lives in
              {s.countries.length ? (
                s.countries.map((c) => (
                  <Chip key={c} onRemove={() => setSeg(i, { countries: s.countries.filter((x) => x !== c) })}>
                    {countryName(c)}
                  </Chip>
                ))
              ) : (
                <span className="text-text">every target country</span>
              )}
              {spec.targets.length > 1 && (
                <select
                  aria-label={`Limit ${s.name} to a country`}
                  value=""
                  onChange={(e) => e.target.value && setSeg(i, { countries: [...new Set([...s.countries, e.target.value])] })}
                  className="h-6 rounded border border-control bg-surface px-1.5 text-[13px] text-muted"
                >
                  <option value="">Only in…</option>
                  {spec.targets.filter((t) => !s.countries.includes(t)).map((t) => (
                    <option key={t} value={t}>
                      {countryName(t)}
                    </option>
                  ))}
                </select>
              )}
            </div>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-[auto_auto_minmax(0,1fr)]">
              <div className="flex items-center gap-2 text-[13px] text-muted">
                Aged
                <Input aria-label={`Youngest in ${s.name}`} type="number" min={15} max={100} placeholder="15" value={s.age_min ?? ""} onChange={(e) => setSeg(i, { age_min: ageNum(e.target.value) })} className="w-16" />
                to
                <Input aria-label={`Oldest in ${s.name}`} type="number" min={15} max={100} placeholder="any" value={s.age_max ?? ""} onChange={(e) => setSeg(i, { age_max: ageNum(e.target.value) })} className="w-16" />
              </div>
              <Select
                label={`Gender of ${s.name}`}
                value={s.gender ?? "any"}
                onChange={(v) => setSeg(i, { gender: v as Segment["gender"] })}
                options={[
                  { value: "any", label: "Any gender" },
                  { value: "woman", label: "Women" },
                  { value: "man", label: "Men" },
                ]}
              />
              <div className="flex min-w-0 items-center gap-2">
                <Input aria-label={`Trait shared by ${s.name}`} placeholder="Shared trait, e.g. owns a dog" value={s.trait ?? ""} onChange={(e) => setSeg(i, { trait: e.target.value || null })} className="min-w-0" />
                {s.trait && (
                  <div className="flex shrink-0 items-center gap-1 text-[13px] text-muted">
                    <Input
                      aria-label={`Share of people with ${s.trait}`}
                      type="number"
                      min={0.1}
                      max={100}
                      step="any"
                      value={s.trait_share != null ? +(s.trait_share * 100).toFixed(1) : ""}
                      placeholder="?"
                      onChange={(e) => setSeg(i, { trait_share: e.target.value === "" ? null : Math.max(0.001, Math.min(1, Number(e.target.value) / 100)) })}
                      className="w-16"
                    />
                    % of adults
                  </div>
                )}
              </div>
            </div>
            <Toggle checked={s.is_buyer} onChange={(v) => setSeg(i, { is_buyer: v })} label="Counts toward the answer" description={s.is_buyer ? "Their decision is what's predicted." : "Heard for context only."} />
          </div>
        ))}
        <Button size="sm" className="self-start" onClick={() => set("segments", [...segs, newSegment()])}>
          Add group
        </Button>
      </Section>

      <Section title="Outside factors" aside="Regulation, competitors or economic pressure that people will feel. They are drawn on the map and land as news during word of mouth.">
        {spec.forces.length === 0 && <p className="text-[13px] text-muted">None added. The influence map still applies.</p>}
        {spec.forces.map((f, i) => (
          <div key={i} className="flex flex-col gap-3 border-b border-border pb-5 last:border-0 last:pb-0">
            <div className="flex flex-wrap items-center gap-3">
              <Input aria-label="Factor name" value={f.name} onChange={(e) => setForce(i, { name: e.target.value })} className="max-w-sm font-medium" />
              <Button size="sm" variant="ghost" className="ml-auto" onClick={() => set("forces", spec.forces.filter((_, j) => j !== i))}>
                Remove
              </Button>
            </div>
            <Textarea aria-label="What it does" rows={2} value={f.description} onChange={(e) => setForce(i, { description: e.target.value })} />
            <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
              <Select label="Comes from" value={f.origin} onChange={(v) => setForce(i, { origin: v })} options={originOptions} />
              <Select
                label="Effect"
                value={f.direction}
                onChange={(v) => setForce(i, { direction: v as Force["direction"] })}
                options={[
                  { value: "hurts", label: "Makes a yes less likely" },
                  { value: "helps", label: "Makes a yes more likely" },
                  { value: "mixed", label: "Mixed effect" },
                ]}
              />
              <Slider label="Strength" value={f.strength} min={0} max={1} step={0.05} onChange={(v) => setForce(i, { strength: v })} format={(v) => pct(v)} />
            </div>
          </div>
        ))}
        <Button size="sm" className="self-start" onClick={() => set("forces", [...spec.forces, newForce()])}>
          Add factor
        </Button>
      </Section>

      <Section title="How to simulate" aside="More people and more answers per person narrow the range, at the cost of more model calls." summary={<>About <span className="num text-text">{int(estimateCalls(spec, config))}</span> model calls.</>}>
        <div className="grid grid-cols-1 gap-5 md:grid-cols-2">
          {spec.lens === "b2b" && (
            <Toggle checked={spec.modes.includes("committee")} onChange={(v) => toggleMode("committee", v)} label="Buying committees" description="Companies debate the purchase before deciding." />
          )}
          <Toggle checked={spec.modes.includes("diffusion")} onChange={(v) => toggleMode("diffusion", v)} label="Society" description="People post, reply to each other and change their minds over several rounds." />
          <Toggle checked={config.research} onChange={(v) => onConfig({ ...config, research: v })} label="Web research" description="Ground people in current facts, prices and competitors." />
          <Field label="Awareness" hint="Share of the audience who would realistically hear about it in the time frame.">
            {(id) => <Slider id={id} value={spec.assumed_reach} min={0.02} max={1} step={0.01} onChange={(v) => set("assumed_reach", v)} format={(v) => pct(v)} />}
          </Field>
        </div>
        <div className="grid grid-cols-1 gap-5 md:grid-cols-2">
          <Field label="People">{(id) => <Slider id={id} value={config.agents} min={20} max={3000} step={10} onChange={(v) => onConfig({ ...config, agents: v })} format={int} />}</Field>
          <Field label="Answers per person" hint="Spread across your crowd models.">
            {(id) => <Slider id={id} value={config.runs_per_agent} min={1} max={6} onChange={(v) => onConfig({ ...config, runs_per_agent: v })} />}
          </Field>
          <Field label="Voices from influencing countries" hint="Heard separately, never counted in the answer.">
            {(id) => <Slider id={id} value={config.influencer_voices} min={0} max={80} onChange={(v) => onConfig({ ...config, influencer_voices: v })} />}
          </Field>
          {spec.modes.includes("committee") && (
            <Field label="Buying committees">{(id) => <Slider id={id} value={config.committees} min={2} max={60} onChange={(v) => onConfig({ ...config, committees: v })} />}</Field>
          )}
          {spec.modes.includes("diffusion") && (
            <Field label="Rounds of conversation" hint="Each round, everyone reads their contacts and may post, reply or move.">{(id) => <Slider id={id} value={config.diffusion_rounds} min={1} max={6} onChange={(v) => onConfig({ ...config, diffusion_rounds: v })} />}</Field>
          )}
        </div>
        <p className="text-[12px] text-faint">
          Question type: {titleCase(spec.subject_kind)}. Sectors: {spec.sectors.map(titleCase).join(", ") || "general"}.
        </p>
      </Section>
    </div>
  );
}
