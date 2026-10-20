"use client";

import { forceCenter, forceCollide, forceLink, forceManyBody, forceSimulation, forceX, forceY, type Simulation, type SimulationLinkDatum, type SimulationNodeDatum } from "d3-force";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Avatar } from "@/components/people/Avatar";
import { Button, Card, Input, Pill, Segmented } from "@/components/ui";
import { useMeta } from "@/lib/meta";
import { cx, int, pctSmart, shortJob, stanceFill, stanceText } from "@/lib/format";
import type { KGEntity, KGKind, KGraph, KGRelation } from "@/lib/types";

/* Kinds share one fixed colour order (validated with the dataviz palette checker). The product
   itself is drawn in ink, and ideas people argue about in neutral grey: neither is a category hue. */
const GROUPS = [
  { id: "customer", label: "People and customers", color: "var(--kg-1)", kinds: ["customer"] },
  { id: "competitor", label: "Competitors and alternatives", color: "var(--kg-2)", kinds: ["competitor"] },
  { id: "company", label: "Companies", color: "var(--kg-3)", kinds: ["company"] },
  { id: "rules", label: "Rules and regulators", color: "var(--kg-4)", kinds: ["regulator", "policy"] },
  { id: "technology", label: "Technology", color: "var(--kg-5)", kinds: ["technology"] },
  { id: "place", label: "Places", color: "var(--kg-6)", kinds: ["place"] },
  { id: "event", label: "Events", color: "var(--kg-7)", kinds: ["event"] },
  { id: "concept", label: "Ideas people weigh", color: "var(--mid)", kinds: ["concept"] },
] as const;
const GROUP_OF: Record<KGKind, (typeof GROUPS)[number] | null> = Object.fromEntries(
  (["product", "competitor", "company", "regulator", "policy", "technology", "customer", "place", "event", "concept"] as KGKind[]).map((k) => [k, GROUPS.find((g) => (g.kinds as readonly string[]).includes(k)) ?? null]),
) as Record<KGKind, (typeof GROUPS)[number] | null>;
const KIND_LABEL: Record<KGKind, string> = {
  product: "The product", competitor: "Competitor", company: "Company", regulator: "Regulator", policy: "Rule or policy",
  technology: "Technology", customer: "People", place: "Place", event: "Event", concept: "Idea",
};
const colorOf = (e: KGEntity) => (e.type === "product" ? "var(--text)" : GROUP_OF[e.type]?.color ?? "var(--mid)");

type N = SimulationNodeDatum & { id: string; e: KGEntity; r: number; degree: number };
type L = SimulationLinkDatum<N> & { rel: KGRelation; key: string };
type View = { k: number; x: number; y: number };
type SizeBy = "talk" | "links";

// The layout lives in a fixed world (wide on desktop, tall on phones); the drawing uses real
// pixels so text stays crisp at any size.
const WORLD = { wide: { w: 1000, h: 640 }, tall: { w: 520, h: 760 } };

function radius(e: KGEntity, degree: number, sizeBy: SizeBy) {
  if (e.type === "product") return 24;
  const v = sizeBy === "talk" ? e.mentions?.people ?? 0 : degree;
  return Math.min(26, 7 + (sizeBy === "talk" ? 2.6 : 2.2) * Math.sqrt(v));
}

/** One entity in the side panel: what it is, what people said about it, its links and sources. */
function Inspector({ e, g, byId, runId, onPick }: { e: KGEntity; g: KGraph; byId: Map<string, KGEntity>; runId: string; onPick: (id: string) => void }) {
  const { countryName } = useMeta();
  const links = g.relations.filter((r) => r.source === e.id || r.target === e.id);
  const m = e.mentions;
  return (
    <div className="flex flex-col gap-5">
      <div>
        <div className="mb-1 flex flex-wrap items-center gap-2">
          <span className="inline-flex items-center gap-1.5 text-[12px] text-muted">
            <span className="size-2.5 rounded-full" style={{ background: colorOf(e) }} aria-hidden />
            {KIND_LABEL[e.type]}
          </span>
          {!e.public && <Pill tone="warning">Only you see this</Pill>}
        </div>
        <h3 className="text-[18px] font-semibold leading-6 text-text">{e.name}</h3>
        {e.summary && <p className="mt-1 text-[14px] leading-5 text-muted">{e.summary}</p>}
        {e.countries.length > 0 && <p className="mt-1 text-[12px] text-faint">Mainly in {e.countries.map(countryName).join(", ")}</p>}
      </div>

      <section>
        <h4 className="mb-2 text-[13px] font-medium">What people said</h4>
        {m && m.people > 0 ? (
          <>
            <div className="flex items-baseline gap-3">
              <span className="t-kpi">{int(m.people)}</span>
              <span className="text-[13px] text-muted">
                {m.people === 1 ? "person" : "people"} brought it up, leaning <span className={cx("num", stanceText(m.lean))}>{pctSmart(m.lean)}</span> on average
              </span>
            </div>
            <ul className="mt-3 flex flex-col gap-3">
              {m.samples.map((s) => (
                <li key={s.persona_id} className="flex items-start gap-2.5">
                  <Link href={`/runs/${runId}/people/${s.persona_id}`} aria-label={`Open ${s.name}'s profile`}>
                    <Avatar seed={s.persona_id} size={28} ring={stanceFill(s.p)} />
                  </Link>
                  <div className="min-w-0 text-[13px] leading-[18px]">
                    <Link href={`/runs/${runId}/people/${s.persona_id}`} className="font-medium text-text hover:underline">
                      {s.name}
                    </Link>
                    <span className="text-faint">
                      , {shortJob(s.occupation)}, {countryName(s.country)} · {s.kind === "post" ? "posted" : "answered"}
                    </span>
                    <p className="text-text">{s.text}</p>
                  </div>
                </li>
              ))}
            </ul>
          </>
        ) : (
          <p className="text-[13px] text-muted">Nobody named it in their answers or posts.</p>
        )}
      </section>

      {links.length > 0 && (
        <section>
          <h4 className="mb-2 text-[13px] font-medium">
            Connections <span className="font-normal text-faint">{links.length}</span>
          </h4>
          <ul className="flex flex-col">
            {links.map((r, i) => {
              const other = byId.get(r.source === e.id ? r.target : r.source);
              if (!other) return null;
              const out = r.source === e.id;
              return (
                <li key={i} className="border-b border-rule py-2 first:pt-0 last:border-0">
                  <button type="button" onClick={() => onPick(other.id)} className="group w-full text-left">
                    <span className="text-[13px] text-muted">
                      {out ? (
                        <>
                          {r.label} <span className="font-medium text-text group-hover:underline">{other.name}</span>
                        </>
                      ) : (
                        <>
                          <span className="font-medium text-text group-hover:underline">{other.name}</span> {r.label} this
                        </>
                      )}
                    </span>
                    {r.detail && <span className="block text-[12px] leading-4 text-faint">{r.detail}</span>}
                    {!r.public && <span className="block text-[12px] leading-4 text-[var(--pill-warning-ink)]">From your files; kept from simulated people.</span>}
                  </button>
                </li>
              );
            })}
          </ul>
        </section>
      )}

      {e.sources.length > 0 && (
        <section>
          <h4 className="mb-2 text-[13px] font-medium">Where this comes from</h4>
          <ul className="flex flex-col gap-2 text-[13px] leading-[18px]">
            {e.sources.map((s, i) => (
              <li key={i}>
                <span className="text-text">{s.statement}</span>
                {!s.public && <span className="ml-1 text-[12px] text-[var(--pill-warning-ink)]">(your files, private)</span>}
                {s.urls.map((u) => (
                  <a key={u} href={u} target="_blank" rel="noreferrer" className="ml-1 text-[12px] text-muted underline underline-offset-2 hover:text-text">
                    {new URL(u).hostname.replace(/^www\./, "")}
                  </a>
                ))}
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}

/** The map of the topic: drag, zoom, hover and select entities to see what they are and what people said. */
export function KnowledgeGraphTab({ g, runId }: { g: KGraph; runId: string }) {
  const byId = useMemo(() => new Map(g.entities.map((e) => [e.id, e])), [g]);
  const degree = useMemo(() => {
    const d = new Map<string, number>();
    for (const r of g.relations) {
      d.set(r.source, (d.get(r.source) ?? 0) + 1);
      d.set(r.target, (d.get(r.target) ?? 0) + 1);
    }
    return d;
  }, [g]);

  const [sizeBy, setSizeBy] = useState<SizeBy>("talk");
  const [hidden, setHidden] = useState<Set<string>>(new Set());
  const [selected, setSelected] = useState<string | null>(null);
  const [hover, setHover] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [labels, setLabels] = useState(false);
  const [asList, setAsList] = useState(false);
  const [view, setView] = useState<View>({ k: 1, x: 0, y: 0 });
  const [, setFrame] = useState(0);

  const svgRef = useRef<SVGSVGElement>(null);
  const boxRef = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ w: 760, h: 640 });
  const narrow = size.w < 640;
  const world = narrow ? WORLD.tall : WORLD.wide;
  useEffect(() => {
    const el = boxRef.current;
    if (!el) return;
    const ro = new ResizeObserver(([entry]) => {
      const w = Math.round(entry.contentRect.width);
      setSize({ w, h: w < 640 ? 540 : 640 });
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, [asList]);
  const simRef = useRef<Simulation<N, L> | null>(null);
  const nodesRef = useRef<N[]>([]);
  const linksRef = useRef<L[]>([]);
  const drag = useRef<{ kind: "node" | "pan"; id?: string; sx: number; sy: number; moved: boolean; vx: number; vy: number } | null>(null);

  const visible = useCallback((e: KGEntity) => e.type === "product" || !hidden.has(GROUP_OF[e.type]?.id ?? ""), [hidden]);

  // Build the simulation once per graph; filters only hide things, so positions stay put.
  useEffect(() => {
    const old = new Map(nodesRef.current.map((n) => [n.id, n]));
    const nodes: N[] = g.entities.map((e) => {
      const prev = old.get(e.id);
      const n: N = { id: e.id, e, r: radius(e, degree.get(e.id) ?? 0, "talk"), degree: degree.get(e.id) ?? 0, x: prev?.x, y: prev?.y };
      if (e.id === g.product) {
        n.fx = world.w / 2;
        n.fy = world.h / 2;
      }
      return n;
    });
    const links: L[] = g.relations.map((rel, i) => ({ source: rel.source, target: rel.target, rel, key: `${rel.source}-${rel.target}-${i}` }));
    nodesRef.current = nodes;
    linksRef.current = links;
    const sim = forceSimulation<N, L>(nodes)
      .force("link", forceLink<N, L>(links).id((n) => n.id).distance((l) => 70 + (l.source as N).r + (l.target as N).r).strength(0.5))
      .force("charge", forceManyBody<N>().strength(narrow ? -300 : -420))
      .force("collide", forceCollide<N>().radius((n) => n.r + 18))
      .force("center", forceCenter(world.w / 2, world.h / 2))
      .force("x", forceX<N>(world.w / 2).strength(narrow ? 0.12 : 0.04))
      .force("y", forceY<N>(world.h / 2).strength(narrow ? 0.03 : 0.06))
      .stop();
    for (let i = 0; i < 320; i++) sim.tick();
    sim.on("tick", () => setFrame((f) => f + 1));
    simRef.current = sim;
    setFrame((f) => f + 1);
    return () => {
      sim.stop();
    };
  }, [g, degree, narrow, world]);

  // Size by people talking or by connections.
  useEffect(() => {
    const sim = simRef.current;
    if (!sim) return;
    for (const n of nodesRef.current) n.r = radius(n.e, n.degree, sizeBy);
    sim.force("collide", forceCollide<N>().radius((n) => n.r + 18));
    sim.alpha(0.4).restart();
  }, [sizeBy]);

  const fit = useCallback(() => {
    const ns = nodesRef.current.filter((n) => visible(n.e));
    if (!ns.length) return;
    const xs = ns.map((n) => n.x ?? 0);
    const ys = ns.map((n) => n.y ?? 0);
    const pad = 70;
    const [x0, x1, y0, y1] = [Math.min(...xs) - pad, Math.max(...xs) + pad, Math.min(...ys) - pad, Math.max(...ys) + pad];
    const k = Math.min(1.8, size.w / (x1 - x0), size.h / (y1 - y0));
    setView({ k, x: size.w / 2 - (k * (x0 + x1)) / 2, y: size.h / 2 - (k * (y0 + y1)) / 2 });
  }, [visible, size]);

  // Fit on first draw and whenever the panel changes size; after that the view is yours.
  const fittedFor = useRef("");
  useEffect(() => {
    const key = `${g.product}|${size.w}|${size.h}`;
    if (fittedFor.current === key) return;
    fittedFor.current = key;
    const t = setTimeout(fit, 0);
    return () => clearTimeout(t);
  }, [g, size, fit]);

  // Pinch / ctrl + wheel zooms toward the pointer; a plain wheel still scrolls the page.
  useEffect(() => {
    const el = svgRef.current;
    if (!el) return;
    const onWheel = (ev: WheelEvent) => {
      if (!ev.ctrlKey && !ev.metaKey) return;
      ev.preventDefault();
      const rect = el.getBoundingClientRect();
      const px = ev.clientX - rect.left;
      const py = ev.clientY - rect.top;
      setView((v) => {
        const k = Math.max(0.3, Math.min(4, v.k * Math.exp(-ev.deltaY * 0.0025)));
        return { k, x: px - ((px - v.x) * k) / v.k, y: py - ((py - v.y) * k) / v.k };
      });
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, []);

  const zoomBy = (f: number) =>
    setView((v) => {
      const k = Math.max(0.3, Math.min(4, v.k * f));
      return { k, x: size.w / 2 - ((size.w / 2 - v.x) * k) / v.k, y: size.h / 2 - ((size.h / 2 - v.y) * k) / v.k };
    });

  const toWorld = (ev: React.PointerEvent) => {
    const rect = svgRef.current!.getBoundingClientRect();
    const px = ev.clientX - rect.left;
    const py = ev.clientY - rect.top;
    return { x: (px - view.x) / view.k, y: (py - view.y) / view.k, px, py };
  };

  const onNodeDown = (ev: React.PointerEvent, id: string) => {
    ev.stopPropagation();
    (ev.target as Element).setPointerCapture?.(ev.pointerId);
    const p = toWorld(ev);
    drag.current = { kind: "node", id, sx: p.px, sy: p.py, moved: false, vx: view.x, vy: view.y };
  };
  const onBgDown = (ev: React.PointerEvent) => {
    (ev.target as Element).setPointerCapture?.(ev.pointerId);
    const p = toWorld(ev);
    drag.current = { kind: "pan", sx: p.px, sy: p.py, moved: false, vx: view.x, vy: view.y };
  };
  const onMove = (ev: React.PointerEvent) => {
    const d = drag.current;
    if (!d) return;
    const p = toWorld(ev);
    if (Math.hypot(p.px - d.sx, p.py - d.sy) > 4) d.moved = true;
    if (!d.moved) return;
    if (d.kind === "pan") {
      setView((v) => ({ ...v, x: d.vx + (p.px - d.sx), y: d.vy + (p.py - d.sy) }));
    } else {
      const n = nodesRef.current.find((x) => x.id === d.id);
      if (!n) return;
      n.fx = p.x;
      n.fy = p.y;
      simRef.current?.alphaTarget(0.25).restart();
    }
  };
  const onUp = () => {
    const d = drag.current;
    drag.current = null;
    if (!d) return;
    if (d.kind === "node") {
      simRef.current?.alphaTarget(0);
      const n = nodesRef.current.find((x) => x.id === d.id);
      // A dragged node stays where you drop it; the product is always pinned.
      if (!d.moved) setSelected((s) => (s === d.id ? null : d.id!));
      else if (n && n.id !== g.product) {
        n.fx = n.x;
        n.fy = n.y;
      }
    } else if (!d.moved) setSelected(null);
  };

  const focus = hover ?? selected;
  const near = useMemo(() => {
    if (!focus) return null;
    const s = new Set([focus]);
    for (const r of g.relations) {
      if (r.source === focus) s.add(r.target);
      if (r.target === focus) s.add(r.source);
    }
    return s;
  }, [focus, g]);
  const q = query.trim().toLowerCase();
  const matches = useMemo(
    () => (q ? new Set(g.entities.filter((e) => e.name.toLowerCase().includes(q) || e.aliases.some((a) => a.toLowerCase().includes(q))).map((e) => e.id)) : null),
    [q, g],
  );

  const nodes = nodesRef.current.filter((n) => visible(n.e));
  const shown = new Set(nodes.map((n) => n.id));
  const links = linksRef.current.filter((l) => shown.has((l.source as N).id) && shown.has((l.target as N).id));
  const bigOnes = new Set([...nodes].sort((a, b) => b.r - a.r).slice(0, 10).map((n) => n.id));
  const showLabel = (n: N) => labels || view.k >= 1.35 || n.id === g.product || bigOnes.has(n.id) || (near?.has(n.id) ?? false) || (matches?.has(n.id) ?? false);
  const dim = (id: string) => (near && !near.has(id)) || (matches && !matches.has(id));

  const counts = useMemo(() => Object.fromEntries(GROUPS.map((gr) => [gr.id, g.entities.filter((e) => GROUP_OF[e.type]?.id === gr.id).length])), [g]);
  const talked = useMemo(() => [...g.entities].filter((e) => (e.mentions?.people ?? 0) > 0).sort((a, b) => (b.mentions?.people ?? 0) - (a.mentions?.people ?? 0)), [g]);
  const sel = selected ? byId.get(selected) : null;
  const hov = hover ? nodesRef.current.find((n) => n.id === hover) : null;

  const pick = (id: string) => {
    setSelected(id);
    const e = byId.get(id);
    const grp = e ? GROUP_OF[e.type]?.id : null;
    if (grp && hidden.has(grp)) setHidden((h) => new Set([...h].filter((x) => x !== grp)));
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-3">
        <div className="min-w-0 flex-1 basis-80">
          <h2 className="t-section">The topic, mapped</h2>
          <p className="text-[13px] leading-[18px] text-muted">
            {int(g.entities.length)} things and {int(g.relations.length)} links from your question, your files and the research. {int(talked.length)} came up in what people said. Select anything to see what it is and who talked about it.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Input aria-label="Find in the graph" placeholder="Find…" value={query} onChange={(ev) => setQuery(ev.target.value)} onKeyDown={(ev) => ev.key === "Enter" && matches?.size && pick([...matches][0])} className="w-40" />
          <Segmented
            label="Size by"
            value={sizeBy}
            onChange={setSizeBy}
            options={[
              { value: "talk", label: "People talking" },
              { value: "links", label: "Connections" },
            ]}
          />
          <Button size="sm" variant="ghost" onClick={() => setAsList(!asList)} aria-pressed={asList}>
            {asList ? "Show the graph" : "Show as a list"}
          </Button>
        </div>
      </div>

      <div className="flex flex-wrap gap-1.5" role="group" aria-label="Show or hide kinds of things">
        <span className="inline-flex min-h-8 items-center gap-1.5 rounded-md border border-border px-2.5 text-[13px] text-text">
          <span className="size-2.5 rounded-full ring-2 ring-[var(--text)] ring-offset-1 ring-offset-[var(--surface)]" style={{ background: "var(--text)" }} aria-hidden />
          The product
        </span>
        {GROUPS.filter((gr) => counts[gr.id]).map((gr) => {
          const off = hidden.has(gr.id);
          return (
            <button
              key={gr.id}
              type="button"
              aria-pressed={!off}
              onClick={() => setHidden((h) => (off ? new Set([...h].filter((x) => x !== gr.id)) : new Set([...h, gr.id])))}
              className={cx("inline-flex min-h-8 items-center gap-1.5 rounded-md border px-2.5 text-[13px] transition-colors", off ? "border-border text-faint line-through" : "border-control text-text hover:bg-raised")}
              title={off ? `Show ${gr.label.toLowerCase()}` : `Hide ${gr.label.toLowerCase()}`}
            >
              <span className="size-2.5 rounded-full" style={{ background: off ? "var(--control)" : gr.color }} aria-hidden />
              {gr.label}
              <span className="num text-faint">{counts[gr.id]}</span>
            </button>
          );
        })}
      </div>

      <div className="grid grid-cols-1 items-start gap-6 lg:grid-cols-12">
        <Card pad={false} className="relative overflow-hidden lg:col-span-8">
          {asList ? (
            <div className="scroll-thin max-h-[640px] overflow-auto p-5">
              <table className="w-full min-w-[520px] text-[14px]">
                <thead>
                  <tr className="border-b border-border text-left text-[12px] text-faint">
                    <th className="pb-2 font-normal">Name</th>
                    <th className="pb-2 font-normal">Kind</th>
                    <th className="pb-2 text-right font-normal">People who brought it up</th>
                    <th className="pb-2 text-right font-normal">Leaning</th>
                    <th className="pb-2 text-right font-normal">Links</th>
                  </tr>
                </thead>
                <tbody>
                  {[...g.entities].sort((a, b) => (b.mentions?.people ?? 0) - (a.mentions?.people ?? 0) || a.name.localeCompare(b.name)).map((e) => (
                    <tr key={e.id} className={cx("border-b border-rule last:border-0", selected === e.id && "bg-raised")}>
                      <td className="py-2">
                        <button type="button" onClick={() => pick(e.id)} className="inline-flex items-center gap-2 text-left hover:underline">
                          <span className="size-2.5 shrink-0 rounded-full" style={{ background: colorOf(e) }} aria-hidden />
                          {e.name}
                        </button>
                      </td>
                      <td className="py-2 text-muted">{KIND_LABEL[e.type]}</td>
                      <td className="num py-2 text-right">{int(e.mentions?.people ?? 0)}</td>
                      <td className={cx("num py-2 text-right", stanceText(e.mentions?.lean ?? null))}>{e.mentions?.people ? pctSmart(e.mentions.lean) : "–"}</td>
                      <td className="num py-2 text-right text-muted">{degree.get(e.id) ?? 0}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <>
              <div ref={boxRef} className="w-full">
              <svg
                ref={svgRef}
                width={size.w}
                height={size.h}
                viewBox={`0 0 ${size.w} ${size.h}`}
                className="block w-full cursor-grab touch-none select-none active:cursor-grabbing"
                onPointerDown={onBgDown}
                onPointerMove={onMove}
                onPointerUp={onUp}
                onPointerCancel={onUp}
                role="img"
                aria-label={`Knowledge graph with ${g.entities.length} entities. Use the list view for a table.`}
              >
                <defs>
                  <marker id="kg-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse">
                    <path d="M0 0L10 5L0 10z" fill="var(--mid)" />
                  </marker>
                  <marker id="kg-arrow-on" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse">
                    <path d="M0 0L10 5L0 10z" fill="var(--text)" />
                  </marker>
                </defs>
                <g transform={`translate(${view.x},${view.y}) scale(${view.k})`}>
                  {links.map((l) => {
                    const s = l.source as N;
                    const t = l.target as N;
                    const on = !!focus && (s.id === focus || t.id === focus);
                    const faded = !!near && !on;
                    const dx = (t.x ?? 0) - (s.x ?? 0);
                    const dy = (t.y ?? 0) - (s.y ?? 0);
                    const len = Math.hypot(dx, dy) || 1;
                    const x1 = (s.x ?? 0) + (dx / len) * s.r;
                    const y1 = (s.y ?? 0) + (dy / len) * s.r;
                    const x2 = (t.x ?? 0) - (dx / len) * (t.r + 3);
                    const y2 = (t.y ?? 0) - (dy / len) * (t.r + 3);
                    const mx = (x1 + x2) / 2;
                    const my = (y1 + y2) / 2;
                    return (
                      <g key={l.key} opacity={faded ? 0.12 : 1}>
                        <line
                          x1={x1}
                          y1={y1}
                          x2={x2}
                          y2={y2}
                          stroke={on ? "var(--text)" : "var(--mid)"}
                          strokeWidth={(on ? 1.75 : 1) / view.k}
                          strokeDasharray={l.rel.public ? undefined : "4 3"}
                          markerEnd={`url(#${on ? "kg-arrow-on" : "kg-arrow"})`}
                        />
                        {(on || (labels && !near)) && (
                          <text x={mx} y={my - 4} textAnchor="middle" className="pointer-events-none fill-[var(--muted)]" style={{ paintOrder: "stroke", stroke: "var(--surface)", strokeWidth: 4 / view.k, strokeLinejoin: "round" }} fontSize={12 / view.k}>
                            {l.rel.label}
                          </text>
                        )}
                      </g>
                    );
                  })}
                  {nodes.map((n) => {
                    const isSel = selected === n.id;
                    const faded = dim(n.id);
                    return (
                      <g
                        key={n.id}
                        transform={`translate(${n.x ?? 0},${n.y ?? 0})`}
                        opacity={faded ? 0.18 : 1}
                        className="cursor-pointer outline-none"
                        onPointerDown={(ev) => onNodeDown(ev, n.id)}
                        onPointerEnter={() => setHover(n.id)}
                        onPointerLeave={() => setHover((h) => (h === n.id ? null : h))}
                        tabIndex={0}
                        role="button"
                        aria-label={`${n.e.name}, ${KIND_LABEL[n.e.type]}${n.e.mentions?.people ? `, ${n.e.mentions.people} people brought it up` : ""}`}
                        aria-pressed={isSel}
                        onKeyDown={(ev) => {
                          if (ev.key === "Enter" || ev.key === " ") {
                            ev.preventDefault();
                            setSelected(isSel ? null : n.id);
                          }
                        }}
                        onFocus={() => setHover(n.id)}
                        onBlur={() => setHover((h) => (h === n.id ? null : h))}
                      >
                        {/* Bigger invisible hit area than the mark. */}
                        <circle r={Math.max(n.r + 8, 16)} fill="transparent" />
                        {(isSel || hover === n.id) && <circle r={n.r + 6 / view.k} fill="none" stroke="var(--text)" strokeWidth={(isSel ? 2 : 1) / view.k} />}
                        {n.e.type === "product" ? (
                          <>
                            <circle r={n.r} fill="var(--text)" />
                            <circle r={n.r * 0.32} fill="var(--surface)" />
                          </>
                        ) : (
                          <>
                            <circle r={n.r} fill={`color-mix(in srgb, ${colorOf(n.e)} 22%, var(--surface))`} stroke={colorOf(n.e)} strokeWidth={2 / view.k} strokeDasharray={n.e.public ? undefined : `${4 / view.k} ${3 / view.k}`} />
                            <circle r={Math.max(3, n.r * 0.28)} fill={colorOf(n.e)} />
                          </>
                        )}
                        {showLabel(n) && (
                          <text
                            y={n.r + 16 / view.k}
                            textAnchor="middle"
                            className={cx("pointer-events-none fill-[var(--text)]", n.e.type === "product" || isSel ? "font-semibold" : "font-medium")}
                            fontSize={(n.e.type === "product" ? 15 : 13) / view.k}
                            style={{ paintOrder: "stroke", stroke: "var(--surface)", strokeWidth: 4 / view.k, strokeLinejoin: "round" }}
                          >
                            {n.e.name.length > 28 ? `${n.e.name.slice(0, 26)}…` : n.e.name}
                          </text>
                        )}
                      </g>
                    );
                  })}
                </g>
              </svg>
              </div>

              {hov && !drag.current && (
                <div
                  className="pointer-events-none absolute z-10 max-w-[260px] rounded-md border border-border bg-surface px-3 py-2 text-[12px] leading-4 shadow-[0_8px_24px_rgba(0,0,0,0.12)]"
                  style={{
                    left: (hov.x ?? 0) * view.k + view.x,
                    top: (hov.y ?? 0) * view.k + view.y,
                    transform: `translate(-50%, calc(-100% - ${hov.r * view.k + 12}px))`,
                  }}
                >
                  <div className="font-medium text-text">{hov.e.name}</div>
                  <div className="text-muted">
                    {KIND_LABEL[hov.e.type]}, {degree.get(hov.id) ?? 0} {degree.get(hov.id) === 1 ? "link" : "links"}
                  </div>
                  {hov.e.mentions?.people ? (
                    <div className="text-muted">
                      {hov.e.mentions.people} brought it up, leaning <span className={stanceText(hov.e.mentions.lean)}>{pctSmart(hov.e.mentions.lean)}</span>
                    </div>
                  ) : null}
                </div>
              )}

              <div className="absolute bottom-3 left-3 flex items-center gap-1 rounded-md border border-border bg-surface p-1">
                <Button size="sm" variant="ghost" onClick={() => zoomBy(1.25)} aria-label="Zoom in">
                  +
                </Button>
                <Button size="sm" variant="ghost" onClick={() => zoomBy(0.8)} aria-label="Zoom out">
                  −
                </Button>
                <Button size="sm" variant="ghost" onClick={fit}>
                  Fit
                </Button>
                <Button size="sm" variant="ghost" onClick={() => setLabels(!labels)} aria-pressed={labels}>
                  {labels ? "Fewer labels" : "All labels"}
                </Button>
              </div>
              <p className="pointer-events-none absolute bottom-4 right-4 hidden text-[12px] text-faint md:block">Drag to move. Pinch or Ctrl + scroll to zoom. Dashed: from your files only.</p>
            </>
          )}
        </Card>

        <Card className="lg:col-span-4">
          {sel ? (
            <>
              <div className="mb-3 flex justify-end">
                <Button size="sm" variant="ghost" onClick={() => setSelected(null)}>
                  Back to overview
                </Button>
              </div>
              <Inspector e={sel} g={g} byId={byId} runId={runId} onPick={pick} />
            </>
          ) : (
            <div className="flex flex-col gap-4">
              <div>
                <h3 className="text-[16px] font-medium">Most talked about</h3>
                <p className="text-[13px] text-muted">What people named in their answers and posts, and how those people leaned.</p>
              </div>
              {talked.length ? (
                <ul className="flex flex-col">
                  {talked.slice(0, 12).map((e) => {
                    const max = talked[0].mentions?.people ?? 1;
                    return (
                      <li key={e.id} className="border-b border-rule last:border-0">
                        <button type="button" onClick={() => pick(e.id)} onPointerEnter={() => setHover(e.id)} onPointerLeave={() => setHover(null)} className="w-full py-2.5 text-left">
                          <span className="flex items-baseline justify-between gap-3">
                            <span className="inline-flex min-w-0 items-center gap-2 text-[14px] text-text">
                              <span className="size-2.5 shrink-0 rounded-full" style={{ background: colorOf(e) }} aria-hidden />
                              <span className="truncate">{e.name}</span>
                            </span>
                            <span className="num shrink-0 text-[13px] text-muted">
                              {int(e.mentions?.people ?? 0)} <span className={stanceText(e.mentions?.lean ?? null)}>{pctSmart(e.mentions?.lean)}</span>
                            </span>
                          </span>
                          <span className="mt-1.5 block h-1 rounded-full bg-raised">
                            <span className="block h-full rounded-full bg-text/40" style={{ width: `${((e.mentions?.people ?? 0) / max) * 100}%` }} />
                          </span>
                        </button>
                      </li>
                    );
                  })}
                </ul>
              ) : (
                <p className="text-[13px] text-muted">Nobody named anything in the graph. Select a node to explore it anyway.</p>
              )}
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
