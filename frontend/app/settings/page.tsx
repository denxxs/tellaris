"use client";

import { useEffect, useMemo, useState } from "react";
import { Button, ErrorNote, Field, Input, PageHead, Pill, Select, Slider, Spinner, Toggle } from "@/components/ui";
import { api, type Settings } from "@/lib/api";
import { cx } from "@/lib/format";
import type { ProviderInfo } from "@/lib/types";

type TestResult = { ok: boolean; latency_ms?: number; error?: string };

function split(model: string): [string, string] {
  const i = model.indexOf("/");
  return i === -1 ? ["openai", model] : [model.slice(0, i), model.slice(i + 1)];
}

function Section({ title, description, aside, children }: { title: string; description: React.ReactNode; aside?: React.ReactNode; children: React.ReactNode }) {
  return (
    <section className="grid grid-cols-1 gap-4 border-b border-border py-8 first:pt-0 last:border-0 lg:grid-cols-[minmax(0,320px)_minmax(0,1fr)] lg:gap-10">
      <div>
        <h2 className="t-section">{title}</h2>
        <div className="mt-1 text-[14px] leading-5 text-muted">{description}</div>
        {aside && <div className="mt-3">{aside}</div>}
      </div>
      <div className="flex min-w-0 flex-col gap-5 rounded-2xl bg-raised p-4 md:p-5">{children}</div>
    </section>
  );
}

/** Provider, model, key and endpoint for one role. */
function ModelPicker({
  id,
  value,
  onChange,
  catalog,
  settings,
  keys,
  setKeys,
  extra,
  setExtra,
  secrets,
  setSecrets,
  machine,
  setMachine,
}: {
  id: string;
  value: string;
  onChange: (v: string) => void;
  catalog: ProviderInfo[];
  settings: Settings;
  keys: Record<string, string>;
  setKeys: (k: Record<string, string>) => void;
  extra: Record<string, string>;
  setExtra: (e: Record<string, string>) => void;
  secrets: Record<string, string>;
  setSecrets: (s: Record<string, string>) => void;
  machine: boolean;
  setMachine: (v: boolean) => void;
}) {
  const [provider, model] = split(value);
  const info = catalog.find((c) => c.id === provider);
  const keyState = settings.keys[provider];
  const [test, setTest] = useState<TestResult | null>(null);
  const [busy, setBusy] = useState(false);
  const known = info?.models.includes(model);

  return (
    <div className="flex flex-col gap-4">
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <Field label="Provider">
          {(fid) => (
            <Select
              id={fid}
              value={info ? provider : "custom"}
              onChange={(v) => {
                setTest(null);
                if (v === "custom") return;
                const next = catalog.find((c) => c.id === v);
                onChange(`${v}/${next?.models[0] ?? ""}`);
              }}
              options={[...catalog.map((c) => ({ value: c.id, label: c.label })), ...(info ? [] : [{ value: "custom", label: `Other (${provider})` }])]}
            />
          )}
        </Field>
        <Field label="Model" hint={info && !known && model ? "Custom model name" : undefined}>
          {(fid) => (
            <>
              <Input
                id={fid}
                list={`${id}-models`}
                value={model}
                onChange={(e) => {
                  setTest(null);
                  onChange(`${provider}/${e.target.value}`);
                }}
                spellCheck={false}
                className="font-mono text-[13px]"
              />
              <datalist id={`${id}-models`}>
                {(info?.models ?? []).map((m) => (
                  <option key={m} value={m} />
                ))}
              </datalist>
            </>
          )}
        </Field>
      </div>
      {info?.note && <p className="-mt-2 text-[12px] text-faint">{info.note}</p>}
      {info?.fields && (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          {info.fields.map((f) => {
            const saved = settings.secrets?.[f.env];
            return (
              <Field
                key={f.env}
                label={f.label}
                hint={
                  f.secret && secrets[f.env] === ""
                    ? "Will be removed when you save."
                    : f.secret && saved?.set
                      ? `Saved, ending ${saved.masked.replace(/•/g, "")}. Never shown or shared.`
                      : f.hint
                }
              >
                {(fid) =>
                  f.secret ? (
                    <div className="flex gap-2">
                      <Input id={fid} type="password" autoComplete="off" placeholder={saved?.set ? saved.masked : "Paste it here"} value={secrets[f.env] ?? ""} onChange={(e) => setSecrets({ ...secrets, [f.env]: e.target.value })} />
                      {saved?.set && (
                        <Button variant="ghost" onClick={() => setSecrets({ ...secrets, [f.env]: "" })}>
                          Remove
                        </Button>
                      )}
                    </div>
                  ) : (
                    <Input id={fid} value={extra[f.env] ?? ""} onChange={(e) => setExtra({ ...extra, [f.env]: e.target.value })} placeholder={f.placeholder} />
                  )
                }
              </Field>
            );
          })}
        </div>
      )}
      {info?.machine_credentials && (
        <div className="rounded-lg border border-border bg-surface p-4">
          <Toggle
            checked={machine}
            onChange={setMachine}
            label="Allow this computer's AWS credentials"
            description="Only used when no API key or access key is saved above. Bedrock would then bill whichever AWS account this computer is signed in to (its default profile, or the profile you name below). Leave this off if that might be a client's account."
          />
          {machine && (
            <div className="mt-4 max-w-sm">
              <Field label="AWS profile" hint="Optional. Leave empty for the default profile.">
                {(fid) => <Input id={fid} value={extra.AWS_PROFILE ?? ""} onChange={(e) => setExtra({ ...extra, AWS_PROFILE: e.target.value })} placeholder="default" />}
              </Field>
            </div>
          )}
        </div>
      )}
      {info && (info.key_env || info.base_env) && (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          {info.key_env && (
            <Field
              label={`${info.label} key`}
              hint={
                keys[provider] === "" ? "Will be removed when you save." : keyState?.set ? (keyState.source === "environment" ? `Using ${info.key_env} from your environment.` : `Saved, ending ${keyState.masked.replace(/•/g, "")}.`) : info.key_url ? (
                  <>
                    Get one at{" "}
                    <a href={info.key_url} target="_blank" rel="noreferrer" className="text-text underline-offset-2 hover:underline">
                      {info.key_url.replace("https://", "")}
                    </a>
                    .
                  </>
                ) : undefined
              }
            >
              {(fid) => (
                <div className="flex gap-2">
                  <Input id={fid} type="password" autoComplete="off" placeholder={keyState?.set ? keyState.masked : "Paste your key"} value={keys[provider] ?? ""} onChange={(e) => setKeys({ ...keys, [provider]: e.target.value })} />
                  {keyState?.source === "settings" && (
                    <Button variant="ghost" onClick={() => setKeys({ ...keys, [provider]: "" })}>
                      Remove
                    </Button>
                  )}
                </div>
              )}
            </Field>
          )}
          {info.base_env && (
            <Field label="Endpoint" hint={info.base_default ? `Leave empty for ${info.base_default}` : undefined}>
              {(fid) => <Input id={fid} value={extra[info.base_env!] ?? ""} onChange={(e) => setExtra({ ...extra, [info.base_env!]: e.target.value })} placeholder={info.base_default ?? "https://"} />}
            </Field>
          )}
          {info.version_env && (
            <Field label="API version">
              {(fid) => <Input id={fid} value={extra[info.version_env!] ?? ""} onChange={(e) => setExtra({ ...extra, [info.version_env!]: e.target.value })} placeholder="2024-10-21" />}
            </Field>
          )}
        </div>
      )}
      <div className="flex flex-wrap items-center gap-3">
        <Button
          onClick={async () => {
            setBusy(true);
            setTest(await api.testModel(value).catch((e) => ({ ok: false, error: e.message })));
            setBusy(false);
          }}
          busy={busy}
          disabled={!model}
        >
          Test connection
        </Button>
        {test && <span className={cx("text-[13px]", test.ok ? "text-positive" : "text-negative")}>{test.ok ? `Connected, replied in ${test.latency_ms} ms` : test.error}</span>}
        {!test && (keys[provider] || extra[info?.base_env ?? ""] || (info?.fields ?? []).some((f) => secrets[f.env] || (!f.secret && (extra[f.env] ?? "") !== (settings.extra[f.env] ?? "")))) && (
          <span className="text-[12px] text-faint">Save first to test new credentials.</span>
        )}
      </div>
    </div>
  );
}

export default function ModelsPage() {
  const [s, setS] = useState<Settings | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [saving, setSaving] = useState(false);
  const [roles, setRoles] = useState<{ planner: string; crowd: string[]; analyst: string } | null>(null);
  const [splitAnalyst, setSplitAnalyst] = useState(false);
  const [keys, setKeys] = useState<Record<string, string>>({});
  const [secrets, setSecrets] = useState<Record<string, string>>({});
  const [machine, setMachine] = useState(false);
  const [extra, setExtra] = useState<Record<string, string>>({});
  const [search, setSearch] = useState<Settings["search_provider"]>("duckduckgo");
  const [concurrency, setConcurrency] = useState(16);
  const [timeout, setTimeoutS] = useState(90);

  const load = (x: Settings) => {
    setS(x);
    setRoles(x.roles);
    setSplitAnalyst(x.roles.analyst !== x.roles.planner);
    setExtra(x.extra);
    setMachine(x.bedrock_machine_credentials);
    setSearch(x.search_provider);
    setConcurrency(x.max_concurrency);
    setTimeoutS(x.request_timeout_s);
  };
  useEffect(() => {
    api.settings().then(load).catch((e) => setError(e.message));
  }, []);

  const catalog = useMemo(() => s?.catalog ?? [], [s]);
  const effective = roles ? { ...roles, analyst: splitAnalyst ? roles.analyst : roles.planner } : null;
  const dirty =
    !!s &&
    !!effective &&
    (JSON.stringify(effective) !== JSON.stringify(s.roles) || Object.keys(keys).length > 0 || Object.keys(secrets).length > 0 || machine !== s.bedrock_machine_credentials || JSON.stringify(extra) !== JSON.stringify(s.extra) || search !== s.search_provider || concurrency !== s.max_concurrency || timeout !== s.request_timeout_s);

  const save = async () => {
    if (!effective) return;
    setSaving(true);
    setError(null);
    try {
      const next = await api.saveSettings({
        roles: { ...effective, crowd: effective.crowd.filter(Boolean) },
        keys,
        secrets,
        bedrock_machine_credentials: machine,
        extra,
        search_provider: search,
        max_concurrency: concurrency,
        request_timeout_s: timeout,
      });
      load(next);
      setKeys({});
      setSecrets({});
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  };

  if (!s || !roles || !effective)
    return (
      <div className="mx-auto max-w-[1152px] px-4 py-6 md:px-6">
        <PageHead title="Models" />
        {error ? <ErrorNote>{error}</ErrorNote> : <Spinner className="size-5 text-muted" />}
      </div>
    );

  const pickerProps = { catalog, settings: s, keys, setKeys, extra, setExtra, secrets, setSecrets, machine, setMachine };
  /** Demo, missing a key, or ready to go, for the badge beside each role. */
  const status = (model: string) => {
    const [prov] = split(model);
    if (prov === "mock") return <Pill tone="warning">Demo model</Pill>;
    const info = catalog.find((c) => c.id === prov);
    if (prov === "bedrock") {
      const has = (k: string) => (s.secrets[k]?.set && secrets[k] !== "") || !!secrets[k];
      const keyed = has("AWS_BEARER_TOKEN_BEDROCK") || (has("AWS_ACCESS_KEY_ID") && has("AWS_SECRET_ACCESS_KEY"));
      return keyed ? <Pill tone="positive">Ready</Pill> : machine ? <Pill tone="warning">Using this computer&apos;s AWS account</Pill> : <Pill tone="negative">Needs AWS keys</Pill>;
    }
    const hasKey = !info?.key_env || s.keys[prov]?.set || !!keys[prov];
    return hasKey ? <Pill tone="positive">Ready</Pill> : <Pill tone="negative">Needs a key</Pill>;
  };
  const all = [effective.planner, effective.analyst, ...effective.crowd];
  const usingMock = all.some((m) => m.startsWith("mock/"));
  const providers = [...new Set(all.map((m) => split(m)[0]))];

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
        Choose who runs the simulation. Any provider works, including NVIDIA NIM, AWS Bedrock and models on your own machine. Keys stay on this computer.
      </PageHead>
      {error && (
        <div className="mb-6">
          <ErrorNote>{error}</ErrorNote>
        </div>
      )}

      <Section
        title="Orchestrator"
        description="Understands your question and files, builds the scenario, researches the web and writes the analysis. A few calls per simulation, so use your strongest model."
        aside={status(effective.planner)}
      >
        <ModelPicker id="planner" value={roles.planner} onChange={(v) => setRoles({ ...roles, planner: v, analyst: splitAnalyst ? roles.analyst : v })} {...pickerProps} />
        <div className="border-t border-border pt-4">
          <Toggle checked={splitAnalyst} onChange={(v) => {
            setSplitAnalyst(v);
            if (!v) setRoles({ ...roles, analyst: roles.planner });
          }} label="Use a different model for research and the report" description="By default the orchestrator does both." />
          {splitAnalyst && (
            <div className="mt-4">
              <ModelPicker id="analyst" value={roles.analyst} onChange={(v) => setRoles({ ...roles, analyst: v })} {...pickerProps} />
            </div>
          )}
        </div>
      </Section>

      <Section
        title="Crowd"
        description="Plays every simulated person: their answers, posts, replies, meetings and chats. Thousands of calls per simulation, so a fast, inexpensive model works best."
        aside={status(effective.crowd[0] ?? "mock/oracle")}
      >
        <ModelPicker id="crowd-0" value={roles.crowd[0] ?? "mock/oracle"} onChange={(v) => setRoles({ ...roles, crowd: [v, ...roles.crowd.slice(1)] })} {...pickerProps} />
        <div className="border-t border-border pt-4">
          <div className="text-[14px] font-medium">Mix in more models</div>
          <p className="mt-0.5 text-[13px] leading-[18px] text-muted">Optional. Answers rotate across every crowd model, so no single model&apos;s habits decide the result. The Method tab shows how much they agree.</p>
          {roles.crowd.slice(1).map((m, i) => (
            <div key={i} className="mt-4 rounded-lg border border-border bg-surface p-4">
              <ModelPicker id={`crowd-${i + 1}`} value={m} onChange={(v) => setRoles({ ...roles, crowd: roles.crowd.map((x, j) => (j === i + 1 ? v : x)) })} {...pickerProps} />
              <Button size="sm" variant="ghost" className="mt-3" onClick={() => setRoles({ ...roles, crowd: roles.crowd.filter((_, j) => j !== i + 1) })}>
                Remove this model
              </Button>
            </div>
          ))}
          <Button size="sm" className="mt-3" onClick={() => setRoles({ ...roles, crowd: [...roles.crowd, "nvidia_nim/meta/llama-3.1-8b-instruct"] })}>
            Add another crowd model
          </Button>
        </div>
      </Section>

      <Section title="Research and speed" description="Web research grounds each simulation in current facts. Lower the parallel calls if your provider limits your rate.">
        <div className="grid grid-cols-1 gap-5 md:grid-cols-3">
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
        {search === "tavily" && (
          <Field label="Tavily key" hint={s.keys.tavily?.set ? `Saved, ending ${s.keys.tavily.masked.replace(/•/g, "")}.` : "Get one at tavily.com."}>
            {(id) => <Input id={id} type="password" autoComplete="off" placeholder={s.keys.tavily?.set ? s.keys.tavily.masked : "Paste your key"} value={keys.tavily ?? ""} onChange={(e) => setKeys({ ...keys, tavily: e.target.value })} />}
          </Field>
        )}
      </Section>

      <Section title="Status" description="What a simulation will use right now.">
        <dl className="grid grid-cols-1 gap-3 text-[14px] sm:grid-cols-2">
          <div>
            <dt className="text-[12px] text-faint">Orchestrator</dt>
            <dd className="font-mono text-[13px]">{effective.planner}</dd>
          </div>
          <div>
            <dt className="text-[12px] text-faint">Crowd</dt>
            <dd className="font-mono text-[13px]">{effective.crowd.filter(Boolean).join(", ")}</dd>
          </div>
          <div className="sm:col-span-2">
            <dt className="text-[12px] text-faint">Keys</dt>
            <dd>
              {providers
                .filter((p) => p !== "mock" && p !== "ollama")
                .map((p) =>
                  p === "bedrock"
                    ? `AWS Bedrock: ${s.secrets.AWS_BEARER_TOKEN_BEDROCK?.set ? "API key saved" : s.secrets.AWS_ACCESS_KEY_ID?.set ? "access key saved" : s.bedrock_machine_credentials ? "this computer's AWS credentials" : "missing"}`
                    : `${catalog.find((c) => c.id === p)?.label ?? p}: ${s.keys[p]?.set || keys[p] ? "ready" : "missing"}`,
                )
                .join(", ") || "None needed"}
            </dd>
          </div>
        </dl>
        {usingMock && <p className="text-[13px] text-muted">The demo model is still in use somewhere. Results will look real but aren&apos;t predictions.</p>}
      </Section>
    </div>
  );
}
