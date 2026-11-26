import { expect, test } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import path from "node:path";
import { custom, makeFeed, makeState, makeUsage, mockApi } from "./fixtures";

test("reference overview shows real quota, usage and navigates to working pages", async ({
  page,
}, info) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("response", (response) => {
    if (response.status() >= 400)
      errors.push(response.url() + " " + response.status());
  });
  await mockApi(page);
  await page.goto("/");
  await expect(
    page.getByRole("tab", { name: "总览", exact: true })
  ).toHaveAttribute("aria-selected", "true");
  await expect(page.getByLabel("当前账号", { exact: true })).toContainText(
    "工作账号"
  );
  await expect(
    page.getByRole("progressbar", { name: "Codex · 5 小时剩余配额" })
  ).toHaveAttribute("aria-valuenow", "81");
  await expect(
    page.getByRole("progressbar", { name: "Codex · 每周剩余配额" })
  ).toHaveAttribute("aria-valuenow", "97");
  await expect(page.getByLabel("用量概览")).toContainText("今日 Token 用量");
  await expect(page.getByLabel("用量概览")).toContainText("21");
  await expect(page.getByLabel("活跃模型", { exact: true })).toContainText(
    "gpt-6.1-sol"
  );
  await expect(
    page.getByRole("img", { name: "最近响应在各小时的 Token 分布" })
  ).toBeVisible();
  await expect(page.getByText(/不代表服务商账单或订阅扣费/)).toBeVisible();
  await mkdir("../output", { recursive: true });
  if (info.project.name === "chromium")
    await page.screenshot({
      path: path.resolve("../output/maox-overview-light.png"),
    });
  await page.getByRole("button", { name: "切换深色" }).click();
  if (info.project.name === "chromium")
    await page.screenshot({
      path: path.resolve("../output/maox-overview-dark.png"),
    });
  await page.getByRole("button", { name: "查看完整用量" }).click();
  await expect(page.getByRole("table", { name: "模型用量明细" })).toBeVisible();
  await page.getByRole("tab", { name: "总览", exact: true }).click();
  await page.getByRole("button", { name: "查看请求记录" }).click();
  await expect(page.getByRole("table", { name: "单次请求明细" })).toBeVisible();
  expect(errors).toEqual([]);
});

test("overview handles empty usage and compatible accounts without inventing quota", async ({
  page,
}) => {
  const state = makeState();
  state.accounts = [{ ...custom, active: true }];
  state.active_account = custom.name;
  state.current.provider_id = "MaoLocal";
  await mockApi(page, {
    state,
    override: async (route, pathname) => {
      if (pathname === "/api/usage") {
        const usage = makeUsage("MaoLocal");
        usage.models = [];
        for (const key of Object.keys(usage.totals))
          usage.totals[key as keyof typeof usage.totals] = 0;
        await route.fulfill({ json: { ok: true, result: usage } });
        return true;
      }
      if (pathname === "/api/requests") {
        const feed = makeFeed("MaoLocal");
        feed.requests = [];
        feed.total_requests = 0;
        await route.fulfill({ json: { ok: true, result: feed } });
        return true;
      }
      return false;
    },
  });
  await page.goto("/");
  await expect(page.getByLabel("当前账号", { exact: true })).toContainText(
    "WebSocket"
  );
  await expect(page.getByRole("button", { name: "刷新配额" })).toHaveCount(0);
  await expect(page.getByText("暂无模型调用", { exact: true })).toBeVisible();
  await expect(page.getByText("当前时段暂无消耗分布")).toBeVisible();
  for (const size of [
    { width: 960, height: 640 },
    { width: 390, height: 844 },
  ]) {
    await page.setViewportSize(size);
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth
      )
    ).toBe(true);
    await page.getByRole("tab", { name: "账号管理", exact: true }).click();
    await expect(
      page.getByRole("button", { name: "添加账号", exact: true })
    ).toBeVisible();
    await page.getByRole("tab", { name: "总览", exact: true }).click();
  }
});

test("unknown quota stays unknown and missing active account has an actionable entry", async ({
  page,
}) => {
  const { state } = await mockApi(page, {
    override: async (route, pathname) => {
      if (pathname !== "/api/accounts/quota") return false;
      await route.fulfill({
        json: { ok: true, result: { errors: { request: "额度服务不可用" } } },
      });
      return true;
    },
  });
  await page.goto("/");
  await expect(page.getByText("配额读取失败：额度服务不可用")).toBeVisible();
  await expect(page.getByLabel("当前账号", { exact: true })).not.toContainText(
    "100%"
  );
  state.accounts = [];
  state.active_account = "";
  await page.getByRole("button", { name: "刷新账号状态" }).click();
  await expect(
    page.getByRole("button", { name: "前往账号管理" })
  ).toBeVisible();
  await page.getByRole("button", { name: "前往账号管理" }).click();
  await expect(page.getByText("添加你的第一个账号")).toBeVisible();
});
