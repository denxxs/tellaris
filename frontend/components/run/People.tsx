"use client";

import { AnimatePresence, motion } from "motion/react";
import { useEffect, useMemo, useRef, useState } from "react";
import { Button, Chip, Input, Panel, Select, Spinner } from "@/components/ui";
import { api } from "@/lib/api";
import { companyLabel, cx, money, pctSmart, stanceMix, titleCase } from "@/lib/format";
import type { ChatMessage, Persona, PersonaSummary, Reaction } from "@/lib/types";

export function PeopleTab({ id }: { id: string }) {
  const [people, setPeople] = useState<PersonaSummary[] | null>(null);
  const [q, setQ] = useState("");
  const [country, setCountry] = useState("");
  const [segment, setSegment] = useState("");
  const [lean, setLean] = useState("");
  const [open, setOpen] = useState<string | null>(null);

  useEffect(() => {
    api.personas(id).then(setPeople).catch(() => setPeople([]));
  }, [id]);

  const countries = useMemo(() => [...new Set((people ?? []).map((p) => p.country))].sort(), [people]);
  const segments = useMemo(() => [...new Set((people ?? []).map((p) => p.segment))], [people]);
  const shown = useMemo(() => {
    const term = q.trim().toLowerCase();
    return (people ?? [])
      .filter((p) => !country || p.country === country)
      .filter((p) => !segment || p.segment === segment)
      .filter((p) => !lean || (lean === "yes" ? (p.p ?? 0) >= 0.55 : lean === "no" ? (p.p ?? 1) <= 0.3 : (p.p ?? 0) > 0.3 && (p.p ?? 0) < 0.55))
      .filter((p) => !term || `${p.name} ${p.occupation} ${p.quote}`.toLowerCase().includes(term))
      .sort((a, b) => (b.p ?? 0) - (a.p ?? 0));
  }, [people, q, country, segment, lean]);

  if (!people)
    return (
      <div className="flex items-center gap-2 text-sm text-ink-3">
        <Spinner className="size-4" /> Loading people
      </div>
    );

  return (
    <div>
      <div className="mb-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-[minmax(0,2fr)_repeat(3,minmax(0,1fr))]">
        <Input placeholder="Search names, jobs or what they said" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search people" />
        <Select value={country} onChange={setCountry} options={[{ value: "", label: "All countries" }, ...countries.map((c) => ({ value: c, label: c }))]} />
        <Select value={segment} onChange={setSegment} options={[{ value: "", label: "All groups" }, ...segments.map((s) => ({ value: s, label: s }))]} />
        <Select
          value={lean}
          onChange={setLean}
          options={[
            { value: "", label: "Any answer" },
            { value: "yes", label: "Leaning yes" },
            { value: "mid", label: "Unsure" },
            { value: "no", label: "Leaning no" },
          ]}
        />
      </div>
      <p className="mb-3 t-small text-ink-3">
        {shown.length} of {people.length} people. Pick anyone to see their full profile and talk to them.
      </p>
      <ul className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {shown.slice(0, 120).map((p) => (
          <li key={p.id}>
            <button onClick={() => setOpen(p.id)} className="flex h-full w-full flex-col rounded-2xl border border-line bg-panel p-4 text-left transition-colors hover:border-iris">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="truncate font-semibold text-ink">{p.name}</div>
                  <div className="truncate t-small text-ink-3">
                    {p.age}, {p.occupation.split("(")[0].trim()}
                  </div>
                </div>
                <span className="num shrink-0 rounded-full px-2 py-0.5 text-[13px] font-bold text-white" style={{ background: stanceMix(p.p ?? 0.4) }}>
                  {pctSmart(p.p)}
                </span>
              </div>
              {p.quote && <p className="mt-2 line-clamp-3 text-sm text-ink-2">“{p.quote}”</p>}
              <div className="mt-auto flex flex-wrap gap-1.5 pt-3">
                <Chip>{p.country_name}</Chip>
                {p.voice && <Chip tone="iris">Outside voice: {p.voice}</Chip>}
                {[...new Set(p.exposures)].slice(0, 2).map((e) => (
                  <Chip key={e} tone="iris">
                    Feels {e}
                  </Chip>
                ))}
              </div>
            </button>
          </li>
        ))}
      </ul>
      {shown.length > 120 && <p className="mt-4 t-small text-ink-3">Showing the first 120. Narrow the filters to see others.</p>}
      <AnimatePresence>{open && <PersonaDrawer runId={id} pid={open} onClose={() => setOpen(null)} />}</AnimatePresence>
    </div>
  );
}

const TRAIT_LABEL: Record<string, string> = {
  tech_affinity: "Comfort with tech",
  skepticism: "Scepticism",
  risk_appetite: "Appetite for risk",
  price_sensitivity: "Price sensitivity",
  conformity: "Follows peers",
  openness: "Openness",
  budget_authority: "Can approve spend",
};

function PersonaDrawer({ runId, pid, onClose }: { runId: string; pid: string; onClose: () => void }) {
  const [data, setData] = useState<{ persona: Persona; reactions: Reaction[]; chat: ChatMessage[] } | null>(null);
  const [msg, setMsg] = useState("");
  const [sending, setSending] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const end = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api.persona(runId, pid).then(setData).catch((e) => setErr(e.message));
    const esc = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", esc);
    return () => window.removeEventListener("keydown", esc);
  }, [runId, pid, onClose]);

  useEffect(() => {
    end.current?.scrollIntoView({ behavior: "smooth" });
  }, [data?.chat.length]);

  const send = async () => {
    const text = msg.trim();
    if (!text || !data) return;
    setSending(true);
    setErr(null);
    setData({ ...data, chat: [...data.chat, { role: "user", content: text }] });
    setMsg("");
    try {
      const r = await api.chat(runId, pid, text);
      setData((d) => (d ? { ...d, chat: r.chat } : d));
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setSending(false);
    }
  };

  const p = data?.persona;
  const r0 = data?.reactions[0];
  return (
    <>
      <motion.div className="fixed inset-0 z-40 bg-black/30" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={onClose} />
      <motion.aside
        role="dialog"
        aria-modal
        aria-label={p?.name ?? "Person"}
        className="fixed inset-y-0 right-0 z-50 flex w-full max-w-[560px] flex-col border-l border-line bg-fog shadow-2xl"
        initial={{ x: "100%" }}
        animate={{ x: 0 }}
        exit={{ x: "100%" }}
        transition={{ type: "spring", bounce: 0, duration: 0.35 }}
      >
        <div className="flex items-start justify-between gap-4 border-b border-line bg-panel px-6 py-5">
          {p ? (
            <div>
              <h2 className="t-1">{p.name}</h2>
              <p className="mt-1 text-sm text-ink-2">
                {p.age}-year-old {p.gender}, {p.occupation} ({p.seniority}) at a {companyLabel(p.company_type).toLowerCase()} in {p.country_name}
              </p>
            </div>
          ) : (
            <Spinner className="size-5" />
          )}
          <Button variant="ghost" size="sm" onClick={onClose} aria-label="Close">
            Close
          </Button>
        </div>

        <div className="scroll-thin flex-1 overflow-y-auto px-6 py-5">
          {p && (
            <div className="flex flex-col gap-6">
              {p.bio && <p className="text-[15px] leading-relaxed text-ink">{p.bio}</p>}

              {r0 && (
                <Panel className="!p-4">
                  <div className="flex items-baseline justify-between">
                    <span className="t-3">Their answer</span>
                    <span className="num t-number text-3xl" style={{ color: stanceMix(r0.p_stated) }}>
                      {pctSmart(data!.reactions.reduce((a, r) => a + r.p_stated, 0) / data!.reactions.length)}
                    </span>
                  </div>
                  <p className="mt-2 text-[15px] text-ink">“{r0.quote}”</p>
                  <div className="mt-3 grid gap-3 text-sm sm:grid-cols-2">
                    <div>
                      <div className="font-semibold text-yes">For</div>
                      <ul className="mt-1 list-disc pl-4 text-ink-2">{r0.reasons.map((x) => <li key={x}>{x}</li>)}</ul>
                    </div>
                    <div>
                      <div className="font-semibold text-no">Against</div>
                      <ul className="mt-1 list-disc pl-4 text-ink-2">{r0.objections.map((x) => <li key={x}>{x}</li>)}</ul>
                    </div>
                  </div>
                  {r0.change_mind.length > 0 && <p className="mt-3 t-small text-ink-2">Would change their mind: {r0.change_mind.join("; ")}</p>}
                  {r0.willingness_to_pay != null && <p className="mt-1 t-small text-ink-2">Would pay up to {money(r0.willingness_to_pay)}</p>}
                  {data!.reactions.length > 1 && (
                    <p className="mt-2 t-tiny text-ink-3">
                      Answered {data!.reactions.length} times: {data!.reactions.map((r) => `${pctSmart(r.p_stated)} via ${r.model}`).join(", ")}
                    </p>
                  )}
                </Panel>
              )}

              <div className="grid gap-x-6 gap-y-2 sm:grid-cols-2">
                {Object.entries(p.traits).map(([k, v]) => (
                  <div key={k}>
                    <div className="flex justify-between t-small">
                      <span className="text-ink-2">{TRAIT_LABEL[k] ?? titleCase(k)}</span>
                      <span className="num text-ink">{Math.round(v * 100)}</span>
                    </div>
                    <div className="mt-1 h-1.5 rounded-full bg-panel-2">
                      <div className="h-full rounded-full bg-ink-2" style={{ width: `${v * 100}%` }} />
                    </div>
                  </div>
                ))}
              </div>

              {p.exposures.length > 0 && (
                <div>
                  <h3 className="t-3 mb-2">Outside pressures they feel</h3>
                  <ul className="flex flex-col gap-2">
                    {p.exposures.map((e, i) => (
                      <li key={i} className="rounded-xl bg-iris-soft px-3.5 py-2.5 text-sm">
                        <span className="font-semibold text-iris-ink">
                          {e.source_name}, {e.channel.replace("_", " ")}
                        </span>
                        <p className="text-ink-2">{e.note}</p>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              <dl className="grid grid-cols-2 gap-x-6 gap-y-3 text-sm">
                <div>
                  <dt className="t-tiny text-ink-3">Income</dt>
                  <dd className="text-ink">
                    {money(p.income_usd)} a year ({p.income_band})
                  </dd>
                </div>
                <div>
                  <dt className="t-tiny text-ink-3">Company</dt>
                  <dd className="text-ink">{p.company_size > 1 ? `${p.company_size.toLocaleString()} people` : "Just them"}</dd>
                </div>
                {p.priorities.length > 0 && (
                  <div className="col-span-2">
                    <dt className="t-tiny text-ink-3">Priorities right now</dt>
                    <dd className="text-ink">{p.priorities.join("; ")}</dd>
                  </div>
                )}
                {p.frustrations.length > 0 && (
                  <div className="col-span-2">
                    <dt className="t-tiny text-ink-3">Frustrations</dt>
                    <dd className="text-ink">{p.frustrations.join("; ")}</dd>
                  </div>
                )}
                {p.info_sources.length > 0 && (
                  <div className="col-span-2">
                    <dt className="t-tiny text-ink-3">Where they get information</dt>
                    <dd className="text-ink">{p.info_sources.join(", ")}</dd>
                  </div>
                )}
              </dl>

              <div>
                <h3 className="t-3 mb-2">Talk to {p.name.split(" ")[0]}</h3>
                <div className="flex flex-col gap-2">
                  {data!.chat.map((m, i) => (
                    <div key={i} className={cx("max-w-[85%] rounded-2xl px-3.5 py-2.5 text-sm", m.role === "user" ? "self-end bg-iris text-white" : "self-start border border-line bg-panel text-ink")}>
                      {m.content}
                    </div>
                  ))}
                  {sending && (
                    <div className="self-start rounded-2xl border border-line bg-panel px-3.5 py-2.5 text-ink-3">
                      <Spinner className="size-4" />
                    </div>
                  )}
                  <div ref={end} />
                </div>
              </div>
            </div>
          )}
          {err && <p className="mt-3 text-sm text-no">{err}</p>}
        </div>

        {p && (
          <form
            className="flex gap-2 border-t border-line bg-panel px-6 py-4"
            onSubmit={(e) => {
              e.preventDefault();
              send();
            }}
          >
            <Input value={msg} onChange={(e) => setMsg(e.target.value)} placeholder={`Ask ${p.name.split(" ")[0]} anything`} aria-label="Message" />
            <Button type="submit" variant="primary" disabled={!msg.trim() || sending}>
              Send
            </Button>
          </form>
        )}
      </motion.aside>
    </>
  );
}
