import { expect, test, type Locator, type Page } from "@playwright/test";
import { mockApi } from "./fixtures";

async function singleClick(page: Page, target: Locator) {
  const box = await target.boundingBox();
  expect(box).not.toBeNull();
  await page.mouse.click(box!.x + box!.width / 2, box!.y + box!.height / 2);
}

test("one physical click activates navigation and opens an account form", async ({
  page,
}) => {
  await mockApi(page);
  await page.goto("/");
  for (const name of [
    "账号管理",
    "工具设置",
    "用量明细",
    "实时请求",
    "账号管理",
  ]) {
    const tab = page.getByRole("tab", { name, exact: true });
    await singleClick(page, tab);
    await expect(tab).toHaveAttribute("aria-selected", "true");
  }
  await singleClick(
    page,
    page.getByRole("button", { name: "添加账号", exact: true }),
  );
  const dialog = page.getByRole("dialog", { name: "添加账号" });
  await expect(dialog).toBeVisible();
  await singleClick(
    page,
    dialog.getByRole("button", { name: "兼容渠道", exact: true }),
  );
  await expect(dialog.getByRole("textbox", { name: "服务地址" })).toBeVisible();
});

test("backdrop clicks preserve account and image drafts until explicitly closed", async ({
  page,
}) => {
  const { posts } = await mockApi(page);
  await page.goto("/");
  await page.getByRole("tab", { name: "账号管理", exact: true }).click();
  await page.getByRole("button", { name: "添加账号", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "添加账号" });
  await dialog.getByRole("button", { name: "兼容渠道", exact: true }).click();
  const name = dialog.getByRole("textbox", { name: "账号名称", exact: false });
  await name.fill("尚未保存的账号");
  await page.mouse.click(4, 4);
  await expect(dialog).toBeVisible();
  await expect(name).toHaveValue("尚未保存的账号");
  await page.keyboard.press("Escape");
  await expect(dialog).not.toBeVisible();
  await page.getByRole("tab", { name: "工具设置", exact: true }).click();
  await page.getByRole("button", { name: "配置", exact: true }).click();
  const image = page.getByRole("dialog", { name: "图片生成配置" });
  const model = image.getByRole("textbox", { name: "图片模型" });
  await model.fill("draft-image-model");
  await page.mouse.click(4, 4);
  await expect(image).toBeVisible();
  await expect(model).toHaveValue("draft-image-model");
  await image.getByRole("button", { name: "取消", exact: true }).click();
  await expect(image).not.toBeVisible();
  expect(posts).toHaveLength(0);
});
