"use client";

import { AnimatePresence, motion } from "motion/react";
import type { LiveState } from "@/lib/useRunStream";
import type { Meta } from "@/lib/types";
import { cx, pctSmart } from "@/lib/format";
import { AnswerTrack } from "@/components/charts";
import { Chip } from "@/components/ui";

export function StageList({ live, meta }: { live: LiveState; meta: Meta | null }) {
  const stages = meta?.stages ?? [];
  return (
    <ol className="flex flex-col">
      {stages.map((s, i) => {
        const st = live.stages[s.id];
        const status = st?.status ?? "pending";
        const running = status === "start" && live.status !== "failed" && live.status !== "cancelled";
        return (
          <li key={s.id} className="flex items-center gap-3 py-1.5">
            <span
              className={cx(
                "grid size-6 shrink-0 place-items-center rounded-full text-[11px] font-bold",
                status === "done" && "bg-iris text-white",
                running && "bg-live text-ink",
                status === "skipped" && "bg-panel-2 text-ink-3",
                status === "pending" && "border border-line-strong text-ink-3",
                status === "start" && !running && "bg-no-soft text-no",
              )}
              aria-hidden
            >
              {status === "done" ? (
                <svg viewBox="0 0 12 12" className="size-3">
                  <path d="M2.5 6.5l2.2 2.2L9.5 3.8" stroke="currentColor" strokeWidth="1.8" fill="none" strokeLinecap="round" />
                </svg>
              ) : (
                i + 1
              )}
            </span>
            <span className={cx("text-sm", status === "pending" || status === "skipped" ? "text-ink-3" : "font-semibold text-ink")}>
              {s.label}
              {status === "skipped" && <span className="font-normal"> (not needed)</span>}
            </span>
            {running && <span className="live-dot ml-auto inline-block size-2 rounded-full bg-live" aria-label="In progress" />}
          </li>
        );
      })}
    </ol>
  );
}

export function Counters({ live }: { live: LiveState }) {
  const people = live.order.length;
  const answers = Object.values(live.scores).reduce((a, s) => a + s.length, 0);
  const vals = Object.entries(live.scores)
    .filter(([id]) => !live.personas[id]?.voice)
    .map(([, s]) => s.reduce((a, b) => a + b, 0) / s.length);
  const lean = vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : null;
  const items = [
    { label: "People", value: people.toLocaleString() },
    { label: "Answers", value: answers.toLocaleString() },
    { label: "Leaning yes (raw)", value: lean == null ? "–" : pctSmart(lean) },
  ];
  return (
    <dl className="grid grid-cols-3 gap-3">
      {items.map((it) => (
        <div key={it.label}>
          <dt className="t-tiny text-ink-3">{it.label}</dt>
          <dd className="num font-display text-2xl font-bold tracking-tight">{it.value}</dd>
        </div>
      ))}
    </dl>
  );
}

export function Ticker({ live }: { live: LiveState }) {
  return (
    <div className="relative">
      <ul className="flex max-h-[340px] flex-col gap-2 overflow-hidden" aria-live="polite">
        <AnimatePresence initial={false}>
          {live.ticker.slice(0, 7).map((t) => {
            const p = live.personas[t.id];
            return (
              <motion.li
                key={`${t.id}-${t.run}`}
                layout
                initial={{ opacity: 0, y: -10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.3 }}
                className="rounded-xl border border-line bg-panel px-3 py-2.5"
              >
                <div className="flex items-baseline justify-between gap-2">
                  <span className="truncate text-[13px] font-semibold text-ink">{p?.name || "Someone"}</span>
                  <span className={cx("num shrink-0 text-[13px] font-bold", t.p >= 0.55 ? "text-yes" : t.p <= 0.3 ? "text-no" : "text-ink-2")}>{pctSmart(t.p)}</span>
                </div>
                <div className="truncate t-tiny text-ink-3">
                  {p ? `${p.occupation.split("(")[0].trim()}, ${p.country}` : ""}
                </div>
                <p className="mt-1 line-clamp-2 text-[13px] leading-snug text-ink-2">“{t.quote}”</p>
              </motion.li>
            );
          })}
        </AnimatePresence>
      </ul>
      <div className="pointer-events-none absolute inset-x-0 bottom-0 h-12 bg-gradient-to-t from-fog to-transparent" />
    </div>
  );
}

const VERDICT: Record<string, { label: string; tone: "yes" | "no" | "iris" | "neutral" }> = {
  strong: { label: "Strong", tone: "yes" },
  promising: { label: "Promising", tone: "yes" },
  uncertain: { label: "Uncertain", tone: "neutral" },
  weak: { label: "Weak", tone: "no" },
  unlikely: { label: "Unlikely", tone: "no" },
};

export function Answer({ live }: { live: LiveState }) {
  const r = live.results;
  const rep = live.report;
  if (!r) return null;
  const h = r.headline;
  const v = VERDICT[rep?.verdict ?? ""];
  return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}>
      <div className="flex flex-wrap items-end gap-x-8 gap-y-4">
        <div>
          <div className="t-number text-[clamp(4rem,10vw,7.5rem)]">{pctSmart(h.value)}</div>
          <div className="mt-2 max-w-md text-[15px] font-semibold text-ink">{h.label}</div>
        </div>
        <div className="min-w-[240px] flex-1 pb-1">
          <AnswerTrack value={h.value} ci={h.ci} ifAware={h.kind === "action" ? h.if_aware : undefined} />
          <p className="mt-6 t-small text-ink-2">
            Likely between <b className="num text-ink">{pctSmart(h.ci[0])}</b> and <b className="num text-ink">{pctSmart(h.ci[1])}</b>.
            {h.kind === "action" && (
              <>
                {" "}
                Among people who hear about it: <b className="num text-ink">{pctSmart(h.if_aware)}</b> (assuming {pctSmart(h.reach)} hear about it).
              </>
            )}
          </p>
        </div>
      </div>
      {rep && (
        <div className="mt-6 flex flex-wrap items-start gap-3">
          {v && <Chip tone={v.tone === "neutral" ? "neutral" : v.tone}>{v.label}</Chip>}
          <p className="max-w-3xl text-[17px] leading-relaxed text-ink">{rep.headline}</p>
        </div>
      )}
      {r.comparison && (
        <p className="mt-4 text-sm text-ink-2">
          Compared with the original run ({pctSmart(r.comparison.parent_value)}):{" "}
          <b className={cx("num", r.comparison.delta > 0 ? "text-yes" : r.comparison.delta < 0 ? "text-no" : "text-ink")}>
            {r.comparison.delta > 0 ? "+" : ""}
            {(r.comparison.delta * 100).toFixed(1)} points
          </b>
          , with the same people.
        </p>
      )}
    </motion.div>
  );
}
