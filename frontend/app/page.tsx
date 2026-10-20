"use client";

import { AnimatePresence, motion } from "motion/react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { CountryPicker } from "@/components/composer/CountryPicker";
import { ScenarioEditor } from "@/components/composer/ScenarioEditor";
import { Button, ErrorNote, Panel, Textarea } from "@/components/ui";
import { WorldMap } from "@/components/world/WorldMap";
import { api } from "@/lib/api";
import { cx } from "@/lib/format";
import { RunTable } from "@/components/run/RunTable";
import type { Meta, RunConfig, RunListItem, Spec, World } from "@/lib/types";

const EXAMPLES = [
  {
    label: "B2B SaaS across the US and India",
    text: "We're launching Ledgerly, an AI tool that automates month-end close for finance teams, at $49 per seat per month. Target B2B SaaS founders and CFOs in the USA, plus financial analysts at Infosys, Cognizant and TCS in India. Will they adopt it within 12 months?",
    targets: ["USA", "IND"],
  },
  {
    label: "A price change",
    text: "Our project management app costs $12 per user per month. We're thinking of raising it to $18 with an AI assistant included. How many existing small-business customers in the UK and Germany would stay versus cancel over the next 6 months?",
    targets: ["GBR", "DEU"],
  },
  {
    label: "A consumer launch",
    text: "A subscription app that plans healthy weekly meals from what's already in your fridge, $6.99 a month, launching in Brazil and Mexico. Will young working adults sign up and keep using it for 3 months?",
    targets: ["BRA", "MEX"],
  },
  {
    label: "A policy question",
    text: "If the EU banned the sale of new combustion-engine cars from 2035, would voters in Germany, France and Poland support or oppose it today? Outcomes: Support, Oppose.",
    targets: ["DEU", "FRA", "POL"],
  },
];

const SIZES = [
  { id: "quick", label: "Quick", sub: "100 people", agents: 100, runs: 1 },
  { id: "standard", label: "Standard", sub: "300 people", agents: 300, runs: 2 },
  { id: "deep", label: "Deep", sub: "1,000 people", agents: 1000, runs: 3 },
] as const;

export default function Home() {
  const router = useRouter();
  const [meta, setMeta] = useState<Meta | null>(null);
  const [prompt, setPrompt] = useState("");
  const [targets, setTargets] = useState<string[]>([]);
  const [size, setSize] = useState<(typeof SIZES)[number]["id"]>("standard");
  const [world, setWorld] = useState<World | null>(null);
  const [spec, setSpec] = useState<Spec | null>(null);
  const [config, setConfig] = useState<RunConfig | null>(null);
  const [busy, setBusy] = useState<"review" | "run" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [recent, setRecent] = useState<RunListItem[]>([]);
  const editorRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api.meta().then(setMeta).catch((e) => setError(e.message));
    api.runs().then((r) => setRecent(r.slice(0, 6))).catch(() => {});
  }, []);

  // The map answers the country picker: pick India and see who shapes it.
  const activeTargets = spec?.targets ?? targets;
  useEffect(() => {
    if (!activeTargets.length) {
      setWorld(null);
      return;
    }
    const t = setTimeout(() => api.world(activeTargets, spec ?? undefined).then(setWorld).catch(() => {}), 200);
    return () => clearTimeout(t);
  }, [activeTargets, spec]);

  const sizeCfg = SIZES.find((s) => s.id === size)!;
  const baseConfig = useMemo<RunConfig | null>(
    () => (meta ? { ...meta.defaults, agents: sizeCfg.agents, runs_per_agent: sizeCfg.runs } : null),
    [meta, sizeCfg],
  );

  const canGo = prompt.trim().length >= 10;

  async function review() {
    setError(null);
    setBusy("review");
    try {
      const r = await api.preview(prompt, targets);
      setSpec(r.spec);
      setWorld(r.world);
      setConfig(baseConfig);
      setTimeout(() => editorRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }), 50);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  }

  async function run() {
    setError(null);
    setBusy("run");
    try {
      const { id } = await api.createRun({ prompt, targets: spec ? spec.targets : targets, config: config ?? baseConfig ?? undefined, spec: spec ?? undefined });
      router.push(`/runs/${id}`);
    } catch (e) {
      setError((e as Error).message);
      setBusy(null);
    }
  }

  const influencerCount = world?.nodes.filter((n) => n.role === "influencer").length ?? 0;

  return (
    <div className="mx-auto max-w-[1320px] px-4 py-8 md:px-8 md:py-12">
      <div className="grid items-start gap-8 lg:grid-cols-[minmax(0,560px)_minmax(0,1fr)] lg:gap-12">
        <div className="flex min-w-0 flex-col gap-6">
          <h1 className="t-hero">How will the world react?</h1>
          <p className="max-w-[52ch] text-[17px] leading-relaxed text-ink-2">
            Describe a product, a price, a policy or anything you want to predict. Oracle builds a population across the countries you pick,
            lets each person decide for themselves, and tells you what&apos;s likely to happen and why.
          </p>

          <Panel pad={false} className="shadow-lift">
            <div className="p-4 md:p-5">
              <label htmlFor="prompt" className="sr-only">
                Describe what you want to predict
              </label>
              <Textarea
                id="prompt"
                rows={6}
                value={prompt}
                onChange={(e) => {
                  setPrompt(e.target.value);
                  if (spec) setSpec(null);
                }}
                onKeyDown={(e) => {
                  if ((e.metaKey || e.ctrlKey) && e.key === "Enter" && canGo) run();
                }}
                placeholder="We're launching an AI tool for finance teams at $49 per seat. Will CFOs in the US and analysts at Indian IT firms adopt it within a year?"
                className="border-0 bg-transparent px-0 text-[16px] leading-relaxed focus:ring-0"
              />
            </div>
            <div className="border-t border-line px-4 py-3 md:px-5">
              <CountryPicker meta={meta} value={spec?.targets ?? targets} onChange={(v) => (spec ? setSpec({ ...spec, targets: v, target_weights: {} }) : setTargets(v))} placeholder="Target countries (optional, we'll pick if empty)" />
            </div>
            <div className="flex flex-wrap items-center justify-between gap-3 border-t border-line px-4 py-3 md:px-5">
              <div role="radiogroup" aria-label="Simulation size" className="flex rounded-lg bg-panel-2 p-0.5">
                {SIZES.map((s) => (
                  <button
                    key={s.id}
                    role="radio"
                    aria-checked={size === s.id}
                    onClick={() => {
                      setSize(s.id);
                      if (config) setConfig({ ...config, agents: s.agents, runs_per_agent: s.runs });
                    }}
                    className={cx("rounded-md px-3 py-1.5 text-left transition-colors", size === s.id ? "bg-panel shadow-lift" : "text-ink-3 hover:text-ink")}
                  >
                    <div className="text-[13px] font-semibold leading-tight">{s.label}</div>
                    <div className="t-tiny text-ink-3">{s.sub}</div>
                  </button>
                ))}
              </div>
              <div className="flex gap-2">
                {!spec && (
                  <Button onClick={review} disabled={!canGo || !!busy} busy={busy === "review"}>
                    Review setup
                  </Button>
                )}
                <Button variant="primary" onClick={run} disabled={!canGo || !!busy} busy={busy === "run"}>
                  Run simulation
                </Button>
              </div>
            </div>
          </Panel>

          {error && <ErrorNote>{error}</ErrorNote>}

          {!spec && (
            <div>
              <h2 className="t-small mb-2 font-semibold text-ink-3">Try one of these</h2>
              <ul className="flex flex-col">
                {EXAMPLES.map((ex) => (
                  <li key={ex.label}>
                    <button
                      onClick={() => {
                        setPrompt(ex.text);
                        setTargets(ex.targets);
                        setSpec(null);
                      }}
                      className="group flex w-full min-w-0 flex-col gap-0.5 border-b border-line py-2.5 text-left sm:flex-row sm:items-baseline sm:gap-3"
                    >
                      <span className="shrink-0 whitespace-nowrap text-sm font-semibold text-ink group-hover:text-iris-ink">{ex.label}</span>
                      <span className="min-w-0 truncate text-sm text-ink-3">{ex.text}</span>
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>

        <div className="min-w-0 lg:sticky lg:top-8">
          <div className="relative overflow-hidden rounded-3xl border border-line bg-panel">
            <WorldMap world={world} targets={activeTargets} />
            <div className="flex flex-wrap items-center gap-x-5 gap-y-1 border-t border-line px-5 py-3 t-small text-ink-2">
              {activeTargets.length ? (
                <>
                  <span className="inline-flex items-center gap-2">
                    <span className="inline-block size-3 rounded-sm border border-iris bg-[var(--land-target)]" aria-hidden />
                    {activeTargets.length} target {activeTargets.length === 1 ? "country" : "countries"}
                  </span>
                  <span className="inline-flex items-center gap-2">
                    <svg width="22" height="8" aria-hidden>
                      <path d="M1 7 Q11 -2 21 7" fill="none" stroke="var(--iris)" strokeWidth="2" />
                    </svg>
                    {influencerCount} outside {influencerCount === 1 ? "influence" : "influences"}
                  </span>
                </>
              ) : (
                <span>Pick countries to see who shapes them.</span>
              )}
            </div>
          </div>
          {world && world.nodes.some((n) => n.role === "influencer") && (
            <ul className="mt-4 grid gap-x-6 gap-y-2 sm:grid-cols-2">
              {world.nodes
                .filter((n) => n.role === "influencer")
                .slice(0, 6)
                .map((n) => {
                  const link = world.links.find((l) => l.source === n.id);
                  return (
                    <li key={n.id} className="text-sm">
                      <span className="font-semibold text-ink">{n.name}</span>
                      <span className="text-ink-3"> on {link?.target} through {link?.channel.replace("_", " ")}</span>
                      {link && <p className="t-small line-clamp-2 text-ink-2">{link.note}</p>}
                    </li>
                  );
                })}
            </ul>
          )}
        </div>
      </div>

      <AnimatePresence>
        {spec && config && (
          <motion.div ref={editorRef} initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} className="mt-12 scroll-mt-6">
            <Panel>
              <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
                <div>
                  <h2 className="t-1">Check the setup</h2>
                  <p className="mt-1 max-w-2xl text-sm text-ink-2">This is how Oracle understood your question. Change anything, then run it.</p>
                </div>
                <div className="flex gap-2">
                  <Button variant="ghost" onClick={() => setSpec(null)}>
                    Discard
                  </Button>
                  <Button variant="primary" size="lg" onClick={run} busy={busy === "run"}>
                    Run simulation
                  </Button>
                </div>
              </div>
              <ScenarioEditor meta={meta} spec={spec} onSpec={setSpec} config={config} onConfig={setConfig} />
            </Panel>
          </motion.div>
        )}
      </AnimatePresence>

      {recent.length > 0 && !spec && (
        <section className="mt-14">
          <div className="mb-3 flex items-baseline justify-between">
            <h2 className="t-2">Recent runs</h2>
            <Link href="/runs" className="text-sm font-semibold text-iris-ink hover:underline">
              See all
            </Link>
          </div>
          <RunTable runs={recent} />
        </section>
      )}
    </div>
  );
}
