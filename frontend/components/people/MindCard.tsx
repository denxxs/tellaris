"use client";

import { Card, CardHead, Pill } from "@/components/ui";
import { cx, pctSmart, stanceText } from "@/lib/format";
import type { Mind, MindMemory } from "@/lib/types";

const KIND_LABEL: Record<MindMemory["kind"], string> = {
  said: "What they said first",
  saw: "Saw a post",
  reply: "Got a reply",
  news: "News",
  meeting: "Their buying meeting",
  thought: "Their own thought",
};

/** How their view moved, round by round, ending with where they landed after reflecting. */
function Path({ points }: { points: { label: string; p: number }[] }) {
  const w = 100;
  const h = 36;
  const x = (i: number) => (points.length === 1 ? w / 2 : 4 + (i * (w - 8)) / (points.length - 1));
  // Zoom to this person's own range so small moves are visible; the dotted line marks 50% when in view.
  const vals = points.map((pt) => pt.p);
  const lo = Math.max(0, Math.min(...vals) - 0.05);
  const hi = Math.min(1, Math.max(...vals) + 0.05);
  const y = (p: number) => h - 4 - ((p - lo) / Math.max(hi - lo, 0.1)) * (h - 8);
  return (
    <div>
      <svg viewBox={`0 0 ${w} ${h}`} preserveAspectRatio="none" className="h-12 w-full" aria-hidden>
        {lo < 0.5 && hi > 0.5 && <line x1={0} x2={w} y1={y(0.5)} y2={y(0.5)} stroke="var(--rule)" strokeDasharray="3 3" vectorEffect="non-scaling-stroke" />}
        <polyline points={points.map((pt, i) => `${x(i)},${y(pt.p)}`).join(" ")} fill="none" stroke="var(--yes)" strokeWidth={2} vectorEffect="non-scaling-stroke" />
      </svg>
      <ol className="mt-1 grid gap-2" style={{ gridTemplateColumns: `repeat(${points.length}, minmax(0, 1fr))` }}>
        {points.map((pt, i) => (
          <li key={i} className={cx("min-w-0", i === 0 ? "text-left" : i === points.length - 1 ? "text-right" : "text-center")}>
            <div className={cx("num text-[14px]", stanceText(pt.p))}>{pctSmart(pt.p)}</div>
            <div className="truncate text-[12px] text-faint">{pt.label}</div>
          </li>
        ))}
      </ol>
    </div>
  );
}

/** What stuck with a person during the society, and how they see it after reflecting. */
export function MindCard({ mind, name }: { mind: Mind; name: string }) {
  const first = name.split(" ")[0];
  const ref = mind.reflection;
  const moved = new Set(ref?.influences ?? []);
  const points = [
    ...mind.trajectory.map((p, i) => ({ label: i === 0 ? "Start" : `Round ${i}`, p })),
    ...(ref ? [{ label: "After reflecting", p: ref.p }] : []),
  ];
  const rounds = [...new Set(mind.memories.map((m) => m.round))].sort((a, b) => a - b);

  return (
    <Card>
      <CardHead title="What they remember" aside={ref?.changed_mind ? <Pill tone="warning">Changed their mind</Pill> : undefined}>
        What stuck with {first} while talking it over, and how their view moved.
      </CardHead>
      {points.length > 1 && <Path points={points} />}
      {ref && (
        <figure className="mt-5 rounded-lg bg-raised p-4">
          <figcaption className="mb-1 text-[13px] text-muted">After thinking it over</figcaption>
          <blockquote className="text-[16px] leading-6 text-text">“{ref.belief}”</blockquote>
          <p className="mt-2 text-[13px] text-muted">
            {moved.size ? `What moved ${first} most is marked below.` : `Nothing ${first} saw moved them much.`}
          </p>
        </figure>
      )}
      <ol className="mt-5 flex flex-col gap-5">
        {rounds.map((rnd) => (
          <li key={rnd}>
            <h3 className="mb-2 text-[13px] font-medium text-muted">{rnd === 0 ? "Before the conversation" : `Round ${rnd}`}</h3>
            <ul className="flex flex-col gap-2.5">
              {mind.memories
                .filter((m) => m.round === rnd)
                .map((m) => (
                  <li key={m.n} className={cx("border-l-2 pl-3", moved.has(m.n) ? "border-[var(--yes)]" : "border-rule")}>
                    <div className="flex flex-wrap items-center gap-2 text-[12px] text-faint">
                      <span>
                        {KIND_LABEL[m.kind]}
                        {m.who ? `, ${m.who}` : ""}
                      </span>
                      {moved.has(m.n) && <Pill tone="yes">Moved them</Pill>}
                    </div>
                    <p className="text-[14px] leading-5 text-text">{m.kind === "saw" || m.kind === "reply" || m.kind === "said" ? `“${m.text}”` : m.text}</p>
                  </li>
                ))}
            </ul>
          </li>
        ))}
      </ol>
    </Card>
  );
}
