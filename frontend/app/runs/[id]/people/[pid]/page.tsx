"use client";

import Link from "next/link";
import { use, useEffect, useState } from "react";
import { PersonaChat } from "@/components/people/Chat";
import { Avatar } from "@/components/people/Avatar";
import { MindCard } from "@/components/people/MindCard";
import { REACH_LABEL, fmtDay } from "@/components/run/NewsTimeline";
import { Card, CardHead, Chip, ErrorNote, Pill, Skeleton } from "@/components/ui";
import { api } from "@/lib/api";
import { useMeta } from "@/lib/meta";
import { companyLabel, cx, money, people, pctSmart, shortJob, stanceFill, stanceText, titleCase } from "@/lib/format";
import type { FeedItem, Profile, Run } from "@/lib/types";

const FACT_TEXT: Record<string, [string, string]> = {
  internet_daily: ["Uses the internet every day", "Doesn't use the internet every day"],
  smartphone: ["Main phone is a smartphone", "Main phone isn't a smartphone"],
  account: ["Has a bank or mobile-money account", "Has no bank or mobile-money account"],
  credit_card: ["Has a credit card", "Has no credit card"],
  emergency_hard: ["Would struggle to find emergency money within a month", "Could find emergency money within a month"],
  news_online: ["Read news online in the past three months", "Hasn't read news online lately"],
};

const TRAIT_LABEL: Record<string, string> = {
  tech_affinity: "Comfort with technology",
  skepticism: "Scepticism",
  risk_appetite: "Appetite for risk",
  price_sensitivity: "Price sensitivity",
  conformity: "Follows their peers",
  openness: "Openness to new ideas",
  budget_authority: "Can approve spending",
};
const ROLE_LABEL: Record<string, string> = {
  economic_buyer: "Signs off on spending",
  champion: "Pushes for new tools",
  technical: "Judges whether it works",
  security_legal: "Checks the risk",
  procurement: "Negotiates the deal",
  end_user: "Uses it day to day",
  none: "Not part of buying decisions",
};

function Fact({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <dt className="text-[12px] text-faint">{label}</dt>
      <dd className="mt-0.5 text-[14px] leading-5 text-text">{children}</dd>
    </div>
  );
}

function SaidItem({ it, parent }: { it: FeedItem; parent?: FeedItem }) {
  return (
    <li className="border-b border-rule py-3 first:pt-0 last:border-0 last:pb-0">
      {parent && (
        <div className="mb-2 flex items-start gap-2 text-[13px] leading-[18px] text-muted">
          <Avatar seed={parent.author ?? parent.id} size={20} className="mt-px" />
          <span>
            <span className="text-text">{parent.author_name}</span>: {parent.text}
          </span>
        </div>
      )}
      <p className={cx("text-[15px] leading-[22px]", parent && "border-l-2 border-border pl-3")}>{it.text}</p>
      <div className="mt-1 text-[12px] text-faint">
        {it.kind === "reply" ? "Replied" : "Posted"} {it.round === 0 ? "in their first reaction" : `in round ${it.round}`}. {it.agrees} people who saw it agreed, {it.disagrees} disagreed
        {it.from_p != null && it.to_p != null && (
          <>
            . Moved from {pctSmart(it.from_p)} to <span className={stanceText(it.to_p)}>{pctSmart(it.to_p)}</span>
          </>
        )}
        .
      </div>
    </li>
  );
}

export default function ProfilePage({ params }: { params: Promise<{ id: string; pid: string }> }) {
  const { id, pid } = use(params);
  const { countryName } = useMeta();
  const [data, setData] = useState<Profile | null>(null);
  const [run, setRun] = useState<Run | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    setData(null);
    api.persona(id, pid).then(setData).catch((e) => setErr(e.message));
    api.run(id).then(setRun).catch(() => {});
  }, [id, pid]);

  useEffect(() => {
    if (data) document.title = `${data.persona.name} | Oracle`;
  }, [data]);

  const p = data?.persona;
  const rs = data?.reactions ?? [];
  const r0 = rs[0];
  const mean = rs.length ? rs.reduce((a, r) => a + r.p_stated, 0) / rs.length : null;
  const finalP = data?.society.final_p ?? null;
  const said = (data?.society.mine ?? []).filter((m) => m.kind === "post" || m.kind === "reply");
  const shifts = (data?.society.mine ?? []).filter((m) => m.kind === "shift");
  const parentById = new Map((data?.society.context ?? []).map((c) => [c.id, c]));
  const runTitle = run?.spec?.title ?? run?.title ?? "Simulation";

  return (
    <div className="mx-auto max-w-[1312px] px-4 py-6 md:px-6">
      <nav aria-label="Breadcrumb" className="mb-4 flex flex-wrap gap-x-1.5 text-[13px] text-muted">
        <Link href="/runs" className="hover:text-text">
          Simulations
        </Link>
        <span className="text-faint">/</span>
        <Link href={`/runs/${id}`} className="max-w-[280px] truncate hover:text-text">
          {runTitle}
        </Link>
        <span className="text-faint">/</span>
        <span className="text-text">{p?.name ?? "Person"}</span>
      </nav>

      {err && <ErrorNote>{err}</ErrorNote>}
      {!p && !err && (
        <div className="flex items-center gap-4">
          <Skeleton className="size-20 rounded-full" />
          <div className="flex flex-col gap-2">
            <Skeleton className="h-6 w-56" />
            <Skeleton className="h-4 w-80" />
          </div>
        </div>
      )}

      {p && data && (
        <>
          <header className="mb-6 flex flex-wrap items-center gap-5">
            <Avatar seed={p.id} size={84} ring={mean != null ? stanceFill(mean) : undefined} />
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2.5">
                <h1 className="t-title">{p.name}</h1>
                {p.influencer_voice && <Pill>Outside voice from {countryName(p.influencer_voice)}</Pill>}
                {!p.is_buyer && !p.influencer_voice && <Pill>Context only, not counted</Pill>}
              </div>
              {p.tagline && <p className="mt-0.5 text-[15px] text-text">{p.tagline}</p>}
              <p className="mt-1 text-[13px] text-muted">
                {p.age}-year-old {p.gender}, {shortJob(p.occupation)} ({p.seniority}) at a {companyLabel(p.company_type).toLowerCase()} in {countryName(p.country)}. In the group “{p.segment}”.
              </p>
            </div>
            <dl className="flex flex-wrap gap-x-8 gap-y-3">
              <div>
                <dt className="text-[13px] text-muted">First answer</dt>
                <dd className={cx("t-kpi mt-1", stanceText(mean))}>{pctSmart(mean)}</dd>
              </div>
              {finalP != null && (
                <div>
                  <dt className="text-[13px] text-muted">After the conversation</dt>
                  <dd className={cx("t-kpi mt-1", stanceText(finalP))}>{pctSmart(finalP)}</dd>
                </div>
              )}
              {p?.mind?.reflection && (
                <div>
                  <dt className="text-[13px] text-muted">After reflecting</dt>
                  <dd className={cx("t-kpi mt-1", stanceText(p.mind.reflection.p))}>{pctSmart(p.mind.reflection.p)}</dd>
                </div>
              )}
            </dl>
          </header>

          <div className="grid grid-cols-1 items-start gap-6 lg:grid-cols-12">
            <div className="flex flex-col gap-6 lg:col-span-8">
              {r0 && (
                <Card>
                  <CardHead title="What they decided" aside={rs.length > 1 ? `Asked ${rs.length} times` : undefined}>
                    {run?.spec?.persona_question}
                  </CardHead>
                  <blockquote className="text-[18px] leading-[26px] text-text">“{r0.quote}”</blockquote>
                  <div className="mt-5 grid gap-6 sm:grid-cols-2">
                    <div>
                      <h3 className="mb-1.5 text-[14px] font-medium text-yes">Reasons for</h3>
                      <ul className="flex flex-col gap-1.5 text-[14px] leading-5">{r0.reasons.map((x, i) => <li key={i}>{x}</li>)}</ul>
                    </div>
                    <div>
                      <h3 className="mb-1.5 text-[14px] font-medium text-no">Reasons against</h3>
                      <ul className="flex flex-col gap-1.5 text-[14px] leading-5">{r0.objections.map((x, i) => <li key={i}>{x}</li>)}</ul>
                    </div>
                  </div>
                  <dl className="mt-5 grid gap-4 rounded-lg bg-raised p-4 sm:grid-cols-3">
                    <Fact label="Would change their mind if">{r0.change_mind.join("; ") || "–"}</Fact>
                    <Fact label="Would pay up to">{r0.willingness_to_pay != null ? money(r0.willingness_to_pay) : "–"}</Fact>
                    <Fact label="How much attention they'd give it">{titleCase(r0.attention)}</Fact>
                  </dl>
                  {rs.length > 1 && (
                    <p className="mt-3 text-[12px] text-faint">
                      Each answer, by model: {rs.map((r) => `${pctSmart(r.p_stated)} (${r.model})`).join(", ")}.
                    </p>
                  )}
                </Card>
              )}

              {p?.news && p.news.length > 0 && (
                <Card>
                  <CardHead title="News they know">Real stories {p.name.split(" ")[0]} has come across, given where they live, their work and age.</CardHead>
                  <ul>
                    {p.news.map((n) => (
                      <li key={n.id} className="border-b border-rule py-2.5 first:pt-0 last:border-0 last:pb-0">
                        <div className="text-[12px] text-faint">
                          {fmtDay(n.published)}, {n.source}, {REACH_LABEL[n.reach].toLowerCase()}
                        </div>
                        <a href={n.url} target="_blank" rel="noreferrer" className="text-[14px] leading-5 text-text hover:underline">
                          {n.headline}
                        </a>
                      </li>
                    ))}
                  </ul>
                </Card>
              )}

              {p?.mind && p.mind.memories.length > 0 && <MindCard mind={p.mind} name={p.name} />}

              <Card>
                <CardHead title="In the conversation">{said.length ? `${said.length} ${said.length === 1 ? "thing" : "things"} they said to their network.` : "They read what others said but did not post."}</CardHead>
                {said.length > 0 ? (
                  <ul>
                    {said.map((m) => (
                      <SaidItem key={m.id} it={m} parent={m.parent ? parentById.get(m.parent) : undefined} />
                    ))}
                  </ul>
                ) : null}
                {shifts.length > 0 && (
                  <div className="mt-4 rounded-lg bg-raised px-4 py-3 text-[13px] leading-[18px]">
                    {shifts.map((s) => (
                      <p key={s.id}>
                        In round {s.round} they quietly moved from {pctSmart(s.from_p)} to <span className={stanceText(s.to_p)}>{pctSmart(s.to_p)}</span>: {s.text}
                      </p>
                    ))}
                  </div>
                )}
                {data.society.replies.length > 0 && (
                  <div className="mt-5">
                    <h3 className="mb-2 text-[14px] font-medium">Replies they got</h3>
                    <ul className="flex flex-col gap-3">
                      {data.society.replies.map((rep) => (
                        <li key={rep.id} className="flex items-start gap-2.5">
                          <Link href={`/runs/${id}/people/${rep.author}`}>
                            <Avatar seed={rep.author ?? rep.id} size={28} ring={rep.p != null ? stanceFill(rep.p) : undefined} />
                          </Link>
                          <div className="text-[14px] leading-5">
                            <Link href={`/runs/${id}/people/${rep.author}`} className="font-medium hover:underline">
                              {rep.author_name}
                            </Link>
                            <span className="text-[12px] text-faint">, {shortJob(rep.occupation ?? "")}</span>
                            <p>{rep.text}</p>
                          </div>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </Card>

              <div className="gap-6 xl:columns-2 [&>*]:mb-6 [&>*]:break-inside-avoid">
                <Card>
                  <CardHead title="Their story" />
                  {p.bio && <p className="text-[15px] leading-[22px]">{p.bio}</p>}
                  <dl className="mt-4 flex flex-col gap-3">
                    {p.typical_day && <Fact label="A typical day">{p.typical_day}</Fact>}
                    {p.household && <Fact label="Home">{p.household}</Fact>}
                    {p.voice && <Fact label="How they talk">{p.voice}</Fact>}
                  </dl>
                  {p.values.length > 0 && (
                    <div className="mt-4">
                      <div className="mb-1.5 text-[12px] text-faint">What they value</div>
                      <div className="flex flex-wrap gap-1.5">{p.values.map((v) => <Chip key={v}>{v}</Chip>)}</div>
                    </div>
                  )}
                  <p className="mt-4 text-[12px] leading-4 text-faint">Name and story written by the model from the facts on this page, to give them a human face. They aren&apos;t used in their answers.</p>
                </Card>
                <Card>
                  <CardHead title="Work and money" />
                  <dl className="grid grid-cols-2 gap-4">
                    <Fact label="Job">{shortJob(p.occupation)}</Fact>
                    <Fact label="Seniority">{titleCase(p.seniority)}</Fact>
                    <Fact label="Company">
                      {companyLabel(p.company_type)}
                      {p.company_size_text && p.company_size_text !== "1 person" && <span className="text-muted">, {p.company_size_text}</span>}
                    </Fact>
                    <Fact label="Sector">{titleCase(p.sector)}</Fact>
                    <Fact label="Earnings">
                      {p.income_usd != null ? (
                        <>
                          <span className="num">{money(p.income_usd)}</span> a year, {p.income_band}
                        </>
                      ) : p.seniority === "none" ? (
                        "None of their own"
                      ) : (
                        <span className="text-muted">No data for this kind of work</span>
                      )}
                    </Fact>
                    <Fact label="In buying decisions">{ROLE_LABEL[p.buyer_role] ?? titleCase(p.buyer_role)}</Fact>
                  </dl>
                  {p.tools_today.length > 0 && (
                    <div className="mt-4">
                      <div className="mb-1.5 text-[12px] text-faint">Uses today</div>
                      <div className="flex flex-wrap gap-1.5">{p.tools_today.map((t) => <Chip key={t}>{t}</Chip>)}</div>
                    </div>
                  )}
                  <p className="mt-4 text-[12px] leading-4 text-faint">Job, gender and age drawn from ILOSTAT employment data for {p.country_name}; earnings from ILOSTAT mean earnings for the job group, spread by the World Bank Gini index.</p>
                </Card>
                {(p.priorities.length > 0 || p.frustrations.length > 0 || p.info_sources.length > 0) && (
                  <Card>
                    <CardHead title="What's on their mind">Written by the model in an older version of Oracle.</CardHead>
                    <dl className="flex flex-col gap-3">
                      {p.priorities.length > 0 && <Fact label="Priorities right now">{p.priorities.join("; ")}</Fact>}
                      {p.frustrations.length > 0 && <Fact label="Frustrations">{p.frustrations.join("; ")}</Fact>}
                      {p.info_sources.length > 0 && <Fact label="Where they get information">{p.info_sources.join(", ")}</Fact>}
                    </dl>
                  </Card>
                )}
                {p.facts && Object.keys(p.facts).length > 0 && (
                  <Card>
                    <CardHead title="Everyday facts">Drawn from World Bank Global Findex rates for people of their country, gender, age and income.</CardHead>
                    <ul className="flex flex-col gap-1.5 text-[14px] leading-5">
                      {Object.entries(p.facts).map(([k, v]) => (
                        <li key={k} className="flex gap-2">
                          <span aria-hidden className={cx("mt-[7px] h-1.5 w-1.5 shrink-0 rounded-full", v ? "bg-text" : "bg-control")} />
                          {FACT_TEXT[k]?.[v ? 0 : 1] ?? titleCase(k)}
                        </li>
                      ))}
                    </ul>
                  </Card>
                )}
                {(p.views_text?.views?.length ?? 0) > 0 && (
                  <Card>
                    <CardHead title="Their views">
                      Answers of a real {p.country_name} respondent to the World Values Survey ({p.views_from?.year}), matched on{" "}
                      {(p.views_from?.matched_on ?? []).join(", ") || "country"}.
                    </CardHead>
                    <ul className="flex flex-col gap-1.5 text-[14px] leading-5">
                      {p.views_text!.views!.map((t) => (
                        <li key={t}>{t}</li>
                      ))}
                    </ul>
                    {(p.views_text?.news?.length ?? 0) > 0 && (
                      <>
                        <h3 className="mt-4 text-[13px] text-muted">How often they get news from</h3>
                        <dl className="mt-1.5 grid grid-cols-[1fr_auto] gap-x-4 gap-y-1 text-[14px] leading-5">
                          {p.views_text!.news!.map((t) => {
                            const [k, v] = t.split(": ");
                            return (
                              <div key={k} className="contents">
                                <dt className="text-muted">{k}</dt>
                                <dd className="text-text">{v}</dd>
                              </div>
                            );
                          })}
                        </dl>
                      </>
                    )}
                  </Card>
                )}
                {Object.values(p.traits).some((v) => v != null) && (
                <Card>
                  <CardHead title="How they think">Personality measures from survey data, from 0 to 100.</CardHead>
                  <div className="flex flex-col gap-2.5">
                    {(Object.entries(p.traits).filter(([, v]) => v != null) as [string, number][]).map(([k, v]) => (
                      <div key={k}>
                        <div className="flex justify-between text-[13px]">
                          <span className="text-muted">{TRAIT_LABEL[k] ?? titleCase(k)}</span>
                          <span className="num text-text">{Math.round(v * 100)}</span>
                        </div>
                        <div className="mt-1 h-1 rounded-full bg-raised">
                          <div className="h-full rounded-full bg-text/70" style={{ width: `${v * 100}%` }} />
                        </div>
                      </div>
                    ))}
                  </div>
                </Card>
                )}
              </div>

              {p.exposures.length > 0 && (
                <Card>
                  <CardHead title="Ties abroad through their work">Measured trade ties of their country that touch their line of work, plus anything you said is true.</CardHead>
                  <ul className="grid grid-cols-1 gap-4 md:grid-cols-2">
                    {p.exposures.map((e, i) => (
                      <li key={i} className="border-l-2 border-flow pl-3 text-[14px] leading-5">
                        <div className="text-text">
                          {e.source_name} <span className="text-muted">through {e.channel.replace("_", " ")}</span>
                        </div>
                        <p className="text-[13px] leading-[18px] text-muted">{e.note}</p>
                      </li>
                    ))}
                  </ul>
                </Card>
              )}

              {data.meeting?.decision && (
                <Card>
                  <CardHead title="The buying meeting they were in" aside={<Pill tone={data.meeting.decision.decision === "reject" ? "no" : data.meeting.decision.decision === "defer" ? "neutral" : "yes"}>{titleCase(data.meeting.decision.decision)}</Pill>}>
                    {companyLabel(data.meeting.company_type ?? "")} in {countryName(data.meeting.country ?? "")}{data.meeting.company_size_text ? `, ${data.meeting.company_size_text}` : ""}.
                  </CardHead>
                  <ul className="flex flex-col gap-3">
                    {(data.meeting.transcript ?? []).map((t, i) => (
                      <li key={i} className={cx("flex items-start gap-2.5", t.persona_id === pid && "rounded-lg bg-raised p-2 -m-2")}>
                        <Avatar seed={t.persona_id} size={28} />
                        <div className="text-[14px] leading-5">
                          <span className="font-medium">{t.name}</span>
                          <span className="text-[12px] text-faint">, {titleCase(t.role)}, round {t.round + 1}</span>
                          <p>{t.statement}</p>
                        </div>
                      </li>
                    ))}
                  </ul>
                  <p className="mt-3 text-[13px] text-muted">{data.meeting.decision.summary}</p>
                </Card>
              )}
            </div>

            <div className="flex flex-col gap-6 lg:sticky lg:top-4 lg:col-span-4">
              <Card className="flex flex-col lg:max-h-[calc(100dvh-140px)]">
                <CardHead title={`Talk to ${p.name.split(" ")[0]}`} />
                <PersonaChat runId={id} pid={pid} name={p.name} initial={data.chat} fill />
              </Card>
              <Card>
                <CardHead title="Their circle" aside={`${data.contacts.length} ${data.contacts.length === 1 ? "contact" : "contacts"}`}>
                  The people whose posts they saw.
                </CardHead>
                {data.contacts.length === 0 ? (
                  <p className="text-[13px] text-muted">They weren&apos;t part of the conversation.</p>
                ) : (
                  <ul>
                    {data.contacts.slice(0, 8).map((c) => (
                      <li key={c.id} className="border-b border-rule last:border-0">
                        <Link href={`/runs/${id}/people/${c.id}`} className="flex items-center gap-2.5 py-2">
                          <Avatar seed={c.id} size={28} ring={c.p != null ? stanceFill(c.p) : undefined} />
                          <span className="min-w-0 flex-1">
                            <span className="block truncate text-[14px] text-text">{c.name}</span>
                            <span className="block truncate text-[12px] text-faint">
                              {shortJob(c.occupation)}, {countryName(c.country)}
                            </span>
                          </span>
                          <span className={cx("num shrink-0 text-[13px]", stanceText(c.p))}>{pctSmart(c.p)}</span>
                        </Link>
                      </li>
                    ))}
                  </ul>
                )}
              </Card>
              <Card>
                <CardHead title="Who they stand for" />
                <p className="text-[14px] leading-5">
                  {p.represents ? (
                    <>
                      About <span className="num">{people(p.represents)}</span> real {p.represents === 1 ? "person" : "people"} like {p.name.split(" ")[0]} in {countryName(p.country)}, from World Bank and ILO data for their job and country.
                    </>
                  ) : (
                    "Heard for context. Not counted in the answer."
                  )}
                </p>
              </Card>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
