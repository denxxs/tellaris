"use client";

import { useEffect, useMemo, useState } from "react";
import { Button, ErrorNote, Field, Input, PageHead, Pill, Select, Slider, Spinner } from "@/components/ui";
import { api, type Settings } from "@/lib/api";
import { cx } from "@/lib/format";

const PROVIDER_LABEL: Record<string, string> = {
  openai: "OpenAI", anthropic: "Anthropic", gemini: "Google Gemini", mistral: "Mistral", groq: "Groq", deepseek: "DeepSeek",
  openrouter: "OpenRouter", together_ai: "Together AI", xai: "xAI", azure: "Azure OpenAI", tavily: "Tavily (web search)",
};

type TestResult = { ok: boolean; latency_ms?: number; reply?: string; error?: string };

function ModelInput({ id, value, onChange, examples, onRemove }: { id: string; value: string; onChange: (v: string) => void; examples: string[]; onRemove?: () => void }) {
  const [test, setTest] = useState<TestResult | null>(null);
  const [busy, setBusy] = useState(false);
  return (
    <div>
      <div className="flex gap-2">
        <Input
          id={id}
          list={`${id}-list`}
          value={value}
          onChange={(e) => {
            onChange(e.target.value);
            setTest(null);
          }}
          placeholder="provider/model-name"
          spellCheck={false}
          className="font-mono text-[13px]"
        />
        <datalist id={`${id}-list`}>
          {examples.map((m) => (
            <option key={m} value={m} />
          ))}
        </datalist>
        <Button
          onClick={async () => {
            setBusy(true);
            setTest(await api.testModel(value).catch((e) => ({ ok: false, error: e.message })));
            setBusy(false);
          }}
          busy={busy}
          disabled={!value}
        >
          Test
        </Button>
        {onRemove && (
          <Button variant="ghost" onClick={onRemove}>
            Remove
          </Button>
        )}
      </div>
      {test && <p className={cx("mt-1.5 text-[12px]", test.ok ? "text-positive" : "text-negative")}>{test.ok ? `Connected, replied in ${test.latency_ms} ms` : test.error}</p>}
    </div>
  );
}

function Section({ title, description, summary, children }: { title: string; description: string; summary?: React.ReactNode; children: React.ReactNode }) {
  return (
    <section className="grid gap-4 border-b border-border py-8 first:pt-0 last:border-0 lg:grid-cols-[minmax(0,320px)_minmax(0,1fr)] lg:gap-10">
      <div>
        <h2 className="t-section">{title}</h2>
        <p className="mt-1 text-[14px] leading-5 text-muted">{description}</p>
        {summary && <div className="mt-3">{summary}</div>}
      </div>
      <div className="flex min-w-0 flex-col gap-5 rounded-2xl bg-raised p-4 md:p-5">{children}</div>
    </section>
  );
}

export default function ModelsPage() {
  const [s, setS] = useState<Settings | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [saving, setSaving] = useState(false);
  const [roles, setRoles] = useState<{ planner: string; crowd: string[]; analyst: string } | null>(null);
  const [keys, setKeys] = useState<Record<string, string>>({});
  const [extra, setExtra] = useState<Record<string, string>>({});
  const [search, setSearch] = useState<Settings["search_provider"]>("duckduckgo");
  const [concurrency, setConcurrency] = useState(16);
  const [timeout, setTimeoutS] = useState(90);

  useEffect(() => {
    api
      .settings()
      .then((x) => {
        setS(x);
        setRoles(x.roles);
        setExtra(x.extra);
        setSearch(x.search_provider);
        setConcurrency(x.max_concurrency);
        setTimeoutS(x.request_timeout_s);
      })
      .catch((e) => setError(e.message));
  }, []);

  const examples = useMemo(() => Object.values(s?.model_examples ?? {}).flat(), [s]);
  const dirty =
    !!s && !!roles && (JSON.stringify(roles) !== JSON.stringify(s.roles) || Object.keys(keys).length > 0 || JSON.stringify(extra) !== JSON.stringify(s.extra) || search !== s.search_provider || concurrency !== s.max_concurrency || timeout !== s.request_timeout_s);

  const save = async () => {
    if (!roles) return;
    setSaving(true);
    setError(null);
    try {
      const next = await api.saveSettings({ roles, keys, extra, search_provider: search, max_concurrency: concurrency, request_timeout_s: timeout });
      setS(next);
      setRoles(next.roles);
      setKeys({});
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  };

  if (!s || !roles)
    return (
      <div className="mx-auto max-w-[1152px] px-4 py-6 md:px-6">
        <PageHead title="Models" />
        {error ? <ErrorNote>{error}</ErrorNote> : <Spinner className="size-5 text-muted" />}
      </div>
    );

  const usingMock = [roles.planner, roles.analyst, ...roles.crowd].some((m) => m.startsWith("mock/"));
  const keysSet = Object.values(s.keys).filter((k) => k.set).length;

  return (
    <div className="mx-auto max-w-[1152px] px-4 py-6 md:px-6">
      <PageHead
        title="Models"
        actions={
          <>
            {saved && <span className="text-[13px] text-positive">Saved</span>}
            <Button variant="primary" onClick={save} busy={saving} disabled={!dirty}>
              Save changes
            </Button>
          </>
        }
      >
        Use any provider. Model names follow the LiteLLM format, like <code className="font-mono text-[13px]">openai/gpt-4o-mini</code> or <code className="font-mono text-[13px]">ollama/llama3.1</code>. Keys stay on this computer.
      </PageHead>
      {error && (
        <div className="mb-6">
          <ErrorNote>{error}</ErrorNote>
        </div>
      )}

      <Section
        title="Who does what"
        description="A strong model plans the scenario and writes the analysis. The crowd answers as people thousands of times, so use fast, cheap models there, and mix providers so no single model's bias decides the answer."
        summary={usingMock ? <Pill tone="warning">Demo model in use</Pill> : <Pill tone="positive">Real models</Pill>}
      >
        <Field label="Planner" hint="Understands your question and sets up the scenario.">
          {(id) => <ModelInput id={id} value={roles.planner} onChange={(v) => setRoles({ ...roles, planner: v })} examples={examples} />}
        </Field>
        <Field label="Analyst" hint="Researches the web, groups themes and writes the report.">
          {(id) => <ModelInput id={id} value={roles.analyst} onChange={(v) => setRoles({ ...roles, analyst: v })} examples={examples} />}
        </Field>
        <div className="flex flex-col gap-2">
          <div className="text-[14px] font-medium">Crowd</div>
          <div className="-mt-1 text-[12px] text-faint">Answers rotate across these models.</div>
          {roles.crowd.map((m, i) => (
            <ModelInput
              key={i}
              id={`crowd-${i}`}
              value={m}
              onChange={(v) => setRoles({ ...roles, crowd: roles.crowd.map((x, j) => (j === i ? v : x)) })}
              examples={examples}
              onRemove={roles.crowd.length > 1 ? () => setRoles({ ...roles, crowd: roles.crowd.filter((_, j) => j !== i) }) : undefined}
            />
          ))}
          <Button size="sm" className="self-start" onClick={() => setRoles({ ...roles, crowd: [...roles.crowd, ""] })}>
            Add a crowd model
          </Button>
        </div>
        {usingMock && <p className="text-[13px] text-muted"><span className="font-mono">mock/oracle</span> is the offline demo model. Replace it to get real predictions.</p>}
      </Section>

      <Section title="API keys" description="Paste a key to save it. Keys already in your environment are used automatically and never shown." summary={<span className="text-[13px] text-muted">{keysSet} of {s.providers.length} providers have a key.</span>}>
        <div className="grid gap-x-6 gap-y-4 md:grid-cols-2">
          {s.providers.map((p) => {
            const k = s.keys[p];
            const willClear = keys[p] === "";
            return (
              <Field
                key={p}
                label={PROVIDER_LABEL[p] ?? p}
                hint={willClear ? "Will be removed when you save." : k?.set ? (k.source === "environment" ? "Using the key from your environment." : `Saved key ending ${k.masked.replace(/•/g, "")}.`) : undefined}
              >
                {(id) => (
                  <div className="flex gap-2">
                    <Input id={id} type="password" autoComplete="off" placeholder={k?.set ? k.masked : "Not set"} value={keys[p] ?? ""} onChange={(e) => setKeys({ ...keys, [p]: e.target.value })} />
                    {k?.source === "settings" && (
                      <Button variant="ghost" onClick={() => setKeys({ ...keys, [p]: "" })}>
                        Remove
                      </Button>
                    )}
                  </div>
                )}
              </Field>
            );
          })}
        </div>
        <div className="grid gap-4 border-t border-border pt-5 md:grid-cols-3">
          {(
            [
              ["AZURE_API_BASE", "Azure endpoint", "https://your-resource.openai.azure.com"],
              ["AZURE_API_VERSION", "Azure API version", "2024-10-21"],
              ["OLLAMA_API_BASE", "Ollama address", "http://localhost:11434"],
            ] as const
          ).map(([v, label, ph]) => (
            <Field key={v} label={label}>
              {(id) => <Input id={id} value={extra[v] ?? ""} onChange={(e) => setExtra({ ...extra, [v]: e.target.value })} placeholder={ph} />}
            </Field>
          ))}
        </div>
      </Section>

      <Section title="Research and speed" description="Web research grounds each simulation in current facts. Lower the parallel calls if your provider rate-limits you.">
        <div className="grid gap-5 md:grid-cols-3">
          <Field label="Web search">
            {(id) => (
              <Select
                id={id}
                value={search}
                onChange={(v) => setSearch(v as Settings["search_provider"])}
                options={[
                  { value: "duckduckgo", label: "DuckDuckGo (free)" },
                  { value: "tavily", label: "Tavily (needs a key)" },
                  { value: "none", label: "Off" },
                ]}
              />
            )}
          </Field>
          <Field label="Parallel calls">{(id) => <Slider id={id} value={concurrency} min={1} max={128} onChange={setConcurrency} />}</Field>
          <Field label="Timeout per call">{(id) => <Slider id={id} value={timeout} min={10} max={300} step={5} onChange={setTimeoutS} format={(v) => `${v} s`} />}</Field>
        </div>
      </Section>
    </div>
  );
}
