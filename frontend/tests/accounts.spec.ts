import { expect, test } from "@playwright/test";
import { makeState, mockApi } from "./fixtures";

test("pending history uses a floating dismissible message without shifting the overview", async ({ page }) => {
  const state = makeState();
  Object.assign(state, { history_claim: { account: "工作账号", status: "pending", failed: 0 } });
  await mockApi(page, { state });
  await page.goto("/");
  await expect(page.getByRole("alert").filter({ hasText: "历史归属待完成" })).toBeVisible();
  const history = page.getByRole("alert").filter({ hasText: "历史归属待完成" });
  await expect(history).toContainText("下次切换账号或启动 Codex 时自动重试");
  const overview = await page.getByLabel("当前账号", { exact: true }).boundingBox();
  expect(overview!.y).toBeLessThan(100);
  await page.screenshot({ path: "test-results/history-message.png" });
  await history.getByRole("button", { name: "Close" }).click();
  await expect(history).toHaveCount(0);
  await page.getByRole("button", { name: "刷新账号状态" }).click();
  await expect(history).toHaveCount(0);

});

test("a partially successful history claim is shown as a warning after switching", async ({ page }) => {
  const state = makeState();
  await mockApi(page, {
    state,
    override: async (route, path) => {
      if (path !== "/api/accounts/activate") return false;
      Object.assign(state, { history_claim: { account: "备用渠道", status: "partial", failed: 1 } });
      await route.fulfill({ json: {
        ok: true, data: state, warning: true,
        message: "账号已切换，但有 1 个历史会话未能归纳，下次切换账号或启动/重启 Codex 时自动重试",
        result: { history: { status: "partial", failed: 1 } },
      } });
      return true;
    },
  });
  await page.goto("/");
  await page.getByRole("tab", { name: "账号管理" }).click();
  await page.getByRole("listitem").filter({ hasText: "备用渠道" }).getByRole("button", { name: "使用", exact: true }).click();
  await expect(page.getByRole("alert").filter({ hasText: "有 1 个历史会话未能归纳" })).toBeVisible();
  await expect(page.getByRole("alert").filter({ hasText: "历史归属未完成" })).toBeVisible({ timeout: 10000 });
});

test("a compatible account can be saved without a profile model", async ({ page }) => {
  const { posts } = await mockApi(page);
  await page.goto("/");
  await page.getByRole("tab", { name: "账号管理" }).click();
  await page.getByRole("button", { name: "添加账号", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "添加账号" });
  await dialog.getByRole("button", { name: "兼容渠道", exact: true }).click();
  await dialog.getByRole("textbox", { name: "账号名称", exact: false }).fill("新渠道");
  await dialog.getByRole("textbox", { name: "服务地址" }).fill("https://example.com/v1");
  await dialog.getByRole("textbox", { name: /^API Key/ }).fill("test-key");
  await dialog.getByRole("button", { name: "保存账号" }).click();
  await expect(dialog).not.toBeVisible();
  expect(posts.find((post) => post.path.endsWith("/save"))?.body).toMatchObject({ default_model: "" });
});

test("custom account validates fields and saves without activating", async ({
  page,
}) => {
  const { posts } = await mockApi(page);
  await page.goto("/");
  await page.getByRole("tab", { name: "账号管理" }).click();
  await page.getByRole("button", { name: "添加账号", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "添加账号" });
  await dialog.getByRole("button", { name: "兼容渠道", exact: true }).click();
  await dialog.getByRole("button", { name: "保存账号" }).click();
  await expect(
    dialog.getByRole("textbox", { name: "账号名称", exact: false }),
  ).toBeFocused();
  await expect(dialog.getByText("请输入 API Key")).toBeVisible();
  await dialog
    .getByRole("textbox", { name: "账号名称", exact: false })
    .fill("隔离渠道");
  await dialog
    .getByRole("textbox", { name: "服务地址" })
    .fill("https://isolated.example.com/v1");
  await dialog
    .getByRole("textbox", { name: /^API Key/ })
    .fill("sk-isolated-test");
  await dialog.getByRole("combobox", { name: "验证模型（可选）" }).fill("gpt-6.1-sol");
  await dialog.getByRole("button", { name: "保存账号" }).click();
  await expect(dialog).not.toBeVisible();
  await expect(
    page.getByRole("list", { name: "账号列表" }).getByText("隔离渠道"),
  ).toBeVisible();
  expect(posts.filter((post) => post.path.endsWith("/save"))).toHaveLength(1);
  expect(posts.some((post) => post.path.endsWith("/activate"))).toBe(false);
});

test("editing keeps saved key and Sub2API connection settings", async ({
  page,
}) => {
  const { posts } = await mockApi(page);
  await page.goto("/");
  await page.getByRole("tab", { name: "账号管理" }).click();
  const row = page.getByRole("listitem").filter({ hasText: "备用渠道" });
  await row.getByRole("button", { name: "详情" }).click();
  await page.getByRole("button", { name: "编辑", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "编辑账号" });
  await expect(dialog.getByRole("textbox", { name: /^API Key/ })).toHaveValue(
    "",
  );
  await dialog.getByRole("button", { name: "保存账号" }).click();
  await expect(dialog).not.toBeVisible();
  const saved = posts.find((post) => post.path.endsWith("/save"))!.body;
  expect(saved).toMatchObject({
    original_name: "备用渠道",
    api_key: "",
    connection_type: "sub2api",
    auth_mode: "api_key",
    transport: "websocket",
  });
  expect(saved).not.toHaveProperty("provider_config");
});

test("config import remains explicit and changed source blocks save", async ({
  page,
}) => {
  const { posts } = await mockApi(page);
  await page.goto("/");
  await page.getByRole("tab", { name: "账号管理" }).click();
  await page.getByRole("button", { name: "添加账号", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "添加账号" });
  await dialog.getByRole("button", { name: "兼容渠道", exact: true }).click();
  await dialog
    .getByRole("textbox", { name: "config.toml", exact: true })
    .fill('model_provider = "source"');
  await dialog
    .getByRole("textbox", { name: "auth.json 或 API Key（可选）" })
    .fill('{"OPENAI_API_KEY":"sk-isolated-test"}');
  await dialog.getByRole("button", { name: "识别并填入" }).click();
  await expect(dialog.getByRole("textbox", { name: "服务地址" })).toHaveValue(
    "https://import.example.com/v1",
  );
  await expect(dialog.getByText(/未导入字段：web_search/)).toBeVisible();
  await dialog.getByRole("button", { name: "已有配置？粘贴导入" }).click();
  await expect(
    dialog.getByRole("textbox", { name: "auth.json 或 API Key（可选）" }),
  ).toHaveValue("");
  await dialog
    .getByRole("textbox", { name: "config.toml", exact: true })
    .fill('model_provider = "changed"');
  await dialog.getByRole("button", { name: "保存账号" }).click();
  await expect(dialog.getByText(/粘贴内容有变化/)).toBeVisible();
  expect(posts.some((post) => post.path.endsWith("/save"))).toBe(false);
});

test("closing device login cancels its isolated session", async ({ page }) => {
  const { posts } = await mockApi(page);
  await page.goto("/");
  await page.getByRole("tab", { name: "账号管理" }).click();
  await page.getByRole("button", { name: "添加账号", exact: true }).click();
  await page.getByRole("button", { name: "登录并添加" }).click();
  await expect(page.getByText("ABCD-1234")).toBeVisible();
  await page.getByRole("button", { name: "取消授权", exact: true }).click();
  await expect(
    page.getByRole("dialog", { name: "添加账号" }),
  ).not.toBeVisible();
  await expect
    .poll(() => posts.filter((post) => post.path.endsWith("/cancel")))
    .toHaveLength(1);
  expect(posts.find((post) => post.path.endsWith("/cancel"))?.body).toEqual({
    login_id: "isolated-login",
  });
});

test("remove confirmation cancellation preserves account and activation keeps overview compact", async ({
  page,
}) => {
  const { posts } = await mockApi(page);
  await page.goto("/");
  await expect(page.getByLabel("用量概览")).toBeVisible();
  await page.getByRole("tab", { name: "账号管理" }).click();
  await page
    .getByRole("listitem")
    .filter({ hasText: "备用渠道" })
    .getByRole("button", { name: "详情" })
    .click();
  await page.getByRole("button", { name: "移除账号", exact: true }).click();
  const confirm = page.getByRole("dialog", { name: "移除账号" });
  await expect(confirm.getByText(/不会注销账号/)).toBeVisible();
  await confirm.getByRole("button", { name: "取消" }).click();
  expect(posts.some((post) => post.path.endsWith("/delete"))).toBe(false);
  await page.getByRole("button", { name: "使用此账号" }).click();
  expect(posts.some((post) => post.path.endsWith("/activate"))).toBe(true);
  await expect(page.getByText("≈$858.7")).toHaveCount(0);
});

test("tools save image configuration separately from apply and omit a standalone history action", async ({
  page,
}) => {
  const { posts } = await mockApi(page);
  await page.goto("/");
  await page.getByRole("tab", { name: "工具设置" }).click();
  await expect(page.getByText("开发模式 · 不检查应用更新")).toBeVisible();
  await expect(page.getByRole("button", { name: "检查更新" })).toBeDisabled();
  await page.getByRole("button", { name: "配置", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "Custom ImageGen" });
  await dialog.getByRole("textbox", { name: "图片模型" }).fill("gpt-image-2");
  await dialog.getByRole("button", { name: "保存配置" }).click();
  await expect(dialog).not.toBeVisible();
  expect(
    posts.some((post) => post.path.endsWith("/image-generation/configure")),
  ).toBe(true);
  expect(
    posts.some((post) => post.path.endsWith("/image-generation/apply")),
  ).toBe(false);
  await expect(page.getByRole("button", { name: "归纳会话" })).toHaveCount(0);
  await expect(page.getByText("历史会话归属", { exact: true })).toHaveCount(0);
  expect(posts.some((post) => post.path.endsWith("/history/claim-all"))).toBe(
    false,
  );
});

test("image configuration uses Platform credentials when only official OAuth accounts exist", async ({
  page,
}) => {
  const state = makeState();
  state.accounts = state.accounts.filter(
    (account) => account.account_type === "official",
  );
  await mockApi(page, { state });
  await page.goto("/");
  await page.getByRole("tab", { name: "工具设置" }).click();
  await page.getByRole("button", { name: "配置", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "Custom ImageGen" });
  await expect(dialog.getByRole("combobox", { name: "凭据来源" })).toHaveText(
    "自定义链接",
  );
  await expect(dialog.getByText(/不能用于公开图片 API/)).toBeVisible();
  await expect(
    dialog.getByRole("textbox", { name: "图片服务地址" }),
  ).toBeVisible();
});


test("account cards show official quotas and keep third-party details simple", async ({ page }) => {
  const quotaNames: string[] = [];
  await mockApi(page, { override: async (route, path) => {
    if (path === "/api/accounts/quota") quotaNames.push(new URL(route.request().url()).searchParams.get("name") || "");
    return false;
  } });
  await page.goto("/");
  await page.getByRole("tab", { name: "账号管理" }).click();
  const official = page.getByRole("listitem", { name: "工作账号" });
  const thirdParty = page.getByRole("listitem", { name: "备用渠道" });
  await expect(official.getByText("5h", { exact: true })).toBeVisible();
  await expect(official.getByText("81%", { exact: true })).toBeVisible();
  await expect(official.getByText("97%", { exact: true })).toBeVisible();
  await official.getByRole("progressbar", { name: "5h剩余" }).locator("..").hover();
  await expect(page.getByRole("tooltip")).toContainText("剩余预估 ≈ $172.10");
  await expect(thirdParty.getByText("https://api.example.com/v1", { exact: true })).toBeVisible();
  await expect(thirdParty.getByText("gpt-6.1-sol", { exact: true })).toHaveCount(0);
  await expect(thirdParty.getByRole("progressbar")).toHaveCount(0);
  expect(quotaNames.every((name) => name === "工作账号")).toBe(true);
  await page.screenshot({ path: "test-results/account-cards.png" });
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(official).toBeVisible();
  expect(await official.evaluate((element) => element.getBoundingClientRect().right)).toBeLessThanOrEqual(390);
  await page.getByRole("textbox", { name: "搜索账号" }).fill("备用");
  await expect(official).toHaveCount(0);
  await expect(thirdParty).toBeVisible();
});

test("official card exposes quota failures and allows retry", async ({ page }) => {
  let fail = true;
  await mockApi(page, { override: async (route, path) => {
    if (path !== "/api/accounts/quota" || !fail) return false;
    await route.fulfill({ status: 503, json: { ok: false, error: "额度服务暂不可用" } });
    return true;
  } });
  await page.goto("/");
  await page.getByRole("tab", { name: "账号管理" }).click();
  const card = page.getByRole("listitem", { name: "工作账号" });
  await expect(card.getByRole("status")).toContainText("额度服务暂不可用");
  fail = false;
  await card.getByRole("button", { name: "刷新工作账号额度" }).click();
  await expect(card.getByText("81%", { exact: true })).toBeVisible();
  await expect(card.getByRole("status")).toHaveCount(0);
});

test("account catalog settings show the source and save the discovery switch", async ({ page }) => {
  const state = makeState();
  Object.assign(state.accounts[1], {
    model_catalog_url: "http://localhost:8317/v1/models",
    api_key_model_discovery: true,
  });
  const { posts } = await mockApi(page, { state });
  await page.goto("/");
  await page.getByRole("tab", { name: "账号管理" }).click();
  await page.getByRole("listitem").filter({ hasText: "备用渠道" }).getByRole("button", { name: "详情" }).click();
  await expect(page.getByText("渠道目录：http://localhost:8317/v1/models", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "编辑", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "编辑账号" });
  await dialog.getByRole("button", { name: "高级连接设置" }).click();
  await expect(dialog.getByRole("textbox", { name: "模型目录地址（可选）" })).toHaveValue("http://localhost:8317/v1/models");
  const discovery = dialog.getByRole("switch", { name: "启用渠道模型目录" });
  await expect(discovery).toBeChecked();
  await discovery.uncheck();
  await dialog.getByRole("button", { name: "保存账号" }).click();
  await expect(dialog).not.toBeVisible();
  expect(posts.find((post) => post.path.endsWith("/save"))?.body).toMatchObject({
    model_catalog_url: "http://localhost:8317/v1/models",
    api_key_model_discovery: false,
  });
  expect(posts.some((post) => post.path.endsWith("/activate"))).toBe(false);
});
