"use client";

import { geoArea, geoBounds, geoContains, geoEqualEarth, geoPath } from "d3-geo";
import type { Feature, FeatureCollection, Geometry } from "geojson";
import { motion, useReducedMotion } from "motion/react";
import { memo, useMemo, useRef, useState } from "react";
import { feature } from "topojson-client";
import type { Topology } from "topojson-specification";
import worldData from "world-atlas/countries-110m.json";
import { useMeta } from "@/lib/meta";
import { pctSmart, stanceFill } from "@/lib/format";
import type { World } from "@/lib/types";

type CountryFeature = Feature<Geometry, { name: string }> & { id?: string };

const features = (() => {
  const topo = worldData as unknown as Topology;
  const fc = feature(topo, topo.objects.countries) as unknown as FeatureCollection<Geometry, { name: string }>;
  return fc.features.filter((f) => (f as CountryFeature).id !== "010") as CountryFeature[]; // no Antarctica
})();

// People live on the main landmass (no US agents in Alaska), except in island nations.
const ARCHIPELAGOS = new Set(["IDN", "PHL", "JPN", "MYS", "NZL", "GBR", "FJI", "SLB", "VUT", "BHS", "CPV", "COM", "MDV", "TON", "WSM"]);
function homelandOf(f: CountryFeature, iso: string): CountryFeature {
  if (f.geometry.type !== "MultiPolygon" || ARCHIPELAGOS.has(iso)) return f;
  const polys = f.geometry.coordinates.map((c) => ({ type: "Feature", properties: f.properties, geometry: { type: "Polygon", coordinates: c } }) as CountryFeature);
  return polys.reduce((a, b) => (geoArea(b) > geoArea(a) ? b : a));
}

const W = 960;
const H = 470;

export type MapAgent = { id: string; country: string; p: number | null; voice?: string | null };

type Props = {
  world?: World | null;
  targets?: string[];
  agents?: MapAgent[];
  /** Country -> 0..1, shown as a tint (used when there are no agents). */
  values?: Record<string, number>;
  showArcs?: boolean;
  compact?: boolean;
  label?: string;
};

function seeded(id: string) {
  let h = 2166136261;
  for (let i = 0; i < id.length; i++) {
    h ^= id.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return () => {
    h += 0x6d2b79f5;
    let t = h;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function WorldMapInner({ world, targets = [], agents = [], values, showArcs = true, compact = false, label = "World map" }: Props) {
  const reduce = useReducedMotion();
  const { meta, countryName } = useMeta();
  const [hover, setHover] = useState<string | null>(null);

  const numToIso = useMemo(() => {
    const m: Record<string, string> = {};
    for (const c of meta?.countries ?? []) if (c.iso_num) m[c.iso_num] = c.iso3;
    return m;
  }, [meta]);
  const anchors = useMemo(() => {
    const m: Record<string, [number, number]> = {};
    for (const c of meta?.countries ?? []) if (c.anchor) m[c.iso3] = c.anchor;
    for (const b of meta?.blocs ?? []) if (b.anchor) m[b.id] = b.anchor;
    for (const n of world?.nodes ?? []) if (n.anchor) m[n.id] = n.anchor;
    m.global = [0, 20];
    return m;
  }, [meta, world]);
  const featureByIso = useMemo(() => {
    const m: Record<string, CountryFeature> = {};
    for (const f of features) {
      const iso = numToIso[String(f.id ?? "")];
      if (iso) m[iso] = f;
    }
    return m;
  }, [numToIso]);

  const projection = useMemo(() => geoEqualEarth().fitExtent([[6, 6], [W - 6, H - 6]], { type: "FeatureCollection", features } as FeatureCollection), []);
  const path = useMemo(() => geoPath(projection), [projection]);

  const targetSet = useMemo(() => new Set(targets.length ? targets : world?.nodes.filter((n) => n.role === "target").map((n) => n.id) ?? []), [targets, world]);
  const influencerCountries = useMemo(() => {
    const s = new Set<string>();
    for (const n of world?.nodes ?? []) {
      if (n.role !== "influencer") continue;
      for (const m of n.kind === "bloc" ? n.members ?? [] : [n.id]) if (!targetSet.has(m)) s.add(m);
    }
    return s;
  }, [world, targetSet]);

  // Positions are cached per agent so dots never jump while answers stream in.
  const cache = useRef(new Map<string, [number, number]>());
  const placed = useMemo(() => {
    if (!meta) return [];
    return agents.map((a) => {
      if (!cache.current.has(a.id)) {
        let xy: [number, number] | null = null;
        const rnd = seeded(a.id);
        const f = featureByIso[a.country] ? homelandOf(featureByIso[a.country], a.country) : null;
        if (f) {
          const [[x0, y0], [x1, y1]] = geoBounds(f);
          const span = x1 >= x0 ? x1 - x0 : x1 + 360 - x0;
          for (let i = 0; i < 50 && !xy; i++) {
            let lon = x0 + rnd() * span;
            if (lon > 180) lon -= 360;
            const pt: [number, number] = [lon, y0 + rnd() * (y1 - y0)];
            if (geoContains(f, pt)) xy = projection(pt) as [number, number];
          }
        }
        if (!xy && anchors[a.country]) {
          const rr = 0.9 * Math.sqrt(rnd());
          const t = rnd() * Math.PI * 2;
          xy = projection([anchors[a.country][0] + rr * Math.cos(t), anchors[a.country][1] + rr * Math.sin(t)]) as [number, number];
        }
        if (!xy) return { a, xy: null };
        cache.current.set(a.id, xy);
      }
      return { a, xy: cache.current.get(a.id) ?? null };
    });
  }, [agents, featureByIso, anchors, projection, meta]);

  const arcs = useMemo(() => {
    if (!world || !showArcs) return [];
    return world.links
      .map((l, i) => {
        const s = anchors[l.source];
        const t = anchors[l.target];
        if (!s || !t) return null;
        const p0 = projection(s);
        const p1 = projection(t);
        if (!p0 || !p1) return null;
        const dx = p1[0] - p0[0];
        const dy = p1[1] - p0[1];
        const dist = Math.hypot(dx, dy) || 1;
        const lift = Math.min(110, dist * 0.3);
        const cx = (p0[0] + p1[0]) / 2 - (dy / dist) * lift * 0.2;
        const cy = (p0[1] + p1[1]) / 2 - lift;
        return { key: `${l.source}-${l.target}-${l.channel}-${i}`, d: `M${p0[0]},${p0[1]} Q${cx},${cy} ${p1[0]},${p1[1]}`, link: l };
      })
      .filter(Boolean) as { key: string; d: string; link: World["links"][number] }[];
  }, [world, projection, anchors, showArcs]);

  const blocLabels = useMemo(
    () =>
      (world?.nodes ?? [])
        .filter((n) => n.role === "influencer" && n.kind === "bloc" && anchors[n.id])
        .map((n) => ({ id: n.id, xy: projection(anchors[n.id]) as [number, number] })),
    [world, anchors, projection],
  );

  const stats = useMemo(() => {
    const m = new Map<string, { n: number; sum: number }>();
    for (const { a } of placed) {
      if (a.p == null || a.voice) continue;
      const s = m.get(a.country) ?? { n: 0, sum: 0 };
      s.n += 1;
      s.sum += a.p;
      m.set(a.country, s);
    }
    return m;
  }, [placed]);

  const r = compact ? 1.8 : agents.length > 1200 ? 1.9 : agents.length > 500 ? 2.4 : 3;
  const hs = hover ? stats.get(hover) : null;

  return (
    <div className="relative w-full">
      <svg viewBox={`0 0 ${W} ${H}`} className="block h-auto w-full" role="img" aria-label={label}>
        <defs>
          <pattern id="map-hatch" width="4" height="4" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
            <rect width="4" height="4" fill="var(--land)" />
            <line x1="0" y1="0" x2="0" y2="4" stroke="var(--flow)" strokeOpacity="0.5" strokeWidth="1.3" />
          </pattern>
          <marker id="map-arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="4.5" markerHeight="4.5" orient="auto-start-reverse">
            <path d="M0 0L10 5L0 10z" fill="var(--flow)" />
          </marker>
        </defs>
        <g>
          {features.map((f, i) => {
            const iso = numToIso[String(f.id ?? "")];
            const isTarget = !!iso && targetSet.has(iso);
            const v = iso && values ? values[iso] : undefined;
            const fill = v != null ? stanceFill(v, 0.55) : isTarget ? "var(--land-target)" : iso && influencerCountries.has(iso) ? "url(#map-hatch)" : "var(--land)";
            return (
              <path
                key={`${f.id}-${i}`}
                d={path(f) || undefined}
                fill={fill}
                stroke={isTarget ? "var(--text)" : "var(--sea)"}
                strokeOpacity={isTarget ? 0.55 : 1}
                strokeWidth={isTarget ? 0.8 : 0.5}
                onMouseEnter={() => iso && setHover(iso)}
                onMouseLeave={() => setHover(null)}
              />
            );
          })}
        </g>
        <g fill="none" strokeLinecap="round">
          {arcs.map(({ key, d, link }, i) => (
            <motion.path
              key={key}
              d={d}
              stroke="var(--flow)"
              strokeOpacity={link.via?.length ? 0.4 : 0.8}
              strokeWidth={0.7 + link.strength * 2.2}
              strokeDasharray={link.via?.length ? "3 4" : undefined}
              markerEnd="url(#map-arrow)"
              initial={reduce ? false : { pathLength: 0, opacity: 0 }}
              animate={{ pathLength: 1, opacity: 1 }}
              transition={{ duration: 0.9, delay: Math.min(i * 0.05, 0.8), ease: [0.22, 1, 0.36, 1] }}
            >
              <title>{`${countryName(link.source)} on ${countryName(link.target)}, ${link.channel.replace("_", " ")}: ${link.note}`}</title>
            </motion.path>
          ))}
        </g>
        <g>
          {placed.map(({ a, xy }) =>
            xy ? (
              <circle
                key={a.id}
                cx={xy[0]}
                cy={xy[1]}
                r={a.voice ? r * 0.9 : r}
                fill={a.p == null ? "var(--faint)" : stanceFill(a.p)}
                fillOpacity={a.p == null ? 0.3 : 0.92}
                stroke={a.voice ? "var(--flow)" : "var(--surface)"}
                strokeWidth={a.voice ? 1 : 0.4}
                style={{ transition: "fill 400ms ease, fill-opacity 400ms ease" }}
              />
            ) : null,
          )}
        </g>
        {!compact &&
          blocLabels.map((b) => (
            <g key={b.id} transform={`translate(${b.xy[0]},${b.xy[1]})`} className="pointer-events-none">
              <rect x={-4 - b.id.length * 3.6} y={-10} width={8 + b.id.length * 7.2} height={19} rx={4} fill="var(--surface)" stroke="var(--flow)" strokeWidth={1} />
              <text textAnchor="middle" y={4} fontSize={11.5} fontWeight={600} fill="var(--flow)">
                {b.id}
              </text>
            </g>
          ))}
      </svg>
      {hover && !compact && (
        <div className="pointer-events-none absolute left-3 top-3 rounded-md border border-border bg-surface px-3 py-2 shadow-[0_6px_18px_rgba(0,0,0,0.1)]">
          <div className="text-[13px] font-medium">{countryName(hover)}</div>
          <div className="text-[12px] text-muted">
            {targetSet.has(hover)
              ? hs
                ? `${hs.n} people simulated, leaning ${pctSmart(hs.sum / hs.n)}`
                : "Target country"
              : influencerCountries.has(hover)
                ? "Shapes your target countries"
                : "Not in this simulation"}
          </div>
        </div>
      )}
    </div>
  );
}

export const WorldMap = memo(WorldMapInner);
