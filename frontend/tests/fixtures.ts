import type { Page, Route } from "@playwright/test";
import type {
  Account,
  AppState,
  RequestFeed,
  TokenUsage,
  Usage,
} from "../src/types";

export const official: Account = {
  name: "工作账号",
  account_type: "official",
  connection_type: "official",
  auth_mode: "",
  transport: "",
  provider_id: "openai",
  provider_name: "OpenAI",
  base_url: "",
  default_model: "",
  reasoning_effort: "high",
  has_api_key: false,
  has_official_auth: true,
  email: "work@example.com",
  plan_type: "pro",
  active: true,
  pending_apply: false,
  model_catalog_url: "",
  api_key_model_discovery: false,
  requires_openai_auth: true,
  updated_at: "2026-10-26T10:00:00+08:00",
};
export const custom: Account = {
  ...official,
  name: "备用渠道",
  account_type: "custom",
  connection_type: "sub2api",
  auth_mode: "api_key",
  transport: "websocket",
  provider_id: "MaoLocal",
  provider_name: "MaoLocal",
  base_url: "https://api.example.com/v1",
  default_model: "gpt-6.1-sol",
  has_api_key: true,
  has_official_auth: false,
  email: "",
  plan_type: "",
  active: false,
  requires_openai_auth: false,
};
export function makeState(): AppState {
  return {
    accounts: structuredClone([official, custom]),
    active_account: official.name,
    codex_home: "/isolated/codex",
    current: {
      model: "gpt-6.1-sol",
      provider_id: "openai",
      base_url: "",
      reasoning_effort: "high",
    },
    codex: { running: true, restart_required: false, application: "Codex" },
    image_generation: {
      configured: true,
      enabled: true,
      installed: true,
      installed_version: "1.0.0",
      bundled_version: "1.0.0",
      update_available: false,
      pending_apply: false,
      mode: "images",
      source: "managed_account",
      account_name: "备用渠道",
      provider: "api",
      base_url: "",
      image_model: "gpt-image-2",
      has_api_key: false,
      runtime_available: true,
    },
  };
}
export const quota = {
  account: official.name,
  fetched_at: "2026-10-26T10:03:00+08:00",
  errors: {},
  limits: {
    rateLimitsByLimitId: {
      codex: {
        limitName: "Codex",
        planType: "pro",
        primary: {
          usedPercent: 19,
          windowDurationMins: 300,
          resetsAt: Math.floor(Date.now() / 1000) + 16500,
        },
        secondary: {
          usedPercent: 3,
          windowDurationMins: 10080,
          resetsAt: Math.floor(Date.now() / 1000) + 604000,
        },
      },
    },
  },
  usage: { summary: { lifetimeTokens: 21895000 } },
  amount_estimate: {
    windows: {
      "codex:primary": {
        remaining_usd: 172.1,
        sample_usd: 40.37,
        total_usd: 212.47,
      },
      "codex:secondary": {
        remaining_usd: 858.7,
        sample_usd: 26.55,
        total_usd: 885.25,
      },
    },
  },
};
export function makeUsage(provider = "openai"): Usage {
  const models = [
    "gpt-6.1-sol",
    "gpt-6-astra",
    "gpt-6-sol",
    "gpt-6-luna",
    "gpt-5.6-sol",
    "gpt-5.6-terra",
  ].map((model, index) => ({
    model,
    input_tokens: 113000 - index * 12000,
    cached_input_tokens: 105000 - index * 13000,
    cache_write_input_tokens: 0,
    output_tokens: 1000 + index * 380,
    reasoning_output_tokens: 540 + index * 100,
    estimated_cost: 0.203 + index * 0.002,
    unpriced_tokens: 0,
  }));
  const totals = Object.fromEntries(
    Object.keys(models[0])
      .filter((key) => key !== "model")
      .map((key) => [
        key,
        models.reduce(
          (sum, row) => sum + (row[key as keyof typeof row] as number),
          0,
        ),
      ]),
  ) as unknown as TokenUsage;
  return {
    date: "2026-10-26",
    end_date: "2026-10-26",
    provider_id: provider,
    unit: "USD",
    price_source: "https://developers.openai.com/api/docs/pricing",
    models,
    totals,
    scanned_files: 21,
    skipped_files: 0,
  };
}
export function makeFeed(provider = "openai"): RequestFeed {
  return {
    provider_id: provider,
    date: "2026-10-26",
    end_date: "2026-10-26",
    total_requests: 21,
    timing_coverage: { total: 21, timed: 0, desktop_total: 21, desktop_timed: 0, cli_timed: 0 },
    skipped_files: 0,
    updated_at: new Date().toISOString(),
    requests: Array.from({ length: 8 }, (_, index) => ({
      id: `response-${index}`,
      session_id: "01a175e9-5551-77d0-916c-e43843ae4bdf",
      client_source: "desktop" as const,
      timestamp: new Date(Date.now() - index * 60000).toISOString(),
      model: "gpt-6.1-sol",
      reasoning_effort: "high",
      input_tokens: 111300 - index * 5000,
      cached_input_tokens: 102700 - index * 4500,
      cache_write_input_tokens: 0,
      output_tokens: 1030 + index * 90,
      reasoning_output_tokens: 516,
      estimated_cost: 0.037428 + index * 0.001,
      first_token_seconds: 1.3 + index,
      first_response_seconds: 0.3 + index,
      duration_seconds: 41.7 + index,
      tps: 24.7 + index * 0.5,
      timing_source: "request_events" as const,
    })),
  };
}

export async function mockApi(
  page: Page,
  options: {
    state?: AppState;
    override?: (route: Route, path: string) => Promise<boolean>;
  } = {},
) {
  const state = options.state || makeState();
  const posts: { path: string; body: Record<string, unknown> }[] = [];
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (options.override && (await options.override(route, path))) return;
    const body =
      route.request().method() === "POST"
        ? route.request().postDataJSON()
        : undefined;
    if (body) posts.push({ path, body });
    let result: unknown;
    if (path === "/api/state")
      return void (await route.fulfill({ json: { ok: true, data: state } }));
    if (path === "/api/requests") result = makeFeed(state.current.provider_id);
    else if (path === "/api/usage")
      result = makeUsage(state.current.provider_id);
    else if (path === "/api/accounts/quota") result = quota;
    else if (path === "/api/updates")
      result = { enabled: false, available: false, current_version: "2.11.0" };
    else if (path === "/api/accounts/parse-config")
      result = {
        name: "imported",
        provider_id: "source",
        base_url: "https://import.example.com/v1",
        default_model: "test-model",
        reasoning_effort: "high",
        provider_config: {
          base_url: "https://import.example.com/v1",
          http_headers: { "X-Test": "preserved" },
          requires_openai_auth: true,
        },
        api_key_model_discovery: true,
        ignored_fields: ["web_search"],
      };
    else if (path === "/api/accounts/verify")
      result = { model_ids: ["test-model", "gpt-6.1-sol"], models: 2 };
    else if (path === "/api/accounts/verify-connection")
      result = { reply: "Hello!", elapsed_ms: 350 };
    else if (path === "/api/accounts/activate") {
      state.accounts.forEach((account) => {
        account.active = account.name === body.name;
        account.pending_apply = false;
      });
      state.active_account = String(body.name);
      state.current.provider_id = state.accounts.find(
        (account) => account.active,
      )!.provider_id;
    } else if (path === "/api/accounts/save") {
      const previous = state.accounts.find(
        (account) => account.name === body.original_name,
      );
      const saved = {
        ...custom,
        ...previous,
        ...body,
        name: String(body.name),
        active: previous?.active ?? false,
        updated_at: new Date().toISOString(),
      };
      state.accounts = [
        ...state.accounts.filter(
          (account) => account.name !== body.original_name,
        ),
        saved,
      ];
    } else if (path === "/api/accounts/delete")
      state.accounts = state.accounts.filter(
        (account) => account.name !== body.name,
      );
    else if (path === "/api/accounts/official-login/start")
      result = {
        login_id: "isolated-login",
        user_code: "ABCD-1234",
        verification_url: "https://auth.openai.com/codex/device",
      };
    else if (path === "/api/accounts/official-login/status")
      result = { status: "pending" };
    else if (path === "/api/accounts/official-login/cancel") result = {};
    else if (path === "/api/image-generation/configure")
      state.image_generation.pending_apply = true;
    else if (
      path === "/api/image-generation/apply" ||
      path === "/api/history/claim-all" ||
      path === "/api/codex/launch"
    )
      result = {};
    else
      return void (await route.fulfill({
        status: 400,
        json: { ok: false, error: `Unhandled mock: ${path}` },
      }));
    await route.fulfill({
      json: {
        ok: true,
        data: body ? state : undefined,
        result,
        message: body
          ? path.includes("verify-connection")
            ? "连接验证通过：Hello!"
            : "操作已完成"
          : undefined,
      },
    });
  });
  return { state, posts };
}
