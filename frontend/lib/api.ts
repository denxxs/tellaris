import type { Clarification, LensId, Committee, FeedItem, Meta, Profile, Run, RunConfig, RunListItem, PersonaSummary, ProviderInfo, Spec, UploadedFile, World, ChatMessage } from "./types";

export const API = (process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000").replace(/\/$/, "");

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
      cache: "no-store",
    });
  } catch {
    throw new ApiError(0, `Can't reach the simulation server at ${API}. Start it with: cd backend && python -m oracle`);
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail ?? body);
    } catch {}
    throw new ApiError(res.status, detail);
  }
  return res.json() as Promise<T>;
}

export const api = {
  meta: () => req<Meta>("/api/meta"),
  preview: (body: { prompt: string; targets: string[]; file_ids?: string[]; lens?: LensId | null; scope?: string | null; global_depth?: string; clarifications?: { question: string; answer: string }[] }) =>
    req<{ spec: Spec; world: World }>("/api/scenario/preview", { method: "POST", body: JSON.stringify(body) }),
  clarify: (prompt: string, targets: string[], file_ids: string[] = [], scope: "countries" | "global" = "countries") =>
    req<Clarification>("/api/scenario/clarify", { method: "POST", body: JSON.stringify({ prompt, targets, file_ids, scope }) }),
  upload: async (files: File[]): Promise<{ files: UploadedFile[]; errors: string[] }> => {
    const form = new FormData();
    for (const f of files) form.append("files", f);
    let res: Response;
    try {
      res = await fetch(`${API}/api/files`, { method: "POST", body: form });
    } catch {
      throw new ApiError(0, `Can't reach the simulation server at ${API}.`);
    }
    if (!res.ok) throw new ApiError(res.status, res.statusText);
    return res.json();
  },
  deleteFile: (id: string) => req<{ ok: boolean }>(`/api/files/${id}`, { method: "DELETE" }),
  feed: (id: string) => req<FeedItem[]>(`/api/runs/${id}/feed`),
  headcount: (spec: Spec) =>
    req<{ segments: { name: string; total: number; by_country: Record<string, number>; estimated?: boolean }[]; total: number }>("/api/scenario/headcount", {
      method: "POST",
      body: JSON.stringify({ spec }),
    }),
  world: (targets: string[], spec?: Spec) =>
    req<World>("/api/world/influence", { method: "POST", body: JSON.stringify({ targets, sectors: spec?.sectors ?? [], spec }) }),
  createRun: (body: {
    prompt: string;
    targets?: string[];
    config?: Partial<RunConfig>;
    spec?: Spec;
    file_ids?: string[];
    lens?: LensId | null;
    scope?: "countries" | "global" | null;
    global_depth?: "quick" | "deep";
    clarifications?: { question: string; answer: string }[];
  }) =>
    req<{ id: string }>("/api/runs", { method: "POST", body: JSON.stringify(body) }),
  runs: () => req<RunListItem[]>("/api/runs"),
  run: (id: string) => req<Run>(`/api/runs/${id}`),
  deleteRun: (id: string) => req<{ ok: boolean }>(`/api/runs/${id}`, { method: "DELETE" }),
  cancel: (id: string) => req<{ ok: boolean }>(`/api/runs/${id}/cancel`, { method: "POST" }),
  personas: (id: string) => req<PersonaSummary[]>(`/api/runs/${id}/personas`),
  persona: (id: string, pid: string) => req<Profile>(`/api/runs/${id}/personas/${pid}`),
  chat: (id: string, pid: string, message: string) =>
    req<{ reply: string; chat: ChatMessage[] }>(`/api/runs/${id}/personas/${pid}/chat`, { method: "POST", body: JSON.stringify({ message }) }),
  committees: (id: string) => req<Committee[]>(`/api/runs/${id}/committees`),
  whatif: (id: string, label: string, changes: Record<string, unknown>) =>
    req<{ id: string }>(`/api/runs/${id}/whatif`, { method: "POST", body: JSON.stringify({ label, changes }) }),
  exportUrl: (id: string) => `${API}/api/runs/${id}/export`,
  settings: () => req<Settings>("/api/settings"),
  saveSettings: (patch: Record<string, unknown>) => req<Settings>("/api/settings", { method: "PUT", body: JSON.stringify(patch) }),
  testModel: (model: string) =>
    req<{ ok: boolean; model: string; latency_ms?: number; reply?: string; error?: string }>("/api/settings/test", {
      method: "POST",
      body: JSON.stringify({ model }),
    }),
  cases: () => req<BacktestCase[]>("/api/backtest/cases"),
  startBacktest: (body: { case_ids: string[]; agents: number; runs_per_agent: number; fit: boolean }) =>
    req<{ id: string }>("/api/backtest", { method: "POST", body: JSON.stringify(body) }),
  backtest: (id: string) => req<BacktestJob>(`/api/backtest/${id}`),
  backtests: () => req<BacktestJob[]>("/api/backtests"),
  calibration: () => req<Record<string, Calibration>>("/api/calibration"),
  interviews: (runId: string) => req<Interview[]>(`/api/runs/${runId}/interviews`),
  interview: (iid: string) => req<Interview>(`/api/interviews/${iid}`),
  askGroup: (runId: string, body: { question: string; kind: InterviewKind; options?: string[]; unit?: string | null; group: Record<string, string>; limit: number }) =>
    req<Interview>(`/api/runs/${runId}/interviews`, { method: "POST", body: JSON.stringify(body) }),
  deleteInterview: (iid: string) => req<{ ok: boolean }>(`/api/interviews/${iid}`, { method: "DELETE" }),
  trackRecord: () => req<{ predictions: Prediction[]; summary: TrackSummary }>("/api/track"),
  runPredictions: (id: string) => req<Prediction[]>(`/api/runs/${id}/track`),
  track: (id: string, body: { resolves_on: string; note?: string }) => req<Prediction>(`/api/runs/${id}/track`, { method: "POST", body: JSON.stringify(body) }),
  resolvePrediction: (pid: string, body: { actual: number; source?: string }) =>
    req<Prediction>(`/api/track/${pid}/resolve`, { method: "POST", body: JSON.stringify(body) }),
  deletePrediction: (pid: string) => req<{ ok: boolean }>(`/api/track/${pid}`, { method: "DELETE" }),
  fitFromTrack: (kind: string) =>
    req<{ calibration: Calibration; n: number; mae_before: number; mae_after: number }>(`/api/track/fit/${kind}`, { method: "POST" }),
  resetCalibration: (kind: string) => req<{ ok: boolean }>(`/api/calibration/${kind}`, { method: "DELETE" }),
};

export type Settings = {
  roles: { planner: string; crowd: string[]; analyst: string };
  keys: Record<string, { set: boolean; source: string | null; masked: string }>;
  secrets: Record<string, { set: boolean; masked: string }>;
  bedrock_machine_credentials: boolean;
  extra: Record<string, string>;
  search_provider: "duckduckgo" | "tavily" | "none";
  max_concurrency: number;
  request_timeout_s: number;
  providers: string[];
  model_examples: Record<string, string[]>;
  catalog: ProviderInfo[];
};

export type BacktestCase = { id: string; kind: "action" | "belief"; as_of: string; targets: string[]; actual: number; prompt: string; source: string };

export type Calibration = { kind: string; a: number; b: number; source: string; n_cases: number };

export type Prediction = {
  id: string;
  run_id: string;
  created_at: number;
  made_on: string;
  resolves_on: string;
  note: string;
  title: string;
  question: string;
  measure: string;
  outcome: string;
  targets: string[];
  lens: string | null;
  kind: "action" | "belief";
  predicted: number;
  ci: [number, number] | null;
  stated: number | null;
  status: "open" | "resolved";
  actual: number | null;
  source: string;
  resolved_at: number | null;
  blind?: boolean;
  error?: number;
  within_range?: boolean;
};

export type InterviewKind = "open" | "choice" | "number" | "scale";
export type InterviewAnswer = {
  n: number;
  persona_id: string;
  name: string;
  country: string;
  occupation: string;
  age: number;
  segment: string;
  weight: number;
  leaning: number;
  answer: string;
  choice: string | null;
  number: number | null;
  scale: number | null;
};
export type InterviewStats = {
  n: number;
  options?: { option: string; share: number; n: number }[];
  mean?: number;
  median?: number;
  p10?: number;
  p90?: number;
  counts?: number[];
};
export type Interview = {
  id: string;
  run_id: string;
  created_at: number;
  status: "running" | "done" | "failed";
  question: string;
  kind: InterviewKind;
  options: string[];
  unit: string | null;
  group: Record<string, string>;
  group_label: string;
  limit: number;
  pool: number;
  asked: number;
  done: number;
  answers: InterviewAnswer[];
  results: { all: InterviewStats | null; leaning_yes: InterviewStats | null; leaning_no: InterviewStats | null } | null;
  digest: { summary: string; themes: { label: string; answers: number[]; share: number }[]; error?: string } | null;
  error?: string;
};

export type TrackSummary = {
  total: number;
  open: number;
  due: number;
  resolved: number;
  mae?: number;
  within_range?: number;
  points?: { id: string; title: string; predicted: number; actual: number; kind: string }[];
  by_kind: Record<string, { n: number; mae: number; mae_stated: number; can_fit: boolean }>;
};

export type BacktestRow = {
  case_id: string;
  run_id: string;
  status: string;
  kind: string;
  actual: number;
  stated: number | null;
  calibrated: number | null;
  flipped: boolean;
  error: string | null;
};

export type BacktestJob = {
  id: string;
  status: "running" | "done" | "failed";
  created_at?: number;
  started?: number;
  done?: number;
  total?: number;
  current?: string;
  rows: BacktestRow[];
  error?: string;
  summary?: {
    cases: number;
    scored: number;
    by_kind: Record<
      string,
      {
        n: number;
        mae_stated: number;
        mae_calibrated: number;
        sq_error_calibrated: number;
        reliability: { bin: string; predicted: number; actual: number; n: number }[];
        fitted: Calibration | null;
        mae_refit?: number;
      }
    >;
  };
};
