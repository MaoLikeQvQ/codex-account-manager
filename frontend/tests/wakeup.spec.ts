import { expect, test } from "@playwright/test";
import { makeState, mockApi, official } from "./fixtures";

const loadedSettings = { enabled: true, times: ["08:00"], model: "gpt-6.1-sol", timezone: "CST", next_run: null, running: false, results: [], error: "" };

test("displays the shifted next run and accumulated delay", async ({ page }) => {
  await mockApi(page, { override: async (route, path) => {
    if (path !== "/api/accounts/wakeup") return false;
    await route.fulfill({ json: { ok: true, result: { ...loadedSettings, delay_minutes: 195, next_run: "2026-10-29T14:15:00+08:00" } } });
    return true;
  } });
  await page.goto("/");
  await page.getByRole("tab", { name: "账号管理" }).click();
  await page.getByRole("button", { name: "定时唤醒", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "定时唤醒", exact: true });
  await expect(dialog).toContainText("今日累计顺延：3 小时 15 分钟");
  await expect(dialog).toContainText("下次执行：");
  await dialog.getByText("使用说明").click();
  await expect(dialog).toContainText("顺延至次日的时间点跳过");
});

test("a stalled settings request times out and retry recovers", async ({ page }) => {
  let requests = 0;
  let release!: () => void;
  const stalled = new Promise<void>((resolve) => { release = resolve; });
  await mockApi(page, { override: async (route, path) => {
    if (path !== "/api/accounts/wakeup") return false;
    if (++requests === 1) await stalled;
    await route.fulfill({ json: { ok: true, result: loadedSettings } });
    return true;
  } });
  await page.goto("/");
  await page.getByRole("tab", { name: "账号管理" }).click();
  await page.getByRole("button", { name: "定时唤醒", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "定时唤醒", exact: true });
  await expect(dialog.getByRole("progressbar", { name: "读取设置" })).toBeVisible();
  await expect(dialog).toContainText("读取定时唤醒设置超时，请重试", { timeout: 15000 });
  await expect(dialog.getByRole("progressbar", { name: "读取设置" })).toHaveCount(0);
  await dialog.getByRole("button", { name: "重试", exact: true }).click();
  await expect(dialog.getByLabel("每日时间", { exact: true })).toHaveValue("08:00");
  await expect(dialog.getByRole("alert")).toHaveCount(0);
  await expect(dialog.getByRole("button", { name: "保存设置" })).toBeEnabled();
  release();
});

test("closing the dialog cancels a stalled read and reopening loads fresh settings", async ({ page }) => {
  let requests = 0;
  let release!: () => void;
  const stalled = new Promise<void>((resolve) => { release = resolve; });
  await mockApi(page, { override: async (route, path) => {
    if (path !== "/api/accounts/wakeup") return false;
    if (++requests === 1) await stalled;
    await route.fulfill({ json: { ok: true, result: loadedSettings } });
    return true;
  } });
  await page.goto("/");
  await page.getByRole("tab", { name: "账号管理" }).click();
  await page.getByRole("button", { name: "定时唤醒", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "定时唤醒", exact: true });
  await expect.poll(() => requests).toBe(1);
  const cancelled = page.waitForEvent("requestfailed", { predicate: (request) => new URL(request.url()).pathname === "/api/accounts/wakeup" });
  await dialog.getByRole("button", { name: "关闭", exact: true }).click();
  await cancelled;
  await page.getByRole("button", { name: "定时唤醒", exact: true }).click();
  await expect(dialog.getByLabel("每日时间", { exact: true })).toHaveValue("08:00");
  release();
});

test("retry after a polling failure preserves unsaved edits", async ({ page }) => {
  let fail = false;
  await mockApi(page, { override: async (route, path) => {
    if (path !== "/api/accounts/wakeup") return false;
    await route.fulfill(fail
      ? { status: 500, json: { ok: false, error: "暂时无法读取设置" } }
      : { json: { ok: true, result: loadedSettings } });
    return true;
  } });
  await page.goto("/");
  await page.getByRole("tab", { name: "账号管理" }).click();
  await page.getByRole("button", { name: "定时唤醒", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "定时唤醒", exact: true });
  await expect(dialog.getByLabel("每日时间", { exact: true })).toHaveValue("08:00");
  await dialog.getByLabel("每日时间", { exact: true }).fill("09:00,18:00");
  fail = true;
  await expect(dialog).toContainText("暂时无法读取设置");
  fail = false;
  await dialog.getByRole("button", { name: "重试", exact: true }).click();
  await expect(dialog.getByRole("alert")).toHaveCount(0);
  await expect(dialog.getByLabel("每日时间", { exact: true })).toHaveValue("09:00,18:00");
});

test("daily multiple times apply to all official accounts and persist after reopening", async ({ page }) => {
  const app = makeState();
  app.accounts.push({ ...official, name: "新增官方", active: false });
  let settings = { enabled: false, times: [] as string[], model: "gpt-6.1-sol", timezone: "CST", next_run: null as string | null, running: false, error: "", results: [] as { account: string; status: string; message: string; at: string }[] };
  const savedBodies: unknown[] = [];
  const { posts } = await mockApi(page, { state: app, override: async (route, path) => {
    if (!path.startsWith("/api/accounts/wakeup")) return false;
    if (path.endsWith("/configure")) {
      savedBodies.push(route.request().postDataJSON());
      settings = { ...settings, ...route.request().postDataJSON(), next_run: "2026-10-30T08:00:00+08:00" };
    }
    if (path.endsWith("/run")) {
      settings.results = [
        { account: "工作账号", status: "failed", message: "授权失效，请重新登录", at: "2026-10-29T08:00:00+08:00" },
        { account: "新增官方", status: "success", message: "hi 已完成响应", at: "2026-10-29T08:00:10+08:00" },
      ];
    }
    await route.fulfill({ json: { ok: true, result: settings } });
    return true;
  } });
  await page.goto("/");
  await page.getByRole("tab", { name: "账号管理" }).click();
  await page.getByRole("button", { name: "定时唤醒", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "定时唤醒", exact: true });
  await expect(dialog).toContainText("每天向 2 个官方账号发送 hi");
  await expect(dialog.getByRole("combobox")).toHaveCount(0);
  await dialog.getByRole("switch").check();
  await dialog.getByLabel("每日时间", { exact: true }).fill("08:00,13:00,18:00");
  await expect(dialog.getByRole("button", { name: "立即唤醒全部" })).toBeDisabled();
  await dialog.getByRole("button", { name: "保存设置" }).click();
  await expect(dialog).toContainText("定时唤醒设置已保存");
  await dialog.getByRole("button", { name: "关闭", exact: true }).click();
  await page.getByRole("button", { name: "定时唤醒", exact: true }).click();
  await expect(dialog.getByLabel("每日时间", { exact: true })).toHaveValue("08:00,13:00,18:00");
  await expect(dialog.getByRole("switch")).toBeChecked();
  await dialog.getByRole("button", { name: "立即唤醒全部" }).click();
  await expect(dialog).toContainText("会消耗额度");
  await dialog.getByRole("button", { name: "确认发送" }).click();
  await expect(dialog).toContainText("授权失效，请重新登录");
  await expect(dialog).toContainText("hi 已完成响应");
  expect(savedBodies[0]).toEqual({ enabled: true, times: ["08:00", "13:00", "18:00"], model: "gpt-6.1-sol" });
  expect(posts.some((post) => post.path.endsWith("/activate"))).toBe(false);
  await page.screenshot({ path: "test-results/wakeup-dialog.png" });
});

test("duplicate times and server failures stay visible without losing draft", async ({ page }) => {
  await mockApi(page, { override: async (route, path) => {
    if (path === "/api/accounts/wakeup") {
      await route.fulfill({ json: { ok: true, result: { enabled: true, times: ["08:00"], model: "gpt-6.1-sol", timezone: "CST", next_run: null, running: false, results: [], error: "" } } });
      return true;
    }
    if (path.endsWith("/wakeup/configure")) {
      await route.fulfill({ status: 400, json: { ok: false, error: "无法保存配置" } });
      return true;
    }
    return false;
  } });
  await page.goto("/");
  await page.getByRole("tab", { name: "账号管理" }).click();
  await page.getByRole("button", { name: "定时唤醒", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "定时唤醒", exact: true });
  await expect(dialog.getByLabel("每日时间", { exact: true })).toHaveValue("08:00");
  await dialog.getByLabel("每日时间", { exact: true }).fill("08:00,08:00");
  await dialog.getByRole("button", { name: "保存设置" }).click();
  await expect(dialog).toContainText("发送时间不能重复");
  await dialog.getByLabel("每日时间", { exact: true }).fill("08:00，18:00");
  await dialog.getByRole("button", { name: "保存设置" }).click();
  await expect(dialog).toContainText("无法保存配置");
  await expect(dialog.getByLabel("每日时间", { exact: true })).toHaveValue("08:00，18:00");
});
