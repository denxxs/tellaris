"use client";

import { createContext, useContext, useEffect, useMemo, useState } from "react";
import { api } from "./api";
import type { Meta } from "./types";

type MetaState = {
  meta: Meta | null;
  error: string | null;
  countryName: (code: string) => string;
};

const Ctx = createContext<MetaState>({ meta: null, error: null, countryName: (c) => c });

/** Loads countries, blocs, occupations and defaults once for the whole app. */
export function MetaProvider({ children }: { children: React.ReactNode }) {
  const [meta, setMeta] = useState<Meta | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    const load = () =>
      api
        .meta()
        .then((m) => {
          if (!alive) return;
          setMeta(m);
          setError(null);
        })
        .catch((e) => {
          if (!alive) return;
          setError(e.message);
          setTimeout(load, 4000);
        });
    load();
    return () => {
      alive = false;
    };
  }, []);

  const value = useMemo(() => {
    const names: Record<string, string> = {};
    for (const c of meta?.countries ?? []) names[c.iso3] = c.name;
    for (const b of meta?.blocs ?? []) names[b.id] = b.name;
    return { meta, error, countryName: (code: string) => names[code] ?? code };
  }, [meta, error]);

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export const useMeta = () => useContext(Ctx);
