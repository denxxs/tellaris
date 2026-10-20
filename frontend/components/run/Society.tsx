"use client";

import { AnimatePresence, motion } from "motion/react";
import { useEffect, useMemo, useState } from "react";
import { LineChart } from "@/components/charts";
import { Avatar } from "@/components/people/Avatar";
import { FeedReachCard, PostReach } from "@/components/run/FeedReach";
import { Card, CardHead, Empty, Pill, Segmented, Select } from "@/components/ui";
import { api } from "@/lib/api";
import { useMeta } from "@/lib/meta";
import { companyLabel, cx, int, pctSmart, shortJob, signedPts, stanceFill, stanceText, titleCase } from "@/lib/format";
import type { LiveState } from "@/lib/useRunStream";
import type { FeedItem, ReflectionSummary, Results } from "@/lib/types";

type Filter = "all" | "talk" | "shifts" | "news" | "meetings";
type Order = "time" | "hot";

const DECISION_TONE = { buy: "yes", pilot: "yes", defer: "neutral", reject: "no" } as const;

function roundLabel(r: number) {
  return r === 0 ? "First reactions" : `Round ${r}`;
}

function Stance({ p }: { p?: number | null }) {
  if (p == null) return null;
  return <span className={cx("num text-[13px]", stanceText(p))}>{pctSmart(p)}</span>;
}

function Shift({ from, to, why }: { from: number; to: number; why?: string | null }) {
  const up = to > from;
  return (
    <div className="mt-2 flex flex-wrap items-baseline gap-x-2 rounded-md bg-raised px-2.5 py-1.5 text-[13px] leading-[18px]">
      <span className="text-muted">Changed their mind</span>
      <span className="num">
        {pctSmart(from)} to <span className={up ? "text-yes" : "text-no"}>{pctSmart(to)}</span>
      </span>
      {why && <span className="text-muted">: {why}</span>}
    </div>
  );
}

function PersonLine({ it, onSelect, size = 36 }: { it: FeedItem; onSelect: (id: string) => void; size?: number }) {
  const { countryName } = useMeta();
  return (
    <button onClick={() => it.author && onSelect(it.author)} className="flex min-w-0 items-center gap-2.5 text-left">
      <Avatar seed={it.author ?? it.id} size={size} ring={it.p != null ? stanceFill(it.p) : undefined} />
      <span className="min-w-0">
        <span className="block truncate text-[14px] font-medium text-text hover:underline">{it.author_name}</span>
        <span className="block truncate text-[12px] leading-4 text-faint">
          {shortJob(it.occupation ?? "")}, {countryName(it.country ?? "")}
        </span>
      </span>
    </button>
  );
}

function Post({ it, replies, onSelect }: { it: FeedItem; replies: FeedItem[]; onSelect: (id: string) => void }) {
  return (
    <article className="border-b border-rule py-4 first:pt-0 last:border-0">
      <header className="flex items-start justify-between gap-3">
        <PersonLine it={it} onSelect={onSelect} />
        <span className="flex shrink-0 items-center gap-2 text-[12px] text-faint">
          {roundLabel(it.round)}
          <Stance p={it.p} />
        </span>
      </header>
      <p className="mt-2 text-[15px] leading-[22px] text-text">{it.text}</p>
      {it.from_p != null && it.to_p != null && <Shift from={it.from_p} to={it.to_p} why={it.why} />}
      <footer className="mt-2 flex gap-4 text-[12px] text-muted">
        <span>
          <span className="num text-text">{it.agrees}</span> agreed
        </span>
        <span>
          <span className="num text-text">{it.disagrees}</span> disagreed
        </span>
        {replies.length > 0 && (
          <span>
            <span className="num text-text">{replies.length}</span> {replies.length === 1 ? "reply" : "replies"}
          </span>
        )}
      </footer>
      <PostReach likes={it.likes} reshares={it.reshares} by={it.reshared_by} seen={it.seen} outside={it.seen_outside} onSelect={onSelect} />
      {replies.length > 0 && (
        <div className="mt-3 flex flex-col gap-3 border-l-2 border-border pl-4">
          {replies.map((r) => (
            <div key={r.id}>
              <div className="flex items-start justify-between gap-3">
                <PersonLine it={r} onSelect={onSelect} size={28} />
                <span className="flex shrink-0 items-center gap-2 text-[12px] text-faint">
                  {roundLabel(r.round)}
                  <Stance p={r.p} />
                </span>
              </div>
              <p className="mt-1.5 text-[14px] leading-5 text-text">{r.text}</p>
              {r.from_p != null && r.to_p != null && <Shift from={r.from_p} to={r.to_p} why={r.why} />}
              <PostReach likes={r.likes} reshares={r.reshares} by={r.reshared_by} onSelect={onSelect} />
            </div>
          ))}
        </div>
      )}
    </article>
  );
}

function News({ it }: { it: FeedItem }) {
  const { countryName } = useMeta();
  return (
    <article className="my-1 border-b border-rule py-4 first:pt-0 last:border-0">
      <div className="rounded-lg border-l-[3px] border-flow bg-flow-soft px-4 py-3">
        <div className="flex items-baseline justify-between gap-3 text-[12px] text-muted">
          <span>
            News from {it.origin === "global" ? "around the world" : countryName(it.origin ?? "")}
          </span>
          <span>{roundLabel(it.round)}</span>
        </div>
        <h3 className="mt-0.5 text-[15px] font-medium text-text">{it.title}</h3>
        <p className="mt-0.5 text-[14px] leading-5 text-muted">{it.text.replace(`${it.title}: `, "")}</p>
      </div>
    </article>
  );
}

function Meeting({ it, onSelect }: { it: FeedItem; onSelect: (id: string) => void }) {
  const { countryName } = useMeta();
  const [open, setOpen] = useState(false);
  const d = it.decision!;
  return (
    <article className="border-b border-rule py-4 first:pt-0 last:border-0">
      <div className="rounded-lg border border-border px-4 py-3">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="text-[12px] text-muted">Buying meeting</div>
            <h3 className="text-[15px] font-medium">
              {companyLabel(it.company_type ?? "")} in {countryName(it.country ?? "")}
              <span className="font-normal text-muted">, {int(it.company_size)} staff</span>
            </h3>
          </div>
          <span className="flex items-center gap-2">
            <Pill tone={DECISION_TONE[d.decision]}>{titleCase(d.decision)}</Pill>
            <span className="num text-[13px] text-muted">{pctSmart(d.probability_of_purchase)}</span>
          </span>
        </div>
        <div className="mt-2 flex -space-x-2">
          {(it.members ?? []).map((m) => (
            <button key={m.persona_id} onClick={() => onSelect(m.persona_id)} title={`${m.name}, ${titleCase(m.role)}`}>
              <Avatar seed={m.persona_id} size={28} className="ring-2 ring-surface" />
            </button>
          ))}
        </div>
        <p className="mt-2 text-[14px] leading-5 text-muted">{d.summary}</p>
        <button className="mt-2 text-[13px] font-medium text-text hover:underline" onClick={() => setOpen(!open)} aria-expanded={open}>
          {open ? "Hide the meeting" : `Read the meeting (${it.transcript?.length ?? 0} statements)`}
        </button>
        {open && (
          <div className="mt-3 flex flex-col gap-3">
            {(it.transcript ?? []).map((t, i) => (
              <div key={i} className="flex gap-2.5">
                <button onClick={() => onSelect(t.persona_id)}>
                  <Avatar seed={t.persona_id} size={28} />
                </button>
                <div className="min-w-0">
                  <div className="text-[13px]">
                    <span className="font-medium text-text">{t.name}</span>
                    <span className="text-faint">, {titleCase(t.role)}, round {t.round + 1}</span>
                  </div>
                  <p className={cx("mt-0.5 border-l-2 pl-2.5 text-[14px] leading-5", t.stance >= 0.2 ? "border-yes" : t.stance <= -0.2 ? "border-no" : "border-control")}>{t.statement}</p>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </article>
  );
}

function ShiftLine({ it, onSelect }: { it: FeedItem; onSelect: (id: string) => void }) {
  return (
    <div className="flex items-center gap-2.5 border-b border-rule py-3 text-[13px] first:pt-0 last:border-0">
      <button onClick={() => it.author && onSelect(it.author)}>
        <Avatar seed={it.author ?? it.id} size={24} />
      </button>
      <span className="min-w-0 text-muted">
        <button className="font-medium text-text hover:underline" onClick={() => it.author && onSelect(it.author)}>
          {it.author_name}
        </button>{" "}
        quietly moved from <span className="num">{pctSmart(it.from_p)}</span> to{" "}
        <span className={cx("num", (it.to_p ?? 0) > (it.from_p ?? 0) ? "text-yes" : "text-no")}>{pctSmart(it.to_p)}</span>
        {it.text && <>: {it.text}</>}
      </span>
      <span className="ml-auto shrink-0 text-[12px] text-faint">{roundLabel(it.round)}</span>
    </div>
  );
}

export function SocietyFeed({ id, live, r, onSelect, compact }: { id: string; live: LiveState; r: Results | null; onSelect: (pid: string) => void; compact?: boolean }) {
  const { countryName } = useMeta();
  const [loaded, setLoaded] = useState<FeedItem[] | null>(null);
  const [filter, setFilter] = useState<Filter>("all");
  const [order, setOrder] = useState<Order>("time");
  const [upTo, setUpTo] = useState<string>("all");
  const [country, setCountry] = useState("");

  // Live runs stream the feed; older runs are fetched once.
  useEffect(() => {
    if (!live.feed.length && r) api.feed(id).then(setLoaded).catch(() => setLoaded([]));
  }, [id, live.feed.length, r]);
  const all = useMemo(() => (live.feed.length ? live.feed : loaded ?? []), [live.feed, loaded]);
  const maxRound = all.reduce((m, it) => Math.max(m, it.round), 0);

  const { tops, repliesOf } = useMemo(() => {
    const limit = upTo === "all" ? Infinity : Number(upTo);
    const items = all.filter((it) => it.round <= limit && (!country || !it.country || it.country === country));
    const byId = new Map(items.map((it) => [it.id, it]));
    const rootOf = (it: FeedItem): string => {
      let cur = it;
      for (let i = 0; i < 6 && cur.parent && byId.get(cur.parent); i++) cur = byId.get(cur.parent)!;
      return cur.id;
    };
    const repliesOf = new Map<string, FeedItem[]>();
    const tops: FeedItem[] = [];
    for (const it of items) {
      if (it.kind === "reply" && it.parent && byId.has(it.parent)) {
        const root = rootOf(it);
        repliesOf.set(root, [...(repliesOf.get(root) ?? []), it]);
      } else tops.push(it);
    }
    return { tops, repliesOf };
  }, [all, upTo, country]);

  const shown = useMemo(() => {
    let xs = tops.filter((it) => {
      if (filter === "talk") return it.kind === "post" || it.kind === "reply";
      if (filter === "news") return it.kind === "news";
      if (filter === "meetings") return it.kind === "meeting";
      if (filter === "shifts") return it.kind === "shift" || it.from_p != null || (repliesOf.get(it.id) ?? []).some((x) => x.from_p != null);
      return true;
    });
    const heat = (x: FeedItem) => (repliesOf.get(x.id)?.length ?? 0) * 3 + x.agrees + x.disagrees + (x.likes ?? 0) + (x.reshares ?? 0) * 2;
    if (order === "hot") xs = [...xs].sort((a, b) => heat(b) - heat(a));
    else xs = [...xs].sort((a, b) => a.round - b.round || (a.kind === "news" ? -1 : b.kind === "news" ? 1 : 0));
    return xs;
  }, [tops, filter, order, repliesOf]);

  const countries = useMemo(() => [...new Set(all.map((it) => it.country).filter(Boolean) as string[])].sort(), [all]);
  const [limit, setLimit] = useState(40);
  useEffect(() => setLimit(40), [filter, order, upTo, country]);

  if (!all.length) {
    return <Empty title={live.status === "done" ? "No conversation recorded" : "The conversation starts after everyone has answered"}>{live.status === "done" ? "This run didn't simulate people talking. Run it again to see the society." : "People post their first takes, then reply to each other round by round."}</Empty>;
  }

  return (
    <div>
      {!compact && (
        <div className="mb-4 flex flex-col gap-2 xl:flex-row xl:items-center">
          <div className="scroll-thin max-w-full overflow-x-auto">
          <Segmented
            label="Show"
            value={filter}
            onChange={setFilter}
            options={[
              { value: "all", label: "Everything" },
              { value: "talk", label: "Posts" },
              { value: "shifts", label: "Changed minds" },
              { value: "news", label: "News" },
              { value: "meetings", label: "Meetings" },
            ]}
          />
          </div>
          <div className="flex flex-wrap gap-2 xl:ml-auto">
            <Select
              label="Replay up to"
              value={upTo}
              onChange={setUpTo}
              options={[{ value: "all", label: "Whole conversation" }, ...Array.from({ length: maxRound + 1 }, (_, i) => ({ value: String(i), label: `Up to ${roundLabel(i).toLowerCase()}` }))]}
              className="w-48"
            />
            {countries.length > 1 && <Select label="Country" value={country} onChange={setCountry} options={[{ value: "", label: "All countries" }, ...countries.map((c) => ({ value: c, label: countryName(c) }))]} className="w-40" />}
            <Select
              label="Order"
              value={order}
              onChange={(v) => setOrder(v as Order)}
              options={[
                { value: "time", label: "As it happened" },
                { value: "hot", label: "Most discussed" },
              ]}
              className="w-40"
            />
          </div>
        </div>
      )}
      <div>
        <AnimatePresence initial={false}>
          {(compact ? [...shown].reverse().slice(0, 4) : shown.slice(0, limit)).map((it) => (
            <motion.div key={it.id} layout="position" initial={{ opacity: 0, y: -6 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.25 }}>
              {it.kind === "news" ? <News it={it} /> : it.kind === "meeting" ? <Meeting it={it} onSelect={onSelect} /> : it.kind === "shift" ? <ShiftLine it={it} onSelect={onSelect} /> : <Post it={it} replies={repliesOf.get(it.id) ?? []} onSelect={onSelect} />}
            </motion.div>
          ))}
        </AnimatePresence>
        {shown.length === 0 && <p className="text-[13px] text-muted">Nothing matches these filters.</p>}
        {!compact && shown.length > limit && (
          <button className="mt-3 text-[13px] font-medium text-text hover:underline" onClick={() => setLimit(limit + 40)}>
            Show more ({shown.length - limit} left)
          </button>
        )}
      </div>
    </div>
  );
}

/** Where people landed after thinking over what they remembered, and what moved them. */
function ReflectionCard({ rf, onSelect }: { rf: ReflectionSummary; onSelect: (pid: string) => void }) {
  const delta = (rf.after ?? 0) - (rf.before ?? 0);
  const quotes = (rf.examples ?? []).filter((e) => Math.abs(e.to - e.from) >= 0.08).slice(0, 3);
  return (
    <Card>
      <CardHead title="After reflecting">
        Each person thought over what they remembered. {int(rf.changed_mind ?? 0)} of {int(rf.people)} changed their minds.
      </CardHead>
      <div className="flex items-baseline gap-3">
        <span className="t-kpi">{pctSmart(rf.after)}</span>
        <span className="text-[13px] text-muted">
          from {pctSmart(rf.before)} at the end of the talk,{" "}
          <span className={cx("num", delta > 0.005 ? "text-yes" : delta < -0.005 ? "text-no" : "text-muted")}>{signedPts(delta)}</span>
        </span>
      </div>
      {rf.moved_by && rf.moved_by.length > 0 && (
        <div className="mt-4">
          <h3 className="mb-2 text-[13px] font-medium">What moved people</h3>
          <ul className="flex flex-col gap-1.5">
            {rf.moved_by.map((m) => (
              <li key={m.kind} className="grid grid-cols-[minmax(0,1fr)_minmax(0,1fr)_40px] items-center gap-2 text-[13px]">
                <span className="truncate text-text">{m.label.replace(/^./, (c) => c.toUpperCase())}</span>
                <span className="h-1.5 rounded-full bg-raised">
                  <span className="block h-full rounded-full bg-yes" style={{ width: `${m.share * 100}%` }} />
                </span>
                <span className="num text-right text-muted">{pctSmart(m.share)}</span>
              </li>
            ))}
          </ul>
          {!!rf.nothing_moved && <p className="mt-2 text-[12px] text-faint">{int(rf.nothing_moved)} people said nothing they saw moved them.</p>}
        </div>
      )}
      {quotes.length > 0 && (
        <ul className="mt-4 border-t border-rule pt-3">
          {quotes.map((e) => (
            <li key={e.persona_id} className="py-1.5">
              <button onClick={() => onSelect(e.persona_id)} className="flex w-full items-start gap-2.5 text-left">
                <Avatar seed={e.persona_id} size={28} ring={stanceFill(e.to)} />
                <span className="min-w-0 flex-1 text-[13px] leading-[18px]">
                  <span className="flex justify-between gap-2">
                    <span className="truncate text-text">{e.name}</span>
                    <span className="num shrink-0">
                      {pctSmart(e.from)} to <span className={e.to > e.from ? "text-yes" : "text-no"}>{pctSmart(e.to)}</span>
                    </span>
                  </span>
                  <span className="text-muted">“{e.belief}”</span>
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

export function SocietyTab({ id, live, r, onSelect }: { id: string; live: LiveState; r: Results; onSelect: (pid: string) => void }) {
  const { countryName } = useMeta();
  const d = r.diffusion;
  const soc = d?.society;
  return (
    <div className="grid grid-cols-1 items-start gap-6 lg:grid-cols-6">
      {soc && (
        <Card pad={false} className="grid grid-cols-2 lg:col-span-6 lg:grid-cols-5">
          {[
            ["Posts", soc.posts, "takes shared with their networks"],
            ["Replies", soc.replies, "people answering each other"],
            ["Changed their mind", soc.shifts, "moved by what they read"],
            ["News", soc.news, "outside events that landed"],
            ["Meetings", soc.meetings, "companies deciding together"],
          ].map(([label, v, sub], i) => (
            <div key={label as string} className={cx("p-5", i < 4 && "lg:border-r", i % 2 === 0 && "border-r lg:border-r", "border-b border-border lg:border-b-0")}>
              <div className="text-[13px] text-muted">{label}</div>
              <div className="t-kpi mt-1">{int(v as number)}</div>
              <div className="mt-1 text-[12px] leading-4 text-faint">{sub}</div>
            </div>
          ))}
        </Card>
      )}
      <Card className="lg:col-span-4">
        <CardHead title="The conversation">
          {d ? `${d.agents} people talking with about ${Math.round((d.edges * 2) / Math.max(d.agents, 1))} contacts each, over ${d.rounds.length - 1} rounds.` : "People reacting to each other."} Select anyone to open their profile.
        </CardHead>
        <SocietyFeed id={id} live={live} r={r} onSelect={onSelect} />
      </Card>
      <div className="flex flex-col gap-6 lg:col-span-2">
        {d?.feed && <FeedReachCard id={id} f={d.feed} people={d.agents} cmp={r.comparison} onSelect={onSelect} />}
        {d && d.rounds.length > 1 && (
          <Card>
            <CardHead title="Opinion as they talk">How the share leaning yes moved, round by round.</CardHead>
            <LineChart
              height={180}
              xLabel="round"
              xFormat={(x) => (x === 0 ? "Start" : `R${x}`)}
              series={[{ id: "all", label: "Everyone", color: "var(--yes)", points: d.rounds.map((x) => ({ x: x.round, y: x.calibrated })) }]}
            />
          </Card>
        )}
        {d?.reflection && d.reflection.people > 0 && <ReflectionCard rf={d.reflection} onSelect={onSelect} />}
        {soc && soc.top_voices.length > 0 && (
          <Card>
            <CardHead title="Loudest voices">Who posted most and drew the most agreement.</CardHead>
            <ul>
              {soc.top_voices.map((v) => (
                <li key={v.persona_id} className="border-b border-rule py-2 first:pt-0 last:border-0 last:pb-0">
                  <button onClick={() => onSelect(v.persona_id)} className="flex w-full items-center gap-2.5 text-left">
                    <Avatar seed={v.persona_id} size={32} ring={v.p != null ? stanceFill(v.p) : undefined} />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-[14px] text-text">{v.name}</span>
                      <span className="block truncate text-[12px] text-faint">
                        {shortJob(v.occupation)}, {countryName(v.country)}
                      </span>
                    </span>
                    <span className="shrink-0 text-right text-[12px] text-muted">
                      <span className="num block text-text">{v.items}</span>
                      {v.items === 1 ? "post" : "posts"}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </Card>
        )}
        {d && d.examples.length > 0 && (
          <Card>
            <CardHead title="Minds changed" />
            <ul>
              {d.examples.slice(0, 6).map((e) => (
                <li key={`${e.persona_id}-${e.round}`} className="border-b border-rule py-2 first:pt-0 last:border-0 last:pb-0">
                  <button onClick={() => onSelect(e.persona_id)} className="flex w-full items-start gap-2.5 text-left">
                    <Avatar seed={e.persona_id} size={28} />
                    <span className="min-w-0 flex-1 text-[13px] leading-[18px]">
                      <span className="flex justify-between gap-2">
                        <span className="truncate text-text">{e.name}</span>
                        <span className="num shrink-0">
                          {pctSmart(e.from)} to <span className={e.to > e.from ? "text-yes" : "text-no"}>{pctSmart(e.to)}</span>
                        </span>
                      </span>
                      <span className="text-muted">{e.why}</span>
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </Card>
        )}
      </div>
    </div>
  );
}
