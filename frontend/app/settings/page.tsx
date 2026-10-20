"use client";

import { useEffect, useMemo, useState } from "react";
import { Button, ErrorNote, Field, Input, Panel, SectionHead, Select, Slider, Spinner } from "@/components/ui";
import { api, type Settings } from "@/lib/api";
import { cx } from "@/lib/format";

const PROVIDER_LABEL: Record<string, string> = {
  openai: "OpenAI", anthropic: "Anthropic", gemini: "Google Gemini", mistral: "Mistral", groq: "Groq", deepseek: "DeepSeek",
  openrouter: "OpenRouter", together_ai: "Together AI", xai: "xAI", azure: "Azure OpenAI", tavily: "Tavily (web search)",
};

type TestResult = { ok: boolean; latency_ms?: number; reply?: string; error?: string };

function ModelInput({ id, value, onChange, examples }: { id: string; value: string; onChange: (v: string) => void; examples: string[] }) {
  const [test, setTest] = useState<TestResult | null>(null);
  const [busy, setBusy] = useState(false);
  return (
    <div>
      <div className="flex gap-2">
        <Input id={id} list={`${id}-list`} value={value} onChange={(e) => { onChange(e.target.value); setTest(null); }} placeholder="provider/model-name" spellCheck={false} />
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
      </div>
      {test && (
        <p className={cx("mt-1.5 t-small", test.ok ? "text-yes" : "text-no")}>
          {test.ok ? `Connected in ${test.latency_ms} ms` : test.error}
        </p>
      )}
    </div>
  );
}

export default function SettingsPage() {
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
  const [newCrowd, setNewCrowd] = useState("");

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

  const save = async () => {
    if (!roles) return;
    setSaving(true);
    setError(null);
    try {
      const keyPatch = Object.fromEntries(Object.entries(keys).filter(([, v]) => v !== undefined));
      const next = await api.saveSettings({ roles, keys: keyPatch, extra, search_provider: search, max_concurrency: concurrency, request_timeout_s: timeout });
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
      <div className="mx-auto max-w-[960px] px-4 py-12 md:px-8">
        {error ? <ErrorNote>{error}</ErrorNote> : <Spinner className="size-5 text-ink-3" />}
      </div>
    );

  const usingMock = [roles.planner, roles.analyst, ...roles.crowd].some((m) => m.startsWith("mock/"));

  return (
    <div className="mx-auto max-w-[960px] px-4 py-8 md:px-8 md:py-12">
      <div className="mb-8 flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="t-1">Models</h1>
          <p className="mt-1 max-w-2xl text-sm text-ink-2">
            Use any provider. Model names follow the <a className="font-semibold text-iris-ink hover:underline" href="https://docs.litellm.ai/docs/providers" target="_blank" rel="noreferrer">LiteLLM format</a>, like{" "}
            <code className="rounded bg-panel px-1">openai/gpt-4o-mini</code> or <code className="rounded bg-panel px-1">ollama/llama3.1</code>. Keys are stored only on this computer.
          </p>
        </div>
        <Button variant="primary" onClick={save} busy={saving}>
          {saved ? "Saved" : "Save changes"}
        </Button>
      </div>
      {error && <div className="mb-6"><ErrorNote>{error}</ErrorNote></div>}

      <div className="flex flex-col gap-6">
        <Panel>
          <SectionHead title="Who does what">
            A strong model plans and writes the analysis. The crowd answers as people, so it runs thousands of times: use cheaper, fast models there, and add several from different providers so no single model&apos;s bias decides the answer.
          </SectionHead>
          {usingMock && (
            <p className="mb-5 rounded-xl bg-panel-2 px-4 py-3 text-sm text-ink-2">
              <b className="text-ink">mock/oracle</b> is the offline demo model. Replace it with real models for real predictions.
            </p>
          )}
          <div className="grid gap-6 md:grid-cols-2">
            <Field label="Planner" hint="Understands your question and sets up the scenario">
              {(id) => <ModelInput id={id} value={roles.planner} onChange={(v) => setRoles({ ...roles, planner: v })} examples={examples} />}
            </Field>
            <Field label="Analyst" hint="Researches, groups themes and writes the report">
              {(id) => <ModelInput id={id} value={roles.analyst} onChange={(v) => setRoles({ ...roles, analyst: v })} examples={examples} />}
            </Field>
          </div>
          <div className="mt-6">
            <h3 className="t-3">Crowd</h3>
            <p className="mb-3 t-small text-ink-2">Answers rotate across these models.</p>
            <div className="flex flex-col gap-2">
              {roles.crowd.map((m, i) => (
                <div key={i} className="flex items-start gap-2">
                  <div className="flex-1">
                    <ModelInput id={`crowd-${i}`} value={m} onChange={(v) => setRoles({ ...roles, crowd: roles.crowd.map((x, j) => (j === i ? v : x)) })} examples={examples} />
                  </div>
                  <Button variant="ghost" onClick={() => setRoles({ ...roles, crowd: roles.crowd.filter((_, j) => j !== i) })} disabled={roles.crowd.length <= 1}>
                    Remove
                  </Button>
                </div>
              ))}
              <div className="flex gap-2">
                <Input list="crowd-new-list" value={newCrowd} onChange={(e) => setNewCrowd(e.target.value)} placeholder="Add a crowd model" spellCheck={false} />
                <datalist id="crowd-new-list">
                  {examples.map((m) => (
                    <option key={m} value={m} />
                  ))}
                </datalist>
                <Button
                  onClick={() => {
                    if (newCrowd.trim()) setRoles({ ...roles, crowd: [...roles.crowd, newCrowd.trim()] });
                    setNewCrowd("");
                  }}
                  disabled={!newCrowd.trim()}
                >
                  Add
                </Button>
              </div>
            </div>
          </div>
        </Panel>

        <Panel>
          <SectionHead title="API keys">Paste a key to save it. Keys already set in your environment are picked up automatically.</SectionHead>
          <div className="grid gap-x-6 gap-y-4 md:grid-cols-2">
            {s.providers.map((p) => {
              const k = s.keys[p];
              return (
                <Field
                  key={p}
                  label={PROVIDER_LABEL[p] ?? p}
                  hint={k?.set ? (k.source === "environment" ? "Using the key from your environment" : `Saved key ending ${k.masked.replace(/•/g, "")}`) : undefined}
                >
                  {(id) => (
                    <div className="flex gap-2">
                      <Input
                        id={id}
                        type="password"
                        autoComplete="off"
                        placeholder={k?.set ? k.masked : "Not set"}
                        value={keys[p] ?? ""}
                        onChange={(e) => setKeys({ ...keys, [p]: e.target.value })}
                      />
                      {k?.source === "settings" && (
                        <Button variant="ghost" onClick={() => setKeys({ ...keys, [p]: "" })} title="Remove the saved key on save">
                          Clear
                        </Button>
                      )}
                    </div>
                  )}
                </Field>
              );
            })}
          </div>
          <div className="mt-6 grid gap-4 border-t border-line pt-5 md:grid-cols-3">
            {["AZURE_API_BASE", "AZURE_API_VERSION", "OLLAMA_API_BASE"].map((v) => (
              <Field key={v} label={{ AZURE_API_BASE: "Azure endpoint", AZURE_API_VERSION: "Azure API version", OLLAMA_API_BASE: "Ollama address" }[v]!}>
                {(id) => (
                  <Input
                    id={id}
                    value={extra[v] ?? ""}
                    onChange={(e) => setExtra({ ...extra, [v]: e.target.value })}
                    placeholder={{ AZURE_API_BASE: "https://your-resource.openai.azure.com", AZURE_API_VERSION: "2024-10-21", OLLAMA_API_BASE: "http://localhost:11434" }[v]}
                  />
                )}
              </Field>
            ))}
          </div>
        </Panel>

        <Panel>
          <SectionHead title="Research and speed" />
          <div className="grid gap-6 md:grid-cols-3">
            <Field label="Web search" hint="Grounds each run in current facts">
              {(id) => (
                <Select
                  id={id}
                  value={search}
                  onChange={(v) => setSearch(v as Settings["search_provider"])}
                  options={[
                    { value: "duckduckgo", label: "DuckDuckGo (free)" },
                    { value: "tavily", label: "Tavily (needs key)" },
                    { value: "none", label: "Off" },
                  ]}
                />
              )}
            </Field>
            <Field label="Parallel calls" hint="Lower it if your provider rate-limits you">
              {(id) => <Slider id={id} value={concurrency} min={1} max={128} onChange={setConcurrency} />}
            </Field>
            <Field label="Timeout per call">{(id) => <Slider id={id} value={timeout} min={10} max={300} step={5} onChange={setTimeoutS} format={(v) => `${v}s`} />}</Field>
          </div>
        </Panel>

      </div>
    </div>
  );
}
