"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type { Meta } from "@/lib/types";
import { Chip } from "@/components/ui";
import { cx } from "@/lib/format";

type Props = {
  meta: Meta | null;
  value: string[];
  onChange: (v: string[]) => void;
  placeholder?: string;
};

export function CountryPicker({ meta, value, onChange, placeholder = "Add a country or region" }: Props) {
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const [hi, setHi] = useState(0);
  const box = useRef<HTMLDivElement>(null);

  const names = useMemo(() => Object.fromEntries((meta?.countries ?? []).map((c) => [c.iso3, c.name])), [meta]);

  const options = useMemo(() => {
    if (!meta) return [];
    const term = q.trim().toLowerCase();
    const blocs = meta.blocs.map((b) => ({ id: b.id, label: b.name, sub: `${b.members.length} countries`, members: b.members }));
    const countries = meta.countries.map((c) => ({ id: c.iso3, label: c.name, sub: c.region, members: [c.iso3] }));
    return [...blocs, ...countries]
      .filter((o) => !term || o.label.toLowerCase().includes(term) || o.id.toLowerCase() === term)
      .filter((o) => o.members.some((m) => !value.includes(m)))
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
      <div className="flex flex-wrap items-center gap-1.5">
        {value.map((iso) => (
          <Chip key={iso} tone="iris" onRemove={() => onChange(value.filter((v) => v !== iso))}>
            {names[iso] ?? iso}
          </Chip>
        ))}
        <input
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
          aria-label="Add a target country"
          role="combobox"
          aria-expanded={open}
          aria-controls="country-options"
          className="h-7 min-w-[160px] flex-1 bg-transparent text-sm text-ink placeholder:text-ink-3 focus:outline-none"
        />
      </div>
      {open && options.length > 0 && (
        <ul id="country-options" role="listbox" className="absolute left-0 top-full z-30 mt-2 w-[320px] max-w-[calc(100vw-48px)] overflow-hidden rounded-xl border border-line bg-panel py-1 shadow-lift">
          {options.map((o, i) => (
            <li key={o.id} role="option" aria-selected={i === hi}>
              <button
                type="button"
                onMouseEnter={() => setHi(i)}
                onClick={() => pick(o.members)}
                className={cx("flex w-full items-baseline justify-between gap-3 px-3 py-2 text-left text-sm", i === hi && "bg-panel-2")}
              >
                <span className="font-medium text-ink">{o.label}</span>
                <span className="t-tiny text-ink-3">{o.sub}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
