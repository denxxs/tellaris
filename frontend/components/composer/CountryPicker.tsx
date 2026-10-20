"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Chip } from "@/components/ui";
import { useMeta } from "@/lib/meta";
import { cx, people } from "@/lib/format";

type Props = {
  value: string[];
  onChange: (v: string[]) => void;
  placeholder?: string;
  id?: string;
};

/** Search every country and bloc; a bloc adds its members. */
export function CountryPicker({ value, onChange, placeholder = "Add a country or region", id }: Props) {
  const { meta, countryName } = useMeta();
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const [hi, setHi] = useState(0);
  const box = useRef<HTMLDivElement>(null);

  const options = useMemo(() => {
    if (!meta) return [];
    const term = q.trim().toLowerCase();
    const blocs = meta.blocs
      .filter((b) => b.members.length > 1)
      .map((b) => ({ id: b.id, label: b.name, sub: `${b.members.length} countries`, members: b.members, size: 0 }));
    const countries = meta.countries.map((c) => ({ id: c.iso3, label: c.name, sub: `${people(c.population_m * 1e6)} people`, members: [c.iso3], size: c.population_m }));
    const all = [...blocs, ...countries].filter((o) => o.members.some((m) => !value.includes(m)));
    if (!term) return countries.filter((c) => !value.includes(c.id)).sort((a, b) => b.size - a.size).slice(0, 8);
    return all
      .filter((o) => o.label.toLowerCase().includes(term) || o.id.toLowerCase() === term)
      .sort((a, b) => Number(!a.label.toLowerCase().startsWith(term)) - Number(!b.label.toLowerCase().startsWith(term)) || b.size - a.size)
      .slice(0, 9);
  }, [meta, q, value]);

  useEffect(() => {
    const close = (e: MouseEvent) => !box.current?.contains(e.target as Node) && setOpen(false);
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);

  const pick = (members: string[]) => {
    onChange([...value, ...members.filter((m) => !value.includes(m))]);
    setQ("");
    setHi(0);
  };

  return (
    <div ref={box} className="relative">
      <div className="flex min-h-9 flex-wrap items-center gap-1.5 rounded-md border border-border bg-surface px-2 py-1.5 focus-within:border-control">
        {value.map((iso) => (
          <Chip key={iso} onRemove={() => onChange(value.filter((v) => v !== iso))}>
            {countryName(iso)}
          </Chip>
        ))}
        <input
          id={id}
          value={q}
          onChange={(e) => {
            setQ(e.target.value);
            setOpen(true);
            setHi(0);
          }}
          onFocus={() => setOpen(true)}
          onKeyDown={(e) => {
            if (e.key === "ArrowDown") {
              e.preventDefault();
              setHi((h) => Math.min(h + 1, options.length - 1));
            } else if (e.key === "ArrowUp") {
              e.preventDefault();
              setHi((h) => Math.max(h - 1, 0));
            } else if (e.key === "Enter" && open && options[hi]) {
              e.preventDefault();
              pick(options[hi].members);
            } else if (e.key === "Backspace" && !q && value.length) {
              onChange(value.slice(0, -1));
            } else if (e.key === "Escape") setOpen(false);
          }}
          placeholder={value.length ? "Add another" : placeholder}
          aria-label="Add a target country or region"
          role="combobox"
          aria-expanded={open}
          aria-controls={`${id ?? "country"}-options`}
          className="h-6 min-w-[140px] flex-1 bg-transparent px-1 text-[14px] text-text placeholder:text-faint focus:outline-none"
        />
      </div>
      {open && options.length > 0 && (
        <ul
          id={`${id ?? "country"}-options`}
          role="listbox"
          className="absolute left-0 top-full z-30 mt-1 max-h-80 w-[340px] max-w-[calc(100vw-32px)] overflow-y-auto rounded-lg border border-border bg-surface py-1 shadow-[0_8px_24px_rgba(0,0,0,0.12)]"
        >
          {!q && <li className="px-3 pb-1 pt-1.5 text-[12px] text-faint">Largest countries. Type to search all {meta?.countries.length} and regional blocs.</li>}
          {options.map((o, i) => (
            <li key={o.id} role="option" aria-selected={i === hi}>
              <button
                type="button"
                onMouseEnter={() => setHi(i)}
                onClick={() => pick(o.members)}
                className={cx("flex w-full items-baseline justify-between gap-3 px-3 py-1.5 text-left", i === hi && "bg-active")}
              >
                <span className="text-[14px] text-text">{o.label}</span>
                <span className="num text-[12px] text-faint">{o.sub}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
