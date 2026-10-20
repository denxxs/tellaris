"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { cx } from "@/lib/format";

const items = [
  { href: "/", label: "Simulate", icon: "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18Zm0 0c2.5 2.4 3.8 5.4 3.8 9s-1.3 6.6-3.8 9m0-18C9.5 5.4 8.2 8.4 8.2 12s1.3 6.6 3.8 9M3.5 9h17M3.5 15h17" },
  { href: "/runs", label: "Runs", icon: "M4 6h16M4 12h16M4 18h10" },
  { href: "/backtest", label: "Accuracy", icon: "M4 19V5m0 14h16M8 15l3-4 3 2 5-6" },
  { href: "/settings", label: "Models", icon: "M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6Zm7.4-3a7.4 7.4 0 0 0-.1-1.2l2-1.6-2-3.4-2.4 1a7.5 7.5 0 0 0-2-1.2L14.5 3h-5l-.4 2.6a7.5 7.5 0 0 0-2 1.2l-2.4-1-2 3.4 2 1.6a7.4 7.4 0 0 0 0 2.4l-2 1.6 2 3.4 2.4-1c.6.5 1.3.9 2 1.2l.4 2.6h5l.4-2.6c.7-.3 1.4-.7 2-1.2l2.4 1 2-3.4-2-1.6c.1-.4.1-.8.1-1.2Z" },
];

function Mark() {
  // A small orbit: one world, many people.
  return (
    <svg viewBox="0 0 32 32" className="size-8" aria-hidden>
      <circle cx="16" cy="16" r="9" fill="var(--iris)" />
      <ellipse cx="16" cy="16" rx="14.5" ry="5.5" fill="none" stroke="var(--ink)" strokeWidth="1.6" transform="rotate(-24 16 16)" />
      <circle cx="28.4" cy="10.6" r="2.1" fill="var(--yes)" />
      <circle cx="4.2" cy="21.6" r="1.6" fill="var(--no)" />
    </svg>
  );
}

function ThemeToggle() {
  const [theme, setTheme] = useState<string | null>(null);
  useEffect(() => {
    setTheme(document.documentElement.dataset.theme ?? null);
  }, []);
  const next = theme === "dark" ? "light" : theme === "light" ? null : "dark";
  const label = theme === "dark" ? "Dark" : theme === "light" ? "Light" : "Auto";
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
      className="grid h-10 w-full place-items-center rounded-xl text-[11px] font-semibold text-ink-3 hover:bg-panel-2 hover:text-ink"
      title="Switch theme"
    >
      {label}
    </button>
  );
}

export function Rail() {
  const path = usePathname();
  const active = (href: string) => (href === "/" ? path === "/" || path.startsWith("/new") : path.startsWith(href));
  return (
    <>
      <nav aria-label="Main" className="sticky top-0 hidden h-dvh w-[76px] shrink-0 flex-col items-center gap-1 border-r border-line bg-panel py-4 md:flex">
        <Link href="/" className="mb-5" aria-label="Oracle home">
          <Mark />
        </Link>
        {items.map((it) => (
          <Link
            key={it.href}
            href={it.href}
            aria-current={active(it.href) ? "page" : undefined}
            className={cx(
              "flex w-[60px] flex-col items-center gap-1 rounded-xl py-2 text-[11px] font-semibold transition-colors",
              active(it.href) ? "bg-iris-soft text-iris-ink" : "text-ink-3 hover:bg-panel-2 hover:text-ink",
            )}
          >
            <svg viewBox="0 0 24 24" className="size-5" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
              <path d={it.icon} />
            </svg>
            {it.label}
          </Link>
        ))}
        <div className="mt-auto w-[60px]">
          <ThemeToggle />
        </div>
      </nav>

      <nav aria-label="Main" className="fixed inset-x-0 bottom-0 z-40 flex border-t border-line bg-panel/95 backdrop-blur md:hidden">
        {items.map((it) => (
          <Link
            key={it.href}
            href={it.href}
            aria-current={active(it.href) ? "page" : undefined}
            className={cx("flex flex-1 flex-col items-center gap-0.5 py-2.5 text-[11px] font-semibold", active(it.href) ? "text-iris-ink" : "text-ink-3")}
          >
            <svg viewBox="0 0 24 24" className="size-5" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
              <path d={it.icon} />
            </svg>
            {it.label}
          </Link>
        ))}
      </nav>
    </>
  );
}
