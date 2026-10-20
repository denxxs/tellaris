"use client";

import { useMemo, useState } from "react";
import { useMeta } from "@/lib/meta";
import { cx, pctSmart, shortJob, stanceFill } from "@/lib/format";
import type { PersonaLite } from "@/lib/types";

type Props = {
  order: string[];
  personas: Record<string, PersonaLite>;
  scores: Record<string, number[]>;
  done: boolean;
  onSelect?: (id: string) => void;
};

/** One square per simulated person, grouped by who they are, coloured by what they said. */
export function Crowd({ order, personas, scores, done, onSelect }: Props) {
  const { countryName } = useMeta();
  const [hover, setHover] = useState<string | null>(null);

  const groups = useMemo(() => {
    const m = new Map<string, string[]>();
    for (const id of order) {
      const p = personas[id];
      if (!p) continue;
      const key = p.voice ? `Outside voices` : `${p.segment}`;
      if (!m.has(key)) m.set(key, []);
      m.get(key)!.push(id);
    }
    const mean = (id: string) => {
      const s = scores[id];
      return s?.length ? s.reduce((a, b) => a + b, 0) / s.length : null;
    };
    return [...m.entries()]
      .sort((a, b) => (a[0] === "Outside voices" ? 1 : b[0] === "Outside voices" ? -1 : 0))
      .map(([label, ids]) => {
        const vals = ids.map(mean).filter((v): v is number => v != null);
        const sorted = done ? [...ids].sort((a, b) => (mean(b) ?? -1) - (mean(a) ?? -1)) : ids;
        const countries = [...new Set(ids.map((id) => personas[id].country))];
        return {
          label,
          ids: sorted,
          mean,
          lean: vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : null,
          answered: vals.length,
          countries,
        };
      });
  }, [order, personas, scores, done]);

  const hp = hover ? personas[hover] : null;
  const hs = hover && scores[hover]?.length ? scores[hover].reduce((a, b) => a + b, 0) / scores[hover].length : null;

  if (!order.length) {
    return <div className="grid h-32 place-items-center rounded-md bg-raised text-[13px] text-muted">People appear here as they are built.</div>;
  }

  return (
    <div className="relative">
      <div className="flex flex-col gap-4">
        {groups.map((g) => (
          <div key={g.label} className="grid grid-cols-1 gap-x-6 gap-y-2 md:grid-cols-[200px_minmax(0,1fr)]">
            <div className="min-w-0">
              <div className="truncate text-[14px] text-text">{g.label}</div>
              <div className="truncate text-[12px] leading-4 text-faint">
                {g.ids.length} people in {g.countries.slice(0, 3).map(countryName).join(", ")}
                {g.countries.length > 3 ? ` and ${g.countries.length - 3} more` : ""}
              </div>
              <div className="num mt-0.5 text-[13px] text-muted">{g.lean == null ? "Waiting for answers" : `Leaning ${pctSmart(g.lean)} yes`}</div>
            </div>
            <div className="flex flex-wrap content-start gap-[3px]" role="list" aria-label={`${g.label}: ${g.answered} of ${g.ids.length} answered`}>
              {g.ids.map((id) => {
                const v = g.mean(id);
                return (
                  <button
                    key={id}
                    role="listitem"
                    onMouseEnter={() => setHover(id)}
                    onMouseLeave={() => setHover((h) => (h === id ? null : h))}
                    onFocus={() => setHover(id)}
                    onClick={() => onSelect?.(id)}
                    aria-label={`${personas[id].name || "Person"}, ${v == null ? "no answer yet" : pctSmart(v)}`}
                    className={cx("size-[11px] rounded-[2px] transition-transform hover:scale-150 focus-visible:scale-150", v != null && "cell-in")}
                    style={{ background: v == null ? "transparent" : stanceFill(v), boxShadow: v == null ? "inset 0 0 0 1px var(--control)" : undefined }}
                  />
                );
              })}
            </div>
          </div>
        ))}
      </div>
      <div className="mt-4 flex min-h-10 flex-wrap items-center justify-between gap-3 border-t border-rule pt-3">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[12px] text-muted">
          <span className="inline-flex items-center gap-1.5">
            <span className="size-2.5 rounded-[2px]" style={{ background: stanceFill(0.9) }} aria-hidden /> Likely yes
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span className="size-2.5 rounded-[2px] bg-mid" aria-hidden /> Unsure
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span className="size-2.5 rounded-[2px]" style={{ background: stanceFill(0.05) }} aria-hidden /> Likely no
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span className="size-2.5 rounded-[2px] shadow-[inset_0_0_0_1px_var(--control)]" aria-hidden /> No answer yet
          </span>
        </div>
        {hp ? (
          <div className="min-w-0 text-[13px]">
            <span className="text-text">{hp.name || "Unnamed"}</span>
            <span className="text-muted">
              , {shortJob(hp.occupation)} in {countryName(hp.country)}
              {hs != null && <>, {pctSmart(hs)}</>}
            </span>
          </div>
        ) : (
          onSelect && <div className="text-[13px] text-faint">Select a square to meet that person.</div>
        )}
      </div>
    </div>
  );
}
