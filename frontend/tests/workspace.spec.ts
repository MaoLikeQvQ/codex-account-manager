import { expect, test } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import path from "node:path";
import { custom, makeState, makeUsage, mockApi } from "./fixtures";

test("production CSP renders overview, dark mode, model filtering and CSV export", async ({
  page,
}, info) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  await mockApi(page);
  const response = await page.goto("/");
  await page.getByRole("tab", { name: "用量明细", exact: true }).click();
  expect(response?.headers()["content-security-policy"]).toContain("nonce-");
  await expect(page.getByRole("tab", { name: "用量明细" })).toBeVisible();
  await expect(page.getByLabel("用量概览")).toBeVisible();
  await expect(
    page.getByRole("table", { name: "模型用量明细" }).getByRole("row"),
  ).toHaveCount(7);
  await expect(page.getByText("API 等价 USD")).toBeVisible();
  if (info.project.name === "chromium") {
    await mkdir("../output", { recursive: true });
    await page.screenshot({
      path: path.resolve("../output/maox-react-mui-light.png"),
      fullPage: true,
      animations: "disabled",
    });
  }
  await page.getByRole("button", { name: "切换深色" }).click();
  await expect(page.getByRole("button", { name: "切换浅色" })).toBeVisible();
  expect(
    await page
      .locator("body")
      .evaluate((element) => getComputedStyle(element).backgroundColor),
  ).toBe("rgb(18, 20, 25)");
  if (info.project.name === "chromium")
    await page.screenshot({
      path: path.resolve("../output/maox-react-mui-dark.png"),
      fullPage: true,
      animations: "disabled",
    });
  await page.getByRole("textbox", { name: "筛选模型" }).fill("gpt-6-astra");
  await expect(
    page.getByRole("table", { name: "模型用量明细" }).getByRole("row"),
  ).toHaveCount(2);
  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "导出", exact: true }).click();
  expect((await downloadPromise).suggestedFilename()).toMatch(
    /maox-usage-.*\.csv/,
  );
  await page.reload();
  await expect(page.getByRole("button", { name: "切换浅色" })).toBeVisible();
  expect(errors).toEqual([]);
});

test("empty workspace remains actionable at narrow widths", async ({
  page,
}) => {
  const state = makeState();
  state.accounts = [];
  state.active_account = "";
  await mockApi(page, { state });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await page.getByRole("tab", { name: "用量明细", exact: true }).click();
  await expect(
    page
      .getByRole("table", { name: "模型用量明细" })
      .getByText("还没有启用账号"),
  ).toBeVisible();
  await page.getByRole("button", { name: "前往账号管理" }).click();
  await expect(page.getByText("添加你的第一个账号")).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page
    .getByRole("button", { name: "添加账号", exact: true })
    .first()
    .click();
  await expect(page.getByRole("dialog", { name: "添加账号" })).toBeVisible();
});

test("late usage response cannot overwrite the newly selected time range", async ({
  page,
}) => {
  let release!: () => void;
  const blocked = new Promise<void>((resolve) => {
    release = resolve;
  });
  await mockApi(page, {
    override: async (route, pathname) => {
      if (pathname !== "/api/usage") return false;
      const period = new URL(route.request().url()).searchParams.get("period");
      if (period === "today") await blocked;
      const usage = makeUsage();
      usage.models = [
        {
          ...usage.models[0],
          model: period === "today" ? "stale-today" : "current-yesterday",
        },
      ];
      await route.fulfill({ json: { ok: true, result: usage } });
      return true;
    },
  });
  await page.goto("/");
  await page.getByRole("tab", { name: "用量明细", exact: true }).click();
  await page.getByRole("combobox", { name: "时间范围" }).click();
  await page.getByRole("option", { name: "昨天", exact: true }).click();
  await expect(
    page.getByText("current-yesterday", { exact: true }),
  ).toBeVisible();
  release();
  await expect(page.getByText("stale-today", { exact: true })).toHaveCount(0);
});

test("usage failure is visible and retry restores the table", async ({
  page,
}) => {
  let fails = true;
  await mockApi(page, {
    override: async (route, path) => {
      if (path !== "/api/usage" || !fails) return false;
      await route.fulfill({
        status: 500,
        json: { ok: false, error: "隔离测试读取失败" },
      });
      return true;
    },
  });
  await page.goto("/");
  await page.getByRole("tab", { name: "用量明细", exact: true }).click();
  await expect(page.getByText("隔离测试读取失败")).toBeVisible();
  fails = false;
  await page.getByRole("button", { name: "重试", exact: true }).click();
  await expect(
    page.getByRole("table", { name: "模型用量明细" }).getByRole("row"),
  ).toHaveCount(7);
});

test("same-name replacement with a custom account keeps quota cards out of overview", async ({
  page,
}) => {
  const { state } = await mockApi(page);
  await page.goto("/");
  await page.getByRole("tab", { name: "用量明细", exact: true }).click();
  await expect(page.getByLabel("用量概览")).toBeVisible();
  state.accounts = [
    {
      ...custom,
      name: state.active_account,
      active: true,
      updated_at: "replacement",
    },
  ];
  state.current.provider_id = "MaoLocal";
  await page.getByRole("button", { name: "刷新账号状态" }).click();
  await expect(page.getByText("≈$858.7")).toHaveCount(0);
  await expect(page.getByText("每周剩余", { exact: true })).toHaveCount(0);
  await expect(page.getByText("5 小时剩余", { exact: true })).toHaveCount(0);
});

test("losing the active account clears an outstanding usage loading indicator", async ({
  page,
}) => {
  let release!: () => void;
  const blocked = new Promise<void>((resolve) => {
    release = resolve;
  });
  const { state } = await mockApi(page, {
    override: async (route, path) => {
      if (path !== "/api/usage") return false;
      await blocked;
      await route.fulfill({ json: { ok: true, result: makeUsage() } });
      return true;
    },
  });
  await page.goto("/");
  await page.getByRole("tab", { name: "用量明细", exact: true }).click();
  await expect(
    page.getByRole("progressbar", { name: "正在读取用量" }),
  ).toBeVisible();
  state.accounts = [];
  state.active_account = "";
  await page.getByRole("button", { name: "刷新账号状态" }).click();
  await expect(
    page
      .getByRole("table", { name: "模型用量明细" })
      .getByText("还没有启用账号"),
  ).toBeVisible();
  await expect(
    page.getByRole("progressbar", { name: "正在读取用量" }),
  ).toHaveCount(0);
  release();
});
