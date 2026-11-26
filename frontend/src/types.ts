export interface Account {
  name: string;
  account_type: "official" | "custom";
  connection_type: string;
  auth_mode: string;
  transport: string;
  provider_id: string;
  provider_name: string;
  base_url: string;
  default_model: string;
  reasoning_effort: string;
  has_api_key: boolean;
  has_official_auth: boolean;
  email: string;
  plan_type: string;
  active: boolean;
  pending_apply: boolean;
  model_catalog_url: string;
  api_key_model_discovery: boolean;
  requires_openai_auth: boolean;
  updated_at: string;
}

export interface ImageSettings {
  configured: boolean;
  enabled: boolean;
  installed: boolean;
  installed_version: string;
  bundled_version: string;
  update_available: boolean;
  pending_apply: boolean;
  mode: string;
  source: string;
  account_name: string;
  provider: string;
  base_url: string;
  image_model: string;
  has_api_key: boolean;
  runtime_available: boolean;
}

export interface AppState {
  accounts: Account[];
  active_account: string;
  codex_home: string;
  current: {
    model: string;
    provider_id: string;
    base_url: string;
    reasoning_effort: string;
  };
  codex: { running: boolean; restart_required: boolean; application: string };
  history_claim?: { account: string; status: "pending" | "partial" | "error"; failed: number } | null;
  image_generation: ImageSettings;
}

export interface TokenUsage {
  input_tokens: number;
  cached_input_tokens: number;
  cache_write_input_tokens: number;
  output_tokens: number;
  reasoning_output_tokens: number;
  estimated_cost: number;
  unpriced_tokens: number;
}
export interface Usage {
  date: string;
  end_date: string;
  provider_id: string;
  unit: string;
  price_source: string;
  totals: TokenUsage;
  models: (TokenUsage & { model: string })[];
  scanned_files: number;
  skipped_files: number;
  pricing?: { warning?: string; updated_at?: number };
}
export interface QuotaWindow {
  usedPercent?: number;
  windowDurationMins?: number;
  resetsAt?: number;
}
export interface QuotaSnapshot {
  limitName?: string;
  planType?: string;
  primary?: QuotaWindow;
  secondary?: QuotaWindow;
  credits?: { unlimited?: boolean; balance?: string; hasCredits?: boolean };
}
export interface Quota {
  account?: string;
  limits?: {
    rateLimitsByLimitId?: Record<string, QuotaSnapshot>;
    rateLimits?: QuotaSnapshot;
    ordinaryUsageAllowed?: boolean;
  };
  usage?: { summary?: { lifetimeTokens?: number } };
  errors?: Record<string, string>;
  fetched_at?: string;
  amount_estimate?: {
    reason?: string;
    windows: Record<
      string,
      {
        remaining_usd?: number;
        sample_usd?: number;
        total_usd?: number;
        reason?: string;
        note?: string;
      }
    >;
  };
}

export interface ApiResponse<T = unknown> {
  ok: boolean;
  warning?: boolean;
  data?: AppState;
  result?: T;
  message?: string;
  error?: string;
  account?: Account;
}
export type RequestApi = <T = unknown>(
  path: string,
  body?: unknown,
  options?: { signal?: AbortSignal },
) => Promise<ApiResponse<T>>;
export type Notify = (message: string, error?: boolean) => void;

export interface RequestRow {
  id: string;
  session_id: string;
  client_source: "desktop" | "cli" | "subagent" | "unknown";
  timestamp: string;
  model: string;
  reasoning_effort: string;
  input_tokens: number;
  cached_input_tokens: number;
  cache_write_input_tokens: number;
  output_tokens: number;
  reasoning_output_tokens: number;
  estimated_cost: number | null;
  first_token_seconds: number | null;
  first_response_seconds: number | null;
  duration_seconds: number | null;
  tps: number | null;
  request_started_at?: string;
  timing_source: "single_turn" | "request_events" | "unavailable";
}

export interface RequestFeed {
  network?: NetworkFeed;
  timing_status?: string;
  timing_coverage: {
    total: number;
    timed: number;
    desktop_total: number;
    desktop_timed: number;
    cli_timed: number;
  };
  provider_id: string;
  date: string;
  end_date: string;
  requests: RequestRow[];
  total_requests: number;
  skipped_files: number;
  updated_at: string;
}

export interface NetworkFeed {
  scope: "all_providers";
  total: number;
  events: {
    id: string;
    timestamp: string;
    session_id: string;
    model: string;
    transport: string;
    endpoint: string;
    http_status: number | null;
    duration_ms: number | null;
    status: string;
    error_category: string;
    event: string;
    kind: string;
  }[];
}
