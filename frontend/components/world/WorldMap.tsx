"use client";

import { geoArea, geoBounds, geoContains, geoEqualEarth, geoPath } from "d3-geo";
import type { Feature, FeatureCollection, Geometry } from "geojson";
import { motion, useReducedMotion } from "motion/react";
import { memo, useMemo, useRef, useState } from "react";
import { feature } from "topojson-client";
import type { Topology } from "topojson-specification";
import worldData from "world-atlas/countries-110m.json";
import type { World } from "@/lib/types";
import { pctSmart, stanceMix } from "@/lib/format";
import { ANCHOR, ISO_NUM, seeded } from "./geo";

type CountryFeature = Feature<Geometry, { name: string }> & { id?: string };

const NUM_TO_ISO = Object.fromEntries(Object.entries(ISO_NUM).map(([k, v]) => [v, k]));

const countriesGeo = (() => {
  const topo = worldData as unknown as Topology;
  const fc = feature(topo, topo.objects.countries) as unknown as FeatureCollection<Geometry, { name: string }>;
  return fc.features.filter((f) => (f as CountryFeature).id !== "010") as CountryFeature[]; // drop Antarctica
})();

const featureByIso: Record<string, CountryFeature> = {};
for (const f of countriesGeo) {
  const iso = NUM_TO_ISO[String(f.id ?? "")];
  if (iso) featureByIso[iso] = f;
}

// Where people live: the main landmass, so US agents don't end up in Alaska.
// Archipelago countries keep every island.
const ARCHIPELAGOS = new Set(["IDN", "PHL", "JPN", "MYS", "NZL", "GBR"]);
const homeland: Record<string, CountryFeature> = {};
for (const [iso, f] of Object.entries(featureByIso)) {
  if (f.geometry.type !== "MultiPolygon" || ARCHIPELAGOS.has(iso)) {
    homeland[iso] = f;
    continue;
  }
  const polys = f.geometry.coordinates.map((c) => ({ type: "Feature", properties: f.properties, geometry: { type: "Polygon", coordinates: c } }) as CountryFeature);
  homeland[iso] = polys.reduce((a, b) => (geoArea(b) > geoArea(a) ? b : a));
}

const W = 960;
const H = 470;

export type MapAgent = { id: string; country: string; p: number | null; voice?: string | null };

type Props = {
  world?: World | null;
  targets?: string[];
  agents?: MapAgent[];
  /** Country -> value (0..1), shown as a tint when there are no agents. */
  values?: Record<string, number>;
  height?: number;
  showArcs?: boolean;
  compact?: boolean;
  onCountry?: (iso: string) => void;
  focus?: string | null;
};

function placeAgent(a: MapAgent, members: Record<string, string[]>): [number, number] | null {
  const rnd = seeded(a.id);
  const iso = a.country;
  const f = homeland[iso];
  if (f) {
    const [[x0, y0], [x1, y1]] = geoBounds(f);
    // Russia & co. wrap around; keep it simple and bounded.
    const lonMin = x1 < x0 ? x0 - 360 : x0;
    for (let i = 0; i < 40; i++) {
      const lon = lonMin + rnd() * ((x1 < x0 ? x1 + 360 : x1) - lonMin);
      const lat = y0 + rnd() * (y1 - y0);
      const pt: [number, number] = [lon > 180 ? lon - 360 : lon, lat];
      if (geoContains(f, pt)) return pt;
    }
  }
  const anchor = ANCHOR[iso] || (members[iso] ? ANCHOR[members[iso][0]] : null);
  if (!anchor) return null;
  const r = 1.2 * Math.sqrt(rnd());
  const t = rnd() * Math.PI * 2;
  return [anchor[0] + r * Math.cos(t), anchor[1] + r * Math.sin(t)];
}

function WorldMapInner({ world, targets = [], agents = [], values, height, showArcs = true, compact = false, onCountry, focus }: Props) {
  const reduce = useReducedMotion();
  const [hover, setHover] = useState<string | null>(null);
  const projection = useMemo(() => geoEqualEarth().fitExtent([[8, 8], [W - 8, H - 8]], { type: "FeatureCollection", features: countriesGeo } as FeatureCollection), []);
  const path = useMemo(() => geoPath(projection), [projection]);

  const targetSet = useMemo(() => new Set(targets.length ? targets : world?.nodes.filter((n) => n.role === "target").map((n) => n.id) ?? []), [targets, world]);
  const influencers = useMemo(() => world?.nodes.filter((n) => n.role === "influencer") ?? [], [world]);
  const influencerCountries = useMemo(() => {
    const s = new Map<string, number>();
    for (const n of influencers) {
      const list = n.kind === "bloc" ? n.members ?? [] : [n.id];
      for (const m of list) if (!targetSet.has(m)) s.set(m, Math.max(s.get(m) ?? 0, n.strength ?? 0.3));
    }
    return s;
  }, [influencers, targetSet]);

  const blocMembers = useMemo(() => {
    const m: Record<string, string[]> = {};
    for (const n of influencers) if (n.kind === "bloc") m[n.id] = n.members ?? [];
    return m;
  }, [influencers]);

  // Agent positions are cached per id so dots don't jump when results stream in.
  const posCache = useRef(new Map<string, [number, number] | null>());
  const placed = useMemo(() => {
    return agents.map((a) => {
      if (!posCache.current.has(a.id)) {
        const geo = placeAgent(a, blocMembers);
        posCache.current.set(a.id, geo ? (projection(geo) as [number, number] | null) : null);
      }
      return { a, xy: posCache.current.get(a.id) };
    });
  }, [agents, projection, blocMembers]);

  const arcs = useMemo(() => {
    if (!world || !showArcs) return [];
    return world.links
      .filter((l) => targetSet.has(l.target) || l.via.length)
      .map((l, i) => {
        const s = ANCHOR[l.source];
        const t = ANCHOR[l.target];
        if (!s || !t) return null;
        const p0 = projection(s);
        const p1 = projection(t);
        if (!p0 || !p1) return null;
        const mx = (p0[0] + p1[0]) / 2;
        const my = (p0[1] + p1[1]) / 2;
        const dx = p1[0] - p0[0];
        const dy = p1[1] - p0[1];
        const dist = Math.hypot(dx, dy) || 1;
        const lift = Math.min(120, dist * 0.32);
        const cx = mx - (dy / dist) * lift * 0.25;
        const cy = my - lift;
        return { key: `${l.source}-${l.target}-${l.channel}-${i}`, d: `M${p0[0]},${p0[1]} Q${cx},${cy} ${p1[0]},${p1[1]}`, link: l, p0, p1 };
      })
      .filter(Boolean) as { key: string; d: string; link: World["links"][number]; p0: [number, number]; p1: [number, number] }[];
  }, [world, projection, targetSet, showArcs]);

  const blocLabels = useMemo(
    () =>
      influencers
        .filter((n) => n.kind === "bloc" && ANCHOR[n.id])
        .map((n) => ({ id: n.id, name: n.name, xy: projection(ANCHOR[n.id]) as [number, number] })),
    [influencers, projection],
  );

  const countryStats = useMemo(() => {
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

  const hoverIso = hover;
  const hoverName = hoverIso ? (featureByIso[hoverIso]?.properties?.name ?? hoverIso) : null;
  const hoverStat = hoverIso ? countryStats.get(hoverIso) : null;
  const dotR = compact ? 1.9 : agents.length > 900 ? 2.1 : agents.length > 400 ? 2.6 : 3.2;

  return (
    <div className="relative w-full" style={height ? { height } : undefined}>
      <svg viewBox={`0 0 ${W} ${H}`} className="h-full w-full" role="img" aria-label="World map of simulated people and influence">
        <defs>
          <pattern id="hatch" width="5" height="5" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
            <rect width="5" height="5" fill="var(--land)" />
            <line x1="0" y1="0" x2="0" y2="5" stroke="var(--iris)" strokeOpacity="0.45" strokeWidth="1.6" />
          </pattern>
          <marker id="arrow" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse">
            <path d="M 0 0 L 10 5 L 0 10 z" fill="var(--iris)" />
          </marker>
        </defs>

        <g>
          {countriesGeo.map((f, i) => {
            const iso = NUM_TO_ISO[String(f.id ?? "")];
            const isTarget = iso && targetSet.has(iso);
            const infl = iso ? influencerCountries.get(iso) : undefined;
            const v = iso && values ? values[iso] : undefined;
            const fill = v != null ? stanceMix(v) : isTarget ? "var(--land-target)" : infl ? "url(#hatch)" : "var(--land)";
            return (
              <path
                key={`${f.id}-${i}`}
                d={path(f) || undefined}
                fill={fill}
                fillOpacity={v != null ? 0.55 : 1}
                stroke={isTarget ? "var(--iris)" : "var(--fog)"}
                strokeWidth={isTarget ? 1.1 : 0.5}
                strokeOpacity={isTarget ? (focus && focus !== iso ? 0.3 : 0.9) : 1}
                onMouseEnter={() => iso && setHover(iso)}
                onMouseLeave={() => setHover(null)}
                onClick={() => iso && onCountry?.(iso)}
                className={iso && onCountry ? "cursor-pointer" : undefined}
              />
            );
          })}
        </g>

        <g fill="none" strokeLinecap="round">
          {arcs.map(({ key, d, link }, i) => (
            <motion.path
              key={key}
              d={d}
              stroke="var(--iris)"
              strokeOpacity={link.via.length ? 0.35 : 0.75}
              strokeWidth={0.8 + link.strength * 2.6}
              strokeDasharray={link.via.length ? "3 4" : undefined}
              markerEnd="url(#arrow)"
              initial={reduce ? false : { pathLength: 0, opacity: 0 }}
              animate={{ pathLength: 1, opacity: 1 }}
              transition={{ duration: 1.1, delay: 0.15 + i * 0.07, ease: [0.22, 1, 0.36, 1] }}
            >
              <title>{`${link.source} to ${link.target}, ${link.channel.replace("_", " ")}: ${link.note}`}</title>
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
                r={a.voice ? dotR * 0.85 : dotR}
                fill={a.p == null ? "var(--ink-3)" : stanceMix(a.p)}
                fillOpacity={a.p == null ? 0.35 : 0.95}
                stroke={a.voice ? "var(--iris)" : "none"}
                strokeWidth={a.voice ? 0.9 : 0}
                style={{ transition: "fill 500ms ease, fill-opacity 500ms ease" }}
              />
            ) : null,
          )}
        </g>

        {!compact && (
          <g className="pointer-events-none">
            {blocLabels.map((b) => (
              <g key={b.id} transform={`translate(${b.xy[0]},${b.xy[1]})`}>
                <rect x={-22} y={-11} width={44} height={20} rx={10} fill="var(--panel)" stroke="var(--iris)" strokeWidth={1} />
                <text textAnchor="middle" y={4} fontSize={11} fontWeight={600} fill="var(--iris-ink)">
                  {b.id}
                </text>
              </g>
            ))}
          </g>
        )}
      </svg>

      {hoverIso && !compact && (
        <div className="pointer-events-none absolute left-3 top-3 rounded-lg border border-line bg-panel px-3 py-2 shadow-lift">
          <div className="t-3">{hoverName}</div>
          <div className="t-tiny text-ink-2">
            {targetSet.has(hoverIso)
              ? hoverStat
                ? `${hoverStat.n} people, leaning ${pctSmart(hoverStat.sum / hoverStat.n)}`
                : "Target market"
              : influencerCountries.has(hoverIso)
                ? "Shapes what happens in your markets"
                : "Not simulated"}
          </div>
        </div>
      )}
    </div>
  );
}

export const WorldMap = memo(WorldMapInner);
