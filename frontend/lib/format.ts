export const pct = (v: number | null | undefined, digits = 0) =>
  v == null || Number.isNaN(v) ? "–" : `${(v * 100).toFixed(digits)}%`;

/** One decimal under 10%, so small numbers keep their meaning. */
export const pctSmart = (v: number | null | undefined) => {
  if (v == null || Number.isNaN(v)) return "–";
  const x = v * 100;
  if (x === 0) return "0%";
  if (Math.abs(x) < 10) return `${x.toFixed(1)}%`;
  return `${Math.round(x)}%`;
};

/** A change in percentage points, always signed. */
export const signedPts = (v: number | null | undefined) => {
  if (v == null || Number.isNaN(v)) return "–";
  const x = v * 100;
  if (Math.abs(x) < 0.05) return "0.0 pts";
  return `${x > 0 ? "+" : "−"}${Math.abs(x).toFixed(1)} pts`;
};

export const money = (v: number | null | undefined, currency = "USD") => {
  if (v == null || Number.isNaN(v)) return "–";
  if (Math.abs(v) >= 100_000) {
    try {
      return new Intl.NumberFormat("en-US", { style: "currency", currency, notation: "compact", maximumFractionDigits: 1 }).format(v);
    } catch {
      return `${(v / 1e6).toFixed(1)}M ${currency}`;
    }
  }
  try {
    return new Intl.NumberFormat("en-US", { style: "currency", currency, minimumFractionDigits: v < 100 ? 2 : 0, maximumFractionDigits: v < 100 ? 2 : 0 }).format(v);
  } catch {
    return `${v.toFixed(2)} ${currency}`;
  }
};

/** People counts: 940, 12.4k, 2.1M, 1.4B. */
export const people = (v: number | null | undefined) => {
  if (v == null || Number.isNaN(v)) return "–";
  if (v < 1000) return Math.round(v).toLocaleString("en-US");
  return new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: v < 1e4 || (v >= 1e6 && v < 1e7) ? 1 : 0 }).format(v);
};

export const int = (v: number | null | undefined) => (v == null || Number.isNaN(v) ? "–" : Math.round(v).toLocaleString("en-US"));

export const ago = (ts: number) => {
  const s = Math.max(0, Date.now() / 1000 - ts);
  if (s < 60) return "Just now";
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
  const d = Math.floor(s / 86400);
  if (d === 1) return "Yesterday";
  if (d < 14) return `${d} days ago`;
  return new Date(ts * 1000).toISOString().slice(0, 10);
};

const COMPANY: Record<string, string> = {
  self_employed: "Self-employed", startup: "Startup", scaleup: "Scale-up", smb: "Small business", midmarket: "Mid-market company",
  enterprise: "Large enterprise", government: "Government", none: "Not employed",
};
export const companyLabel = (s: string) => COMPANY[s] ?? s.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());

export const titleCase = (s: string) => s.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());

export const shortJob = (s: string) => s.split(" (")[0].trim();

/** Stance colour: teal for yes, amber for no, grey in between, with strength by distance from the middle. */
export function stanceFill(p: number, alpha = 1): string {
  const t = Math.max(0, Math.min(1, p));
  if (t >= 0.5) {
    const k = Math.round(35 + ((t - 0.5) / 0.5) * 65);
    return `color-mix(in oklab, var(--yes) ${Math.round(k * alpha)}%, var(--mid))`;
  }
  if (t <= 0.35) {
    const k = Math.round(35 + ((0.35 - t) / 0.35) * 65);
    return `color-mix(in oklab, var(--no) ${Math.round(k * alpha)}%, var(--mid))`;
  }
  return "var(--mid)";
}

export const stanceText = (p: number | null | undefined) => (p == null ? "text-muted" : p >= 0.55 ? "text-yes" : p <= 0.3 ? "text-no" : "text-muted");

export const cx = (...xs: (string | false | null | undefined)[]) => xs.filter(Boolean).join(" ");
