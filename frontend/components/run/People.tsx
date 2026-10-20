"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { Avatar } from "@/components/people/Avatar";
import { Card, Input, Select, Skeleton } from "@/components/ui";
import { api } from "@/lib/api";
import { useMeta } from "@/lib/meta";
import { cx, pctSmart, shortJob, stanceFill, stanceText } from "@/lib/format";
import type { PersonaSummary } from "@/lib/types";

const PAGE = 50;

export function PeopleTab({ id, onSelect }: { id: string; onSelect: (pid: string) => void }) {
  const { countryName } = useMeta();
  const [rows, setRows] = useState<PersonaSummary[] | null>(null);
  const [q, setQ] = useState("");
  const [country, setCountry] = useState("");
  const [segment, setSegment] = useState("");
  const [lean, setLean] = useState("");
  const [shown, setShown] = useState(PAGE);

  useEffect(() => {
    api.personas(id).then(setRows).catch(() => setRows([]));
  }, [id]);

  const countries = useMemo(() => [...new Set((rows ?? []).map((p) => p.country))].sort(), [rows]);
  const segments = useMemo(() => [...new Set((rows ?? []).map((p) => p.segment))], [rows]);
  const filtered = useMemo(() => {
    const t = q.trim().toLowerCase();
    return (rows ?? [])
      .filter((p) => !country || p.country === country)
      .filter((p) => !segment || p.segment === segment)
      .filter((p) => !lean || (lean === "yes" ? (p.p ?? 0) >= 0.55 : lean === "no" ? (p.p ?? 1) <= 0.3 : (p.p ?? 0) > 0.3 && (p.p ?? 0) < 0.55))
      .filter((p) => !t || `${p.name} ${p.occupation} ${p.quote}`.toLowerCase().includes(t))
      .sort((a, b) => (b.p ?? 0) - (a.p ?? 0));
  }, [rows, q, country, segment, lean]);

  useEffect(() => setShown(PAGE), [q, country, segment, lean]);

  return (
    <Card>
      <div className="mb-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-[minmax(0,2fr)_repeat(3,minmax(0,1fr))]">
        <Input placeholder="Search names, jobs or what they said" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search people" />
        <Select label="Country" value={country} onChange={setCountry} options={[{ value: "", label: "All countries" }, ...countries.map((c) => ({ value: c, label: countryName(c) }))]} />
        <Select label="Group" value={segment} onChange={setSegment} options={[{ value: "", label: "All groups" }, ...segments.map((s) => ({ value: s, label: s }))]} />
        <Select
          label="Answer"
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
      {!rows ? (
        <div className="flex flex-col gap-3">
          {[0, 1, 2, 3, 4].map((i) => (
            <Skeleton key={i} className="h-10" />
          ))}
        </div>
      ) : (
        <>
          <p className="mb-2 text-[13px] text-muted">
            <span className="num">{filtered.length}</span> of <span className="num">{rows.length}</span> people. Select a row for a quick look, or a name for the full profile.
          </p>
          <table className="w-full text-[14px]">
            <thead>
              <tr className="border-b border-border text-left text-[12px] text-faint">
                <th className="pb-2 font-normal">Person</th>
                <th className="hidden pb-2 font-normal md:table-cell">What they said</th>
                <th className="pb-2 text-right font-normal">Answer</th>
              </tr>
            </thead>
            <tbody>
              {filtered.slice(0, shown).map((p) => (
                <tr key={p.id} onClick={() => onSelect(p.id)} className="cursor-pointer border-b border-rule last:border-0 hover:bg-raised">
                  <td className="max-w-0 py-2.5 pr-4 md:w-[38%]">
                    <span className="flex items-center gap-2.5">
                      <Avatar seed={p.id} size={32} ring={p.p != null ? stanceFill(p.p) : undefined} />
                      <span className="min-w-0">
                        <Link href={`/runs/${id}/people/${p.id}`} onClick={(e) => e.stopPropagation()} className="block truncate text-text hover:underline">
                          {p.name}
                        </Link>
                        <span className="block truncate text-[12px] leading-4 text-faint">
                          {p.age}, {shortJob(p.occupation)}, {countryName(p.country)}
                          {p.voice ? ", outside voice" : ""}
                        </span>
                      </span>
                    </span>
                  </td>
                  <td className="hidden max-w-0 py-2.5 pr-4 text-[13px] text-muted md:table-cell">
                    <span className="line-clamp-2">{p.quote ? `“${p.quote}”` : "–"}</span>
                  </td>
                  <td className={cx("num py-2.5 text-right", stanceText(p.p))}>{pctSmart(p.p)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {filtered.length > shown && (
            <div className="mt-3 flex items-center justify-between text-[13px] text-muted">
              <span>
                Showing <span className="num">1–{shown}</span> of <span className="num">{filtered.length}</span>
              </span>
              <button className="font-medium text-text hover:underline" onClick={() => setShown(shown + PAGE)}>
                Show more
              </button>
            </div>
          )}
        </>
      )}
    </Card>
  );
}
