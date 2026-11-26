import { expect, test } from "@playwright/test";
import { mkdir, readFile } from "node:fs/promises";
import path from "node:path";
import { makeFeed, mockApi } from "./fixtures";

test("per-request average rate and newly logged responses appear automatically", async ({
  page,
}, info) => {
  let count = 0;
  await mockApi(page, {
    override: async (route, pathname) => {
      if (pathname !== "/api/requests") return false;
      const feed = makeFeed();
      if (++count === 1) {
        feed.total_requests = 0;
        feed.requests = [];
      } else if (count > 2) {
        feed.total_requests = 22;
        feed.requests.unshift({
          ...feed.requests[0],
          id: "new-request",
          tps: 66,
          output_tokens: 660,
          duration_seconds: 10,
        });
      }
      await route.fulfill({ json: { ok: true, result: feed } });
      return true;
    },
  });
  await page.goto("/");
  await page.getByRole("tab", { name: "实时请求", exact: true }).click();
  await expect(
    page.getByRole("tab", { name: "实时请求", exact: true }),
  ).toHaveAttribute("aria-selected", "true");
  const overview = page.getByLabel("用量概览", { exact: true });
  await expect(overview).toContainText("今日估算费用");
  await expect(page.getByText("每周剩余", { exact: true })).toHaveCount(0);
  await expect(page.getByText("5 小时剩余", { exact: true })).toHaveCount(0);
  expect((await overview.boundingBox())!.height).toBeLessThan(120);
  const table = page.getByRole("table", { name: "单次请求明细" });
  await expect(table.locator("tbody tr")).toHaveCount(0);
  await expect(table.getByRole("row").nth(1)).toContainText("24.7", {
    timeout: 5000,
  });
  await expect(page.getByText("请求平均速率，含等待")).toBeVisible();
  await table.getByText("首响 / 耗时 ⓘ").hover();
  await expect(page.getByRole("tooltip")).toContainText("并非流式生成速度");
  await expect(table.getByRole("row").nth(1)).toContainText("66.0", {
    timeout: 5000,
  });
  await expect(table.getByRole("row").nth(1).getByRole("cell").nth(3)).toHaveText(
    "66.0 tok/s",
  );
  await expect(
    page.getByText("最近请求 TPS", { exact: true }).locator("..").getByText("66.0 tok/s", { exact: true }),
  ).toBeVisible();
  await expect(page.getByText(/22 次记录/)).toBeVisible();
  if (info.project.name === "chromium") {
    await mkdir("../output", { recursive: true });
    await page.screenshot({
      path: path.resolve("../output/maox-realtime-light.png"),
      fullPage: true,
      animations: "disabled",
    });
    await page.getByRole("button", { name: "切换深色" }).click();
    await page.screenshot({
      path: path.resolve("../output/maox-realtime-dark.png"),
      fullPage: true,
      animations: "disabled",
    });
  }
});

test("token consumption combines input, cache, output and reasoning in both tables", async ({ page }) => {
  await mockApi(page);
  await page.goto("/");
  await page.getByRole("tab", { name: "实时请求", exact: true }).click();
  const requests = page.getByRole("table", { name: "单次请求明细" });
  await expect(requests.getByRole("columnheader", { name: "Token 消耗" })).toBeVisible();
  const requestTokens = requests.getByRole("row").nth(1).getByLabel(/输入 .*缓存读取 .*输出 .*其中思考/);
  await expect(requestTokens).toBeVisible();
  await expect(requestTokens.locator("svg")).toHaveCount(4);
  await page.getByRole("tab", { name: "用量明细" }).click();
  const usage = page.getByRole("table", { name: "模型用量明细" });
  await expect(usage.getByRole("columnheader", { name: "Token 消耗" })).toBeVisible();
  await expect(usage.getByRole("row").nth(1).getByLabel(/输入 .*缓存读取 .*输出 .*其中思考/)).toBeVisible();
});

test("missing request timing and unknown prices remain unknown and export as empty fields", async ({
  page,
}) => {
  await mockApi(page, {
    override: async (route, pathname) => {
      if (pathname !== "/api/requests") return false;
      const feed = makeFeed();
      feed.requests = [
        {
          ...feed.requests[0],
          timing_source: "unavailable",
          tps: null,
          first_token_seconds: null,
          first_response_seconds: null,
          duration_seconds: null,
          estimated_cost: null,
        },
      ];
      feed.total_requests = 1;
      await route.fulfill({ json: { ok: true, result: feed } });
      return true;
    },
  });
  await page.goto("/");
  await page.getByRole("tab", { name: "实时请求", exact: true }).click();
  const row = page
    .getByRole("table", { name: "单次请求明细" })
    .getByRole("row")
    .nth(1);
  await expect(row.getByRole("cell").nth(2)).toHaveText("—");
  await expect(row.getByRole("cell").nth(4)).toContainText("首响 —");
  await expect(row.getByRole("cell").nth(4)).toContainText("耗时 —");
  await expect(row.getByRole("cell").nth(3)).toContainText("—");
  await row.getByRole("cell").nth(4).hover();
  await expect(page.getByRole("tooltip")).toContainText("不再使用轮次耗时");
  const pending = page.waitForEvent("download");
  await page.getByRole("button", { name: "导出 CSV" }).click();
  const download = await pending;
  expect(download.suggestedFilename()).toBe(
    "maox-requests-2026-10-26.csv",
  );
  const csv = await readFile(await download.path(), "utf8");
  expect(csv).toContain('"估算 TPS (tok/s)","请求总耗时 s"');
});

test("slow request polling does not overlap and old date data cannot replace the new date", async ({
  page,
}) => {
  let pendingToday = 0;
  let maxPending = 0;
  let release!: () => void;
  const blocked = new Promise<void>((resolve) => {
    release = resolve;
  });
  await mockApi(page, {
    override: async (route, pathname) => {
      if (pathname !== "/api/requests") return false;
      const selected = new URL(route.request().url()).searchParams.get(
        "period",
      );
      if (selected === "today") {
        pendingToday++;
        maxPending = Math.max(maxPending, pendingToday);
        await blocked;
        pendingToday--;
      }
      const feed = makeFeed();
      feed.requests[0].model =
        selected === "today" ? "stale-today-model" : "fresh-yesterday-model";
      await route.fulfill({ json: { ok: true, result: feed } });
      return true;
    },
  });
  await page.goto("/");
  await page.getByRole("tab", { name: "实时请求", exact: true }).click();
  await expect.poll(() => pendingToday).toBe(1);
  await page.waitForTimeout(1300);
  expect(maxPending).toBe(1);
  await page.getByRole("combobox", { name: "请求时间范围" }).click();
  await page.getByRole("option", { name: "昨天", exact: true }).click();
  await expect(page.getByText("fresh-yesterday-model")).toBeVisible();
  release();
  await expect(page.getByText("stale-today-model")).toHaveCount(0);
});

test("polling pauses while an account dialog is open", async ({ page }) => {
  let calls = 0;
  await mockApi(page, {
    override: async (route, pathname) => {
      if (pathname !== "/api/requests") return false;
      calls++;
      await route.fulfill({ json: { ok: true, result: makeFeed() } });
      return true;
    },
  });
  await page.goto("/");
  await page.getByRole("tab", { name: "实时请求", exact: true }).click();
  await expect(
    page.getByRole("table", { name: "单次请求明细" }).getByRole("row"),
  ).toHaveCount(9);
  await page.getByRole("tab", { name: "账号管理", exact: true }).click();
  await page.getByRole("button", { name: "添加账号", exact: true }).click();
  const before = calls;
  await page.waitForTimeout(1300);
  expect(calls).toBe(before);
});

test("observed request events show timing while waiting for new events without a restart instruction", async ({ page }) => {
  await mockApi(page, {
    override: async (route, pathname) => {
      if (pathname !== "/api/requests") return false;
      const feed = makeFeed();
      await route.fulfill({ json: { ok: true, result: {
        ...feed,
        timing_status: "restart_required",
        requests: [{ ...feed.requests[0], timing_source: "request_events", tps: 20,
          duration_seconds: 10, first_token_seconds: 5, first_response_seconds: 2,
          request_started_at: "2026-10-27T08:00:00Z" }],
      } } });
      return true;
    },
  });
  await page.goto("/");
  await page.getByRole("tab", { name: "实时请求", exact: true }).click();
  const row = page.getByRole("table", { name: "单次请求明细" }).getByRole("row").nth(1);
  await expect(row.getByRole("cell").nth(3)).toContainText("20.0 tok/s");
  await expect(row.getByRole("cell").nth(4)).toContainText("首响 2.00s");
  await expect(row.getByRole("cell").nth(4)).toContainText("10.00s");
  await expect(page.getByText("请求平均速率，含等待", { exact: true })).toBeVisible();
  const coverage = page.getByRole("alert").filter({ hasText: "当前范围请求计时覆盖" });
  await expect(coverage).toBeVisible();
  await expect(coverage).not.toContainText("重启");
});

test("CLI timing never implies desktop timing coverage", async ({ page }) => {
  await mockApi(page, {
    override: async (route, pathname) => {
      if (pathname !== "/api/requests") return false;
      await route.fulfill({ json: { ok: true, result: {
        ...makeFeed(),
        timing_status: "receiving_requests",
        timing_coverage: { total: 101, timed: 1, desktop_total: 100, desktop_timed: 0, cli_timed: 1 },
      } } });
      return true;
    },
  });
  await page.goto("/");
  await page.getByRole("tab", { name: "实时请求", exact: true }).click();
  const coverage = page.getByRole("alert").filter({ hasText: "当前范围请求计时覆盖" });
  await expect(coverage).toContainText("1 / 101");
  await expect(coverage).toContainText("桌面 0 / 100");
  await expect(coverage).toContainText("CLI 1");
  await coverage.hover();
  await expect(page.getByRole("tooltip")).toContainText("桌面请求尚缺少可关联的请求事件");
  await expect(coverage).not.toContainText("重启");

});

test("desktop timing coverage remains scoped while waiting for new request events", async ({ page }) => {
  await mockApi(page, {
    override: async (route, pathname) => {
      if (pathname !== "/api/requests") return false;
      await route.fulfill({ json: { ok: true, result: {
        ...makeFeed(),
        timing_status: "awaiting_request_events",
        timing_coverage: { total: 102, timed: 3, desktop_total: 100, desktop_timed: 2, cli_timed: 1 },
      } } });
      return true;
    },
  });
  await page.goto("/");
  await page.getByRole("tab", { name: "实时请求", exact: true }).click();
  const coverage = page.getByRole("alert").filter({ hasText: "当前范围请求计时覆盖" });
  await expect(coverage).toContainText("3 / 102");
  await expect(coverage).toContainText("桌面 2 / 100");
  await expect(coverage).not.toContainText("桌面请求尚缺少");

});
