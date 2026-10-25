"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { ClarifyPanel, initialAnswers, toClarifications, type Answers } from "@/components/composer/ClarifyPanel";
import { CountryPicker } from "@/components/composer/CountryPicker";
import { FileDrop } from "@/components/composer/FileDrop";
import { ScenarioEditor, estimateCalls } from "@/components/composer/ScenarioEditor";
import { RunTable } from "@/components/run/RunTable";
import { Button, Card, CardHead, ErrorNote, Field, Notice, PageHead, Segmented, Skeleton, Textarea, Toggle } from "@/components/ui";
import { WorldMap } from "@/components/world/WorldMap";
import { api } from "@/lib/api";
import { useMeta } from "@/lib/meta";
import { int } from "@/lib/format";
import type { Clarification, LensId, RunConfig, RunListItem, Spec, UploadedFile, World } from "@/lib/types";

const EXAMPLES = [
  {
    label: "A B2B tool in the US and India",
    text: "We're launching Ledgerly, an AI tool that automates month-end close for finance teams, at $49 per seat per month. Target B2B SaaS founders and CFOs in the USA, plus financial analysts at Infosys, Cognizant and TCS in India. Will they adopt it within 12 months?",
    targets: ["USA", "IND"],
  },
  {
    label: "A price rise",
    text: "Our project management app costs $12 per user per month. We're thinking of raising it to $18 with an AI assistant included. How many existing small-business customers in the UK and Germany would stay versus cancel over the next 6 months?",
    targets: ["GBR", "DEU"],
  },
  {
    label: "A consumer app in Latin America",
    text: "A subscription app that plans healthy weekly meals from what's already in your fridge, $6.99 a month, launching in Brazil, Mexico and Colombia. Will young working adults sign up and keep using it for 3 months?",
    targets: ["BRA", "MEX", "COL"],
  },
  {
    label: "A policy vote",
    text: "If the EU banned the sale of new combustion-engine cars from 2035, would voters in Germany, France and Poland support or oppose it today? Outcomes: Support, Oppose.",
    targets: ["DEU", "FRA", "POL"],
  },
  {
    label: "Pineapple on pizza",
    text: "Pineapple on pizza: what do people actually think of it, and does it split by country and age? Outcomes: Love it, It's fine, Never.",
    targets: ["ITA", "USA", "BRA", "JPN"],
  },
  {
    label: "Would Gen Z move abroad?",
    text: "Would Gen Z in India, Nigeria and the Philippines move abroad for a job paying 50% more, if it meant leaving family for at least 3 years?",
    targets: ["IND", "NGA", "PHL"],
  },
  {
    label: "Fintech across Africa",
    text: "A mobile app that lets small shop owners in Nigeria, Kenya and Ghana get stock on credit from wholesalers, paid back daily through mobile money, with a 2% fee per order. Will shop owners use it at least weekly within 6 months?",
    targets: ["NGA", "KEN", "GHA"],
  },
];

const SIZES = [
  { value: "quick", label: "Quick", sub: "100 people", agents: 100, runs: 1 },
  { value: "standard", label: "Standard", sub: "300 people", agents: 300, runs: 2 },
  { value: "deep", label: "Deep", sub: "1,000 people", agents: 1000, runs: 3 },
] as const;
type Size = (typeof SIZES)[number]["value"];

const FLOW = [
  { title: "Understand", text: "Your words and files become a precise question: who decides, where, at what price, over what time." },
  { title: "Research", text: "Facts from your files and the web: competitors, prices, rules, news." },
  { title: "Map influence", text: "Finds the countries and blocs pressing on your markets, like EU rules on Indian IT firms." },
  { title: "Build people", text: "Real job and income data for each country become people with names, stories and pressures." },
  { title: "Each person decides", text: "Privately, in their own words, several times across your models." },
  { title: "Companies meet", text: "For B2B, buying groups argue it out and decide to buy, pilot or pass." },
  { title: "Society talks", text: "People post, reply and change their minds as news lands." },
  { title: "Answer", text: "Corrected for say-do gaps, scaled to real headcounts, explained, with changes to test." },
];

const QUICK_PICKS = ["USA", "IND", "CHN", "GBR", "DEU", "BRA", "JPN", "NGA", "IDN", "MEX"];

export default function NewSimulation() {
  const router = useRouter();
  const { meta, countryName } = useMeta();
  const [prompt, setPrompt] = useState("");
  const [targets, setTargets] = useState<string[]>([]);
  const [size, setSize] = useState<Size>("standard");
  const [world, setWorld] = useState<World | null>(null);
  const [spec, setSpec] = useState<Spec | null>(null);
  const [config, setConfig] = useState<RunConfig | null>(null);
  const [busy, setBusy] = useState<"review" | "run" | "think" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [recent, setRecent] = useState<RunListItem[] | null>(null);
  const [files, setFiles] = useState<UploadedFile[]>([]);
  const [scope, setScope] = useState<"countries" | "global">("countries");
  const [depth, setDepth] = useState<"quick" | "deep">("quick");
  const [clar, setClar] = useState<Clarification | null>(null);
  const [answers, setAnswers] = useState<Answers>({});
  const [lens, setLens] = useState<LensId | null>(null);
  const editorRef = useRef<HTMLDivElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api.runs().then((r) => setRecent(r.slice(0, 5))).catch(() => setRecent([]));
  }, []);

  const globalTargets = useMemo(() => (meta ? meta.global[depth] : []), [meta, depth]);
  const activeTargets = useMemo(() => spec?.targets ?? (scope === "global" ? globalTargets : targets), [spec, scope, globalTargets, targets]);
  useEffect(() => {
    if (!activeTargets.length) {
      setWorld(null);
      return;
    }
    const t = setTimeout(() => api.world(activeTargets, spec ?? undefined).then(setWorld).catch(() => {}), 200);
    return () => clearTimeout(t);
  }, [activeTargets, spec]);

  const sizeCfg = SIZES.find((s) => s.value === size)!;
  const baseConfig = useMemo<RunConfig | null>(() => {
    if (!meta) return null;
    if (scope === "global") return { ...meta.defaults, agents: depth === "deep" ? 1200 : 400, runs_per_agent: 1, influencer_voices: 0 };
    return { ...meta.defaults, agents: sizeCfg.agents, runs_per_agent: sizeCfg.runs };
  }, [meta, sizeCfg, scope, depth]);
  const canGo = prompt.trim().length >= 10;
  const fileIds = files.map((f) => f.id);
  const editing = () => {
    setClar(null);
    setSpec(null);
  };

  async function review() {
    setError(null);
    setBusy("review");
    try {
      const r = await api.preview({
        prompt,
        targets: scope === "global" ? [] : targets,
        file_ids: fileIds,
        lens,
        scope,
        global_depth: depth,
        clarifications: toClarifications(clar, answers),
      });
      setClar(null);
      setSpec(r.spec);
      setWorld(r.world);
      setConfig(baseConfig);
      setTimeout(() => editorRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }), 60);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  async function launch(opts: { lens: LensId | null; withAnswers: boolean }) {
    setError(null);
    setBusy("run");
    try {
      const { id } = await api.createRun({
        prompt,
        targets: spec ? spec.targets : scope === "global" ? [] : targets,
        config: config ?? baseConfig ?? undefined,
        spec: spec ?? undefined,
        file_ids: fileIds,
        lens: opts.lens,
        scope: spec ? spec.scope : scope,
        global_depth: depth,
        clarifications: opts.withAnswers ? toClarifications(clar, answers) : [],
      });
      router.push(`/runs/${id}`);
    } catch (e) {
      setError((e as Error).message);
      setBusy(null);
    }
  }

  /** Run: let the orchestrator read it first, ask only if it needs to, otherwise go straight away. */
  async function run() {
    if (spec) return launch({ lens: spec.lens ?? null, withAnswers: false });
    if (clar) return launch({ lens, withAnswers: true });
    setError(null);
    setBusy("think");
    try {
      const c = await api.clarify(prompt, scope === "global" ? [] : targets, fileIds, scope);
      const chosen = lens ?? c.lens;
      setLens(chosen);
      if (c.scope === "global" && scope === "countries" && !targets.length) setScope("global");
      if (c.questions.length) {
        setClar(c);
        setAnswers(initialAnswers(c));
        setBusy(null);
        setTimeout(() => panelRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" }), 60);
        return;
      }
      await launch({ lens: chosen, withAnswers: false });
    } catch (e) {
      setError((e as Error).message);
      setBusy(null);
    }
  }

  const influencers = world?.nodes.filter((n) => n.role === "influencer") ?? [];

  return (
    <div className="mx-auto max-w-[1312px] px-4 py-6 md:px-6">
      <PageHead title="New simulation">
        Ask anything about people: a launch, a price, a policy, a habit, an opinion or something silly. Attach documents if you have them. Tellaris builds the people it depends on, lets each one decide, lets them talk it over, and tells you what is likely to happen and where.
      </PageHead>
      {meta?.mock && (
        <div className="mb-6">
          <Notice>
            Demo mode: simulations run on an offline stand-in model, so you can see how everything works, but the numbers aren&apos;t predictions.{" "}
            <Link href="/settings" className="font-medium underline">
              Connect a model
            </Link>{" "}
            for real results.
          </Notice>
        </div>
      )}

      <div className="grid grid-cols-1 items-start gap-6 lg:grid-cols-12">
        <div className="flex flex-col gap-6 lg:col-span-7">
          <Card>
            <Field label="What do you want to know?" hint="Who, where and when help. For a product, include the price. Tellaris asks if anything important is missing.">
              {(id) => (
                <Textarea
                  id={id}
                  rows={7}
                  value={prompt}
                  onChange={(e) => {
                    setPrompt(e.target.value);
                    if (spec || clar) editing();
                  }}
                  onKeyDown={(e) => {
                    if ((e.metaKey || e.ctrlKey) && e.key === "Enter" && canGo) run();
                  }}
                  placeholder="We're launching an AI tool for finance teams at $49 per seat. Will CFOs in the US and analysts at Indian IT firms adopt it within a year?"
                  className="text-[15px]"
                />
              )}
            </Field>
            <div className="mt-5">
              <div className="mb-2 text-[14px] font-medium">Context files</div>
              <FileDrop files={files} onChange={setFiles} />
              <p className="mt-1.5 text-[12px] text-faint">Optional. Tellaris reads them to get the product, price and audience right. People only see what a customer could see, never internal numbers.</p>
            </div>
            <div className="mt-5">
              <Toggle
                checked={scope === "global"}
                onChange={(v) => {
                  setScope(v ? "global" : "countries");
                  editing();
                }}
                label="Whole world"
                description={scope === "global" ? "Tellaris simulates the largest countries in every region and shows where it works and where it doesn't." : "Simulate across every region instead of picking countries."}
              />
              {scope === "global" ? (
                <div className="mt-3">
                  <Segmented
                    label="Global depth"
                    value={depth}
                    onChange={(v) => {
                      setDepth(v);
                      editing();
                    }}
                    options={[
                      { value: "quick", label: "Quick", sub: `${meta?.global.quick.length ?? 20} countries, 400 people` },
                      { value: "deep", label: "Deep", sub: `${meta?.global.deep.length ?? 32} countries, 1,200 people` },
                    ]}
                  />
                </div>
              ) : (
                <div className="mt-4">
                  <Field label="Target countries" hint="Optional. Leave empty and Tellaris picks the markets that matter.">
                    {(id) => <CountryPicker id={id} value={spec?.targets ?? targets} onChange={(v) => (spec ? setSpec({ ...spec, targets: v, target_weights: {} }) : setTargets(v))} />}
                  </Field>
                </div>
              )}
            </div>
            <div className="mt-5 flex flex-wrap items-end justify-between gap-4">
              <div className={scope === "global" ? "invisible" : undefined} aria-hidden={scope === "global"}>
                <div className="mb-2 text-[14px] font-medium">Size</div>
                <Segmented
                  label="Simulation size"
                  value={size}
                  onChange={(v) => {
                    setSize(v);
                    const s = SIZES.find((x) => x.value === v)!;
                    if (config) setConfig({ ...config, agents: s.agents, runs_per_agent: s.runs });
                  }}
                  options={SIZES.map((s) => ({ value: s.value, label: s.label, sub: s.sub }))}
                />
              </div>
              <div className="flex flex-wrap items-center gap-2">
                {!spec && (
                  <Button size="lg" variant="ghost" onClick={review} disabled={!canGo || !!busy} busy={busy === "review"}>
                    Adjust setup first
                  </Button>
                )}
                {!clar && (
                  <Button size="lg" variant="primary" onClick={run} disabled={!canGo || !!busy} busy={busy === "run" || busy === "think"}>
                    {busy === "think" ? "Reading your question" : "Run simulation"}
                  </Button>
                )}
              </div>
            </div>
            {error && (
              <div className="mt-4">
                <ErrorNote>{error}</ErrorNote>
              </div>
            )}
          </Card>

          {clar && (
            <div ref={panelRef} className="scroll-mt-4">
              <ClarifyPanel
                c={clar}
                lens={lens}
                onLens={setLens}
                answers={answers}
                onAnswers={setAnswers}
                onRun={() => launch({ lens, withAnswers: true })}
                onSkip={() => launch({ lens, withAnswers: false })}
                onCancel={() => setClar(null)}
                busy={busy === "run"}
              />
            </div>
          )}

          {!spec && !clar && (
            <Card>
              <CardHead title="Start from an example" />
              <ul className="flex flex-col">
                {EXAMPLES.map((ex) => (
                  <li key={ex.label} className="border-b border-rule last:border-0">
                    <button
                      onClick={() => {
                        setPrompt(ex.text);
                        setTargets(ex.targets);
                        setScope("countries");
                        setLens(null);
                        editing();
                      }}
                      className="group flex w-full flex-col gap-0.5 py-2.5 text-left"
                    >
                      <span className="flex items-baseline justify-between gap-3">
                        <span className="text-[14px] text-text group-hover:underline">{ex.label}</span>
                        <span className="hidden shrink-0 text-[12px] text-faint sm:block">{ex.targets.map(countryName).join(", ")}</span>
                      </span>
                      <span className="line-clamp-1 text-[13px] text-muted">{ex.text}</span>
                    </button>
                  </li>
                ))}
              </ul>
            </Card>
          )}
        </div>

        <div className="flex flex-col gap-6 lg:col-span-5">
        <Card pad={false}>
          <div className="px-5 pt-5">
            <CardHead title="Who shapes these markets" aside={influencers.length ? `${influencers.length} outside ${influencers.length === 1 ? "influence" : "influences"}` : undefined}>
              {scope === "global" && !spec
                ? `The ${activeTargets.length} countries a global run simulates, covering most of the world's adults.`
                : activeTargets.length
                  ? "Arrows show outside countries and blocs that affect your target countries. Thicker means stronger."
                  : "Pick a country to see who shapes it."}
            </CardHead>
          </div>
          <div className="px-2">{meta ? <WorldMap world={world} targets={activeTargets} label="Target countries and the influences on them" /> : <Skeleton className="mx-3 aspect-[2/1]" />}</div>
          <div className="px-5 pb-5 pt-2">
            {activeTargets.length === 0 ? (
              <div>
                <div className="mb-2 text-[13px] text-muted">Common markets</div>
                <div className="flex flex-wrap gap-1.5">
                  {QUICK_PICKS.map((c) => (
                    <button key={c} onClick={() => setTargets([...targets, c])} className="h-6 rounded border border-control px-2 text-[13px] text-muted hover:bg-active hover:text-text">
                      {countryName(c)}
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              <ul className="flex flex-col">
                {influencers.slice(0, 5).map((n) => {
                  const link = world!.links.find((l) => l.source === n.id);
                  return (
                    <li key={n.id} className="border-b border-rule py-2 last:border-0">
                      <div className="flex items-baseline justify-between gap-3">
                        <span className="text-[14px] text-text">{n.name}</span>
                        <span className="shrink-0 text-[12px] text-faint">
                          {link ? `${link.channel.replace("_", " ")} on ${countryName(link.target)}` : ""}
                        </span>
                      </div>
                      {link && <p className="line-clamp-2 text-[13px] leading-[18px] text-muted">{link.note}</p>}
                    </li>
                  );
                })}
                {influencers.length === 0 && <li className="py-2 text-[13px] text-muted">Looking for influences…</li>}
              </ul>
            )}
          </div>
        </Card>
        {!spec && (
          <Card>
            <CardHead title="What happens when you run it">Fully automatic. You can watch every step live.</CardHead>
            <ol className="flex flex-col">
              {FLOW.map((f, i) => (
                <li key={f.title} className="flex gap-3 border-b border-rule py-2.5 first:pt-0 last:border-0 last:pb-0">
                  <span className="num grid size-5 shrink-0 place-items-center rounded-full bg-raised text-[11px] font-medium text-muted">{i + 1}</span>
                  <span>
                    <span className="block text-[14px] text-text">{f.title}</span>
                    <span className="block text-[13px] leading-[18px] text-muted">{f.text}</span>
                  </span>
                </li>
              ))}
            </ol>
          </Card>
        )}
        </div>
      </div>

      {spec && config && (
        <div ref={editorRef} className="mt-10 scroll-mt-4">
          <div className="mb-6 flex flex-wrap items-end justify-between gap-4 border-t border-border pt-8">
            <div>
              <h2 className="t-title">Check the setup</h2>
              <p className="mt-1 max-w-2xl text-[14px] text-muted">This is how Tellaris understood your question. Change anything, then run it.</p>
            </div>
          </div>
          <ScenarioEditor spec={spec} onSpec={setSpec} config={config} onConfig={setConfig} />
          <div className="sticky bottom-0 -mx-4 mt-2 flex flex-wrap items-center justify-end gap-3 border-t border-border bg-surface px-4 py-3 md:-mx-6 md:px-6">
            <span className="mr-auto text-[13px] text-muted">
              {config.agents.toLocaleString()} people, about <span className="num">{int(estimateCalls(spec, config))}</span> model calls
            </span>
            <Button variant="ghost" onClick={() => setSpec(null)}>
              Discard changes
            </Button>
            <Button variant="primary" size="lg" onClick={run} busy={busy === "run"} disabled={!spec.targets.length}>
              Run simulation
            </Button>
          </div>
        </div>
      )}

      {!spec && (
        <Card className="mt-6">
          <CardHead
            title="Recent simulations"
            aside={
              <Link href="/runs" className="font-medium text-text hover:underline">
                View all
              </Link>
            }
          />
          {recent === null ? (
            <div className="flex flex-col gap-3">
              {[0, 1, 2].map((i) => (
                <Skeleton key={i} className="h-5 w-full" />
              ))}
            </div>
          ) : recent.length === 0 ? (
            <p className="text-[13px] text-muted">No simulations yet. Your runs are saved here.</p>
          ) : (
            <RunTable runs={recent} compact />
          )}
        </Card>
      )}
    </div>
  );
}
