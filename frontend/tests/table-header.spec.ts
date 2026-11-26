import { expect, test } from '@playwright/test';
import { mockApi } from './fixtures';

for (const dark of [false, true]) {
  test('sticky header covers scrolling edge: dark=' + dark, async ({ page }) => {
    await page.setViewportSize({ width: 900, height: 600 });
    await mockApi(page);
    await page.goto('/');
    await page.getByRole('tab', { name: '实时请求', exact: true }).click();
    if (dark) await page.getByRole('button', { name: '切换深色' }).click();
    const table = page.getByRole('table', { name: '单次请求明细' });
    await expect(table.locator('tbody tr').first()).toBeVisible();
    await table.evaluate(t => { t.parentElement!.scrollTop = 40; });
    await expect.poll(() => table.evaluate(t => {
      const container = t.parentElement!;
      return Math.max(...Array.from(t.querySelectorAll('th'), h =>
        h.getBoundingClientRect().top - container.getBoundingClientRect().top));
    })).toBeLessThanOrEqual(-0.5);
    await expect(table.locator('th').first()).toBeVisible();
  });
}
