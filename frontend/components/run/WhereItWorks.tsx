"use client";

import { useMemo, useState } from "react";
import { BarRows } from "@/components/charts";
import { Card, CardHead, Segmented } from "@/components/ui";
import { WorldMap } from "@/components/world/WorldMap";
import { cx, int, pctSmart, signedPts } from "@/lib/format";
import type { LiveState } from "@/lib/useRunStream";
import type { Results, SplitCell } from "@/lib/types";
import type { GroupPreset } from "./AskGroup";

const ORDER = ["country", "region", "age", "gender", "income", "work", "segment", "company"];

function Spot({ c, tone, onAsk }: { c: SplitCell; tone: "hot" | "cold"; onAsk?: (g: GroupPreset) => void }) {
  return (
    <li className="flex items-baseline justify-between gap-4 border-b border-rule py-2.5 first:pt-0 last:border-0 last:pb-0">
      <div className="min-w-0">
        <div className="text-[14px] text-text">{c.label}</div>
        <div className="text-[12px] text-faint">
          {int(c.n)} people simulated, likely {pctSmart(c.ci[0])} to {pctSmart(c.ci[1])}
          {onAsk && c.keys && (
            <>
              {". "}
              <button type="button" onClick={() => onAsk({ keys: c.keys!, label: c.label })} className="text-muted underline underline-offset-2 hover:text-text">
                Ask them why
              </button>
            </>
          )}
        </div>
      </div>
      <div className="shrink-0 text-right">
        <div className={cx("num text-[16px]", tone === "hot" ? "text-yes" : "text-no")}>{pctSmart(c.value)}</div>
        <div className="num text-[12px] text-muted">{signedPts(c.vs_overall)} vs overall</div>
      </div>
    </li>
  );
}

/** Where the answer is clearly higher or lower than overall, and every breakdown. */
export function WhereItWorks({ r, live, measure, onAsk }: { r: Results; live: LiveState; measure: string; onAsk?: (g: GroupPreset) => void }) {
  const sp = r.splits!;
  const dims = useMemo(() => ORDER.filter((d) => sp.dimensions[d]), [sp]);
  const [dim, setDim] = useState(dims[0] ?? "country");
  const current = sp.dimensions[dim];
  const overall = r.headline.value;
  // Shade by distance from the overall answer, so the differences show even when every
  // country is well below or above 50%.
  const countryValues = useMemo(() => {
    const rows = sp.dimensions.country?.rows ?? [];
    const spread = Math.max(0.02, ...rows.map((row) => Math.abs(row.value - overall)));
    return Object.fromEntries(rows.map((row) => [row.key, 0.5 + ((row.value - overall) / spread) * 0.45]));
  }, [sp, overall]);

  return (
    <div className="grid grid-cols-1 items-start gap-6 lg:grid-cols-6">
      <Card className="lg:col-span-3">
        <CardHead title="Where it works best">Groups clearly above the overall {pctSmart(r.headline.value)}: their likely range sits entirely above it.</CardHead>
        {sp.hot.length ? (
          <ul>{sp.hot.map((c, i) => <Spot key={i} c={c} tone="hot" onAsk={onAsk} />)}</ul>
        ) : (
          <p className="text-[13px] leading-[18px] text-muted">No group is clearly above the overall answer. More people would make smaller differences visible.</p>
        )}
      </Card>
      <Card className="lg:col-span-3">
        <CardHead title="Where it struggles">Groups clearly below the overall answer.</CardHead>
        {sp.cold.length ? (
          <ul>{sp.cold.map((c, i) => <Spot key={i} c={c} tone="cold" onAsk={onAsk} />)}</ul>
        ) : (
          <p className="text-[13px] leading-[18px] text-muted">No group is clearly below the overall answer. More people would make smaller differences visible.</p>
        )}
      </Card>

      {sp.dimensions.country && sp.dimensions.country.rows.length > 1 && (
        <Card pad={false} className="lg:col-span-6">
          <div className="px-5 pt-5">
            <CardHead title="Around the world">{measure}, by country. Teal is above the overall {pctSmart(overall)}, amber below it.</CardHead>
          </div>
          <div className="px-2 pb-3">
            <WorldMap world={live.world} targets={Object.keys(countryValues)} values={countryValues} showArcs={false} compact label="Countries shaded by their answer" />
          </div>
        </Card>
      )}

      {current && (
        <Card className="lg:col-span-6">
          <CardHead title="Every breakdown" aside="Overall is the tick">
            {measure}. Only groups with at least {sp.min_n ?? 12} simulated people are shown.
          </CardHead>
          <div className="scroll-thin mb-4 max-w-full overflow-x-auto">
            <Segmented label="Break down by" value={dim} onChange={setDim} options={dims.map((d) => ({ value: d, label: sp.dimensions[d].label }))} />
          </div>
          <BarRows reference={r.headline.value} rows={current.rows.map((row) => ({ key: row.key, label: row.label, value: row.value, ci: row.ci, people: row.people, sub: `${row.n} simulated` }))} />
          {current.hidden > 0 && (
            <p className="mt-3 text-[12px] text-faint">
              {current.hidden} smaller {current.hidden === 1 ? "group" : "groups"} had too few simulated people to show on their own.
            </p>
          )}
        </Card>
      )}
    </div>
  );
}
