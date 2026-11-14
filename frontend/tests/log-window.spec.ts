import { expect, test } from '@playwright/test';
import { mockCatalog } from './catalog-fixtures';

test('opens a separate log page that can refresh without starting the main UI', async ({ page }) => {
  await mockCatalog(page);
  let log = 'First log line';
  await page.context().route('**/vcclient.log', route => route.fulfill({ contentType: 'text/plain', body: log }));
  await page.goto('/');
  const popupPromise = page.waitForEvent('popup');
  await page.getByRole('button', { name: 'ログ', exact: true }).click();
  const popup = await popupPromise;
  await expect(popup.locator('.log-content')).toHaveText('First log line');
  await expect(popup.getByRole('button', { name: '開始', exact: true })).toHaveCount(0);
  await expect(page.getByRole('button', { name: '開始', exact: true })).toBeVisible();
  log = 'Second log line';
  await popup.getByRole('button', { name: '再読み込み', exact: true }).click();
  await expect(popup.locator('.log-content')).toHaveText('Second log line');
  await popup.close();
  await expect(page.getByRole('button', { name: 'ログ', exact: true })).toBeEnabled();
});

test('reports a log fetch error and can retry', async ({ page }) => {
  let failed = true;
  await page.route('**/vcclient.log', route => failed ? route.fulfill({ status: 503 }) : route.fulfill({ body: 'Recovered' }));
  await page.goto('/?view=log');
  await expect(page.getByRole('alert')).toContainText('ログを取得できませんでした。');
  failed = false;
  await page.getByRole('button', { name: '再読み込み' }).click();
  await expect(page.locator('.log-content')).toHaveText('Recovered');
  await expect(page.getByRole('alert')).toHaveCount(0);
});

test('updates automatically, follows the end, and preserves the position when reading older lines', async ({ page }) => {
  let log = Array.from({ length: 200 }, (_, index) => `Line ${index}`).join('\n');
  await page.route('**/vcclient.log', route => route.fulfill({ contentType: 'text/plain', body: log }));
  await page.goto('/?view=log');
  const content = page.locator('.log-content');
  await expect(content).toContainText('Line 199');
  await expect.poll(() => content.evaluate(element => element.scrollHeight - element.scrollTop - element.clientHeight)).toBeLessThanOrEqual(1);

  log += '\nNew line';
  await expect(content).toContainText('New line', { timeout: 5000 });
  await expect.poll(() => content.evaluate(element => element.scrollHeight - element.scrollTop - element.clientHeight)).toBeLessThanOrEqual(1);

  await content.evaluate(element => { element.scrollTop = 0; });
  log += '\nLater line';
  await expect(content).toContainText('Later line', { timeout: 5000 });
  expect(await content.evaluate(element => element.scrollTop)).toBe(0);
});

test('recovers automatically after a failed refresh', async ({ page }) => {
  let failed = true;
  await page.route('**/vcclient.log', route => failed ? route.fulfill({ status: 503 }) : route.fulfill({ body: 'Recovered automatically' }));
  await page.goto('/?view=log');
  await expect(page.getByRole('alert')).toBeVisible();
  failed = false;
  await expect(page.locator('.log-content')).toHaveText('Recovered automatically', { timeout: 5000 });
  await expect(page.getByRole('alert')).toHaveCount(0);
});

test('uses the desktop bridge instead of opening a browser window', async ({ page }) => {
  await mockCatalog(page);
  await page.addInitScript(() => { (window as unknown as { vcclientForge: object }).vcclientForge = { openLogWindow: () => { (window as unknown as { logOpened: boolean }).logOpened = true; return true; } }; });
  await page.goto('/');
  await page.getByRole('button', { name: 'ログ', exact: true }).click();
  expect(await page.evaluate(() => (window as unknown as { logOpened?: boolean }).logOpened)).toBe(true);
});
