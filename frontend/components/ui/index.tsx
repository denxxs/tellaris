"use client";

import { motion } from "motion/react";
import Link from "next/link";
import { forwardRef, useId } from "react";
import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode, TextareaHTMLAttributes } from "react";
import { cx } from "@/lib/format";

type Variant = "primary" | "secondary" | "ghost" | "danger";

const variants: Record<Variant, string> = {
  primary: "bg-iris text-white hover:brightness-110 active:brightness-95 shadow-[0_1px_0_rgba(255,255,255,0.2)_inset]",
  secondary: "bg-panel text-ink border border-line-strong hover:border-ink-3",
  ghost: "text-ink-2 hover:text-ink hover:bg-panel-2",
  danger: "text-no hover:bg-no-soft",
};

export const Button = forwardRef<HTMLButtonElement, ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; size?: "sm" | "md" | "lg"; busy?: boolean }>(
  function Button({ variant = "secondary", size = "md", busy, className, children, disabled, ...rest }, ref) {
    const sizes = { sm: "h-8 px-3 text-[13px] rounded-lg", md: "h-10 px-4 text-sm rounded-[10px]", lg: "h-12 px-6 text-[15px] rounded-xl" };
    return (
      <button
        ref={ref}
        className={cx(
          "inline-flex items-center justify-center gap-2 font-semibold whitespace-nowrap transition-[filter,background,border-color,color] disabled:cursor-not-allowed disabled:opacity-50",
          variants[variant],
          sizes[size],
          className,
        )}
        disabled={disabled || busy}
        aria-busy={busy || undefined}
        {...rest}
      >
        {busy && <Spinner className="size-4" />}
        {children}
      </button>
    );
  },
);

export function LinkButton({ href, variant = "secondary", className, children }: { href: string; variant?: Variant; className?: string; children: ReactNode }) {
  return (
    <Link
      href={href}
      className={cx("inline-flex h-10 items-center justify-center gap-2 rounded-[10px] px-4 text-sm font-semibold transition-[filter,background,border-color]", variants[variant], className)}
    >
      {children}
    </Link>
  );
}

export function Spinner({ className }: { className?: string }) {
  return (
    <svg className={cx("animate-spin", className)} viewBox="0 0 24 24" fill="none" aria-hidden>
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeOpacity="0.25" strokeWidth="3" />
      <path d="M21 12a9 9 0 0 0-9-9" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
    </svg>
  );
}

export function Field({ label, hint, children, className }: { label: string; hint?: ReactNode; children: (id: string) => ReactNode; className?: string }) {
  const id = useId();
  return (
    <div className={cx("flex flex-col gap-1.5", className)}>
      <label htmlFor={id} className="t-small font-semibold text-ink">
        {label}
      </label>
      {children(id)}
      {hint && <div className="t-tiny text-ink-3">{hint}</div>}
    </div>
  );
}

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(function Input({ className, ...rest }, ref) {
  return (
    <input
      ref={ref}
      className={cx(
        "h-10 w-full rounded-lg border border-line-strong bg-panel px-3 text-sm text-ink placeholder:text-ink-3 transition-colors focus:border-iris focus:outline-none",
        className,
      )}
      {...rest}
    />
  );
});

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaHTMLAttributes<HTMLTextAreaElement>>(function Textarea({ className, ...rest }, ref) {
  return (
    <textarea
      ref={ref}
      className={cx(
        "w-full resize-y rounded-lg border border-line-strong bg-panel px-3 py-2.5 text-sm text-ink placeholder:text-ink-3 transition-colors focus:border-iris focus:outline-none",
        className,
      )}
      {...rest}
    />
  );
});

export function Select({ value, onChange, options, id, className }: { value: string; onChange: (v: string) => void; options: { value: string; label: string }[]; id?: string; className?: string }) {
  return (
    <select
      id={id}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className={cx("h-10 w-full rounded-lg border border-line-strong bg-panel px-3 text-sm text-ink focus:border-iris focus:outline-none", className)}
    >
      {options.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  );
}

export function Toggle({ checked, onChange, label, id }: { checked: boolean; onChange: (v: boolean) => void; label: string; id?: string }) {
  return (
    <button
      id={id}
      type="button"
      role="switch"
      aria-checked={checked}
      onClick={() => onChange(!checked)}
      className="inline-flex items-center gap-2.5 text-sm text-ink"
    >
      <span className={cx("relative h-5 w-9 shrink-0 rounded-full transition-colors", checked ? "bg-iris" : "bg-line-strong")}>
        <span className={cx("absolute top-0.5 size-4 rounded-full bg-white shadow transition-transform", checked ? "translate-x-[18px]" : "translate-x-0.5")} />
      </span>
      {label}
    </button>
  );
}

export function Slider({ value, min, max, step = 1, onChange, id, format }: { value: number; min: number; max: number; step?: number; onChange: (v: number) => void; id?: string; format?: (v: number) => string }) {
  return (
    <div className="flex items-center gap-3">
      <input
        id={id}
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="h-1.5 flex-1 cursor-pointer appearance-none rounded-full bg-line-strong accent-[var(--iris)]"
      />
      <span className="num w-16 text-right text-sm font-semibold text-ink">{format ? format(value) : value}</span>
    </div>
  );
}

export function Chip({ children, active, onClick, onRemove, tone = "neutral", title }: { children: ReactNode; active?: boolean; onClick?: () => void; onRemove?: () => void; tone?: "neutral" | "iris" | "yes" | "no"; title?: string }) {
  const tones = {
    neutral: active ? "bg-ink text-fog border-ink" : "bg-panel text-ink-2 border-line-strong hover:border-ink-3 hover:text-ink",
    iris: "bg-iris-soft text-iris-ink border-transparent",
    yes: "bg-yes-soft text-yes border-transparent",
    no: "bg-no-soft text-no border-transparent",
  };
  const Comp = onClick ? "button" : "span";
  return (
    <Comp
      type={onClick ? "button" : undefined}
      onClick={onClick}
      title={title}
      aria-pressed={onClick ? !!active : undefined}
      className={cx("inline-flex min-h-7 items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-left text-[13px] font-medium leading-tight transition-colors", tones[tone])}
    >
      {children}
      {onRemove && (
        <span
          role="button"
          tabIndex={0}
          aria-label="Remove"
          onClick={(e) => {
            e.stopPropagation();
            onRemove();
          }}
          onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && onRemove()}
          className="-mr-1 grid size-4 place-items-center rounded-full hover:bg-black/10"
        >
          <svg viewBox="0 0 12 12" className="size-2.5" aria-hidden>
            <path d="M3 3l6 6M9 3l-6 6" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
          </svg>
        </span>
      )}
    </Comp>
  );
}

export function Tabs<T extends string>({ tabs, value, onChange }: { tabs: { id: T; label: string; badge?: ReactNode }[]; value: T; onChange: (v: T) => void }) {
  return (
    <div role="tablist" className="scroll-thin -mx-1 flex gap-1 overflow-x-auto px-1">
      {tabs.map((t) => (
        <button
          key={t.id}
          role="tab"
          aria-selected={value === t.id}
          onClick={() => onChange(t.id)}
          className={cx("relative h-9 shrink-0 rounded-lg px-3 text-sm font-semibold transition-colors", value === t.id ? "text-ink" : "text-ink-3 hover:text-ink-2")}
        >
          {value === t.id && <motion.span layoutId="tab-bg" className="absolute inset-0 rounded-lg bg-panel shadow-lift" transition={{ type: "spring", bounce: 0.15, duration: 0.4 }} />}
          <span className="relative inline-flex items-center gap-1.5">
            {t.label}
            {t.badge}
          </span>
        </button>
      ))}
    </div>
  );
}

export function Panel({ children, className, pad = true }: { children: ReactNode; className?: string; pad?: boolean }) {
  return <section className={cx("rounded-2xl border border-line bg-panel", pad && "p-5 md:p-6", className)}>{children}</section>;
}

export function SectionHead({ title, children, aside }: { title: string; children?: ReactNode; aside?: ReactNode }) {
  return (
    <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
      <div className="max-w-2xl">
        <h2 className="t-2">{title}</h2>
        {children && <p className="mt-1 text-sm text-ink-2">{children}</p>}
      </div>
      {aside}
    </div>
  );
}

export function Empty({ title, children, action }: { title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-start gap-2 rounded-2xl border border-dashed border-line-strong p-8">
      <div className="t-3">{title}</div>
      {children && <p className="max-w-lg text-sm text-ink-2">{children}</p>}
      {action && <div className="mt-2">{action}</div>}
    </div>
  );
}

export function ErrorNote({ children }: { children: ReactNode }) {
  return <div className="rounded-xl border border-no/30 bg-no-soft px-4 py-3 text-sm text-ink">{children}</div>;
}

export function Meter({ value, tone = "iris", className }: { value: number; tone?: "iris" | "yes" | "no"; className?: string }) {
  const bg = { iris: "bg-iris", yes: "bg-yes", no: "bg-no" }[tone];
  return (
    <div className={cx("h-1.5 w-full overflow-hidden rounded-full bg-panel-2", className)}>
      <div className={cx("h-full rounded-full transition-[width] duration-500", bg)} style={{ width: `${Math.max(0, Math.min(1, value)) * 100}%` }} />
    </div>
  );
}
