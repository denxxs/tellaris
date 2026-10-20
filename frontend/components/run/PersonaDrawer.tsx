"use client";

import { motion } from "motion/react";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { PersonaChat } from "@/components/people/Chat";
import { Avatar } from "@/components/people/Avatar";
import { Button, LinkButton, Spinner } from "@/components/ui";
import { api } from "@/lib/api";
import { useMeta } from "@/lib/meta";
import { companyLabel, cx, pctSmart, shortJob, stanceFill, stanceText } from "@/lib/format";
import type { Profile } from "@/lib/types";

/** A quick look at one person, with a way into their full profile. */
export function PersonaDrawer({ runId, pid, onClose }: { runId: string; pid: string; onClose: () => void }) {
  const { countryName } = useMeta();
  const [data, setData] = useState<Profile | null>(null);
  const [err, setErr] = useState<string | null>(null);
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

  const p = data?.persona;
  const rs = data?.reactions ?? [];
  const r0 = rs[0];
  const mean = rs.length ? rs.reduce((a, r) => a + r.p_stated, 0) / rs.length : null;
  const said = data?.society.mine.filter((m) => m.kind === "post" || m.kind === "reply") ?? [];

  return (
    <>
      <motion.div className="fixed inset-0 z-50 bg-black/25" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={onClose} />
      <motion.aside
        role="dialog"
        aria-modal
        aria-label={p?.name ?? "Person"}
        className="fixed inset-y-0 right-0 z-50 flex w-full max-w-[500px] flex-col bg-surface shadow-[0_0_40px_rgba(0,0,0,0.18)]"
        initial={{ x: "100%" }}
        animate={{ x: 0 }}
        exit={{ x: "100%" }}
        transition={{ type: "spring", bounce: 0, duration: 0.32 }}
      >
        <div className="flex items-start gap-3 border-b border-border px-6 py-4">
          {p ? (
            <>
              <Avatar seed={p.id} size={52} ring={mean != null ? stanceFill(mean) : undefined} />
              <div className="min-w-0 flex-1">
                <h2 className="t-title truncate">{p.name}</h2>
                <p className="truncate text-[13px] text-muted">{p.tagline || `${shortJob(p.occupation)}, ${countryName(p.country)}`}</p>
              </div>
            </>
          ) : (
            <Spinner className="mt-1 size-5 text-muted" />
          )}
          <Button ref={closeBtn} variant="ghost" size="sm" onClick={onClose} className="ml-auto">
            Close
          </Button>
        </div>

        <div className="scroll-thin flex-1 overflow-y-auto px-6 py-5">
          {err && <p className="text-[13px] text-negative">{err}</p>}
          {p && (
            <div className="flex flex-col gap-5">
              <p className="text-[13px] leading-[18px] text-muted">
                {p.age}, {shortJob(p.occupation)} ({p.seniority}) at a {companyLabel(p.company_type).toLowerCase()} in {countryName(p.country)}.
              </p>
              {r0 && (
                <div>
                  <div className="flex items-baseline justify-between gap-4">
                    <span className="text-[14px] font-medium">Their answer</span>
                    <span className={cx("t-kpi", stanceText(mean))}>{pctSmart(mean)}</span>
                  </div>
                  <p className="mt-1.5 text-[15px] leading-[22px]">“{r0.quote}”</p>
                  {data!.society.final_p != null && mean != null && Math.abs(data!.society.final_p - mean) > 0.05 && (
                    <p className="mt-1.5 text-[13px] text-muted">
                      After talking with others: <span className={cx("num", stanceText(data!.society.final_p))}>{pctSmart(data!.society.final_p)}</span>
                    </p>
                  )}
                </div>
              )}
              {said.length > 0 && (
                <div>
                  <h3 className="mb-2 text-[14px] font-medium">What they said to others</h3>
                  <ul className="flex flex-col gap-2">
                    {said.slice(0, 3).map((m) => (
                      <li key={m.id} className="border-l-2 border-border pl-3 text-[14px] leading-5">
                        {m.text}
                        <span className="mt-0.5 block text-[12px] text-faint">
                          {m.kind === "reply" ? "Reply" : "Post"}, {m.round === 0 ? "first reactions" : `round ${m.round}`}, {m.agrees} agree
                        </span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              <LinkButton href={`/runs/${runId}/people/${pid}`} className="self-start">
                Open full profile
              </LinkButton>
              <div className="border-t border-border pt-5">
                <h3 className="mb-3 text-[14px] font-medium">Talk to {p.name.split(" ")[0]}</h3>
                <PersonaChat runId={runId} pid={pid} name={p.name} initial={data!.chat} />
              </div>
            </div>
          )}
        </div>
        {p && (
          <div className="border-t border-border px-6 py-3 text-[12px] text-faint">
            Simulated person. <Link href={`/runs/${runId}/people/${pid}`} className="text-text hover:underline">See everything about {p.name.split(" ")[0]}</Link>
          </div>
        )}
      </motion.aside>
    </>
  );
}
