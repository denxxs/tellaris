"use client";

import { motion } from "motion/react";
import Link from "next/link";
import { forwardRef, useId } from "react";
import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode, TextareaHTMLAttributes } from "react";
import { cx } from "@/lib/format";

/* ---------------------------------------------------------------- buttons */

type Variant = "primary" | "secondary" | "ghost" | "danger";

const variants: Record<Variant, string> = {
  primary: "bg-primary text-primary-ink hover:opacity-90 active:opacity-100",
  secondary: "bg-surface text-text border border-control hover:bg-raised",
  ghost: "text-muted hover:text-text hover:bg-active",
  danger: "text-negative hover:bg-[var(--pill-negative-bg)]",
};
const sizes = { sm: "h-7 px-2.5 text-[13px]", md: "h-8 px-3 text-[13px]", lg: "h-10 px-4 text-[14px]" };

export const Button = forwardRef<HTMLButtonElement, ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; size?: keyof typeof sizes; busy?: boolean }>(
  function Button({ variant = "secondary", size = "md", busy, className, children, disabled, ...rest }, ref) {
    return (
      <button
        ref={ref}
        className={cx(
          "inline-flex shrink-0 items-center justify-center gap-2 whitespace-nowrap rounded-md font-medium transition-[background,opacity,color] active:translate-y-px disabled:cursor-not-allowed disabled:opacity-50",
          variants[variant],
          sizes[size],
          className,
        )}
        disabled={disabled || busy}
        aria-busy={busy || undefined}
        {...rest}
      >
        {busy && <Spinner className="size-3.5" />}
        {children}
      </button>
    );
  },
);

export function LinkButton({ href, variant = "secondary", size = "md", className, children }: { href: string; variant?: Variant; size?: keyof typeof sizes; className?: string; children: ReactNode }) {
  return (
    <Link href={href} className={cx("inline-flex shrink-0 items-center justify-center gap-2 whitespace-nowrap rounded-md font-medium transition-colors", variants[variant], sizes[size], className)}>
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

/* ---------------------------------------------------------------- fields */

export function Field({ label, hint, children, className }: { label: string; hint?: ReactNode; children: (id: string) => ReactNode; className?: string }) {
  const id = useId();
  return (
    <div className={cx("flex flex-col gap-2", className)}>
      <label htmlFor={id} className="text-[14px] font-medium text-text">
        {label}
      </label>
      {children(id)}
      {hint && <div className="text-[12px] leading-4 text-faint">{hint}</div>}
    </div>
  );
}

const fieldClass = "w-full rounded-md border border-border bg-surface px-3 text-[14px] text-text placeholder:text-faint transition-colors focus:border-control focus:outline-none";

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(function Input({ className, ...rest }, ref) {
  return <input ref={ref} className={cx(fieldClass, "h-9", className)} {...rest} />;
});

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaHTMLAttributes<HTMLTextAreaElement>>(function Textarea({ className, ...rest }, ref) {
  return <textarea ref={ref} className={cx(fieldClass, "resize-y py-2 leading-[22px]", className)} {...rest} />;
});

export function Select({ value, onChange, options, id, className, label }: { value: string; onChange: (v: string) => void; options: { value: string; label: string }[]; id?: string; className?: string; label?: string }) {
  return (
    <select
      id={id}
      aria-label={label}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className={cx("rounded-md border border-control bg-surface px-3 text-[14px] text-text transition-colors focus:border-text focus:outline-none", "h-9 pr-8", className ?? "w-full")}
    >
      {options.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  );
}

export function Toggle({ checked, onChange, label, description, id }: { checked: boolean; onChange: (v: boolean) => void; label: string; description?: string; id?: string }) {
  return (
    <button id={id} type="button" role="switch" aria-checked={checked} onClick={() => onChange(!checked)} className="flex w-full items-start justify-between gap-4 text-left">
      <span>
        <span className="block text-[14px] font-medium text-text">{label}</span>
        {description && <span className="mt-0.5 block text-[13px] leading-[18px] text-muted">{description}</span>}
      </span>
      <span className={cx("relative mt-0.5 h-4 w-7 shrink-0 rounded-full transition-colors", checked ? "bg-primary" : "bg-control")}>
        <span className={cx("absolute top-0.5 size-3 rounded-full bg-surface transition-transform", checked ? "translate-x-[14px]" : "translate-x-0.5")} />
      </span>
    </button>
  );
}

export function Slider({ value, min, max, step = 1, onChange, id, format, label }: { value: number; min: number; max: number; step?: number; onChange: (v: number) => void; id?: string; format?: (v: number) => string; label?: string }) {
  return (
    <div className="flex items-center gap-3">
      <input
        id={id}
        aria-label={label}
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="h-1 flex-1 cursor-pointer accent-[var(--text)]"
      />
      <span className="num min-w-16 shrink-0 whitespace-nowrap text-right text-[14px] text-text">{format ? format(value) : value}</span>
    </div>
  );
}

export function Segmented<T extends string>({ value, onChange, options, label }: { value: T; onChange: (v: T) => void; options: { value: T; label: string; sub?: string }[]; label: string }) {
  return (
    <div role="radiogroup" aria-label={label} className="inline-flex rounded-md bg-raised p-0.5">
      {options.map((o) => (
        <button
          key={o.value}
          role="radio"
          aria-checked={value === o.value}
          onClick={() => onChange(o.value)}
          className={cx("rounded-[5px] px-3 py-1 text-left transition-colors", value === o.value ? "bg-surface text-text ring-1 ring-border" : "text-muted hover:text-text")}
        >
          <span className="block text-[13px] font-medium leading-[18px]">{o.label}</span>
          {o.sub && <span className="block text-[12px] leading-4 text-faint">{o.sub}</span>}
        </button>
      ))}
    </div>
  );
}

/* ---------------------------------------------------------------- marks */

export function Chip({ children, onRemove, onClick, active, title }: { children: ReactNode; onRemove?: () => void; onClick?: () => void; active?: boolean; title?: string }) {
  const Comp = onClick ? "button" : "span";
  return (
    <Comp
      type={onClick ? "button" : undefined}
      onClick={onClick}
      title={title}
      aria-pressed={onClick ? !!active : undefined}
      className={cx(
        "inline-flex min-h-6 flex-none items-center gap-1 whitespace-nowrap rounded px-2 text-[13px] leading-5",
        active ? "bg-primary text-primary-ink" : "bg-[var(--pill-neutral-bg)] text-[var(--pill-neutral-ink)]",
        onClick && !active && "hover:bg-active",
      )}
    >
      {children}
      {onRemove && (
        <button
          type="button"
          aria-label="Remove"
          onClick={(e) => {
            e.stopPropagation();
            onRemove();
          }}
          className="-mr-1 grid size-4 place-items-center rounded text-faint hover:bg-control/40 hover:text-text"
        >
          <svg viewBox="0 0 12 12" className="size-2.5" aria-hidden>
            <path d="M3 3l6 6M9 3l-6 6" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
          </svg>
        </button>
      )}
    </Comp>
  );
}

export function Pill({ tone = "neutral", children }: { tone?: "neutral" | "positive" | "negative" | "warning" | "yes" | "no"; children: ReactNode }) {
  const style = {
    neutral: "bg-[var(--pill-neutral-bg)] text-[var(--pill-neutral-ink)]",
    positive: "bg-[var(--pill-positive-bg)] text-[var(--pill-positive-ink)]",
    negative: "bg-[var(--pill-negative-bg)] text-[var(--pill-negative-ink)]",
    warning: "bg-[var(--pill-warning-bg)] text-[var(--pill-warning-ink)]",
    yes: "bg-yes-soft text-yes",
    no: "bg-no-soft text-no",
  }[tone];
  return <span className={cx("inline-flex h-5 flex-none items-center whitespace-nowrap rounded px-1.5 text-[12px] font-medium", style)}>{children}</span>;
}

export function Tabs<T extends string>({ tabs, value, onChange }: { tabs: { id: T; label: string }[]; value: T; onChange: (v: T) => void }) {
  return (
    <div role="tablist" className="scroll-thin flex gap-5 overflow-x-auto border-b border-border">
      {tabs.map((t) => (
        <button
          key={t.id}
          role="tab"
          aria-selected={value === t.id}
          onClick={() => onChange(t.id)}
          className={cx("relative h-10 shrink-0 text-[14px] transition-colors", value === t.id ? "font-medium text-text" : "text-muted hover:text-text")}
        >
          {t.label}
          {value === t.id && <motion.span layoutId="tab-line" className="absolute inset-x-0 -bottom-px h-0.5 bg-text" transition={{ type: "spring", bounce: 0.1, duration: 0.35 }} />}
        </button>
      ))}
    </div>
  );
}

/* ---------------------------------------------------------------- surfaces */

export function Card({ children, className, pad = true, as: As = "section" }: { children: ReactNode; className?: string; pad?: boolean; as?: "section" | "div" }) {
  return <As className={cx("rounded-lg border border-border bg-surface", pad && "p-5", className)}>{children}</As>;
}

export function CardHead({ title, children, aside }: { title: string; children?: ReactNode; aside?: ReactNode }) {
  return (
    <div className="mb-4 flex flex-wrap items-start justify-between gap-x-4 gap-y-1">
      <div className="min-w-0">
        <h2 className="t-section">{title}</h2>
        {children && <p className="mt-0.5 text-[13px] leading-[18px] text-muted">{children}</p>}
      </div>
      {aside && <div className="shrink-0 text-[13px] text-muted">{aside}</div>}
    </div>
  );
}

export function PageHead({ title, children, actions }: { title: string; children?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
      <div className="min-w-0 max-w-3xl">
        <h1 className="t-title">{title}</h1>
        {children && <p className="mt-1 text-[14px] leading-5 text-muted">{children}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

export function Empty({ title, children, action, className }: { title: string; children?: ReactNode; action?: ReactNode; className?: string }) {
  return (
    <div className={cx("rounded-lg border border-dashed border-control px-4 py-3.5", className)}>
      <div className="text-[14px] font-medium text-text">{title}</div>
      {children && <p className="mt-0.5 max-w-xl text-[13px] leading-[18px] text-muted">{children}</p>}
      {action && <div className="mt-3">{action}</div>}
    </div>
  );
}

export function ErrorNote({ children, action }: { children: ReactNode; action?: ReactNode }) {
  return (
    <div role="alert" className="flex flex-wrap items-center justify-between gap-3 rounded-lg bg-[var(--pill-negative-bg)] px-4 py-3 text-[13px] leading-[18px] text-[var(--pill-negative-ink)]">
      <div>{children}</div>
      {action}
    </div>
  );
}

export function Notice({ children }: { children: ReactNode }) {
  return <div className="rounded-lg border border-[#fde68a] bg-[var(--pill-warning-bg)] px-4 py-2.5 text-[13px] leading-[18px] text-[var(--pill-warning-ink)] dark:border-transparent">{children}</div>;
}

export function Meter({ value, className, tone = "text" }: { value: number; className?: string; tone?: "text" | "yes" }) {
  return (
    <div className={cx("h-1 w-full overflow-hidden rounded-full bg-raised", className)} role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(value * 100)}>
      <div className={cx("h-full rounded-full transition-[width] duration-500", tone === "yes" ? "bg-yes" : "bg-text")} style={{ width: `${Math.max(0, Math.min(1, value)) * 100}%` }} />
    </div>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <span className={cx("block rounded bg-raised", className)} aria-hidden />;
}
