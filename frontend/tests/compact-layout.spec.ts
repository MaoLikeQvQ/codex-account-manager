import { expect, test } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import path from "node:path";
import { custom, makeState, makeUsage, mockApi } from "./fixtures";

for (const dark of [false, true]) {
  test(
    "compact pages fit a small desktop window: dark=" + dark,
    async ({ page }, info) => {
      const state = makeState();
      state.accounts[0].active = false;
      state.accounts.push({ ...custom, name: "本机", active: true });
      state.active_account = "本机";
      state.current.provider_id = "MaoLocal";
      await mockApi(page, {
        state,
        override: async (route, pathname) => {
          if (pathname !== "/api/usage") return false;
          const usage = makeUsage("MaoLocal");
          usage.models = usage.models.slice(0, 1);
          await route.fulfill({ json: { ok: true, result: usage } });
          return true;
        },
      });
      await page.setViewportSize({ width: 960, height: 612 });
      await page.goto("/");
      if (dark) await page.getByRole("button", { name: "切换深色" }).click();
      await expect(page.locator("aside")).toHaveCSS(
        "border-right-width",
        "0px"
      );
      await expect(page.getByLabel("活跃模型", { exact: true })).toContainText(
        "gpt-6.1-sol"
      );
      const account = await page
        .getByLabel("当前账号", { exact: true })
        .boundingBox();
      expect(account!.height).toBeLessThan(115);
      const main = page.getByRole("main");
      expect(
        await main.evaluate(
          (element) => element.scrollHeight <= element.clientHeight + 1
        )
      ).toBe(true);
      await mkdir("../output", { recursive: true });
      const save = async (name: string) => {
        if (info.project.name === "chromium")
          await page.screenshot({
            path: path.resolve(
              "../output/maox-compact-" +
                name +
                (dark ? "-dark" : "-light") +
                ".png"
            ),
          });
      };
      await save("overview");
      await page.getByRole("tab", { name: "账号管理", exact: true }).click();
      const compatible = page.getByRole("listitem", {
        name: "本机",
        exact: true,
      });
      await expect(
        compatible.getByText("gpt-6.1-sol", { exact: true })
      ).toHaveCount(0);
      expect((await compatible.boundingBox())!.height).toBeLessThan(100);
      await expect(
        page
          .getByRole("listitem", { name: "工作账号" })
          .getByRole("progressbar")
      ).toHaveCount(2);
      expect(
        await main.evaluate(
          (element) => element.scrollHeight <= element.clientHeight + 1
        )
      ).toBe(true);
      const official = page.getByRole("listitem", {
        name: "工作账号",
        exact: true,
      });
      const compatibleBounds = await compatible.boundingBox();
      expect(
        Math.abs(
          (await official.boundingBox())!.height - compatibleBounds!.height
        )
      ).toBeLessThanOrEqual(1);
      await expect(official.getByText("5h", { exact: true })).toBeVisible();
      await expect(official.getByText("7d", { exact: true })).toBeVisible();
      const quotaContainer = official.getByLabel("账号配额", { exact: true });
      expect((await quotaContainer.boundingBox())!.width).toBeLessThanOrEqual(
        95
      );
      const bars = official.getByRole("progressbar");
      const barA = await bars.nth(0).boundingBox();
      const barB = await bars.nth(1).boundingBox();
      expect(Math.abs(barA!.x - barB!.x)).toBeLessThan(1);
      expect(barB!.y).toBeGreaterThan(barA!.y);
      const quotaBar = await official
        .getByRole("progressbar")
        .first()
        .boundingBox();
      expect(quotaBar!.width).toBeLessThanOrEqual(90);
      const officialBounds = await official.boundingBox();
      expect(quotaBar!.y + quotaBar!.height).toBeLessThan(
        officialBounds!.y + officialBounds!.height
      );
      const cards = page.getByRole("listitem");
      const first = await cards.nth(0).boundingBox();
      const second = await cards.nth(1).boundingBox();
      expect(Math.abs(first!.y - second!.y)).toBeLessThan(1);
      expect(second!.x).toBeGreaterThan(first!.x + first!.width);
      await expect(page.getByText("未启用", { exact: true })).toHaveCount(0);
      await expect(page.getByText("额度受限", { exact: true })).toHaveCount(0);
      await save("accounts");
      await page.getByRole("tab", { name: "用量明细", exact: true }).click();
      const table = page.getByRole("table", { name: "模型用量明细" });
      await expect(table.getByRole("row")).toHaveCount(2);
      const panel = await page
        .getByRole("tabpanel", { name: "用量明细", exact: true })
        .locator("..")
        .boundingBox();
      expect(panel!.height).toBeLessThan(340);
      expect(
        await table
          .locator("..")
          .evaluate((element) => element.scrollWidth <= element.clientWidth + 1)
      ).toBe(true);
      await save("usage");
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth
        )
      ).toBe(true);
    }
  );
}
