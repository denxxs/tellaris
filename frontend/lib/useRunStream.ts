"use client";

import { useEffect, useReducer, useRef } from "react";
import { API, api } from "./api";
import type { FactSheet, FeedItem, PersonaLite, Report, Results, Run, Spec, StreamEvent, UploadedFile, Usage, World } from "./types";

export type StageState = { stage: string; label: string; status: "pending" | "start" | "done" | "skipped"; progress?: number; detail?: Record<string, unknown> };

export type LiveReaction = { id: string; p: number; choice: string; attention: string; quote: string; model: string; run: number };

export type LiveState = {
  run: Run | null;
  spec: Spec | null;
  world: World | null;
  research: FactSheet | null;
  personas: Record<string, PersonaLite>;
  order: string[];
  scores: Record<string, number[]>;
  ticker: (LiveReaction & { seq: number })[];
  stages: Record<string, StageState>;
  logs: { message: string; level: string; ts: number }[];
  interim: { headline: Results["headline"]; by_country: Results["by_country"] } | null;
  committees: { id: string; country: string; company_type: string; decision: { decision: string; probability_of_purchase: number } | null }[];
  diffusion: { round: number; calibrated: number; changed: number; news: string | null; posts?: number; replies?: number }[];
  feed: FeedItem[];
  files: UploadedFile[];
  results: Results | null;
  report: Report | null;
  usage: Usage | null;
  status: "connecting" | "live" | "done" | "failed" | "cancelled";
  error: string | null;
  progress: number;
};

const initial: LiveState = {
  run: null, spec: null, world: null, research: null, personas: {}, order: [], scores: {}, ticker: [], stages: {}, logs: [],
  interim: null, committees: [], diffusion: [], feed: [], files: [], results: null, report: null, usage: null, status: "connecting", error: null, progress: 0,
};

type Action = { type: "run"; run: Run } | { type: "events"; events: StreamEvent[] } | { type: "status"; status: LiveState["status"]; error?: string };

function apply(s: LiveState, e: StreamEvent): LiveState {
  const d = e.data as never;
  switch (e.type) {
    case "stage": {
      const st = d as StageState & { progress: number };
      return { ...s, stages: { ...s.stages, [st.stage]: { ...st, detail: st as unknown as Record<string, unknown> } }, progress: Math.max(s.progress, st.progress ?? 0) };
    }
    case "scenario":
      return { ...s, spec: d as Spec };
    case "research":
      return { ...s, research: d as FactSheet };
    case "world":
      return { ...s, world: d as World };
    case "personas": {
      const list = d as PersonaLite[];
      const personas = { ...s.personas };
      const order = [...s.order];
      for (const p of list) {
        if (!personas[p.id]) order.push(p.id);
        personas[p.id] = p;
      }
      return { ...s, personas, order };
    }
    case "reactions": {
      const list = d as LiveReaction[];
      const scores = { ...s.scores };
      for (const r of list) scores[r.id] = [...(scores[r.id] || []), r.p];
      const fresh = list.filter((r) => r.quote).slice(-6).map((r) => ({ ...r, seq: e.seq }));
      return { ...s, scores, ticker: [...fresh.reverse(), ...s.ticker].slice(0, 40) };
    }
    case "interim":
      return { ...s, interim: d };
    case "committee":
      return { ...s, committees: [...s.committees, d] };
    case "diffusion_round":
      return { ...s, diffusion: [...s.diffusion, d] };
    case "feed":
      return { ...s, feed: [...s.feed, ...(d as FeedItem[])] };
    case "files":
      return { ...s, files: d as UploadedFile[] };
    case "results":
      return { ...s, results: d as Results };
    case "report":
      return { ...s, report: d as Report };
    case "log":
      return { ...s, logs: [...s.logs, { ...(d as { message: string; level: string }), ts: e.ts }].slice(-50) };
    case "done":
      return { ...s, status: "done", usage: (d as { usage: Usage }).usage, progress: 1 };
    case "error":
      return { ...s, status: (d as { message: string }).message === "Cancelled" ? "cancelled" : "failed", error: (d as { message: string }).message };
    default:
      return s;
  }
}

function reducer(s: LiveState, a: Action): LiveState {
  if (a.type === "run") {
    const r = a.run;
    return {
      ...s,
      run: r,
      spec: s.spec ?? r.spec,
      world: s.world ?? r.world,
      research: s.research ?? r.research,
      results: s.results ?? r.results,
      report: s.report ?? r.report,
      usage: s.usage ?? r.usage,
      error: s.error ?? r.error,
      progress: Math.max(s.progress, r.progress ?? 0),
      status: r.status === "done" ? "done" : r.status === "failed" ? "failed" : r.status === "cancelled" ? "cancelled" : s.status,
    };
  }
  if (a.type === "status") return { ...s, status: a.status, error: a.error ?? s.error };
  let next = s;
  for (const e of a.events) next = apply(next, e);
  if (next.status === "connecting") next = { ...next, status: "live" };
  return next;
}

/** Replays a run's stored events, then follows it live. Works for finished runs too. */
export function useRunStream(id: string) {
  const [state, dispatch] = useReducer(reducer, initial);
  const lastSeq = useRef(-1);

  useEffect(() => {
    let closed = false;
    let es: EventSource | null = null;
    let buffer: StreamEvent[] = [];
    let raf = 0;

    const flush = () => {
      raf = 0;
      if (buffer.length) {
        const batch = buffer;
        buffer = [];
        dispatch({ type: "events", events: batch });
      }
    };

    api.run(id).then((r) => !closed && dispatch({ type: "run", run: r })).catch((e) => dispatch({ type: "status", status: "failed", error: String(e.message || e) }));

    const connect = () => {
      es = new EventSource(`${API}/api/runs/${id}/events?after=${lastSeq.current}`);
      es.onmessage = (m) => {
        const evt = JSON.parse(m.data) as StreamEvent;
        if (evt.seq <= lastSeq.current) return;
        lastSeq.current = evt.seq;
        buffer.push(evt);
        if (!raf) raf = requestAnimationFrame(flush);
      };
      es.addEventListener("end", () => {
        es?.close();
        flush();
        api.run(id).then((r) => !closed && dispatch({ type: "run", run: r })).catch(() => {});
      });
      es.onerror = () => {
        es?.close();
        if (!closed) setTimeout(() => !closed && connect(), 1500);
      };
    };
    connect();
    return () => {
      closed = true;
      es?.close();
      if (raf) cancelAnimationFrame(raf);
    };
  }, [id]);

  return state;
}
