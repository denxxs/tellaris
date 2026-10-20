export const pct = (v: number | null | undefined, digits = 0) =>
  v == null || Number.isNaN(v) ? "–" : `${(v * 100).toFixed(digits)}%`;

/** Percentage with one decimal under 10%, so small numbers keep meaning. */
export const pctSmart = (v: number | null | undefined) => {
  if (v == null || Number.isNaN(v)) return "–";
  const x = v * 100;
  if (x > 0 && x < 1) return `${x.toFixed(1)}%`;
  if (x < 10) return `${x.toFixed(1)}%`;
  return `${Math.round(x)}%`;
};

export const signedPts = (v: number | null | undefined) => {
  if (v == null || Number.isNaN(v)) return "–";
  const x = v * 100;
  const s = Math.abs(x) < 10 ? x.toFixed(1) : Math.round(x).toString();
  return `${x > 0 ? "+" : x < 0 ? "" : "±"}${s} pts`;
};

export const money = (v: number | null | undefined, currency = "USD") => {
  if (v == null || Number.isNaN(v)) return "–";
  try {
    return new Intl.NumberFormat("en-US", { style: "currency", currency, maximumFractionDigits: v < 100 ? 2 : 0 }).format(v);
  } catch {
    return `${v.toFixed(2)} ${currency}`;
  }
};

export const compact = (v: number) => new Intl.NumberFormat("en-US", { notation: "compact", maximumFractionDigits: 1 }).format(v);

export const ago = (ts: number) => {
  const s = Math.max(0, Date.now() / 1000 - ts);
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
  const d = Math.floor(s / 86400);
  if (d < 14) return `${d} day${d === 1 ? "" : "s"} ago`;
  return new Date(ts * 1000).toLocaleDateString();
};

const COMPANY: Record<string, string> = {
  self_employed: "Self-employed", startup: "Startup", scaleup: "Scale-up", smb: "Small business", midmarket: "Mid-market company",
  enterprise: "Large enterprise", government: "Government", none: "Not employed",
};
export const companyLabel = (s: string) => COMPANY[s] ?? s.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());

export const titleCase = (s: string) => s.replace(/_/g, " ").replace(/^\w/, (c) => c.toUpperCase());

/** Diverging colour for a 0..1 likelihood: raspberry -> neutral -> teal. */
export function stanceColor(p: number | null | undefined): string {
  if (p == null) return "var(--mid)";
  if (p >= 0.55) return "var(--yes)";
  if (p <= 0.3) return "var(--no)";
  return "var(--mid)";
}

export function stanceMix(p: number): string {
  // Smooth mix for dots: below 0.5 towards --no, above towards --yes.
  const t = Math.max(0, Math.min(1, p));
  if (t < 0.42) return `color-mix(in oklab, var(--no) ${Math.round(((0.42 - t) / 0.42) * 70 + 30)}%, var(--mid))`;
  if (t > 0.5) return `color-mix(in oklab, var(--yes) ${Math.round(((t - 0.5) / 0.5) * 70 + 30)}%, var(--mid))`;
  return "var(--mid)";
}

export const cx = (...xs: (string | false | null | undefined)[]) => xs.filter(Boolean).join(" ");
