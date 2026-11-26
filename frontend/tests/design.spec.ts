import { expect, test } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import path from "node:path";
import { mockApi } from "./fixtures";

for (const dark of [false, true]) {
  const mode = dark ? "dark" : "light";
  test(`${mode} theme keeps reference density, text hierarchy and usable dialogs`, async ({ page }, info) => {
    await page.setViewportSize({ width: 1180, height: 792 });
    await mockApi(page);
    await page.goto("/");
    if (dark) await page.getByRole("button", { name: "切换深色" }).click();
      await page.getByRole("tab", { name: "实时请求", exact: true }).click();
    const description = page.getByText("按单次模型响应计数", { exact: true });
    await expect(description).toHaveCSS("color", dark ? "rgb(163, 173, 191)" : "rgb(122, 125, 134)");
    const rows = page.getByRole("table", { name: "单次请求明细" }).getByRole("row");
    await expect(rows.nth(6)).toBeVisible();
    const sixth = await rows.nth(6).boundingBox();
    const container = await page.getByRole("table", { name: "单次请求明细" }).locator("..").boundingBox();
    expect(sixth!.y + sixth!.height).toBeLessThanOrEqual(container!.y + container!.height);

    if (info.project.name === "chromium") {
      await mkdir("../output", { recursive: true });
      await page.screenshot({ path: path.resolve(`../output/maox-final-${mode}.png`), animations: "disabled" });
    }
    for (const size of [{ width: 960, height: 640 }, { width: 390, height: 844 }]) {
      await page.setViewportSize(size);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      await page.getByRole("tab", { name: "账号管理", exact: true }).click();
      await page.getByRole("button", { name: "添加账号", exact: true }).click();
      const dialog = page.getByRole("dialog", { name: "添加账号" });
      await expect(dialog).toBeVisible();
      const bounds = await dialog.boundingBox();
      expect(bounds!.x).toBeGreaterThanOrEqual(0);
      expect(bounds!.y).toBeGreaterThanOrEqual(0);
      expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(size.width);
      expect(bounds!.y + bounds!.height).toBeLessThanOrEqual(size.height);
      await page.keyboard.press("Escape");
      await expect(dialog).not.toBeVisible();
    }
    await page.setViewportSize({ width: 1180, height: 820 });
    if (info.project.name === "chromium") {
      await page.screenshot({ path: path.resolve(`../output/maox-accounts-${mode}.png`), animations: "disabled" });
      await page.getByRole("button", { name: "添加账号", exact: true }).click();
      await page.getByRole("dialog").getByRole("button", { name: "兼容渠道", exact: true }).click();
      await page.screenshot({ path: path.resolve(`../output/maox-dialog-${mode}.png`), animations: "disabled" });
      await page.keyboard.press("Escape");
      await page.getByRole("tab", { name: "工具设置", exact: true }).click();
      await page.screenshot({ path: path.resolve(`../output/maox-tools-${mode}.png`), animations: "disabled" });
    }
  });
}
