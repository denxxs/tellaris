"use client";

import { motion } from "motion/react";
import { useEffect, useRef, useState } from "react";
import { Button, Input, Spinner } from "@/components/ui";
import { api } from "@/lib/api";
import { useMeta } from "@/lib/meta";
import { companyLabel, cx, money, people, pctSmart, shortJob, stanceText, titleCase } from "@/lib/format";
import type { ChatMessage, Persona, Reaction } from "@/lib/types";

const TRAIT_LABEL: Record<string, string> = {
  tech_affinity: "Comfort with technology",
  skepticism: "Scepticism",
  risk_appetite: "Appetite for risk",
  price_sensitivity: "Price sensitivity",
  conformity: "Follows their peers",
  openness: "Openness to new ideas",
  budget_authority: "Can approve spending",
};

const STARTERS = ["What would make you say yes?", "What do you use today instead?", "What would you pay for it?"];

export function PersonaDrawer({ runId, pid, onClose }: { runId: string; pid: string; onClose: () => void }) {
  const { countryName } = useMeta();
  const [data, setData] = useState<{ persona: Persona; reactions: Reaction[]; chat: ChatMessage[] } | null>(null);
  const [msg, setMsg] = useState("");
  const [sending, setSending] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const end = useRef<HTMLDivElement>(null);
  const closeBtn = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    setData(null);
    api.persona(runId, pid).then(setData).catch((e) => setErr(e.message));
  }, [runId, pid]);

  useEffect(() => {
    closeBtn.current?.focus();
    const esc = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", esc);
    return () => window.removeEventListener("keydown", esc);
  }, [onClose]);

  useEffect(() => {
    end.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [data?.chat.length, sending]);

  const send = async (text: string) => {
    const t = text.trim();
    if (!t || !data) return;
    setSending(true);
    setErr(null);
    setData({ ...data, chat: [...data.chat, { role: "user", content: t }] });
    setMsg("");
    try {
      const r = await api.chat(runId, pid, t);
      setData((d) => (d ? { ...d, chat: r.chat } : d));
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setSending(false);
    }
  };

  const p = data?.persona;
  const rs = data?.reactions ?? [];
  const r0 = rs[0];
  const mean = rs.length ? rs.reduce((a, r) => a + r.p_stated, 0) / rs.length : null;
  const first = p?.name.split(" ")[0] ?? "them";

  return (
    <>
      <motion.div className="fixed inset-0 z-50 bg-black/25" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={onClose} />
      <motion.aside
        role="dialog"
        aria-modal
        aria-label={p?.name ?? "Person"}
        className="fixed inset-y-0 right-0 z-50 flex w-full max-w-[520px] flex-col bg-surface shadow-[0_0_40px_rgba(0,0,0,0.18)]"
        initial={{ x: "100%" }}
        animate={{ x: 0 }}
        exit={{ x: "100%" }}
        transition={{ type: "spring", bounce: 0, duration: 0.32 }}
      >
        <div className="flex items-start justify-between gap-4 border-b border-border px-6 py-4">
          {p ? (
            <div className="min-w-0">
              <h2 className="t-title truncate">{p.name}</h2>
              <p className="mt-0.5 text-[13px] leading-[18px] text-muted">
                {p.age}, {shortJob(p.occupation)} ({p.seniority}) at a {companyLabel(p.company_type).toLowerCase()} in {countryName(p.country)}
              </p>
            </div>
          ) : (
            <Spinner className="mt-1 size-5 text-muted" />
          )}
          <Button ref={closeBtn} variant="ghost" size="sm" onClick={onClose}>
            Close
          </Button>
        </div>

        <div className="scroll-thin flex-1 overflow-y-auto px-6 py-5">
          {p && (
            <div className="flex flex-col gap-6">
              {r0 && (
                <div>
                  <div className="flex items-baseline justify-between gap-4">
                    <span className="text-[14px] font-medium">Their answer</span>
                    <span className={cx("t-kpi", stanceText(mean))}>{pctSmart(mean)}</span>
                  </div>
                  <p className="mt-2 text-[15px] leading-[22px] text-text">“{r0.quote}”</p>
                  <div className="mt-3 grid gap-4 text-[13px] leading-[18px] sm:grid-cols-2">
                    <div>
                      <div className="font-medium text-text">For</div>
                      <ul className="mt-1 flex flex-col gap-1 text-muted">{r0.reasons.map((x, i) => <li key={i}>{x}</li>)}</ul>
                    </div>
                    <div>
                      <div className="font-medium text-text">Against</div>
                      <ul className="mt-1 flex flex-col gap-1 text-muted">{r0.objections.map((x, i) => <li key={i}>{x}</li>)}</ul>
                    </div>
                  </div>
                  <dl className="mt-3 grid grid-cols-2 gap-3 rounded-lg bg-raised p-3 text-[13px]">
                    {r0.change_mind.length > 0 && (
                      <div className="col-span-2">
                        <dt className="text-faint">Would change their mind</dt>
                        <dd className="text-text">{r0.change_mind.join("; ")}</dd>
                      </div>
                    )}
                    {r0.willingness_to_pay != null && (
                      <div>
                        <dt className="text-faint">Would pay up to</dt>
                        <dd className="num text-text">{money(r0.willingness_to_pay)}</dd>
                      </div>
                    )}
                    <div>
                      <dt className="text-faint">Attention</dt>
                      <dd className="text-text">{titleCase(r0.attention)}</dd>
                    </div>
                  </dl>
                  {rs.length > 1 && (
                    <p className="mt-2 text-[12px] text-faint">
                      Asked {rs.length} times: {rs.map((r) => `${pctSmart(r.p_stated)} via ${r.model}`).join(", ")}.
                    </p>
                  )}
                </div>
              )}

              {p.bio && <p className="text-[14px] leading-[22px] text-text">{p.bio}</p>}

              <dl className="grid grid-cols-2 gap-x-6 gap-y-3 text-[13px] leading-[18px]">
                <div>
                  <dt className="text-faint">Income</dt>
                  <dd className="num text-text">
                    {money(p.income_usd)} a year, {p.income_band}
                  </dd>
                </div>
                <div>
                  <dt className="text-faint">Stands for</dt>
                  <dd className="num text-text">{p.represents ? `${people(p.represents)} real people` : "–"}</dd>
                </div>
                {p.priorities.length > 0 && (
                  <div className="col-span-2">
                    <dt className="text-faint">Priorities right now</dt>
                    <dd className="text-text">{p.priorities.join("; ")}</dd>
                  </div>
                )}
                {p.info_sources.length > 0 && (
                  <div className="col-span-2">
                    <dt className="text-faint">Gets information from</dt>
                    <dd className="text-text">{p.info_sources.join(", ")}</dd>
                  </div>
                )}
              </dl>

              <div className="grid grid-cols-2 gap-x-6 gap-y-2.5">
                {Object.entries(p.traits).map(([k, v]) => (
                  <div key={k}>
                    <div className="flex justify-between text-[12px]">
                      <span className="text-muted">{TRAIT_LABEL[k] ?? titleCase(k)}</span>
                      <span className="num text-text">{Math.round(v * 100)}</span>
                    </div>
                    <div className="mt-1 h-1 rounded-full bg-raised">
                      <div className="h-full rounded-full bg-text/70" style={{ width: `${v * 100}%` }} />
                    </div>
                  </div>
                ))}
              </div>

              {p.exposures.length > 0 && (
                <div>
                  <h3 className="mb-2 text-[14px] font-medium">Outside pressures they feel</h3>
                  <ul className="flex flex-col gap-2">
                    {p.exposures.map((e, i) => (
                      <li key={i} className="border-l-2 border-flow pl-3 text-[13px] leading-[18px]">
                        <span className="text-text">
                          {e.source_name}, {e.channel.replace("_", " ")}
                        </span>
                        <p className="text-muted">{e.note}</p>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              <div>
                <h3 className="mb-2 text-[14px] font-medium">Talk to {first}</h3>
                {data!.chat.length === 0 && (
                  <div className="mb-3 flex flex-wrap gap-1.5">
                    {STARTERS.map((s) => (
                      <button key={s} onClick={() => send(s)} className="h-7 rounded-md border border-control px-2.5 text-[13px] text-muted hover:bg-active hover:text-text">
                        {s}
                      </button>
                    ))}
                  </div>
                )}
                <div className="flex flex-col gap-2">
                  {data!.chat.map((m, i) => (
                    <div key={i} className={cx("max-w-[88%] rounded-lg px-3 py-2 text-[14px] leading-5", m.role === "user" ? "self-end bg-primary text-primary-ink" : "self-start bg-raised text-text")}>
                      {m.content}
                    </div>
                  ))}
                  {sending && (
                    <div className="self-start rounded-lg bg-raised px-3 py-2 text-muted">
                      <Spinner className="size-4" />
                    </div>
                  )}
                  <div ref={end} />
                </div>
              </div>
            </div>
          )}
          {err && <p className="mt-3 text-[13px] text-negative">{err}</p>}
        </div>

        {p && (
          <form
            className="flex gap-2 border-t border-border px-6 py-3"
            onSubmit={(e) => {
              e.preventDefault();
              send(msg);
            }}
          >
            <Input value={msg} onChange={(e) => setMsg(e.target.value)} placeholder={`Ask ${first} anything`} aria-label="Message" />
            <Button type="submit" variant="primary" disabled={!msg.trim() || sending}>
              Send
            </Button>
          </form>
        )}
      </motion.aside>
    </>
  );
}
