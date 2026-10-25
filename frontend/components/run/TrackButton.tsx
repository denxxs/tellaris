"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { Button, Input } from "@/components/ui";
import { api, type Prediction } from "@/lib/api";

const inMonths = (m: number) => {
  const d = new Date();
  d.setMonth(d.getMonth() + m);
  return d.toISOString().slice(0, 10);
};
const tomorrow = () => new Date(Date.now() + 86400000).toISOString().slice(0, 10);
const day = (iso: string) => new Date(`${iso}T00:00:00`).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });

/** Freeze this run's answer as a prediction to score once the real outcome is known. */
export function TrackButton({ runId, horizonMonths, demo = false }: { runId: string; horizonMonths?: number; demo?: boolean }) {
  const [preds, setPreds] = useState<Prediction[] | null>(null);
  const [open, setOpen] = useState(false);
  const [date, setDate] = useState(() => inMonths(Math.min(Math.max(horizonMonths ?? 6, 1), 24)));
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api.runPredictions(runId).then(setPreds).catch(() => setPreds([]));
  }, [runId]);

  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent | KeyboardEvent) => {
      if (e instanceof KeyboardEvent ? e.key === "Escape" : !box.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", close);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", close);
    };
  }, [open]);

  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      const p = await api.track(runId, { resolves_on: date, note });
      setPreds([p, ...(preds ?? [])]);
      setOpen(false);
      setNote("");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  if (preds === null) return null;
  const latest = preds[0];

  return (
    <div ref={box} className="relative">
      {latest ? (
        <Link
          href="/backtest#track"
          className="inline-flex h-8 items-center rounded-md border border-control bg-surface px-3 text-[13px] text-muted hover:bg-raised"
          title="See it in your track record"
        >
          {latest.status === "resolved" ? "Scored in your track record" : `Tracked, resolves ${day(latest.resolves_on)}`}
        </Link>
      ) : (
        <Button onClick={() => setOpen(!open)} aria-expanded={open}>
          Track this prediction
        </Button>
      )}
      {open && (
        <div role="dialog" aria-label="Track this prediction" className="absolute right-0 top-10 z-30 w-[min(340px,calc(100vw-32px))] rounded-lg border border-border bg-surface p-4 shadow-[0_8px_24px_rgba(0,0,0,0.12)]">
          <p className="text-[13px] leading-[18px] text-muted">
            Tellaris freezes today&apos;s answer. When the real result is known, enter it on the Accuracy page to score it.
          </p>
          {demo && <p className="mt-2 text-[13px] leading-[18px] text-[var(--pill-warning-ink)]">This run used the demo model, so tracking it only tries out the flow.</p>}
          <label className="mt-3 block text-[13px] font-medium" htmlFor="track-date">
            Real answer known by
          </label>
          <Input id="track-date" type="date" min={tomorrow()} value={date} onChange={(e) => setDate(e.target.value)} className="mt-1" />
          <label className="mt-3 block text-[13px] font-medium" htmlFor="track-note">
            Where it will come from <span className="font-normal text-faint">(optional)</span>
          </label>
          <Input id="track-note" placeholder="e.g. official results, app store data" value={note} onChange={(e) => setNote(e.target.value)} className="mt-1" />
          {error && <p className="mt-2 text-[13px] text-negative">{error}</p>}
          <div className="mt-4 flex justify-end gap-2">
            <Button variant="ghost" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button variant="primary" onClick={save} busy={busy} disabled={!date}>
              Track it
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
