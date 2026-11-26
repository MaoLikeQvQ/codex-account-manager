import { expect, test, type Locator } from "@playwright/test";
import { makeFeed, mockApi } from "./fixtures";

async function fits(locator: Locator) {
  const box = await locator.boundingBox();
  expect(box).not.toBeNull();
  expect(box!.x).toBeGreaterThanOrEqual(0);
  expect(box!.y).toBeGreaterThanOrEqual(0);
  expect(box!.x + box!.width).toBeLessThanOrEqual(961);
  expect(box!.y + box!.height).toBeLessThanOrEqual(612);
}

for (const dark of [false, true]) {
  test(
    "all pages and controls fit the native minimum window: dark=" + dark,
    async ({ page }) => {
      await mockApi(page, {
        override: async (route, pathname) => {
          if (pathname !== "/api/requests") return false;
          const feed = makeFeed();
          feed.network = {
            scope: "all_providers",
            total: 1,
            events: [
              {
                id: "rate-limit",
                timestamp: new Date().toISOString(),
                session_id: "session-12345678",
                model: "gpt-6.1-sol",
                transport: "HTTP/SSE",
                endpoint: "https://example.com/v1/responses",
                http_status: 429,
                duration_ms: 1000,
                status: "failed",
                error_category: "rate_limit",
                event: "codex.api_request",
                kind: "",
              },
            ],
          };
          await route.fulfill({ json: { ok: true, result: feed } });
          return true;
        },
      });
      await page.setViewportSize({ width: 960, height: 612 });
      await page.goto("/");
      if (dark) await page.getByRole("button", { name: "切换深色" }).click();
      for (const name of [
        "总览",
        "账号管理",
        "用量明细",
        "实时请求",
        "工具设置",
      ]) {
        await page.getByRole("tab", { name, exact: true }).click();
        const panel = page.getByRole("tabpanel", { name, exact: true });
        await expect(panel).toBeVisible();
        if (name === "总览")
          await expect(
            panel.getByLabel("活跃模型", { exact: true })
          ).toContainText("gpt-6.1-sol");
        if (name === "用量明细")
          await expect(panel.getByRole("table").getByRole("row")).toHaveCount(
            7
          );
        await fits(panel);
        expect(
          await page
            .getByRole("main")
            .evaluate((el) => el.scrollHeight - el.clientHeight),
          name
        ).toBeLessThanOrEqual(1);
        for (const control of await panel.getByRole("button").all())
          await fits(control);
        for (const table of await panel.getByRole("table").all()) {
          expect(
            await table
              .locator("..")
              .evaluate((el) => el.scrollWidth <= el.clientWidth + 1)
          ).toBe(true);
          for (const heading of await table.getByRole("columnheader").all())
            await fits(heading);
          expect(
            await table
              .getByRole("cell")
              .evaluateAll((cells) =>
                cells.every((el) => el.scrollWidth <= el.clientWidth + 1)
              ),
            name + " 单元格"
          ).toBe(true);
        }
        if (name === "用量明细" || name === "实时请求") {
          await panel
            .getByRole("combobox", {
              name: name === "实时请求" ? "请求时间范围" : "时间范围",
              exact: true,
            })
            .click();
          await page
            .getByRole("option", { name: "指定日期", exact: true })
            .click();
          await fits(
            panel.getByRole("button", {
              name: name === "实时请求" ? "导出 CSV" : "导出",
              exact: true,
            })
          );
        }
        if (name === "实时请求") {
          await panel.getByRole("button", { name: "网络事件（1）" }).click();
          await fits(panel.getByRole("button", { name: "导出网络 CSV" }));
          const table = panel.getByRole("table", { name: "网络请求事件" });
          expect(
            await table
              .locator("..")
              .evaluate((el) => el.scrollWidth <= el.clientWidth + 1)
          ).toBe(true);
          for (const heading of await table.getByRole("columnheader").all())
            await fits(heading);
          expect(
            await table
              .getByRole("cell")
              .evaluateAll((cells) =>
                cells.every((el) => el.scrollWidth <= el.clientWidth + 1)
              ),
            name + " 单元格"
          ).toBe(true);
          expect(
            await page
              .getByRole("main")
              .evaluate((el) => el.scrollHeight - el.clientHeight),
            name
          ).toBeLessThanOrEqual(1);
        }
      }
      await page.getByRole("tab", { name: "账号管理", exact: true }).click();
      await page.getByRole("button", { name: "添加账号", exact: true }).click();
      const dialog = page.getByRole("dialog", { name: "添加账号" });
      await fits(dialog);
      await dialog
        .getByRole("button", { name: "兼容渠道", exact: true })
        .click();
      await fits(dialog);
      await fits(dialog.getByRole("button", { name: "保存账号", exact: true }));
    }
  );
}
