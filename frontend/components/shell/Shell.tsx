"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { API, api } from "@/lib/api";
import { ago, cx } from "@/lib/format";
import type { RunListItem } from "@/lib/types";

const NAV = [
  { href: "/", label: "New simulation", icon: "M12 5v14M5 12h14", match: (p: string) => p === "/" },
  { href: "/runs", label: "Simulations", icon: "M4 6h16M4 12h16M4 18h10", match: (p: string) => p.startsWith("/runs") },
  { href: "/backtest", label: "Accuracy", icon: "M4 19V5m0 14h16M8 15l3-4 3 2 5-6", match: (p: string) => p.startsWith("/backtest") },
  { href: "/settings", label: "Models", icon: "M4 7h10M18 7h2M4 17h4M12 17h8M14 4v6M8 14v6", match: (p: string) => p.startsWith("/settings") },
];

/** The product's mark: a world (the ring) holding its people (three answers). */
export function Mark({ size = 22 }: { size?: number }) {
  return (
    <svg viewBox="0 0 24 24" width={size} height={size} aria-hidden>
      <rect x="6.15" y="1.55" width="2.51" height="2.51" rx="0.55" fill="var(--yes)" />
      <rect x="10.57" y="1.37" width="2.86" height="2.86" rx="0.63" fill="var(--yes)" />
      <rect x="15.35" y="1.55" width="2.51" height="2.51" rx="0.55" fill="var(--yes)" />
      <rect x="1.55" y="6.15" width="2.51" height="2.51" rx="0.55" fill="var(--yes)" />
      <rect x="5.73" y="5.73" width="3.34" height="3.34" rx="0.73" fill="var(--yes)" />
      <rect x="10.23" y="5.63" width="3.53" height="3.53" rx="0.78" fill="var(--yes)" />
      <rect x="14.93" y="5.73" width="3.34" height="3.34" rx="0.73" fill="var(--no)" />
      <rect x="19.95" y="6.15" width="2.51" height="2.51" rx="0.55" fill="var(--yes)" />
      <rect x="1.37" y="10.57" width="2.86" height="2.86" rx="0.63" fill="var(--yes)" />
      <rect x="5.63" y="10.23" width="3.53" height="3.53" rx="0.78" fill="var(--yes)" />
      <rect x="10.15" y="10.15" width="3.7" height="3.7" rx="0.81" fill="var(--yes)" />
      <rect x="14.83" y="10.23" width="3.53" height="3.53" rx="0.78" fill="var(--yes)" />
      <rect x="19.77" y="10.57" width="2.86" height="2.86" rx="0.63" fill="var(--yes)" />
      <rect x="1.55" y="15.35" width="2.51" height="2.51" rx="0.55" fill="var(--yes)" />
      <rect x="5.73" y="14.93" width="3.34" height="3.34" rx="0.73" fill="var(--yes)" />
      <rect x="10.23" y="14.83" width="3.53" height="3.53" rx="0.78" fill="var(--yes)" />
      <rect x="14.93" y="14.93" width="3.34" height="3.34" rx="0.73" fill="var(--yes)" />
      <rect x="19.95" y="15.35" width="2.51" height="2.51" rx="0.55" fill="var(--yes)" />
      <rect x="6.15" y="19.95" width="2.51" height="2.51" rx="0.55" fill="var(--yes)" />
      <rect x="10.57" y="19.77" width="2.86" height="2.86" rx="0.63" fill="var(--yes)" />
      <rect x="15.35" y="19.95" width="2.51" height="2.51" rx="0.55" fill="var(--yes)" />
    </svg>
  );
}

function Icon({ d }: { d: string }) {
  return (
    <svg viewBox="0 0 24 24" className="size-4 shrink-0" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
      <path d={d} />
    </svg>
  );
}

function useHealth() {
  const [state, setState] = useState<{ status: "ok" | "mock" | "down" | null }>({ status: null });
  useEffect(() => {
    let alive = true;
    const check = () =>
      fetch(`${API}/api/health`, { cache: "no-store" })
        .then((r) => r.json())
        .then((h) => alive && setState({ status: h.mock ? "mock" : "ok" }))
        .catch(() => alive && setState({ status: "down" }));
    check();
    const t = setInterval(check, 15000);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, []);
  return state.status;
}

function ModelStatus({ status }: { status: ReturnType<typeof useHealth> }) {
  if (!status) return null;
  const text = { ok: "Models connected", mock: "Demo model, not real predictions", down: "Server not running" }[status];
  const dot = { ok: "bg-positive", mock: "bg-live", down: "bg-negative" }[status];
  return (
    <Link href="/settings" className="flex items-start gap-2 rounded-md px-2 py-1.5 text-[13px] leading-[18px] text-muted hover:bg-active hover:text-text">
      <span className={cx("mt-[5px] size-2 shrink-0 rounded-full", dot)} aria-hidden />
      <span>{text}</span>
    </Link>
  );
}

function ThemeToggle() {
  const [theme, setTheme] = useState<string | null>(null);
  useEffect(() => {
    setTheme(document.documentElement.dataset.theme ?? null);
  }, []);
  const next = theme === "dark" ? "light" : theme === "light" ? null : "dark";
  const label = theme === "dark" ? "Dark" : theme === "light" ? "Light" : "System";
  return (
    <button
      onClick={() => {
        if (next) document.documentElement.dataset.theme = next;
        else delete document.documentElement.dataset.theme;
        try {
          if (next) localStorage.setItem("oracle-theme", next);
          else localStorage.removeItem("oracle-theme");
        } catch {}
        setTheme(next);
      }}
      className="rounded-md px-2 py-1.5 text-left text-[13px] text-muted hover:bg-active hover:text-text"
      title="Switch between light, dark and your system setting"
    >
      Theme: {label}
    </button>
  );
}

function SearchBox({ onNavigate }: { onNavigate?: () => void }) {
  const router = useRouter();
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const [runs, setRuns] = useState<RunListItem[] | null>(null);
  const [hi, setHi] = useState(0);
  const input = useRef<HTMLInputElement>(null);
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        input.current?.focus();
      }
    };
    const close = (e: MouseEvent) => !box.current?.contains(e.target as Node) && setOpen(false);
    window.addEventListener("keydown", key);
    document.addEventListener("mousedown", close);
    return () => {
      window.removeEventListener("keydown", key);
      document.removeEventListener("mousedown", close);
    };
  }, []);

  const results = useMemo(() => {
    const t = q.trim().toLowerCase();
    return (runs ?? []).filter((r) => !t || `${r.title} ${r.prompt} ${r.targets.join(" ")}`.toLowerCase().includes(t)).slice(0, 7);
  }, [runs, q]);

  const go = (id: string) => {
    setOpen(false);
    setQ("");
    onNavigate?.();
    router.push(`/runs/${id}`);
  };

  return (
    <div ref={box} className="relative w-full max-w-[548px]">
      <svg viewBox="0 0 24 24" className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-faint" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden>
        <circle cx="11" cy="11" r="6.5" />
        <path d="m16 16 4 4" strokeLinecap="round" />
      </svg>
      <input
        ref={input}
        value={q}
        onChange={(e) => {
          setQ(e.target.value);
          setHi(0);
          setOpen(true);
        }}
        onFocus={() => {
          setOpen(true);
          if (!runs) api.runs().then(setRuns).catch(() => setRuns([]));
        }}
        onKeyDown={(e) => {
          if (e.key === "ArrowDown") {
            e.preventDefault();
            setHi((h) => Math.min(h + 1, results.length - 1));
          } else if (e.key === "ArrowUp") {
            e.preventDefault();
            setHi((h) => Math.max(h - 1, 0));
          } else if (e.key === "Enter" && results[hi]) go(results[hi].id);
          else if (e.key === "Escape") {
            setOpen(false);
            input.current?.blur();
          }
        }}
        placeholder="Search simulations"
        aria-label="Search simulations"
        role="combobox"
        aria-expanded={open}
        aria-controls="search-results"
        className="h-8 w-full rounded-md border border-border bg-surface pl-9 pr-14 text-[13px] text-text placeholder:text-faint focus:border-control focus:outline-none"
      />
      <kbd className="pointer-events-none absolute right-2 top-1/2 hidden -translate-y-1/2 rounded border border-border px-1.5 text-[11px] text-faint sm:block">Ctrl K</kbd>
      {open && runs && (
        <ul id="search-results" role="listbox" className="absolute inset-x-0 top-full z-50 mt-1 overflow-hidden rounded-lg border border-border bg-surface py-1 shadow-[0_8px_24px_rgba(0,0,0,0.12)]">
          {results.length === 0 ? (
            <li className="px-3 py-2 text-[13px] text-muted">{runs.length ? "No simulation matches that." : "No simulations yet."}</li>
          ) : (
            results.map((r, i) => (
              <li key={r.id} role="option" aria-selected={i === hi}>
                <button onMouseEnter={() => setHi(i)} onClick={() => go(r.id)} className={cx("flex w-full items-baseline justify-between gap-3 px-3 py-2 text-left", i === hi && "bg-active")}>
                  <span className="truncate text-[13px] text-text">{r.title}</span>
                  <span className="shrink-0 text-[12px] text-faint">{ago(r.created_at)}</span>
                </button>
              </li>
            ))
          )}
        </ul>
      )}
    </div>
  );
}

function NavLinks({ onNavigate }: { onNavigate?: () => void }) {
  const path = usePathname();
  return (
    <nav aria-label="Main" className="flex flex-col gap-0.5">
      {NAV.map((n) => {
        const active = n.match(path);
        return (
          <Link
            key={n.href}
            href={n.href}
            onClick={onNavigate}
            aria-current={active ? "page" : undefined}
            className={cx("flex h-8 items-center gap-2.5 rounded-md px-2 text-[14px]", active ? "bg-active text-text" : "text-muted hover:bg-active/60 hover:text-text")}
          >
            <Icon d={n.icon} />
            {n.label}
          </Link>
        );
      })}
    </nav>
  );
}

export function Shell({ children }: { children: React.ReactNode }) {
  const status = useHealth();
  const [menu, setMenu] = useState(false);
  const path = usePathname();
  const current = NAV.find((n) => n.match(path))?.label ?? "Project Tellaris";

  return (
    <div className="min-h-dvh bg-ground">
      {/* Desktop: the L-frame */}
      <aside className="fixed inset-y-0 left-0 hidden w-[228px] flex-col px-3 pb-3 pt-3 lg:flex">
        <Link href="/" className="flex h-9 items-center gap-2.5 px-2">
          <Mark />
          <span className="text-[15px] font-semibold tracking-[-0.01em]">Project Tellaris</span>
        </Link>
        <div className="mb-4 mt-0.5 px-2 text-[12px] text-faint">Local workspace</div>
        <NavLinks />
        <div className="mt-auto flex flex-col gap-0.5">
          <ModelStatus status={status} />
          <ThemeToggle />
        </div>
      </aside>

      <header className="fixed left-[228px] right-0 top-0 hidden h-12 items-center justify-center px-6 lg:flex">
        <SearchBox />
      </header>

      {/* Phone and tablet: a 48px bar and a menu sheet */}
      <header className="sticky top-0 z-40 flex h-12 items-center gap-3 border-b border-border bg-ground px-4 lg:hidden">
        <button onClick={() => setMenu(true)} className="-ml-1 grid size-9 place-items-center rounded-md text-text hover:bg-active" aria-label="Open menu">
          <svg viewBox="0 0 24 24" className="size-5" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" aria-hidden>
            <path d="M4 7h16M4 12h16M4 17h16" />
          </svg>
        </button>
        <Mark size={20} />
        <span className="text-[15px] font-semibold">{current}</span>
        {path !== "/" && (
          <Link href="/" className="ml-auto inline-flex h-8 items-center rounded-md bg-primary px-3 text-[13px] font-medium text-primary-ink">
            New
          </Link>
        )}
      </header>
      {menu && (
        <div className="fixed inset-0 z-50 flex flex-col bg-ground p-4 lg:hidden" role="dialog" aria-modal aria-label="Menu">
          <div className="mb-4 flex items-center justify-between">
            <span className="flex items-center gap-2.5">
              <Mark />
              <span className="text-[15px] font-semibold">Project Tellaris</span>
            </span>
            <button onClick={() => setMenu(false)} className="h-9 rounded-md px-3 text-[14px] text-muted hover:bg-active" aria-label="Close menu">
              Close
            </button>
          </div>
          <div className="mb-4">
            <SearchBox onNavigate={() => setMenu(false)} />
          </div>
          <NavLinks onNavigate={() => setMenu(false)} />
          <div className="mt-auto flex flex-col gap-0.5">
            <ModelStatus status={status} />
            <ThemeToggle />
          </div>
        </div>
      )}

      {/* The sheet */}
      <main className="min-h-[calc(100dvh-48px)] bg-surface lg:fixed lg:bottom-2 lg:left-[228px] lg:right-2 lg:top-12 lg:min-h-0 lg:overflow-y-auto lg:rounded-2xl lg:border lg:border-border">
        {status === "down" && (
          <div role="status" className="border-b border-border bg-[var(--pill-negative-bg)] px-6 py-2.5 text-[13px] text-[var(--pill-negative-ink)]">
            The simulation server isn&apos;t running. Start it with <code className="font-mono">cd backend &amp;&amp; python -m oracle</code>, or run <code className="font-mono">./dev.ps1</code>.
          </div>
        )}
        {children}
      </main>
    </div>
  );
}
