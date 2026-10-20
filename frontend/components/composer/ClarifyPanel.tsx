"use client";

import { Button, Card, CardHead, Input, Textarea } from "@/components/ui";
import { useMeta } from "@/lib/meta";
import { cx } from "@/lib/format";
import type { Clarification, ClarifyQuestion, LensId } from "@/lib/types";

const DECIDE = "__oracle__";

export type Answers = Record<string, string | string[]>;

/** The answers worth sending: anything the user chose, minus "let Oracle decide". */
export function toClarifications(c: Clarification | null, answers: Answers): { question: string; answer: string }[] {
  if (!c) return [];
  return c.questions
    .map((q) => {
      const a = answers[q.id];
      const text = Array.isArray(a) ? a.join(", ") : a;
      return text && text !== DECIDE ? { question: q.question, answer: text + (q.kind === "number" && q.unit ? ` ${q.unit}` : "") } : null;
    })
    .filter(Boolean) as { question: string; answer: string }[];
}

export function initialAnswers(c: Clarification): Answers {
  const a: Answers = {};
  for (const q of c.questions) a[q.id] = q.kind === "multi" ? (q.default ? [q.default] : []) : q.default || DECIDE;
  return a;
}

function Choice({ active, onClick, children, hint }: { active: boolean; onClick: () => void; children: React.ReactNode; hint?: string }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      title={hint}
      className={cx("inline-flex min-h-8 items-center rounded-md border px-3 text-[14px] transition-colors", active ? "border-text bg-text text-surface" : "border-control bg-surface text-text hover:bg-raised")}
    >
      {children}
    </button>
  );
}

function QuestionInput({ q, value, onChange }: { q: ClarifyQuestion; value: string | string[] | undefined; onChange: (v: string | string[]) => void }) {
  if (q.kind === "single" || q.kind === "boolean") {
    const options = q.kind === "boolean" ? ["Yes", "No"] : q.options;
    return (
      <div className="flex flex-wrap gap-1.5" role="radiogroup" aria-label={q.question}>
        {options.map((o) => (
          <Choice key={o} active={value === o} onClick={() => onChange(o)} hint={o === q.default ? "Oracle's guess" : undefined}>
            {o}
            {o === q.default && <span className={cx("ml-1.5 text-[11px]", value === o ? "text-surface/70" : "text-faint")}>guess</span>}
          </Choice>
        ))}
        <Choice active={value === DECIDE} onClick={() => onChange(DECIDE)}>
          Let Oracle decide
        </Choice>
      </div>
    );
  }
  if (q.kind === "multi") {
    const list = Array.isArray(value) ? value : [];
    return (
      <div className="flex flex-wrap gap-1.5">
        {q.options.map((o) => (
          <Choice key={o} active={list.includes(o)} onClick={() => onChange(list.includes(o) ? list.filter((x) => x !== o) : [...list, o])}>
            {o}
          </Choice>
        ))}
      </div>
    );
  }
  const text = typeof value === "string" && value !== DECIDE ? value : "";
  if (q.kind === "number") {
    return (
      <div className="flex max-w-xs items-center gap-2">
        <Input type="number" step="any" aria-label={q.question} value={text} placeholder={q.default || "Let Oracle decide"} onChange={(e) => onChange(e.target.value || DECIDE)} />
        {q.unit && <span className="shrink-0 text-[13px] text-muted">{q.unit}</span>}
      </div>
    );
  }
  if (q.kind === "long") {
    return <Textarea rows={3} aria-label={q.question} value={text} placeholder={q.default || "Let Oracle decide"} onChange={(e) => onChange(e.target.value || DECIDE)} />;
  }
  return <Input aria-label={q.question} value={text} placeholder={q.default || "Let Oracle decide"} onChange={(e) => onChange(e.target.value || DECIDE)} />;
}

/** "Here's how I read it" plus any questions worth asking, before a run. */
export function ClarifyPanel({
  c,
  lens,
  onLens,
  answers,
  onAnswers,
  onRun,
  onSkip,
  onCancel,
  busy,
}: {
  c: Clarification;
  lens: LensId | null;
  onLens: (l: LensId) => void;
  answers: Answers;
  onAnswers: (a: Answers) => void;
  onRun: () => void;
  onSkip: () => void;
  onCancel: () => void;
  busy: boolean;
}) {
  const { meta } = useMeta();
  const lenses = meta?.lenses ?? [];
  const current = lenses.find((l) => l.id === lens);
  return (
    <Card className="border-text/20">
      <CardHead title={c.questions.length ? "A few quick questions first" : "Here's how Oracle reads it"}>{c.reading}</CardHead>
      <div className="flex flex-col gap-6">
        <div>
          <div className="mb-2 text-[14px] font-medium">Reading this as</div>
          <div className="flex flex-wrap gap-1.5" role="radiogroup" aria-label="Lens">
            {lenses.map((l) => (
              <Choice key={l.id} active={lens === l.id} onClick={() => onLens(l.id)}>
                {l.label}
              </Choice>
            ))}
          </div>
          {current && <p className="mt-1.5 text-[13px] leading-[18px] text-muted">{current.description}</p>}
        </div>
        {c.questions.map((q) => (
          <div key={q.id}>
            <div className="text-[14px] font-medium">{q.question}</div>
            {q.why && <p className="mb-2 mt-0.5 text-[13px] text-muted">{q.why}</p>}
            <QuestionInput q={q} value={answers[q.id]} onChange={(v) => onAnswers({ ...answers, [q.id]: v })} />
          </div>
        ))}
        <div className="flex flex-wrap items-center justify-end gap-2 border-t border-border pt-4">
          <Button variant="ghost" onClick={onCancel}>
            Back to editing
          </Button>
          {c.questions.length > 0 && (
            <Button onClick={onSkip} disabled={busy}>
              Skip questions
            </Button>
          )}
          <Button variant="primary" size="lg" onClick={onRun} busy={busy}>
            Run simulation
          </Button>
        </div>
      </div>
    </Card>
  );
}
