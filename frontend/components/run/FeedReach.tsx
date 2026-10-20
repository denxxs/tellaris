"use client";

import { useState } from "react";
import { Avatar } from "@/components/people/Avatar";
import { Button, Card, CardHead } from "@/components/ui";
import { api } from "@/lib/api";
import { useMeta } from "@/lib/meta";
import { cx, int, pctSmart, signedPts, stanceFill } from "@/lib/format";
import Link from "next/link";
import type { FeedReach, FeedStyle, Results } from "@/lib/types";

export const FEED_LABEL: Record<FeedStyle, string> = {
  word_of_mouth: "Word of mouth",
  ranked: "Ranked feed",
  viral: "Viral",
};

const FEED_SUB: Record<FeedStyle, string> = {
  word_of_mouth: "People only saw what their own contacts said.",
  ranked: "A platform picked each feed by freshness, likes, reshares and closeness.",
  viral: "A platform that pushes whatever is popular, far beyond people's circles.",
};

/** How far posts travelled under this run's feed style, and a one-click rerun under another. */
export function FeedReachCard({ id, f, people, cmp, onSelect }: { id: string; f: FeedReach; people: number; cmp?: Results["comparison"]; onSelect: (pid: string) => void }) {
  const { countryName } = useMeta();
  const [starting, setStarting] = useState<FeedStyle | null>(null);
  const platform = f.style !== "word_of_mouth";
  const others = (Object.keys(FEED_LABEL) as FeedStyle[]).filter((s) => s !== f.style);

  const rerun = async (s: FeedStyle) => {
    setStarting(s);
    try {
      const res = await api.whatif(id, `Feed: ${FEED_LABEL[s]}`, {}, { feed_style: s });
      window.location.href = `/runs/${res.id}`;
    } catch {
      setStarting(null);
    }
  };

  const stats: [string, string, string][] = [
    ["Seen per post", f.avg_reach.toFixed(1), "people, on average"],
    ["Outside their circle", pctSmart(f.outside_share), "of views came from people the author doesn't know"],
    ...(platform
      ? ([
          ["Likes", int(f.likes), "across the conversation"],
          ["Reshares", int(f.reshares), "posts passed on to new circles"],
        ] as [string, string, string][])
      : []),
  ];

  return (
    <Card>
      <CardHead title="How far posts travelled">
        <span className="font-medium text-text">{f.label}.</span> {FEED_SUB[f.style]}
      </CardHead>
      <dl className="grid grid-cols-2 gap-x-4 gap-y-3">
        {stats.map(([label, v, sub]) => (
          <div key={label}>
            <dt className="text-[13px] text-muted">{label}</dt>
            <dd className="num mt-0.5 text-[22px] leading-7 text-text">{v}</dd>
            <dd className="text-[12px] leading-4 text-faint">{sub}</dd>
          </div>
        ))}
      </dl>

      {cmp?.society && cmp.society.parent.feed !== f.style && <Versus cmp={cmp} />}

      {f.travelled.length > 0 && (
        <div className="mt-5">
          <h3 className="text-[13px] font-medium">Furthest-reaching posts</h3>
          <p className="mb-2 flex flex-wrap items-center gap-x-3 text-[12px] text-faint">
            <span className="inline-flex items-center gap-1.5">
              <span className="inline-block h-2 w-3 rounded-sm bg-[var(--control)]" aria-hidden /> their contacts
            </span>
            <span className="inline-flex items-center gap-1.5">
              <span className="inline-block h-2 w-3 rounded-sm bg-flow" aria-hidden /> beyond their circle
            </span>
          </p>
          <ul className="flex flex-col">
            {f.travelled.map((t) => {
              const inside = Math.max(t.seen - t.seen_outside, 0);
              return (
                <li key={t.id} className="border-b border-rule py-2.5 first:pt-0 last:border-0 last:pb-0">
                  <button onClick={() => onSelect(t.author)} className="flex w-full items-start gap-2.5 text-left">
                    <Avatar seed={t.author} size={28} ring={t.p != null ? stanceFill(t.p) : undefined} />
                    <span className="min-w-0 flex-1">
                      <span className="flex items-baseline justify-between gap-2 text-[13px]">
                        <span className="truncate text-text">
                          {t.author_name}
                          {t.country && <span className="text-faint">, {countryName(t.country)}</span>}
                        </span>
                        <span className="num shrink-0 text-muted">{pctSmart(t.share)}</span>
                      </span>
                      <span className="mt-0.5 line-clamp-2 block text-[13px] leading-[18px] text-muted">“{t.text}”</span>
                      <span
                        className="mt-1.5 flex h-1.5 gap-[2px] overflow-hidden rounded-full bg-raised"
                        role="img"
                        aria-label={`Seen by ${t.seen} of ${people} people, ${t.seen_outside} outside the author's circle`}
                      >
                        {inside > 0 && <span className="h-full rounded-full bg-[var(--control)]" style={{ width: `${(inside / people) * 100}%` }} />}
                        {t.seen_outside > 0 && <span className="h-full rounded-full bg-flow" style={{ width: `${(t.seen_outside / people) * 100}%` }} />}
                      </span>
                      <span className="mt-1 block text-[12px] text-faint">
                        Seen by <span className="num">{t.seen}</span> of <span className="num">{people}</span>
                        {platform && (
                          <>
                            , <span className="num">{t.likes}</span> {t.likes === 1 ? "like" : "likes"}, <span className="num">{t.reshares}</span>{" "}
                            {t.reshares === 1 ? "reshare" : "reshares"}
                          </>
                        )}
                      </span>
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        </div>
      )}

      <div className="mt-5 border-t border-rule pt-4">
        <h3 className="text-[13px] font-medium">Try another feed</h3>
        <p className="mb-2.5 text-[12px] leading-4 text-muted">Rerun the same people with only the feed changed, then compare.</p>
        <div className="flex flex-wrap gap-2">
          {others.map((s) => (
            <Button key={s} size="sm" busy={starting === s} disabled={starting !== null} onClick={() => rerun(s)}>
              {FEED_LABEL[s]}
            </Button>
          ))}
        </div>
      </div>
    </Card>
  );
}

/** This run's conversation against the run it was rerun from, with another feed. */
function Versus({ cmp }: { cmp: NonNullable<Results["comparison"]> }) {
  const s = cmp.society!;
  const rows: [string, number | null, number | null, boolean][] = [
    ["Leaning yes after the talk", s.parent.after_talk, s.this.after_talk, true],
    ["Views from beyond people's circles", s.parent.outside_share, s.this.outside_share, false],
  ];
  return (
    <div className="mt-5 rounded-md bg-raised p-3">
      <h3 className="text-[13px] font-medium">
        Against the <Link href={`/runs/${cmp.parent_id}`} className="underline decoration-control underline-offset-2 hover:decoration-text">original run</Link>
      </h3>
      <table className="mt-2 w-full text-[13px]">
        <thead>
          <tr className="text-left text-[12px] text-faint">
            <th className="pb-1 font-normal"><span className="sr-only">Measure</span></th>
            <th className="pb-1 text-right font-normal">{FEED_LABEL[s.parent.feed]}</th>
            <th className="pb-1 text-right font-normal">{FEED_LABEL[s.this.feed]}</th>
          </tr>
        </thead>
        <tbody>
          {rows.filter(([, a, b]) => a != null && b != null).map(([label, a, b, signed]) => {
            const d = (b as number) - (a as number);
            return (
              <tr key={label} className="border-t border-rule">
                <td className="py-1.5 pr-2 align-top text-muted">{label}</td>
                <td className="num py-1.5 text-right align-top text-muted">{pctSmart(a)}</td>
                <td className="num whitespace-nowrap py-1.5 pl-3 text-right align-top text-text">
                  {pctSmart(b)}
                  {signed && Math.abs(d) >= 0.0005 && <span className={cx("block whitespace-nowrap text-[12px] leading-4", d > 0 ? "text-yes" : "text-no")}>{signedPts(d)}</span>}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

/** Likes, reshares and reach under a post. */
export function PostReach({ likes = 0, reshares = 0, by = [], seen, outside = 0, onSelect }: { likes?: number; reshares?: number; by?: { id: string; name: string }[]; seen?: number; outside?: number; onSelect: (pid: string) => void }) {
  if (!likes && !reshares && !seen) return null;
  return (
    <div className="mt-1.5 flex flex-wrap gap-x-4 gap-y-1 text-[12px] text-muted">
      {likes > 0 && (
        <span>
          <span className="num text-text">{likes}</span> {likes === 1 ? "like" : "likes"}
        </span>
      )}
      {reshares > 0 && by.length === 0 && (
        <span>
          <span className="num text-text">{reshares}</span> {reshares === 1 ? "reshare" : "reshares"}
        </span>
      )}
      {reshares > 0 && by.length > 0 && (
        <span>
          Reshared by{" "}
          {by.slice(0, 2).map((b, i) => (
            <span key={b.id}>
              {i > 0 && " and "}
              <button className="text-text hover:underline" onClick={() => onSelect(b.id)}>
                {b.name.split(" ")[0]}
              </button>
            </span>
          ))}
          {reshares > Math.min(by.length, 2) && <> and {reshares - Math.min(by.length, 2)} more</>}
        </span>
      )}
      {!!seen && (
        <span>
          Seen by <span className="num text-text">{seen}</span>
          {outside > 0 && <>, {outside} beyond their circle</>}
        </span>
      )}
    </div>
  );
}
