export type Segment = {
  name: string;
  description: string;
  occupations: string[];
  custom_occupation: string | null;
  company_types: string[];
  countries: string[];
  weight: number;
  is_buyer: boolean;
};

export type Force = {
  name: string;
  origin: string;
  affects: string[];
  sectors: string[];
  channel: string;
  direction: "helps" | "hurts" | "mixed";
  strength: number;
  description: string;
};

export type Spec = {
  title: string;
  question: string;
  subject_kind: string;
  subject: string;
  outcome_type: "binary" | "categorical" | "numeric";
  outcomes: string[];
  numeric_unit: string | null;
  numeric_range: number[] | null;
  persona_question: string;
  horizon_months: number;
  targets: string[];
  target_weights: Record<string, number>;
  segments: Segment[];
  general_population_share: number;
  sectors: string[];
  b2b: boolean;
  committee_roles: string[];
  modes: string[];
  forces: Force[];
  price: { amount: number; currency: string; period: string } | null;
  competitors: string[];
  assumed_reach: number;
  research_queries: string[];
  key_uncertainties: string[];
  assumptions: string[];
};

export type RunConfig = {
  agents: number;
  runs_per_agent: number;
  committees: number;
  committee_rounds: number;
  diffusion_rounds: number;
  diffusion_agent_cap: number;
  influencer_voices: number;
  research: boolean;
  influence_threshold: number;
  seed: number | null;
  temperature: number;
  weighting: "population" | "equal";
};

export type WorldNode = {
  id: string;
  name: string;
  anchor?: [number, number] | null;
  role: "target" | "influencer";
  kind?: "country" | "bloc";
  strength?: number;
  order?: number;
  members?: string[];
};
export type WorldLink = {
  source: string;
  target: string;
  channel: string;
  strength: number;
  note: string;
  origin: string;
  via: string[];
};
export type World = { nodes: WorldNode[]; links: WorldLink[]; channels: Record<string, string> };

export type Summary = {
  n: number;
  people?: number;
  adopters?: number;
  stated: number;
  calibrated: number;
  value: number;
  ci: [number, number];
  key?: string;
  label?: string;
  share?: number;
  top_objection?: string[];
};

export type InfluenceEffect = {
  source: string;
  source_name: string;
  channel: string;
  note: string;
  direction: string;
  exposed_n: number;
  others_n: number;
  exposed_value: number;
  others_value: number | null;
  delta: number | null;
  mentions: number;
  countries: string[];
};

export type Quote = {
  persona_id: string;
  name: string;
  country: string;
  occupation: string;
  segment?: string;
  p?: number;
  quote: string;
};

export type Theme = { theme: string; share: number; example: string };

export type Results = {
  headline: Summary & {
    label: string;
    reach: number;
    if_aware: number;
    kind: "action" | "belief";
    calibration: { kind: string; a: number; b: number; source: string; n_cases: number };
    samples: number;
    agents_total: number;
  };
  outcomes: { option: string; share: number }[] | { unit: string | null; median: number; p10: number; p90: number; mean: number } | null;
  attention: Record<string, number>;
  by_country: Summary[];
  by_segment: Summary[];
  by_occupation: Summary[];
  by_seniority: Summary[];
  by_company_type: Summary[];
  by_country_segment: Summary[];
  influence_effects: InfluenceEffect[];
  influencer_voices: { source: string; n: number; value: number; countries: string[]; quotes: Quote[] }[];
  drivers: { trait: string; correlation: number }[];
  wtp: {
    currency: string;
    period: string;
    price: number;
    median: number;
    p25: number;
    p75: number;
    share_at_price: number;
    curve: { price: number; share: number }[];
    by_country: { country: string; median: number; n: number }[];
  } | null;
  model_agreement: { model: string; n: number; stated: number; calibrated: number }[];
  quotes: { positive: Quote[]; negative: Quote[]; undecided: Quote[] };
  committees?: {
    n: number;
    decisions: Record<"buy" | "pilot" | "defer" | "reject", number>;
    purchase_probability: number;
    purchase_ci: [number, number];
    median_cycle_months: number | null;
    top_blockers: { blocker: string; count: number }[];
    decisive_factors: { factor: string; count: number }[];
    by_country: { country: string; n: number; purchase_probability: number; buy_or_pilot: number }[];
    by_company_type: { company_type: string; n: number; purchase_probability: number }[];
    role_stance: Record<string, number>;
  };
  diffusion?: {
    agents: number;
    edges: number;
    rounds: { round: number; stated: number; calibrated: number; by_country: Record<string, number>; changed: number; sharers: number; news: string | null }[];
    examples: { round: number; persona_id: string; name: string; country: string; from: number; to: number; why: string }[];
    social_pull: number;
    bass: { m: number; p: number; q: number; curve: { month: number; adoption: number }[] };
    network: { nodes: { id: string; country: string; p: number; name: string }[]; links: { source: string; target: string }[] };
  };
  themes?: { objections: Theme[]; reasons: Theme[]; change_mind: Theme[] };
  comparison?: { parent_id: string; parent_title: string; parent_value: number; delta: number };
};

export type Report = {
  headline: string;
  verdict: "strong" | "promising" | "uncertain" | "weak" | "unlikely";
  summary: string;
  drivers: { factor: string; effect: "positive" | "negative" | "mixed"; evidence: string }[];
  country_insights: { title: string; detail: string }[];
  segment_insights: { title: string; detail: string }[];
  influence_insights: { title: string; detail: string }[];
  risks: string[];
  recommendations: { action: string; why: string; expected_impact: string; priority: "high" | "medium" | "low" }[];
  levers: { label: string; description: string; changes: Record<string, unknown> }[];
  confidence_note: string;
};

export type Fact = { statement: string; relevance: string; countries: string[]; stance: string; source_urls: string[] };
export type FactSheet = { facts: Fact[]; competitors: string[]; price_points: string[] };

export type Usage = {
  calls: number;
  failures: number;
  repairs: number;
  prompt_tokens: number;
  completion_tokens: number;
  cost_usd: number;
  by_model: Record<string, { calls: number; prompt_tokens: number; completion_tokens: number; cost_usd: number }>;
};

export type RunStatus = "queued" | "running" | "done" | "failed" | "cancelled";

export type Run = {
  id: string;
  created_at: number;
  updated_at: number;
  status: RunStatus;
  stage: string | null;
  progress: number;
  title: string;
  prompt: string;
  parent_id: string | null;
  request: { prompt: string; targets: string[]; config: RunConfig } | null;
  spec: Spec | null;
  world: World | null;
  research: FactSheet | null;
  results: Results | null;
  report: Report | null;
  usage: Usage | null;
  error: string | null;
  live?: boolean;
};

export type RunListItem = {
  id: string;
  created_at: number;
  status: RunStatus;
  stage: string | null;
  progress: number;
  title: string;
  prompt: string;
  parent_id: string | null;
  targets: string[];
  subject_kind: string | null;
  headline: Results["headline"] | null;
  error: string | null;
};

export type PersonaLite = {
  id: string;
  name: string;
  country: string;
  segment: string;
  occupation: string;
  seniority: string;
  voice: string | null;
  exposures: string[];
};

export type PersonaSummary = PersonaLite & {
  country_name: string;
  age: number;
  company_type: string;
  is_buyer: boolean;
  weight: number;
  p: number | null;
  choice: string | null;
  quote: string | null;
  attention: string | null;
};

export type Exposure = { source: string; source_name: string; channel: string; strength: number; note: string; direction: string; origin: string };

export type Persona = {
  id: string;
  country: string;
  country_name: string;
  segment: string;
  occupation: string;
  occupation_id: string;
  sector: string;
  company_type: string;
  company_size: number;
  seniority: string;
  buyer_role: string;
  age: number;
  gender: string;
  income_usd: number;
  income_band: string;
  traits: Record<string, number>;
  exposures: Exposure[];
  is_buyer: boolean;
  weight: number;
  represents: number;
  influencer_voice: string | null;
  name: string;
  bio: string;
  priorities: string[];
  frustrations: string[];
  info_sources: string[];
  voice: string;
};

export type Reaction = {
  persona_id: string;
  run: number;
  model: string;
  p_stated: number;
  attention: string;
  juster: number;
  likelihood: number;
  choice: string;
  willingness_to_pay: number | null;
  reasons: string[];
  objections: string[];
  change_mind: string[];
  influences: string[];
  quote: string;
  confidence: number;
};

export type ChatMessage = { role: "user" | "assistant"; content: string };

export type Committee = {
  id: string;
  country: string;
  company_type: string;
  company_size: number;
  sector: string;
  members: { role: string; role_label: string; persona_id: string; name: string; occupation: string; seniority: string }[];
  transcript: { round: number; persona_id: string; name: string; role: string; stance: number; statement: string; conditions: string[]; concerns: string[] }[];
  decision: {
    decision: "buy" | "pilot" | "defer" | "reject";
    probability_of_purchase: number;
    deal_cycle_months: number;
    decisive_factor: string;
    blockers: string[];
    conditions: string[];
    summary: string;
  } | null;
};

export type Meta = {
  version: string;
  mock: boolean;
  countries: {
    iso3: string;
    iso_num: string | null;
    name: string;
    region: string;
    income: string;
    blocs: string[];
    population_m: number;
    workforce_m: number;
    gdp_pc_usd: number;
    anchor: [number, number] | null;
    internet_pct: number;
    isco_source: string;
  }[];
  blocs: { id: string; name: string; members: string[]; description: string; anchor: [number, number] | null }[];
  occupations: { id: string; title: string; isco: number; buyer_role: string }[];
  company_types: Record<string, { label: string; employees: number[] }>;
  sectors: string[];
  channels: Record<string, string>;
  stages: { id: string; label: string }[];
  model_examples: Record<string, string[]>;
  defaults: RunConfig;
};

export type StreamEvent = { seq: number; ts: number; type: string; data: unknown };
