import { expect, test } from "@playwright/test";
import { makeFeed, mockApi } from "./fixtures";

test("network diagnostics include failed requests without usage and keep transport success distinct", async ({ page }) => {
  await mockApi(page, { override: async (route, pathname) => {
    if (pathname !== "/api/requests") return false;
    const feed = makeFeed();
    feed.network = { scope: "all_providers", total: 3, events: [
      { id: "failure", timestamp: "2026-10-30T01:00:00Z", session_id: "session-fail", model: "gpt-6.1-sol", transport: "HTTP/SSE", endpoint: "https://example.com/v1/responses", http_status: 429, duration_ms: 1500, status: "failed", error_category: "rate_limit", event: "codex.api_request", kind: "" },
      { id: "headers", timestamp: "2026-10-30T00:59:00Z", session_id: "session-ok", model: "gpt-6.1-sol", transport: "HTTP/SSE", endpoint: "/responses", http_status: 200, duration_ms: 250, status: "response_received", error_category: "", event: "codex.api_request", kind: "" },
      { id: "timeout", timestamp: "2026-10-30T00:58:00Z", session_id: "", model: "", transport: "WebSocket", endpoint: "", http_status: null, duration_ms: 90000, status: "failed", error_category: "timeout", event: "codex.websocket_request", kind: "" },
    ] };
    await route.fulfill({ json: { ok: true, result: feed } }); return true;
  } });
  await page.goto("/");
  await page.getByRole("tab", { name: "实时请求", exact: true }).click();
  await page.getByRole("button", { name: "网络事件（3）" }).click();
  const table = page.getByRole("table", { name: "网络请求事件" });
  await expect(table).toContainText("https://example.com/v1/responses");
  await expect(table).toContainText("429 · 失败");
  await expect(table).toContainText("限流或额度不足");
  await expect(table).toContainText("200 · 已收到响应头");
  await expect(table).toContainText("主机未上报");
  await expect(table).toContainText("请求超时");
  await expect(table).toContainText("90.00s");
  await expect(table).toContainText("未上报");
  await expect(table).not.toContainText("响应完成");
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "导出网络 CSV" }).click();
  expect((await download).suggestedFilename()).toBe("maox-network-events.csv");
  await page.screenshot({ path: "test-results/network-events-" + test.info().project.name + ".png" });
  await page.getByRole("button", { name: "响应与用量", exact: true }).click();
  await expect(page.getByRole("table", { name: "单次请求明细" })).toBeVisible();
});

test("uncollected network events show an honest empty state", async ({ page }) => {
  await mockApi(page);
  await page.goto("/");
  await page.getByRole("tab", { name: "实时请求", exact: true }).click();
  await page.getByRole("button", { name: "网络事件（0）" }).click();
  await expect(page.getByRole("table", { name: "网络请求事件" })).toContainText("暂无网络事件");
  await expect(page.getByRole("button", { name: "导出网络 CSV" })).toBeDisabled();
});
