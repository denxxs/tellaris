export type LensId = "b2b" | "consumer" | "personal" | "opinion" | "forecast";

export type Segment = {
  age_min?: number | null;
  age_max?: number | null;
  gender?: "any" | "woman" | "man";
  trait?: string | null;
  trait_share?: number | null;
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
  lens?: LensId | null;
  scope?: "countries" | "global";
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
  memory?: boolean;
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
    revenue?: { customers: number; monthly: number; monthly_ci: [number, number]; currency: string; note: string } | null;
    lens?: LensId;
    lens_label?: string;
    leading?: { option: string; share: number; ci: [number, number] } | null;
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
    society?: {
      posts: number;
      replies: number;
      shifts: number;
      news: number;
      meetings: number;
      top_voices: { persona_id: string; name: string; country: string; occupation: string; items: number; agrees: number; p: number | null }[];
      hot_threads: { id: string; author_name: string; text: string; replies: number; agrees: number; disagrees: number }[];
    };
    agents: number;
    edges: number;
    rounds: { round: number; stated: number; calibrated: number; by_country: Record<string, number>; changed: number; sharers: number; posts?: number; replies?: number; news: string | null }[];
    examples: { round: number; persona_id: string; name: string; country: string; from: number; to: number; why: string }[];
    social_pull: number;
    reflection?: ReflectionSummary;
    bass: { m: number; p: number; q: number; curve: { month: number; adoption: number }[] };
    network: { nodes: { id: string; country: string; p: number; name: string }[]; links: { source: string; target: string }[] };
  };
  themes?: { objections: Theme[]; reasons: Theme[]; change_mind: Theme[] };
  splits?: Splits;
  comparison?: { parent_id: string; parent_title: string; parent_value: number; delta: number };
};

export type SplitCell = { label: string; dims: string[]; keys?: Record<string, string>; n: number; value: number; ci: [number, number]; people?: number; vs_overall?: number };
export type Splits = {
  dimensions: Record<string, { label: string; rows: { key: string; label: string; n: number; value: number; ci: [number, number]; people?: number }[]; hidden: number }>;
  hot: SplitCell[];
  cold: SplitCell[];
  overall?: number;
  min_n?: number;
};

export type ClarifyQuestion = {
  id: string;
  question: string;
  why: string;
  kind: "single" | "multi" | "boolean" | "number" | "short" | "long";
  options: string[];
  default: string;
  unit?: string | null;
};
export type Clarification = {
  reading: string;
  lens: LensId | null;
  lens_reason: string;
  scope: "countries" | "global";
  questions: ClarifyQuestion[];
  error?: string;
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
  represents?: number;
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

export type MindMemory = {
  n: number;
  round: number;
  kind: "said" | "saw" | "reply" | "news" | "meeting" | "thought";
  text: string;
  who: string | null;
  item: string | null;
  importance: number;
};
export type Mind = {
  memories: MindMemory[];
  trajectory: number[];
  reflection: { belief: string; p: number; influences: number[]; changed_mind: boolean } | null;
};
export type ReflectionSummary = {
  people: number;
  changed_mind?: number;
  before?: number;
  after?: number;
  moved_by?: { kind: MindMemory["kind"]; label: string; share: number }[];
  nothing_moved?: number;
  examples?: { persona_id: string; name: string; country: string; occupation: string; from: number; to: number; belief: string }[];
};

export type Persona = {
  mind?: Mind;
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
  tagline: string;
  values: string[];
  typical_day: string;
  tools_today: string[];
  household: string;
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
  lenses: { id: LensId; label: string; description: string }[];
  global: { quick: string[]; deep: string[] };
  model_examples: Record<string, string[]>;
  defaults: RunConfig;
};

export type StreamEvent = { seq: number; ts: number; type: string; data: unknown };

export type FeedItem = {
  id: string;
  round: number;
  kind: "post" | "reply" | "news" | "meeting" | "shift";
  text: string;
  author: string | null;
  author_name?: string;
  country?: string;
  segment?: string;
  occupation?: string;
  tagline?: string;
  p?: number;
  parent: string | null;
  agrees: number;
  disagrees: number;
  replies?: number;
  from_p: number | null;
  to_p: number | null;
  why?: string | null;
  title?: string;
  origin?: string;
  direction?: string;
  company_type?: string;
  company_size?: number;
  decision?: { decision: "buy" | "pilot" | "defer" | "reject"; probability_of_purchase: number; deal_cycle_months: number; decisive_factor: string; blockers: string[]; conditions: string[]; summary: string };
  transcript?: { round: number; persona_id: string; name: string; role: string; stance: number; statement: string; conditions: string[]; concerns: string[] }[];
  members?: { role: string; role_label: string; persona_id: string; name: string; occupation: string; seniority: string }[];
};

export type UploadedFile = { id: string; name: string; size: number; chars: number; truncated: boolean; preview: string; uploaded_at: number };

export type Contact = { id: string; name: string; country: string; occupation: string; segment: string; p: number | null };

export type Profile = {
  persona: Persona;
  reactions: Reaction[];
  chat: ChatMessage[];
  contacts: Contact[];
  society: { mine: FeedItem[]; context: FeedItem[]; replies: FeedItem[]; final_p: number | null };
  meeting: FeedItem | null;
};

export type ProviderInfo = {
  id: string;
  label: string;
  key_env: string | null;
  base_env?: string;
  base_default?: string;
  version_env?: string;
  key_url?: string;
  models: string[];
  note?: string;
  fields?: { env: string; label: string; secret?: boolean; optional?: boolean; placeholder?: string; hint?: string }[];
  machine_credentials?: boolean;
};
