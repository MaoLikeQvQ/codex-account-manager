import { expect, test } from "@playwright/test";
import path from "node:path";
import { mockApi, makeState } from "./fixtures";

const svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 600 360"><rect width="600" height="360" fill="#eef3f8"/><circle cx="175" cy="255" r="65" fill="none" stroke="#203447" stroke-width="7"/><circle cx="425" cy="255" r="65" fill="none" stroke="#203447" stroke-width="7"/><path d="M175 255L255 150L320 255H175L360 160L425 255M255 150H295M345 140L360 160L380 130" fill="none" stroke="#287cc3" stroke-width="10" stroke-linejoin="round"/><ellipse cx="290" cy="130" rx="68" ry="43" fill="white" stroke="#667b8b" stroke-width="3"/><path d="M325 112Q350 65 350 45" fill="none" stroke="white" stroke-width="28"/><circle cx="352" cy="48" r="22" fill="white"/><path d="M369 47L455 67L366 67Z" fill="#f0b047"/><path d="M370 67Q410 110 448 68" fill="#efc06c"/><circle cx="358" cy="42" r="4"/><path d="M270 165L300 208L285 237M306 166L340 215L323 248M316 121L368 145" fill="none" stroke="#e1a547" stroke-width="9" stroke-linecap="round"/></svg>';

async function openTest(page: import("@playwright/test").Page) {
  await page.goto("/");
  await page.getByRole("tab", { name: "工具设置", exact: true }).click();
  await page.getByRole("button", { name: "鹈鹕测试", exact: true }).click();
  return page.getByRole("dialog", { name: "降智测试 · 鹈鹕骑自行车" });
}

test("pelican displays the configured model when the account profile differs", async ({ page }) => {
  const state = makeState();
  state.accounts[0].default_model = "old-profile-model";
  await mockApi(page, { state });
  const dialog = await openTest(page);
  await expect(dialog).toContainText("gpt-6.1-sol");
  await expect(dialog).not.toContainText("old-profile-model");
});

test("pelican uses current default model once and shows static preview and original output", async ({ page }, info) => {
  let calls = 0;
  let sent: unknown;
  let release!: () => void;
  const blocked = new Promise<void>((resolve) => { release = resolve; });
  await mockApi(page, { override: async (route, pathname) => {
    if (pathname !== "/api/benchmark/pelican") return false;
    calls++;
    sent = route.request().postDataJSON();
    await blocked;
    await route.fulfill({ json: { ok: true, result: {
      account: "工作账号", model: "gpt-6.1-sol", reported_model: "service-reported-model", reasoning_effort: "high",
      prompt: "Draw an SVG of a pelican riding a bicycle.", reply: svg,
      preview_svg: svg, warning: "", elapsed_ms: 2345,
    } } });
    return true;
  } });
  const dialog = await openTest(page);
  expect(calls).toBe(0);
  await expect(dialog).toContainText("gpt-6.1-sol");
  await expect(dialog).toContainText("可能消耗额度");
  await dialog.getByRole("button", { name: "开始测试（1 次请求）" }).click();
  await expect(dialog.getByRole("button", { name: "测试中…" })).toBeDisabled();
  await page.keyboard.press("Escape");
  await expect(dialog).toBeVisible();
  expect(calls).toBe(1);
  expect(sent).toEqual({ account: "工作账号", model: "gpt-6.1-sol" });
  release();
  const image = dialog.getByRole("img", { name: "鹈鹕骑自行车测试结果" });
  await expect(image).toBeVisible();
  await expect.poll(() => image.evaluate((element) => (element as HTMLImageElement).naturalWidth)).toBeGreaterThan(0);
  await expect(dialog.getByRole("textbox", { name: "原始回答" })).toHaveValue(svg);
  await expect(dialog).toContainText("2.3 秒");
  await expect(dialog).toContainText("service-reported-model");
  const download = page.waitForEvent("download");
  await dialog.getByRole("button", { name: "导出原始回答" }).click();
  expect((await download).suggestedFilename()).toBe("maox-pelican-original.txt");
  if (info.project.name === "chromium") {
    await page.screenshot({ path: path.resolve("../output/maox-pelican-test-light.png"), animations: "disabled" });
  }
  await dialog.getByRole("button", { name: "关闭", exact: true }).click();
  await page.getByRole("button", { name: "切换深色" }).click();
  await page.getByRole("button", { name: "鹈鹕测试", exact: true }).click();
  await expect(image).toBeVisible();
  if (info.project.name === "chromium") {
    await page.screenshot({ path: path.resolve("../output/maox-pelican-test-dark.png"), animations: "disabled" });
  }
  expect(calls).toBe(1);
});

test("failed test remains visible without automatic retry", async ({ page }) => {
  let calls = 0;
  await mockApi(page, { override: async (route, pathname) => {
    if (pathname !== "/api/benchmark/pelican") return false;
    calls++;
    await route.fulfill({ status: 500, json: { ok: false, error: "测试请求失败：HTTP 429；未自动重试。" } });
    return true;
  } });
  const dialog = await openTest(page);
  await dialog.getByRole("button", { name: "开始测试（1 次请求）" }).click();
  await expect(dialog).toContainText("HTTP 429");
  await expect(dialog.getByRole("button", { name: "开始测试（1 次请求）" })).toBeEnabled();
  expect(calls).toBe(1);
  await page.mouse.click(2, 2);
  await expect(dialog).toBeVisible();
  expect(calls).toBe(1);
});

test("pending account changes block generation and narrow dialogs fit", async ({ page }) => {
  const state = makeState();
  state.accounts[0].pending_apply = true;
  await mockApi(page, { state });
  await page.setViewportSize({ width: 390, height: 844 });
  const dialog = await openTest(page);
  await expect(dialog).toContainText("请先应用后再测试");
  await expect(dialog.getByRole("button", { name: "开始测试（1 次请求）" })).toBeDisabled();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});
